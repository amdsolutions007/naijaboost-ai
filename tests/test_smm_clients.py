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


def test_mtp_client_balance_and_order(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.smm_partners.mtp_client import MoreThanPanelClient

    mocker.register_uri(
        "POST",
        "https://morethanpanel.com/api/v2",
        json={"balance": "3.8015400", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    client = MoreThanPanelClient(
        base_url="https://morethanpanel.com/api/v2",
        api_key="51139ff558f02990c1daf3f9a5a23da9",
        session=session,
    )
    balance_res = client.get_balance()
    assert balance_res["balance"] == "3.8015400"
    assert balance_res["currency"] == "USD"


def test_provider_orchestrator_mapping(mocked_session: tuple[Session, Any]) -> None:
    session, _ = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.mtp_client import MoreThanPanelClient

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("mtp")
    assert isinstance(client, MoreThanPanelClient)
    assert client.api_key == "51139ff558f02990c1daf3f9a5a23da9"


def test_jasasmm_client_and_idr_conversion(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.jasasmm_client import JasaSMMClient

    mocker.register_uri(
        "POST",
        "https://jasasmm.com/api/v2",
        json={"balance": "162000.0000000", "currency": "IDR"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("jasasmm")
    assert isinstance(client, JasaSMMClient)
    assert client.api_key == "3ce3b8e2059ec5cc97fcb38ce8770fcd"

    # Verify IDR balance is parsed and converted safely to USD
    bal_data = orch.check_provider_balance("jasasmm", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "IDR"
    assert bal_data["balance_native"] == 162000.0
    assert isinstance(bal_data["balance_usd"], float)


def test_indosmm_client_and_idr_conversion(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.indosmm_client import IndoSMMClient

    mocker.register_uri(
        "POST",
        "https://indosmm.id/api/v2",
        json={"balance": "324000.0000000", "currency": "IDR"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("indosmm")
    assert isinstance(client, IndoSMMClient)
    assert client.api_key == "5cdf4a20b7c58227f05d14c09efbca81"

    bal_data = orch.check_provider_balance("indosmm", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "IDR"
    assert bal_data["balance_native"] == 324000.0
    assert isinstance(bal_data["balance_usd"], float)


def test_godsmm_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.godsmm_client import GodSMMClient

    mocker.register_uri(
        "POST",
        "https://godsmm.com/api/v2",
        json={"balance": "15.5000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("godsmm")
    assert isinstance(client, GodSMMClient)
    assert client.api_key == "054533776b26d195c82dc31d731fe1517c90f81c5944f7cb9e917504a7a7d12e"

    bal_data = orch.check_provider_balance("godsmm", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 15.5


def test_smmmain_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.smmmain_client import SMMMainClient

    mocker.register_uri(
        "POST",
        "https://smmmain.com/api/v2",
        json={"balance": "42.0000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("smmmain")
    assert isinstance(client, SMMMainClient)
    assert client.api_key == "76e212495c47d38e08cc8991299fc6ac"

    bal_data = orch.check_provider_balance("smmmain", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 42.0


def test_smmkings_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.smmkings_client import SMMKingsClient

    mocker.register_uri(
        "POST",
        "https://smmkings.com/api/v2",
        json={"balance": "99.5000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("smmkings")
    assert isinstance(client, SMMKingsClient)
    assert client.api_key == "5802d5c9b5c03272de5c507b6de36a6c"

    bal_data = orch.check_provider_balance("smmkings", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 99.5


def test_justanotherpanel_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.jap_client import JustAnotherPanelClient

    mocker.register_uri(
        "POST",
        "https://justanotherpanel.com/api/v2",
        json={"balance": "8.4500000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client_jap = orch.get_provider_client("justanotherpanel")
    assert isinstance(client_jap, JustAnotherPanelClient)
    assert client_jap.api_key == "e3348e1236ab3106f67cb7a21b5f0eb5"

    client_short = orch.get_provider_client("jap")
    assert isinstance(client_short, JustAnotherPanelClient)

    bal_data = orch.check_provider_balance("justanotherpanel", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 8.45


def test_instantfans_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.instantfans_client import InstantFansClient

    mocker.register_uri(
        "POST",
        "https://instant-fans.com/api/v2",
        json={"balance": "15.7500000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("instantfans")
    assert isinstance(client, InstantFansClient)
    assert client.api_key == "18f616085df9edde3111887f09c72f59"

    client_hyphen = orch.get_provider_client("instant-fans")
    assert isinstance(client_hyphen, InstantFansClient)

    bal_data = orch.check_provider_balance("instantfans", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 15.75


def test_nicesmmpanel_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.nicesmmpanel_client import NiceSMMPanelClient

    mocker.register_uri(
        "POST",
        "https://nicesmmpanel.com/api/v2",
        json={"balance": "42.1000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("nicesmmpanel")
    assert isinstance(client, NiceSMMPanelClient)
    assert client.api_key == "aaf66ec1cec36e5030a9f2daa48fb6ea"

    client_short = orch.get_provider_client("nicesmm")
    assert isinstance(client_short, NiceSMMPanelClient)

    bal_data = orch.check_provider_balance("nicesmmpanel", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 42.10


def test_yoyomedia_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.yoyomedia_client import YoYoMediaClient

    mocker.register_uri(
        "POST",
        "https://yoyomedia.com/api/v2",
        json={"balance": "55.0000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("yoyomedia")
    assert isinstance(client, YoYoMediaClient)
    assert client.api_key == "6e6e26efb489ee38ed8228d159aff57d5e5d885fbc8792195a9ba220dd6c21a5"

    client_short = orch.get_provider_client("yoyo")
    assert isinstance(client_short, YoYoMediaClient)

    bal_data = orch.check_provider_balance("yoyomedia", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 55.00


def test_peakerr_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.peakerr_client import PeakerrClient

    mocker.register_uri(
        "POST",
        "https://peakerr.com/api/v2",
        json={"balance": "88.5000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("peakerr")
    assert isinstance(client, PeakerrClient)
    assert client.api_key == "f974254175d766a4d0611241dfa8952e"

    client_alias = orch.get_provider_client("peakerrsmm")
    assert isinstance(client_alias, PeakerrClient)

    bal_data = orch.check_provider_balance("peakerr", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 88.50


def test_likesng_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.likesng_client import LikesNgClient

    mocker.register_uri(
        "POST",
        "https://likes.ng/api/v2",
        json={"balance": "120.0000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("likesng")
    assert isinstance(client, LikesNgClient)

    bal_data = orch.check_provider_balance("likesng", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 120.00


def test_owlet_client_balance(mocked_session: tuple[Session, Any]) -> None:
    session, mocker = mocked_session
    from services.provider_orchestrator import ProviderOrchestrator
    from services.smm_partners.owlet_client import OwletClient

    mocker.register_uri(
        "POST",
        "https://theowlet.com/api/v2",
        json={"balance": "75.0000000", "currency": "USD"},
        additional_matcher=_match_action("balance"),
    )

    orch = ProviderOrchestrator()
    client = orch.get_provider_client("owlet")
    assert isinstance(client, OwletClient)

    bal_data = orch.check_provider_balance("owlet", session=session)
    assert bal_data["status"] == "success"
    assert bal_data["currency"] == "USD"
    assert bal_data["balance_usd"] == 75.00

