#!/usr/bin/env python3
"""Read-only X-Ray weapon-addon mapping and save observations.

The original X-Ray weapon state stores addon presence as a bit mask, while
the actual component names and compatibility rules live in release-specific
weapon configuration.  This tool reports both sides without changing a save.
It deliberately does not turn a flag into an attach/detach writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.xray_catalog import (  # noqa: E402
    _candidate_archives,
    _decode,
    _has_obvious_mod_overlay,
    _parse_ltx,
    _read_xray_archive,
    _resolve_sections,
)
from editor.xray_save import (  # noqa: E402
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRayFormatSpec,
    XRaySave,
    _read_dynamic_visual_state,
    _Reader,
    parse_xray,
)

ADDON_MASKS: dict[str, int] = {
    "scope": 0x01,
    "grenade_launcher": 0x02,
    "silencer": 0x04,
}
ADDON_STATUS_NAMES: dict[int, str] = {
    0: "disabled",
    1: "permanent",
    2: "attachable",
}
_ADDON_SLOTS = tuple(ADDON_MASKS)
_WEAPON_STATUS_KEYS = tuple(f"{slot}_status" for slot in _ADDON_SLOTS)
_SOURCE_STATE_URL = (
    "https://raw.githubusercontent.com/OpenXRay/xray-16/"
    "c37860c09850d894b721ba115cd936bb3f11482c/"
    "src/xrServerEntities/xrServer_Objects_ALife_Items.cpp"
)
_SOURCE_HEADER_URL = (
    "https://raw.githubusercontent.com/OpenXRay/xray-16/"
    "c37860c09850d894b721ba115cd936bb3f11482c/"
    "src/xrServerEntities/xrServer_Objects_ALife_Items.h"
)
_SOURCE_STATUS_URL = (
    "https://raw.githubusercontent.com/OpenXRay/xray-16/"
    "c37860c09850d894b721ba115cd936bb3f11482c/"
    "src/xrServerEntities/alife_space.h"
)


@dataclass(frozen=True)
class WeaponAddonState:
    """The exact parsed weapon STATE addon byte, or a versioned blocker."""

    addon_flags: int | None
    addon_flags_offset: int | None
    attached_slots: tuple[str, ...]
    unknown_flags: int
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "addon_flags": self.addon_flags,
            "addon_flags_hex": (
                None if self.addon_flags is None else f"0x{self.addon_flags:02X}"
            ),
            "addon_flags_offset": self.addon_flags_offset,
            "flag_attached_slots": list(self.attached_slots),
            "unknown_flags": self.unknown_flags,
            "unknown_flags_hex": f"0x{self.unknown_flags:02X}",
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WeaponProfile:
    """Release-configured addon statuses and component references."""

    key: str
    class_name: str | None
    statuses: tuple[tuple[str, str], ...]
    status_codes: tuple[tuple[str, int], ...]
    components: tuple[tuple[str, str], ...]
    scope_options: tuple[str, ...]
    source: str

    @property
    def attachable_slots(self) -> tuple[str, ...]:
        return tuple(slot for slot, status in self.statuses if status == "attachable")

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "class_name": self.class_name,
            "statuses": dict(self.statuses),
            "status_codes": dict(self.status_codes),
            "components": dict(self.components),
            "scope_options": list(self.scope_options),
            "attachable_slots": list(self.attachable_slots),
            "source": self.source,
        }


@dataclass(frozen=True)
class WeaponAddonObservation:
    """One actor-owned weapon's state plus optional config applicability."""

    object_id: int
    name: str
    version: int
    state_offset: int
    state: WeaponAddonState
    profile: WeaponProfile | None
    upgrades: tuple[str, ...] | None

    @property
    def effective_attached_slots(self) -> tuple[str, ...]:
        """Combine state flags with permanent/attachable config semantics."""

        if self.profile is None:
            return self.state.attached_slots
        flag_slots = frozenset(self.state.attached_slots)
        status_by_slot = dict(self.profile.statuses)
        return tuple(
            slot
            for slot in _ADDON_SLOTS
            if status_by_slot.get(slot) == "permanent"
            or (status_by_slot.get(slot) == "attachable" and slot in flag_slots)
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "object_id": f"0x{self.object_id:04X}",
            "name": self.name,
            "version": self.version,
            "state_offset": self.state_offset,
            "addon_flags_absolute_offset": (
                None
                if self.state.addon_flags_offset is None
                else self.state_offset + self.state.addon_flags_offset
            ),
            "state": self.state.as_dict(),
            "effective_attached_slots": list(self.effective_attached_slots),
            "profile": None if self.profile is None else self.profile.as_dict(),
            "upgrades": None if self.upgrades is None else list(self.upgrades),
        }


