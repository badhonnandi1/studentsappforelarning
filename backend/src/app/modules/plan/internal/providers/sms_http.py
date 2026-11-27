"""Generic HTTP SMS gateway (the vendor is chosen later; only settings change).

``POST SMS_API_URL`` with a bearer key and ``{"to", "sender_id", "message"}``; the response
carries ``message_id`` and, when the vendor reports it, ``cost_poisha``. Calls go through a
Redis-backed circuit breaker so an outage fails fast instead of piling up workers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.http_client import make_http_client
from app.core.redis import get_redis
from app.core.resilience import CircuitBreaker
from app.core.settings import Settings
from app.modules.plan.internal.providers.sms_base import SendResult, SmsGatewayError

TIMEOUT_S = 5.0


@dataclass
class HttpSmsGateway:
    settings: Settings
    client: httpx.AsyncClient = field(default_factory=lambda: make_http_client(timeout_s=TIMEOUT_S))
    breaker: CircuitBreaker | None = None
    name: str = "http"

    def _breaker(self) -> CircuitBreaker:
        if self.breaker is None:
            self.breaker = CircuitBreaker("sms_gateway", get_redis())
        return self.breaker

    async def send(self, to_phone: str, body: str) -> SendResult:
        return await self._breaker().call(lambda: self._post(to_phone, body))

    async def _post(self, to_phone: str, body: str) -> SendResult:
        payload = {"to": to_phone, "sender_id": self.settings.sms_sender_id, "message": body}
        key = self.settings.sms_api_key.get_secret_value()
        try:
            response = await self.client.post(
                self.settings.sms_api_url, json=payload, headers={"Authorization": f"Bearer {key}"}
            )
        except httpx.HTTPError as exc:
            raise SmsGatewayError(f"sms gateway unreachable: {type(exc).__name__}") from None
        if response.status_code >= 300:
            raise SmsGatewayError(f"sms gateway returned {response.status_code}")
        try:
            data: dict[str, Any] = response.json()
        except ValueError:
            raise SmsGatewayError("sms gateway returned invalid JSON") from None
        cost = data.get("cost_poisha")
        message_id = data.get("message_id")
        return SendResult(
            provider_msg_id=str(message_id) if message_id is not None else None,
            cost_poisha=int(cost) if isinstance(cost, int | float) else None,
        )
