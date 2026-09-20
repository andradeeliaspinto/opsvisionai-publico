from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    attempts: int
    payload: dict[str, Any]
    mode: str
    http_status: int | None = None
    error_message: str | None = None


class AlertAdapter(Protocol):
    name: str
    payload_format: str
    dry_run: bool

    def send(self, alert: dict[str, Any]) -> DeliveryResult: ...
