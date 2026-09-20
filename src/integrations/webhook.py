from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from src.integrations.base import DeliveryResult
from src.integrations.serializers import build_payload


class WebhookAlertAdapter:
    name = "WebhookAlertAdapter"

    def __init__(
        self,
        *,
        webhook_url: str | None,
        payload_format: str = "generic",
        dry_run: bool = True,
        timeout_seconds: float = 5,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.payload_format = payload_format
        self.dry_run = bool(dry_run)
        self.timeout_seconds = float(timeout_seconds)
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Timeout deve ser um número positivo e finito.")
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def send(self, alert: dict[str, Any]) -> DeliveryResult:
        payload = build_payload(alert, self.payload_format)
        if self.dry_run:
            return DeliveryResult(
                status="DRY_RUN",
                attempts=0,
                payload=payload,
                mode="DRY_RUN",
            )
        if not self.webhook_url:
            return DeliveryResult(
                status="FAILED",
                attempts=0,
                payload=payload,
                mode="LIVE",
                error_message="URL do webhook não configurada.",
            )
        endpoint = urlsplit(self.webhook_url)
        local_http = endpoint.scheme == "http" and endpoint.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if not endpoint.hostname or not (endpoint.scheme == "https" or local_http):
            return DeliveryResult(
                status="FAILED",
                attempts=0,
                payload=payload,
                mode="LIVE",
                error_message="Webhook live exige HTTPS ou endereço local explícito.",
            )

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        attempts = 0
        last_error: str | None = None
        last_status: int | None = None
        for attempt in range(self.max_retries + 1):
            attempts += 1
            request = urllib.request.Request(
                self.webhook_url,
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "OpsVisionAI/1.0"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    last_status = int(response.status)
                    if 200 <= last_status < 300:
                        return DeliveryResult(
                            status="SUCCESS",
                            attempts=attempts,
                            payload=payload,
                            mode="LIVE",
                            http_status=last_status,
                        )
                    last_error = f"HTTP {last_status}"
            except urllib.error.HTTPError as exc:
                last_status = int(exc.code)
                last_error = f"HTTP {exc.code}: {exc.reason}"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = str(exc)
            if attempt < self.max_retries:
                time.sleep(self.retry_backoff_seconds * (attempt + 1))
        return DeliveryResult(
            status="FAILED",
            attempts=attempts,
            payload=payload,
            mode="LIVE",
            http_status=last_status,
            error_message=last_error,
        )
