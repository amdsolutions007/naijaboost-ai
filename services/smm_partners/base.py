"""Core abstractions for NaijaBoost AI SMM partner integrations.

This module defines the foundational contract that every SMM partner client must
respect. Concrete implementations for panels such as YoYoMedia and GodSMM will
extend :class:`BaseSMMClient`, customizing request payloads, authentication and
response normalisation as required.
"""

from __future__ import annotations

import json
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Dict, Optional, cast

import requests
from requests import Response, Session

logger = logging.getLogger(__name__)


class SMMServiceError(Exception):
    """Represents an error returned by an SMM partner service.

    Parameters
    ----------
    message:
        High-level description of the failure.
    response:
        The raw :class:`requests.Response` object returned by the partner.
        Optional because some errors can occur before an HTTP response exists
        (for example, connectivity issues).
    payload:
        Parsed representation of the partner's response body or error payload.
    """

    def __init__(self, message: str, *, response: Optional[Response] = None, payload: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.response = response
        self.payload = payload if payload is not None else self._safe_extract_payload(response)
        self.status_code = response.status_code if response is not None else None

    @staticmethod
    def _safe_extract_payload(response: Optional[Response]) -> Any:
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def __str__(self) -> str:  # pragma: no cover - defensive formatting
        response_info = f" status={self.status_code}" if self.status_code is not None else ""
        payload_preview = ""
        if self.payload is not None:
            try:
                payload_preview = f" payload={json.dumps(self.payload)[:200]}"
            except TypeError:
                payload_preview = f" payload={str(self.payload)[:200]}"
        return f"{self.message}{response_info}{payload_preview}"


class ServiceUnavailableError(SMMServiceError):
    """Raised when the circuit breaker blocks requests due to partner instability."""


class InsufficientFundsError(SMMServiceError):
    """Raised when a partner indicates the account balance is too low for a request."""


class OrderRejectedError(SMMServiceError):
    """Raised when a partner rejects an order for business-rule reasons."""


class InvalidServiceError(SMMServiceError):
    """Raised when the requested service_id is not valid on the partner."""


@dataclass
class _CircuitState:
    state: str = "closed"  # closed | open | half-open
    failure_count: int = 0
    opened_at: Optional[float] = None


class BaseSMMClient(ABC):
    """Abstract base class for all SMM partner API clients."""

    def __init__(self, *, base_url: str, api_key: str, session: Optional[Session] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session or self._build_session()
        self._health_check_in_progress = False
        self._circuit_state = _CircuitState()
        self._circuit_breaker_threshold = 3
        self._circuit_breaker_reset_timeout = 30.0  # seconds
        self._max_retries = 3
        self._base_backoff = 0.5
        self._max_backoff = 5.0

    # ------------------------------------------------------------------
    # Authentication helpers
    # ------------------------------------------------------------------
    @classmethod
    def build_auth_headers(cls, api_key: str) -> Dict[str, str]:
        """Return the default authentication headers for partner requests."""
        return {"Authorization": f"Bearer {api_key}"}

    def _apply_authentication(self, headers: Optional[MutableMapping[str, str]] = None) -> MutableMapping[str, str]:
        merged_headers: MutableMapping[str, str] = {
            "Accept": "application/json",
            **self.build_auth_headers(self.api_key),
        }
        if headers:
            merged_headers.update(headers)
        return merged_headers

    @staticmethod
    def _build_session() -> Session:
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session

    # ------------------------------------------------------------------
    # Abstract operations every partner must implement
    # ------------------------------------------------------------------
    def submit_order(self, *, service_id: str, quantity: int, **kwargs: Any) -> Mapping[str, Any]:
        """Create an order while applying idempotency safeguards."""

        self._validate_order_inputs(service_id=service_id, quantity=quantity, extra=kwargs)

        request_id = str(uuid.uuid4())
        logger.info(
            "Submitting order to partner",
            extra={"service_id": service_id, "quantity": quantity, "request_id": request_id},
        )
        raw_headers = kwargs.pop("headers", None)
        headers: MutableMapping[str, str] | None
        if raw_headers is None:
            headers = {"Idempotency-Key": request_id}
        elif isinstance(raw_headers, MutableMapping):
            headers = cast(MutableMapping[str, str], raw_headers)
            headers.setdefault("Idempotency-Key", request_id)
        else:
            logger.debug(
                "Headers not mutable mapping; skipping Idempotency-Key injection",
                extra={"type": type(raw_headers).__name__},
            )
            headers = None

        response = self.create_order(service_id=service_id, quantity=quantity, headers=headers, **kwargs)
        logger.info("Order submission completed", extra={"request_id": request_id})
        return response

    @abstractmethod
    def create_order(self, *, service_id: str, quantity: int, **kwargs: Any) -> Mapping[str, Any]:
        """Create an order on the partner service."""

    @abstractmethod
    def get_status(self, order_id: str) -> Mapping[str, Any]:
        """Retrieve the status of an existing order."""

    @abstractmethod
    def get_services(self) -> Mapping[str, Any]:
        """Fetch the catalogue of services offered by the partner."""

    @abstractmethod
    def get_balance(self) -> Mapping[str, Any]:
        """Return the current account balance for the partner integration."""

    # ------------------------------------------------------------------
    # Input validation hook (subclasses may extend)
    # ------------------------------------------------------------------
    def _validate_order_inputs(self, *, service_id: str, quantity: int, extra: Mapping[str, Any]) -> None:
        if not service_id:
            raise ValueError("service_id must be provided")
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")

    # ------------------------------------------------------------------
    # Shared request helper
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_payload: Optional[Mapping[str, Any]] = None,
        data_payload: Optional[Mapping[str, Any]] = None,
        headers: Optional[MutableMapping[str, str]] = None,
        timeout: float = 30.0,
        circuit_check: bool = True,
    ) -> Any:
        """Send an HTTP request to the partner API and return the parsed payload.

        Concrete clients should call this helper to benefit from consistent
        authentication, error handling, and logging. The method returns the
        parsed JSON payload when available, falling back to text content.
        """

        attempt = 0
        url = f"{self.base_url}/{endpoint.lstrip('/')}".rstrip("/") if endpoint else self.base_url

        if json_payload is not None and data_payload is not None:
            raise ValueError("Provide either json_payload or data_payload, not both.")

        while True:
            if circuit_check and not self._health_check_in_progress:
                self._ensure_circuit_allows_request()

            request_headers = self._apply_authentication(headers)
            if data_payload is not None:
                request_headers["Content-Type"] = "application/x-www-form-urlencoded"
            elif json_payload is not None:
                request_headers["Content-Type"] = "application/json"

            logger.debug(
                "Dispatching partner request",
                extra={
                    "method": method,
                    "url": url,
                    "params": params,
                    "json_payload": json_payload,
                    "data_payload": data_payload,
                    "attempt": attempt + 1,
                },
            )

            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_payload,
                    data=data_payload,
                    headers=request_headers,
                    timeout=timeout,
                )
            except requests.RequestException as exc:  # pragma: no cover - network failure path
                logger.exception("Transport layer error when calling partner API")
                # Catastrophic: immediate open on connection errors
                if isinstance(exc, requests.ConnectionError):
                    self._open_circuit()
                    raise ServiceUnavailableError("Connection error; circuit opened", payload=str(exc)) from exc
                # Other transport errors treated as transient
                self._record_failure()
                if attempt < self._max_retries:
                    attempt += 1
                    self._sleep_with_backoff(attempt)
                    continue
                raise ServiceUnavailableError("Transport error while communicating with partner", payload=str(exc)) from exc

            if response.status_code in {502, 503}:
                # Catastrophic: open circuit immediately
                logger.warning(
                    "Partner catastrophic error",
                    extra={"status_code": response.status_code, "text": response.text[:200]},
                )
                self._open_circuit()
                raise ServiceUnavailableError("Partner returned a catastrophic error", response=response)

            if response.status_code in {500, 504}:
                logger.warning(
                    "Partner transient 5xx response",
                    extra={"status_code": response.status_code, "text": response.text[:200]},
                )
                self._record_failure()
                if attempt < self._max_retries:
                    attempt += 1
                    self._sleep_with_backoff(attempt)
                    continue
                raise ServiceUnavailableError("Partner API returned repeated 5xx responses", response=response)

            if 400 <= response.status_code < 500:
                payload = self._parse_response(response)
                logger.warning(
                    "Partner client-side error",
                    extra={"status_code": response.status_code, "payload": payload},
                )
                try:
                    self._translate_partner_errors(payload, response)
                except SMMServiceError as exc:
                    self._record_failure()
                    raise exc
                else:
                    self._record_failure()
                    raise SMMServiceError("Partner API returned a client error", response=response, payload=payload)

            payload = self._parse_response(response)

            try:
                self._translate_partner_errors(payload, response)
            except SMMServiceError as exc:
                self._record_failure()
                raise exc

            self._record_success()
            return payload

    def _parse_response(self, response: Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    # ------------------------------------------------------------------
    # Resilience helpers
    # ------------------------------------------------------------------
    def _ensure_circuit_allows_request(self) -> None:
        if self._circuit_state.state == "closed":
            return

        if self._circuit_state.state == "open":
            if self._circuit_state.opened_at is None:
                raise ServiceUnavailableError("Circuit breaker open")
            elapsed = time.time() - self._circuit_state.opened_at
            if elapsed < self._circuit_breaker_reset_timeout:
                raise ServiceUnavailableError("Circuit breaker open; partner marked as unstable")

            logger.info("Circuit breaker half-open; performing synthetic balance check")
            self._circuit_state.state = "half-open"
            try:
                self._perform_health_check()
            except SMMServiceError:
                logger.warning("Health check failed; keeping circuit open")
                self._open_circuit()
                raise ServiceUnavailableError("Partner health check failed; circuit remains open")
            else:
                logger.info("Health check passed; closing circuit")
                self._close_circuit()

        elif self._circuit_state.state == "half-open":
            # Allow a single request through; success/failure recorded later.
            return

    def _perform_health_check(self) -> None:
        if self._health_check_in_progress:
            return
        self._health_check_in_progress = True
        try:
            self.get_balance()
        finally:
            self._health_check_in_progress = False

    def _record_failure(self) -> None:
        if self._circuit_state.state == "half-open":
            self._open_circuit()
            return

        self._circuit_state.failure_count += 1
        if self._circuit_state.failure_count >= self._circuit_breaker_threshold:
            self._open_circuit()

    def _record_success(self) -> None:
        self._circuit_state.failure_count = 0
        if self._circuit_state.state in {"open", "half-open"}:
            self._close_circuit()

    def _open_circuit(self) -> None:
        self._circuit_state.state = "open"
        self._circuit_state.opened_at = time.time()
        self._circuit_state.failure_count = 0

    def _close_circuit(self) -> None:
        self._circuit_state.state = "closed"
        self._circuit_state.opened_at = None
        self._circuit_state.failure_count = 0

    def _sleep_with_backoff(self, attempt: int) -> None:
        capped = min(self._base_backoff * (2 ** (attempt - 1)), self._max_backoff)
        jitter = random.uniform(0, capped / 2)
        sleep_for = min(capped + jitter, self._max_backoff)
        logger.debug("Backing off before retry", extra={"sleep": sleep_for, "attempt": attempt})
        time.sleep(sleep_for)

    def _translate_partner_errors(self, payload: Any, response: Response) -> None:
        if not isinstance(payload, Mapping):
            return

        payload_mapping = cast(Mapping[str, object], payload)

        # Normalise potential fields across partner APIs.
        status = str(payload_mapping.get("status", "")).lower()
        error_code = str(payload_mapping.get("error_code", payload_mapping.get("code", ""))).lower()
        message = str(payload_mapping.get("error", payload_mapping.get("message", "")))

        if status in {"error", "failed", "failure"} or error_code or message:
            diagnostic = message or status or error_code or "Unknown partner error"

            lower_msg = diagnostic.lower()
            if "insufficient" in lower_msg or "not enough funds" in lower_msg or error_code == "insufficient_funds":
                raise InsufficientFundsError("Partner reported insufficient funds", response=response, payload=payload)

            if "reject" in lower_msg or error_code in {"order_rejected", "order_failed"}:
                raise OrderRejectedError("Partner rejected the order", response=response, payload=payload)

            if "invalid service" in lower_msg or "service not found" in lower_msg or error_code in {"invalid_service", "service_not_found"}:
                raise InvalidServiceError("Partner reported invalid service", response=response, payload=payload)

            # Fallback to generic error
            raise SMMServiceError("Partner returned an error payload", response=response, payload=payload)


# ----------------------------------------------------------------------
# Demonstration stub for rapid prototyping & testing
# ----------------------------------------------------------------------
class _StubSMMClient(BaseSMMClient):
    """Simple concrete implementation used for contract testing examples."""

    def create_order(self, *, service_id: str, quantity: int, **kwargs: Any) -> Mapping[str, Any]:
        headers = kwargs.pop("headers", None)
        return self._request(
            "POST",
            "/post",
            json_payload={"service_id": service_id, "quantity": quantity, **kwargs},
            headers=headers,
        )

    def get_status(self, order_id: str) -> Mapping[str, Any]:
        return self._request("GET", "/status", params={"order_id": order_id})

    def get_services(self) -> Mapping[str, Any]:
        return self._request("GET", "/services")

    def get_balance(self) -> Mapping[str, Any]:
        return self._request("GET", "/balance")


def _example_request_flow() -> None:  # pragma: no cover - illustrative helper
    """Illustrates how integration tests can exercise the request helper.

    The function is intentionally separated from runtime code so it can be
    reused inside unit tests or Jupyter notebooks without side effects during
    normal application execution.
    """

    # During prototyping we can leverage httpbin.org or mocked responses
    # provided by Oracle 007 to simulate partner behaviour.
    demo_client = _StubSMMClient(base_url="https://httpbin.org", api_key="demo-key")

    # Example: create order prototype using httpbin's /post endpoint.
    response = demo_client.submit_order(service_id="1234", quantity=500)

    logger.info("Prototype response received", extra={"response": response})


if __name__ == "__main__":  # pragma: no cover - manual smoke entry point
    logging.basicConfig(level=logging.INFO)
    _example_request_flow()
