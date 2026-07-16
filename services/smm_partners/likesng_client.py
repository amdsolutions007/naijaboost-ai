"""Concrete SMM client implementation for the Likes.ng partner."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, Optional, cast

from .base import BaseSMMClient


class LikesNgClient(BaseSMMClient):
    """Client responsible for interacting with the Likes.ng SMM API."""

    DEFAULT_ENDPOINT: str = "api/v2"
    DEFAULT_TIMEOUT: float = 30.0

    @property
    def endpoint(self) -> str:
        """Resolve the target endpoint dynamically based on the configured base_url."""
        normalized = self.base_url.rstrip("/")
        if normalized.endswith("/api/v2") or normalized.endswith("/api"):
            return ""
        return self.DEFAULT_ENDPOINT

    @classmethod
    def build_auth_headers(cls, api_key: str) -> dict[str, str]:
        # Likes.ng authenticates via payload key parameter.
        return {}

    def create_order(self, *, service_id: str, quantity: int, **kwargs: Any) -> Mapping[str, Any]:
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        request_kwargs: dict[str, Any] = dict(kwargs)
        headers = self._extract_headers(request_kwargs)
        timeout = self._extract_timeout(request_kwargs)

        payload_fields = self._prepare_payload_fields(service_id=service_id, quantity=quantity, extra=request_kwargs)
        payload = self._build_payload("add", payload_fields)

        return self._request(
            "POST",
            self.endpoint,
            data_payload=payload,
            headers=headers,
            timeout=timeout if timeout is not None else self.DEFAULT_TIMEOUT,
        )

    def get_status(self, order_id: str) -> Mapping[str, Any]:
        payload = self._build_payload("status", {"order": order_id})
        return self._request("POST", self.endpoint, data_payload=payload)

    def check_status(self, order_id: str) -> Mapping[str, Any]:
        return self.get_status(order_id)

    def get_services(self) -> Mapping[str, Any]:
        payload = self._build_payload("services")
        return self._request("POST", self.endpoint, data_payload=payload)

    def get_balance(self) -> Mapping[str, Any]:
        payload = self._build_payload("balance")
        return self._request("POST", self.endpoint, data_payload=payload, circuit_check=False)

    def _build_payload(self, action: str, extra_fields: Optional[Mapping[str, Any]] = None) -> dict[str, str]:
        payload: dict[str, str] = {"key": self.api_key, "action": action}
        if extra_fields:
            for key, value in extra_fields.items():
                if value is None:
                    continue
                payload[key] = str(value)
        return payload

    def _extract_headers(self, request_kwargs: MutableMapping[str, Any]) -> MutableMapping[str, str] | None:
        raw_headers = request_kwargs.pop("headers", None)
        if raw_headers is None:
            return None
        if isinstance(raw_headers, MutableMapping):
            return cast(MutableMapping[str, str], raw_headers)
        raise TypeError("headers must be a mutable mapping when provided")

    def _extract_timeout(self, request_kwargs: MutableMapping[str, Any]) -> Optional[float]:
        timeout_value = request_kwargs.pop("timeout", None)
        if timeout_value is None:
            return None
        if isinstance(timeout_value, (int, float)):
            return float(timeout_value)
        raise TypeError("timeout must be numeric if provided")

    def _prepare_payload_fields(
        self,
        *,
        service_id: str,
        quantity: int,
        extra: MutableMapping[str, Any],
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"service": service_id, "quantity": quantity}
        for key in list(extra.keys()):
            if key in {"headers", "timeout"}:
                continue
            payload[key] = extra[key]
        return payload
