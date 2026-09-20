"""Shared Steam Cloud write-capability contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloudWriteCapability:
    writable: bool
    reason: str


class CloudWriteNotAttemptedError(RuntimeError):
    """Raised only when a transport proves no remote write was sent."""


def cloud_write_capability(transport: object | None) -> CloudWriteCapability:
    """Return an explicit transport capability and fail closed when absent."""

    if transport is None:
        return CloudWriteCapability(False, "Steam Cloud не подключён")
    capability = getattr(transport, "write_capability", None)
    if callable(capability):
        capability = capability()
    if not isinstance(capability, CloudWriteCapability):
        return CloudWriteCapability(
            False,
            "Cloud transport не подтверждает безопасную запись",
        )
    if capability.writable:
        return CloudWriteCapability(True, capability.reason or "Cloud writer готов")
    return CloudWriteCapability(False, capability.reason or "Cloud transport доступен только для чтения")


__all__ = [
    "CloudWriteCapability",
    "CloudWriteNotAttemptedError",
    "cloud_write_capability",
]
