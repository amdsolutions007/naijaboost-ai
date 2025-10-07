"""Contract test stubs for SMM partner clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import pytest
from requests import Session

from services.smm_partners import (
    GodSMMClient,
    InsufficientFundsError,
    OrderRejectedError,
    ServiceUnavailableError,
    YoYoMediaClient,
)


def _match_action(expected_action: str) -> Callable[[Any], bool]:
    def matcher(request: Any) -> bool:
        body_obj = getattr(request, "text", None)
        if isinstance(body_obj, str):
            body = body_obj
        else:
            body_bytes = getattr(request, "body", None)
            if isinstance(body_bytes, bytes):
                body = body_bytes.decode("utf-8")
            else:  # pragma: no cover - defensive
                return False

        data = parse_qs(body)
        action_values = data.get("action")
        action = action_values[0] if action_values else ""
        return action.lower() == expected_action.lower()

    return matcher


def test_circuit_breaker_blocks_recent_failures(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session

    mocker.register_uri(
        "POST",
        "https://partner.test/api",
        [
            {"status_code": 500, "json": {"error": "server down"}},
            {"status_code": 500, "json": {"error": "server down"}},
            {"status_code": 500, "json": {"error": "server down"}},
        ],
        additional_matcher=_match_action("add"),
    )

    client = YoYoMediaClient(base_url="https://partner.test", api_key="abc123", session=session)

    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="100", quantity=100, link="https://example.com")

    assert mocker.call_count == 3

    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="100", quantity=100, link="https://example.com")

    assert mocker.call_count == 3


def test_translate_partner_insufficient_funds_error(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session

    mocker.register_uri(
        "POST",
        "https://partner.test/api",
        json={"status": "error", "message": "Insufficient funds"},
        additional_matcher=_match_action("add"),
    )

    client = GodSMMClient(base_url="https://partner.test", api_key="def456", session=session)

    with pytest.raises(InsufficientFundsError):
        client.submit_order(service_id="200", quantity=50, link="https://example.com")


def test_translate_partner_order_rejected_error(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session

    mocker.register_uri(
        "POST",
        "https://partner.test/api",
        json={"status": "failure", "error_code": "order_rejected"},
        additional_matcher=_match_action("add"),
    )

    client = YoYoMediaClient(base_url="https://partner.test", api_key="ghi789", session=session)

    with pytest.raises(OrderRejectedError):
        client.submit_order(service_id="300", quantity=75, link="https://example.com")


def test_catastrophic_502_opens_circuit(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session

    mocker.register_uri(
        "POST",
        "https://partner.test/api",
        status_code=502,
        text="bad gateway",
        additional_matcher=_match_action("add"),
    )

    client = YoYoMediaClient(base_url="https://partner.test", api_key="abc123", session=session)

    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="100", quantity=100, link="https://example.com")

    # subsequent attempt should be blocked immediately by circuit
    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="100", quantity=100, link="https://example.com")


def test_catastrophic_503_opens_circuit(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session

    mocker.register_uri(
        "POST",
        "https://partner.test/api",
        status_code=503,
        text="service unavailable",
        additional_matcher=_match_action("add"),
    )

    client = GodSMMClient(base_url="https://partner.test", api_key="def456", session=session)

    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="200", quantity=50, link="https://example.com")

    # subsequent attempt should be blocked immediately by circuit
    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="200", quantity=50, link="https://example.com")


def test_connection_error_opens_circuit(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session

    import requests

    def raise_connection_error(*args: Any, **kwargs: Any) -> None:  # type: ignore[no-untyped-def]
        raise requests.ConnectionError("network unreachable")

    mocker.register_uri(
        "POST",
        "https://partner.test/api",
        text=raise_connection_error,  # type: ignore[arg-type]
        additional_matcher=_match_action("add"),
    )

    client = YoYoMediaClient(base_url="https://partner.test", api_key="ghi789", session=session)

    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="300", quantity=75, link="https://example.com")

    # subsequent attempt should be blocked immediately by circuit
    with pytest.raises(ServiceUnavailableError):
        client.submit_order(service_id="300", quantity=75, link="https://example.com")