@dataclass(frozen=True)
class AttachmentAnalysis:
    """Aggregate, serializable output for one parsed X-Ray save."""

    release_id: str
    actor_version: int
    observations: tuple[WeaponAddonObservation, ...]
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        flag_counts = Counter(
            state.addon_flags
            for observation in self.observations
            if (state := observation.state).addon_flags is not None
        )
        return {
            "release_id": self.release_id,
            "actor_version": self.actor_version,
            "weapon_count": len(self.observations),
            "flag_counts": {
                f"0x{value:02X}": count
                for value, count in sorted(flag_counts.items())
            },
            "observations": [item.as_dict() for item in self.observations],
            "failures": list(self.failures),
        }


def _status_name(code: int) -> str:
    return ADDON_STATUS_NAMES.get(code, f"unknown({code})")


def _split_config_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        token.strip()
        for token in value.replace(";", ",").split(",")
        if token.strip()
    )


def _profiles_from_sections(sections: Mapping[str, object]) -> dict[str, WeaponProfile]:
    profiles: dict[str, WeaponProfile] = {}
    for name, section, values in _resolve_sections(sections):  # type: ignore[arg-type]
        lowered = name.casefold()
        if not (lowered.startswith("wpn_") or lowered.startswith("mp_wpn_")):
            continue
        if not any(key in values for key in _WEAPON_STATUS_KEYS):
            continue
        statuses: list[tuple[str, str]] = []
        status_codes: list[tuple[str, int]] = []
        components: list[tuple[str, str]] = []
        for slot in _ADDON_SLOTS:
            status_value = values.get(f"{slot}_status")
            if status_value is not None:
                try:
                    status_code = int(status_value, 0)
                except ValueError:
                    status_code = -1
                status_codes.append((slot, status_code))
                statuses.append((slot, _status_name(status_code)))
            component = values.get(f"{slot}_name")
            if component:
                components.append((slot, component))
        profiles[name] = WeaponProfile(
            key=name,
            class_name=values.get("class"),
            statuses=tuple(statuses),
            status_codes=tuple(status_codes),
            components=tuple(components),
            scope_options=_split_config_list(values.get("scopes_sect")),
            source=f"{section.source}#{name}",
        )
    return profiles


def weapon_profiles_from_ltx(text: str, *, source: str = "fixture.ltx") -> dict[str, WeaponProfile]:
    """Parse release-style weapon sections from one LTX text fixture."""

    return _profiles_from_sections(_parse_ltx(text, source))


def weapon_profiles_from_sources(sources: Mapping[str, bytes]) -> dict[str, WeaponProfile]:
    """Parse only weapon LTX resources from an official source map."""

    sections: dict[str, object] = {}
    for source, raw in sorted(sources.items()):
        normalized = source.replace("\\", "/").casefold()
        if not normalized.endswith(".ltx") or "/weapons/" not in normalized:
            continue
        sections.update(_parse_ltx(_decode(raw), source))
    return _profiles_from_sections(sections)


def read_weapon_addon_state(raw: bytes, *, version: int, label: str) -> WeaponAddonState:
    """Read the source-defined addon flag byte from a weapon STATE payload.

    ``raw`` must start at the object's STATE boundary.  The function consumes
    every source-defined field before the flag and the versioned fields after
    it, so a guessed byte pattern cannot be reported as an addon anchor.
    """

    reader = _Reader(bytes(raw), label=label)
    _read_dynamic_visual_state(reader, version)
    if version > 52:
        reader.f32()  # CSE_ALifeInventoryItem::m_fCondition
    if version > 123:
        count = reader.u32()  # CSE_ALifeInventoryItem::m_upgrades
        if count > 100_000:
            raise ValueError(f"{label}: upgrades count слишком велик")
        for _ in range(count):
            reader.zstring()

    reader.u16()  # a_current
    reader.u16()  # a_elapsed
    reader.u8()  # wpn_state
    if version <= 40:
        return WeaponAddonState(
            addon_flags=None,
            addon_flags_offset=None,
            attached_slots=(),
            unknown_flags=0,
            reason="addon flag is absent before weapon STATE version 41",
        )

    addon_flags_offset = reader.pos
    addon_flags = reader.u8()
    if version > 46:
        reader.u8()  # ammo_type
    if version > 122:
        reader.u8()  # packed grenade count/type
    attached_slots = tuple(
        slot for slot, mask in ADDON_MASKS.items() if addon_flags & mask
    )
    return WeaponAddonState(
        addon_flags=addon_flags,
        addon_flags_offset=addon_flags_offset,
        attached_slots=attached_slots,
        unknown_flags=addon_flags & ~sum(ADDON_MASKS.values()),
    )


