"""Static save-format registry shared by every editor front end."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from save_format import WALLET_FIELD_ID, SaveError, SaveInfo, decompress_save, inspect_save

from .capabilities import CapabilitySupport, FormatCapabilities, gate_mutations_for_release
from .catalog import GameCatalog, ItemCatalog
from .equipment import equipment_support_for_release
from .models import EditPlan, PreparedEdit
from .prepare import prepare_edit
from .releases import ReleaseDescriptor, release_by_id
from .s2_catalog import (
    S2CatalogProvider,
    S2CatalogSource,
    discover_s2_catalog_sources,
)
from .xray_catalog import XRayCatalogProvider
from .xray_save import (
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRayFormatSpec,
    inspect_xray,
    parse_xray,
    prepare_xray,
)


class SaveFormat(Protocol):
    """The read and write contract for one save-file format."""

    id: str
    title: str
    release_id: str
    edition: str
    capabilities: FormatCapabilities

    def detect(self, data: bytes) -> bool:
        """Return whether ``data`` belongs to this format."""

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        """Inspect bytes without modifying them."""

    def prepare(
        self,
        data: bytes,
        plan: EditPlan,
        *,
        source_name: str | None = None,
        catalog: ItemCatalog | None = None,
        game_catalog: GameCatalog | None = None,
    ) -> PreparedEdit:
        """Prepare an immutable edit for bytes in this format."""


@dataclass(frozen=True)
class DetectionFailure:
    """Why one registered format rejected a byte sequence."""

    format_id: str
    format_title: str
    reason: str


@dataclass(frozen=True)
class FormatInspection:
    """Inspection result plus the format metadata selected for its bytes."""

    format_id: str
    format_title: str
    info: SaveInfo
    release_id: str = ""
    edition: str = ""
    capabilities: FormatCapabilities = field(default_factory=FormatCapabilities)
    catalog: ItemCatalog | None = None
    game_catalog: GameCatalog | None = None


class FormatDetectionError(SaveError):
    """A stable, user-facing error for bytes no registered format accepts."""

    def __init__(
        self,
        *,
        display_name: str,
        size: int,
        failures: tuple[DetectionFailure, ...],
        supported: tuple[SaveFormat, ...],
    ) -> None:
        self.display_name = display_name
        self.size = size
        self.failures = failures
        self.supported = supported
        reasons = "; ".join(
            f"{failure.format_id} ({failure.format_title}) — {failure.reason}"
            for failure in failures
        ) or "зарегистрированные форматы отсутствуют"
        supported_text = ", ".join(
            f"{format_.id} — {format_.title}" for format_ in supported
        ) or "нет зарегистрированных форматов"
        super().__init__(
            f"Error: Формат файла {display_name!r} не распознан "
            f"(размер: {size} байт). Причины: {reasons}. "
            f"Поддерживаются сейчас: {supported_text}."
        )


_S2_RELEASE = release_by_id("stalker2")


class _Stalker2Format:
    id = _S2_RELEASE.id
    title = _S2_RELEASE.title
    release_id = _S2_RELEASE.id
    edition = _S2_RELEASE.edition
    capabilities = gate_mutations_for_release(
        release_id,
        FormatCapabilities(
            read_inventory=True,
            catalog=True,
            equipment=equipment_support_for_release(_S2_RELEASE.id),
            mutation_support={
                "edit_money": CapabilitySupport("experimental"),
                "edit_stacks": CapabilitySupport(
                    "research", "S2 stack writer не подтверждён."
                ),
                "edit_durability": _S2_RELEASE.equipment.support("durability")
                if _S2_RELEASE.equipment is not None
                else CapabilitySupport("unsupported"),
            },
        ),
    )

    def __init__(self) -> None:
        # Catalog discovery can inspect Steam library metadata and loose cfg
        # trees.  The service asks for both the item catalog and the full game
        # catalog during one save inspection, so keep one source-scoped result
        # instead of parsing the same tree twice.  ``None`` sources are not
        # cached because an explicit Zone Kit/Workshop environment can change
        # during a process lifetime.
        self._catalog_cache: dict[
            tuple[str, tuple[str, ...]], tuple[ItemCatalog | None, GameCatalog | None]
        ] = {}

    def detect(self, data: bytes) -> bool:
        """Recognize the confirmed S.T.A.L.K.E.R. 2 container signature.

        Detection is deliberately defensive: arbitrary foreign bytes are an
        expected input to this method and must never escape parser exceptions.
        The existing parser's unique money anchor is the only confirmed
        content marker available to M01.
        """

        try:
            info = inspect_save(data, with_inventory=False)
        except Exception:
            return False
        return info.money_anchor_count == 1

    def detection_reason(self, data: bytes) -> str:
        try:
            info = inspect_save(data, with_inventory=False)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        if info.money_anchor_count == 0:
            try:
                raw = decompress_save(data)
            except Exception:
                raw = b""
            if raw.count(WALLET_FIELD_ID) == 1:
                # Read-only diagnosis; nothing is parsed from this layout.
                return (
                    "legacy S2 layout: wallet field present without the confirmed "
                    "anchor (save from a launch build, re-save it in the game)"
                )
        return (
            "подтверждённая wallet anchor встречается "
            f"{info.money_anchor_count} раз(а), ожидалась ровно 1"
        )

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        return inspect_save(data, with_inventory=with_inventory)

    def catalog_for_source(
        self,
        source_name: str | None,
        *,
        catalog_roots: Sequence[Path] = (),
    ) -> ItemCatalog | None:
        """Read loose S2 metadata, keeping Workshop overlays explicit."""

        return self._catalog_bundle_for_source(source_name, catalog_roots=catalog_roots)[0]

    def _catalog_bundle_for_source(
        self,
        source_name: str | None,
        *,
        catalog_roots: Sequence[Path] = (),
    ) -> tuple[ItemCatalog | None, GameCatalog | None]:
        cache_key = (
            str(source_name) if source_name else "",
            tuple(str(Path(root).expanduser()) for root in catalog_roots),
        )
        if (cache_key[0] or cache_key[1]) and cache_key in self._catalog_cache:
            return self._catalog_cache[cache_key]

        provider = S2CatalogProvider()
        release = release_by_id(self.release_id)
        installed_roots: list[Path] = []
        steam_roots: tuple[Path, ...] = ()
        try:
            from .platforms import installed_releases, steam_libraries

            installed_roots.extend(
                game.install_dir
                for game in installed_releases()
                if game.release_id == self.release_id
            )
            steam_roots = steam_libraries()
        except (OSError, RuntimeError):
            pass
        sources = discover_s2_catalog_sources(
            source_name,
            installed_roots=installed_roots,
            steam_libraries=steam_roots,
            catalog_roots=catalog_roots,
        )
        result: tuple[ItemCatalog | None, GameCatalog | None]
        for source in sources:
            bundle = self._load_bundle_source(provider, release, source)
            if bundle is not None:
                result = (bundle.items, bundle)
                if cache_key[0] or cache_key[1]:
                    self._catalog_cache[cache_key] = result
                return result
        result = (None, None)
        if cache_key[0] or cache_key[1]:
            self._catalog_cache[cache_key] = result
        return result

    def game_catalog_for_source(
        self,
        source_name: str | None,
        *,
        catalog_roots: Sequence[Path] = (),
    ) -> GameCatalog | None:
        """Expose S2 item/upgrades metadata with no faction or writer claim."""
        return self._catalog_bundle_for_source(source_name, catalog_roots=catalog_roots)[1]

    @staticmethod
    def _load_bundle_source(
        provider: S2CatalogProvider,
        release: ReleaseDescriptor,
        source: S2CatalogSource,
    ) -> GameCatalog | None:
        if source.kind == "workshop":
            return provider.load_overlay_bundle(release, source.root)
        return provider.load_bundle(release, source.root)

    def prepare(
        self,
        data: bytes,
        plan: EditPlan,
        *,
        source_name: str | None = None,
        catalog: ItemCatalog | None = None,
        game_catalog: GameCatalog | None = None,
    ) -> PreparedEdit:
        return prepare_edit(data, plan)


class _XRayFormat:
    """Adapter exposing one original-game X-Ray family to the shared registry."""

    def __init__(self, spec: XRayFormatSpec) -> None:
        self.spec = spec
        self.id = spec.id
        self.title = spec.title
        self.release_id = spec.id
        release = release_by_id(spec.id)
        self.edition = release.edition
        equipment = release.equipment
        if equipment is None:
            raise ValueError(f"release {spec.id!r} lacks equipment metadata")
        self.capabilities = gate_mutations_for_release(
            self.release_id,
            FormatCapabilities(
                read_inventory=True,
                catalog=True,
                equipment=equipment_support_for_release(spec.id),
                mutation_support={
                    "edit_money": CapabilitySupport("verified"),
                    "edit_stacks": CapabilitySupport("verified"),
                    "add_items": CapabilitySupport("verified"),
                    "remove_items": CapabilitySupport("verified"),
                    "edit_durability": equipment.support("durability"),
                    "edit_relations": CapabilitySupport("experimental"),
                    "edit_player_faction": CapabilitySupport("experimental"),
                    "edit_placement": equipment.support("placement"),
                    **(
                        {"edit_upgrades": equipment.support("upgrades")}
                        if equipment.support("upgrades").writable
                        else {}
                    ),
                },
            ),
        )

    def detect(self, data: bytes) -> bool:
        # Avoid decompressing the same bytes for all three X-Ray adapters when
        # the outer version already selects a single family.
        if len(data) < 8:
            return False
        outer = struct.unpack_from("<I", data, 4)[0]
        if outer not in self.spec.outer_versions:
            return False
        try:
            parse_xray(data, self.spec, with_inventory=False)
        except Exception:
            return False
        return True

    def detect_fast(self, data: bytes) -> bool:
        """Recognize a candidate without scanning the registry tail.

        Slot discovery uses this inexpensive probe outside the UI thread.  A
        selected row still goes through ``detect``/full inspection before any
        edit is prepared.
        """

        if len(data) < 8:
            return False
        outer = struct.unpack_from("<I", data, 4)[0]
        if outer not in self.spec.outer_versions:
            return False
        try:
            parse_xray(
                data,
                self.spec,
                with_inventory=False,
                strict_registry=False,
            )
        except Exception:
            return False
        return True

    def detection_reason(self, data: bytes) -> str:
        if len(data) < 8:
            return "заголовок короче 8 байт"
        outer = struct.unpack_from("<I", data, 4)[0]
        if outer not in self.spec.outer_versions:
            expected = ", ".join(str(value) for value in sorted(self.spec.outer_versions))
            return f"outer version={outer}, для {self.id} ожидалось {expected}"
        try:
            parsed = parse_xray(data, self.spec, with_inventory=False)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return f"X-Ray actor spawn version {parsed.actor_version} подтверждён"

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        return inspect_xray(data, self.spec, with_inventory=with_inventory)

    def catalog_for_source(
        self,
        source_name: str | None,
        *,
        catalog_roots: Sequence[Path] = (),
    ) -> ItemCatalog | None:
        """Find an official catalog by walking up from a local save path."""

        if not source_name:
            return None
        source = Path(source_name).expanduser()
        if not source.is_absolute() and not source.exists():
            return None
        try:
            source = source.resolve()
        except OSError:
            return None
        start = source.parent if source.is_file() else source
        provider = XRayCatalogProvider()
        release = release_by_id(self.release_id)
        for root in (start, *start.parents):
            catalog = provider.load(release, root)
            if catalog is not None:
                return catalog
        # The repository ships a compact snapshot generated from official
        # resources.  It is a metadata-only fallback for releases whose
        # installation has no unpacked/verified catalog (notably the local
        # Linux SoC install); it never supplies prototypes or save bytes.
        generated = provider.load_generated_bundle(release)
        return generated.items if generated is not None else None

    def game_catalog_for_source(
        self,
        source_name: str | None,
        *,
        catalog_roots: Sequence[Path] = (),
    ) -> GameCatalog | None:
        """Find the full official item/community catalog for a local save."""

        if not source_name:
            return None
        source = Path(source_name).expanduser()
        if not source.is_absolute() and not source.exists():
            return None
        try:
            source = source.resolve()
        except OSError:
            return None
        start = source.parent if source.is_file() else source
        provider = XRayCatalogProvider()
        release = release_by_id(self.release_id)
        for root in (start, *start.parents):
            catalog = provider.load_bundle(release, root)
            if catalog is not None:
                return catalog
        generated = provider.load_generated_bundle(release)
        return generated

    def prepare(
        self,
        data: bytes,
        plan: EditPlan,
        *,
        source_name: str | None = None,
        catalog: ItemCatalog | None = None,
        game_catalog: GameCatalog | None = None,
    ) -> PreparedEdit:
        selected_catalog = catalog or self.catalog_for_source(source_name)
        return prepare_xray(
            data,
            plan,
            self.spec,
            catalog=selected_catalog,
            faction_catalog=game_catalog.factions if game_catalog is not None else None,
            upgrade_catalog=game_catalog.upgrades if game_catalog is not None else None,
        )


STALKER2_FORMAT: SaveFormat = _Stalker2Format()
STALKER_SOC_FORMAT: SaveFormat = _XRayFormat(SOC_FORMAT)
STALKER_CS_FORMAT: SaveFormat = _XRayFormat(CS_FORMAT)
STALKER_COP_FORMAT: SaveFormat = _XRayFormat(COP_FORMAT)
_REGISTERED_FORMATS: list[SaveFormat] = []


def register(fmt: SaveFormat) -> None:
    """Register one static format, rejecting duplicate identifiers."""

    if any(existing.id == fmt.id for existing in _REGISTERED_FORMATS):
        raise ValueError(f"Format ID already registered: {fmt.id!r}")
    _REGISTERED_FORMATS.append(fmt)


def formats() -> tuple[SaveFormat, ...]:
    """Return the registered formats in deterministic registration order."""

    return tuple(_REGISTERED_FORMATS)


def by_id(format_id: str) -> SaveFormat:
    """Return a format by ID or raise ``KeyError`` for an unknown ID."""

    for fmt in _REGISTERED_FORMATS:
        if fmt.id == format_id:
            return fmt
    raise KeyError(format_id)


def detect(data: bytes) -> SaveFormat | None:
    """Return the first format accepting ``data``, or ``None``."""

    for fmt in _REGISTERED_FORMATS:
        try:
            if fmt.detect(data):
                return fmt
        except Exception:
            # A foreign or malformed file must not prevent other registered
            # formats from getting a chance to inspect its bytes.
            continue
    return None


def detect_fast(data: bytes) -> SaveFormat | None:
    """Return a format using its optional cheap candidate detector.

    This is for local slot discovery only.  Callers that need an inspection
    result or an edit must use :func:`detect` and the normal strict parser.
    """

    for fmt in _REGISTERED_FORMATS:
        fast_detector = getattr(fmt, "detect_fast", None)
        try:
            accepted = (
                fast_detector(data)
                if callable(fast_detector)
                else fmt.detect(data)
            )
        except Exception:
            continue
        if accepted:
            return fmt
    return None


def detection_failures(data: bytes) -> tuple[DetectionFailure, ...]:
    """Return per-format reasons without letting malformed input escape."""

    failures: list[DetectionFailure] = []
    for fmt in _REGISTERED_FORMATS:
        try:
            if fmt.detect(data):
                return ()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
        else:
            reason_fn = getattr(fmt, "detection_reason", None)
            if callable(reason_fn):
                try:
                    reason = str(reason_fn(data))
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
            else:
                reason = "сигнатура не подтверждена"
        failures.append(DetectionFailure(fmt.id, fmt.title, reason))
    return tuple(failures)


def format_detection_error(
    data: bytes, *, display_name: str | None = None
) -> FormatDetectionError:
    """Build the shared diagnostic raised for an unknown save format."""

    label = display_name.strip() if display_name and display_name.strip() else "<без имени>"
    return FormatDetectionError(
        display_name=label,
        size=len(data),
        failures=detection_failures(data),
        supported=formats(),
    )


def detect_or_raise(data: bytes, *, display_name: str | None = None) -> SaveFormat:
    """Resolve a format or raise the shared, user-facing diagnostic."""

    format_ = detect(data)
    if format_ is None:
        raise format_detection_error(data, display_name=display_name)
    return format_


register(STALKER2_FORMAT)
register(STALKER_SOC_FORMAT)
register(STALKER_CS_FORMAT)
register(STALKER_COP_FORMAT)


__all__ = [
    "STALKER2_FORMAT",
    "STALKER_COP_FORMAT",
    "STALKER_CS_FORMAT",
    "STALKER_SOC_FORMAT",
    "DetectionFailure",
    "FormatDetectionError",
    "FormatInspection",
    "SaveFormat",
    "by_id",
    "detect",
    "detect_fast",
    "detect_or_raise",
    "detection_failures",
    "format_detection_error",
    "formats",
    "register",
]
