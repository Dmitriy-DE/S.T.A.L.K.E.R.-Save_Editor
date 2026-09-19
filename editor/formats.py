"""Static save-format registry shared by every editor front end."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from save_format import SaveError, SaveInfo, inspect_save

from .capabilities import FormatCapabilities, gate_mutations_for_release
from .catalog import GameCatalog, ItemCatalog
from .equipment import equipment_support_for_release
from .models import EditPlan, PreparedEdit
from .prepare import prepare_edit
from .releases import release_by_id
from .s2_catalog import S2CatalogProvider
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


class _Stalker2Format:
    id = "stalker2"
    title = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
    release_id = "stalker2"
    edition = "s2"
    capabilities = gate_mutations_for_release(
        release_id,
        FormatCapabilities(
            read_inventory=True,
            edit_money=True,
            edit_stacks=True,
            edit_durability=True,
            catalog=True,
            equipment=equipment_support_for_release("stalker2"),
            experimental_fields=frozenset({"edit_money", "edit_durability"}),
        ),
    )

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
        return (
            "подтверждённая wallet anchor встречается "
            f"{info.money_anchor_count} раз(а), ожидалась ровно 1"
        )

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        return inspect_save(data, with_inventory=with_inventory)

    @staticmethod
    def _roots_for_source(source_name: str | None) -> tuple[Path, ...]:
        if not source_name:
            return ()
        source = Path(source_name).expanduser()
        if not source.is_absolute() and not source.exists():
            return ()
        try:
            source = source.resolve()
        except OSError:
            return ()
        start = source.parent if source.is_file() else source
        return (start, *start.parents)

    def catalog_for_source(self, source_name: str | None) -> ItemCatalog | None:
        """Read official loose S2 prototype metadata, never save mappings."""

        provider = S2CatalogProvider()
        release = release_by_id(self.release_id)
        roots = list(self._roots_for_source(source_name))
        try:
            from .platforms import installed_releases

            roots.extend(
                game.install_dir
                for game in installed_releases()
                if game.release_id == self.release_id
            )
        except (OSError, RuntimeError):
            pass
        for root in dict.fromkeys(roots):
            catalog = provider.load(release, root)
            if catalog is not None:
                return catalog
        return None

    def game_catalog_for_source(self, source_name: str | None) -> GameCatalog | None:
        """Expose S2 item/upgrades metadata with no faction or writer claim."""

        provider = S2CatalogProvider()
        release = release_by_id(self.release_id)
        roots = list(self._roots_for_source(source_name))
        try:
            from .platforms import installed_releases

            roots.extend(
                game.install_dir
                for game in installed_releases()
                if game.release_id == self.release_id
            )
        except (OSError, RuntimeError):
            pass
        for root in dict.fromkeys(roots):
            catalog = provider.load_bundle(release, root)
            if catalog is not None:
                return catalog
        return None

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
        self.edition = "original"
        self.capabilities = gate_mutations_for_release(
            self.release_id,
            FormatCapabilities(
                read_inventory=True,
                edit_money=True,
                edit_stacks=True,
                add_items=True,
                remove_items=True,
                edit_durability=True,
                edit_upgrades=spec.id in {"stalker-cs", "stalker-cop"},
                edit_relations=True,
                edit_player_faction=True,
                edit_placement=True,
                catalog=True,
                equipment=equipment_support_for_release(spec.id),
                experimental_fields=frozenset(
                    {
                        "edit_durability",
                        "edit_relations",
                        "edit_player_faction",
                        "edit_placement",
                        *(
                            {"edit_upgrades"}
                            if spec.id in {"stalker-cs", "stalker-cop"}
                            else set()
                        ),
                    }
                ),
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

    def catalog_for_source(self, source_name: str | None) -> ItemCatalog | None:
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

    def game_catalog_for_source(self, source_name: str | None) -> GameCatalog | None:
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