def analyze_xray_save(
    parsed: XRaySave,
    *,
    profiles: Mapping[str, WeaponProfile] | None = None,
) -> AttachmentAnalysis:
    """Analyze actor-owned original X-Ray weapons without mutating bytes."""

    known_profiles = profiles or {}
    observations: list[WeaponAddonObservation] = []
    failures: list[str] = []
    for obj in parsed.objects:
        if obj.parent_id != parsed.actor_id:
            continue
        lowered = obj.name.casefold()
        if not lowered.startswith("wpn_") or lowered.startswith("wpn_addon_"):
            continue
        try:
            state = read_weapon_addon_state(
                parsed.state_bytes(obj),
                version=obj.version,
                label=f"{obj.name} STATE",
            )
        except Exception as error:
            failures.append(f"0x{obj.object_id:04X}: {type(error).__name__}")
            continue
        observations.append(
            WeaponAddonObservation(
                object_id=obj.object_id,
                name=obj.name,
                version=obj.version,
                state_offset=obj.state_offset,
                state=state,
                profile=known_profiles.get(obj.name),
                upgrades=obj.upgrades,
            )
        )
    return AttachmentAnalysis(
        release_id=parsed.spec.id,
        actor_version=parsed.actor_version,
        observations=tuple(observations),
        failures=tuple(failures),
    )


def _official_weapon_sources(game_root: Path) -> dict[str, bytes]:
    """Read release config text while ignoring obvious mod overlays."""

    root = Path(game_root).expanduser()
    data_root = root / "gamedata"
    if data_root.is_dir() and not _has_obvious_mod_overlay(data_root):
        sources: dict[str, bytes] = {}
        for path in sorted(data_root.rglob("*.ltx"), key=lambda item: item.as_posix().casefold()):
            try:
                sources[path.relative_to(root).as_posix()] = path.read_bytes()
            except OSError:
                continue
        return sources

    sources = {}
    for archive in _candidate_archives(root):
        try:
            sources.update(_read_xray_archive(archive))
        except (OSError, ValueError):
            continue
    return sources


def profiles_for_game_root(game_root: Path | None) -> dict[str, WeaponProfile]:
    if game_root is None:
        return {}
    return weapon_profiles_from_sources(_official_weapon_sources(game_root))


def _failure_label(error: BaseException) -> str:
    return f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


def _spec_for_release(release_id: str) -> XRayFormatSpec:
    try:
        return {
            SOC_FORMAT.id: SOC_FORMAT,
            CS_FORMAT.id: CS_FORMAT,
            COP_FORMAT.id: COP_FORMAT,
        }[release_id]
    except KeyError as error:
        raise argparse.ArgumentTypeError(
            "attachments analysis supports original stalker-soc, stalker-cs, "
            "and stalker-cop saves"
        ) from error


def analyze_paths(
    paths: Sequence[Path],
    *,
    release_id: str,
    game_root: Path | None = None,
) -> dict[str, object]:
    spec = _spec_for_release(release_id)
    profiles = profiles_for_game_root(game_root)
    samples: list[dict[str, object]] = []
    failures: Counter[str] = Counter()
    for path in paths:
        try:
            data = path.read_bytes()
            parsed = parse_xray(data, spec, with_inventory=True)
            analysis = analyze_xray_save(parsed, profiles=profiles)
            sample = analysis.as_dict()
            sample.update(
                {
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            samples.append(sample)
        except Exception as error:
            failures[_failure_label(error)] += 1
    return {
        "release_id": release_id,
        "source": {
            "state_codec": _SOURCE_STATE_URL,
            "addon_masks": _SOURCE_HEADER_URL,
            "status_enum": _SOURCE_STATUS_URL,
        },
        "config_profiles": len(profiles),
        "samples": samples,
        "failures": [
            {"error": label, "count": count}
            for label, count in sorted(failures.items())
        ],
        "control_gate": {
            "status": "blocked",
            "reason": (
                "No controlled same-handle attach/detach series with three states "
                "and an independent instance was supplied; observations remain read-only."
            ),
        },
    }


def _parse_game_root(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"game root is not a directory: {value}")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release",
        required=True,
        choices=(SOC_FORMAT.id, CS_FORMAT.id, COP_FORMAT.id),
        help="original X-Ray release family",
    )
    parser.add_argument(
        "--game-root",
        type=_parse_game_root,
        help="optional official installation root for release config mapping",
    )
    parser.add_argument("saves", nargs="+", type=Path, help="X-Ray saves to inspect")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            analyze_paths(
                args.saves,
                release_id=args.release,
                game_root=args.game_root,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
