"""Read back a save re-saved by the game during the M10 protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from editor.formats import FormatDetectionError
from editor.service import EditorService
from save_format import SaveError
from tools.prepare_ingame_verification import VerificationManifest


@dataclass(frozen=True)
class VerificationResult:
    """Hash and parser result for one manually re-saved game file."""

    manifest_path: Path
    resaved_path: Path
    release_id: str
    format_id: str
    resaved_sha256: str | None
    parser_ok: bool
    money_matches: bool
    observed_money: int | None
    container_version: int | None
    format_version: int | None
    warnings: tuple[str, ...]
    error: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "manifest_path": str(self.manifest_path),
            "resaved_path": str(self.resaved_path),
            "release_id": self.release_id,
            "format_id": self.format_id,
            "resaved_sha256": self.resaved_sha256,
            "parser_ok": self.parser_ok,
            "money_matches": self.money_matches,
            "observed_money": self.observed_money,
            "container_version": self.container_version,
            "format_version": self.format_version,
            "warnings": list(self.warnings),
            "error": self.error,
        }


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(path: Path) -> VerificationManifest:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveError(f"Не удалось прочитать manifest: {exc}") from exc
    if payload.get("manifest_version") != 1:
        raise SaveError("Неподдерживаемая версия manifest")
    required = (
        "release_id",
        "format_id",
        "source_path",
        "edited_path",
        "source_sha256",
        "edited_sha256",
        "original_money",
        "edited_money",
    )
    if any(key not in payload for key in required):
        raise SaveError("Manifest не содержит обязательные поля протокола")
    return VerificationManifest(
        release_id=str(payload["release_id"]),
        format_id=str(payload["format_id"]),
        source_path=Path(str(payload["source_path"])),
        edited_path=Path(str(payload["edited_path"])),
        manifest_path=path,
        source_sha256=str(payload["source_sha256"]),
        edited_sha256=str(payload["edited_sha256"]),
        original_money=int(payload["original_money"]),
        edited_money=int(payload["edited_money"]),
        container_version=(
            int(payload["container_version"])
            if payload.get("container_version") is not None
            else None
        ),
        format_version=(
            int(payload["format_version"])
            if payload.get("format_version") is not None
            else None
        ),
        warnings=tuple(str(value) for value in payload.get("warnings", ())),
    )


def verify_resaved_save(manifest: Path, resaved: Path) -> VerificationResult:
    """Parse a game re-save and report failure without claiming a pass."""

    manifest = Path(manifest).expanduser()
    resaved = Path(resaved).expanduser()
    loaded = _load_manifest(manifest)
    try:
        resaved_sha = _sha256_path(resaved)
    except OSError as exc:
        return VerificationResult(
            manifest_path=manifest,
            resaved_path=resaved,
            release_id=loaded.release_id,
            format_id=loaded.format_id,
            resaved_sha256=None,
            parser_ok=False,
            money_matches=False,
            observed_money=None,
            container_version=None,
            format_version=None,
            warnings=(),
            error=f"Не удалось прочитать re-saved файл: {exc}",
        )

    try:
        data = resaved.read_bytes()
        inspection = EditorService().inspect_result(data, source_name=str(resaved))
        if inspection.release_id != loaded.release_id:
            raise SaveError(
                f"re-saved файл распознан как {inspection.release_id!r}, "
                f"а ожидался {loaded.release_id!r}"
            )
    except (FormatDetectionError, OSError, SaveError, ValueError) as exc:
        return VerificationResult(
            manifest_path=manifest,
            resaved_path=resaved,
            release_id=loaded.release_id,
            format_id=loaded.format_id,
            resaved_sha256=resaved_sha,
            parser_ok=False,
            money_matches=False,
            observed_money=None,
            container_version=None,
            format_version=None,
            warnings=(),
            error=str(exc),
        )

    observed_money = inspection.info.money
    return VerificationResult(
        manifest_path=manifest,
        resaved_path=resaved,
        release_id=loaded.release_id,
        format_id=inspection.format_id,
        resaved_sha256=resaved_sha,
        parser_ok=True,
        money_matches=observed_money == loaded.edited_money,
        observed_money=observed_money,
        container_version=inspection.info.container_version,
        format_version=inspection.info.format_version,
        warnings=inspection.info.warnings,
        error=None,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a save after the game loaded and re-saved it"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--resaved", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = verify_resaved_save(args.manifest, args.resaved)
        print(json.dumps(result.to_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.parser_ok and result.money_matches else 1
    except (OSError, SaveError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["VerificationResult", "build_parser", "main", "verify_resaved_save"]
