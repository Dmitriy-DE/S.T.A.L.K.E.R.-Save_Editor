"""Shared evidence maturity type for every user-facing mutation capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CapabilityMaturity = Literal["unsupported", "research", "experimental", "verified"]


@dataclass(frozen=True)
class CapabilitySupport:
    """One capability's evidence maturity and the reason shown to users."""

    maturity: CapabilityMaturity
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.maturity not in {
            "unsupported",
            "research",
            "experimental",
            "verified",
        }:
            raise ValueError(f"unsupported maturity: {self.maturity!r}")
        if self.reason is not None:
            normalized = str(self.reason).strip()
            object.__setattr__(self, "reason", normalized or None)

    @property
    def writable(self) -> bool:
        """Return whether the operation may be staged by a source-backed writer."""

        return self.maturity in {"experimental", "verified"}

    def as_dict(self) -> dict[str, str | None]:
        """Return the stable JSON projection used by Qt/web/CLI adapters."""

        return {"maturity": self.maturity, "reason": self.reason}


__all__ = ["CapabilityMaturity", "CapabilitySupport"]
