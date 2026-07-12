"""Tests for local payment wallet engine and financial validation in FastAPI."""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from main import app, get_db_path
from services.smm_partners.base import InsufficientFundsError
from wallet_engine import WalletEngine


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def temp_wallet_user() -> Generator[str, None, None]:
    """Provide a temporary user ID and clean up after test."""
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    yield user_id
    db_path = get_db_path()
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            conn.execute("DELETE FROM wallet_transactions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_wallets WHERE user_id = ?", (user_id,))


def test_wallet_engine_database_schema() -> None:
    """Verify that user_wallets and wallet_transactions tables exist."""
    db_path = get_db_path()
    assert db_path.exists(), f"Database not found at {db_path}"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_wallets'")
        assert cursor.fetchone() is not None, "user_wallets table missing"

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wallet_transactions'")
        assert cursor.fetchone() is not None, "wallet_transactions table missing"


def test_wallet_engine_credit_and_balance(temp_wallet_user: str) -> None:
    """Verify crediting a user wallet updates NGN and USD balances and records transaction."""
    engine = WalletEngine()
    ref = f"REF_{uuid.uuid4().hex[:8]}"
    res = engine.credit_wallet(temp_wallet_user, 30000.0, ref, gateway="paystack")

    assert res["status"] == "success"
    assert res["balance_ngn"] == 30000.0
    assert res["balance_usd"] > 0.0

    balance = engine.get_wallet_balance(temp_wallet_user)
    assert balance["balance_ngn"] == 30000.0
    assert balance["balance_usd"] == res["balance_usd"]


def test_wallet_engine_deduct_order_cost_success(temp_wallet_user: str) -> None:
    """Verify atomically deducting order cost from a funded wallet."""
    engine = WalletEngine()
    ref = f"REF_{uuid.uuid4().hex[:8]}"
    engine.credit_wallet(temp_wallet_user, 50000.0, ref)

    deduct = engine.deduct_order_cost(temp_wallet_user, 10.0, transaction_id=f"TXN_{uuid.uuid4().hex[:8]}")
    assert deduct["status"] == "success"
    assert deduct["deducted_usd"] == 10.0
    assert deduct["new_balance_ngn"] < 50000.0


def test_wallet_engine_deduct_order_cost_insufficient_funds(temp_wallet_user: str) -> None:
    """Verify that deducting more than available balance raises InsufficientFundsError."""
    engine = WalletEngine()
    with pytest.raises(InsufficientFundsError) as exc_info:
        engine.deduct_order_cost(temp_wallet_user, 100.0)
    assert "insufficient funds" in str(exc_info.value).lower()


def test_fastapi_campaign_prompt_payment_required(test_client: TestClient, temp_wallet_user: str) -> None:
    """Verify that calling /api/v1/campaign/prompt with 0 wallet balance returns 402 Payment Required."""
    payload = {
        "user_id": temp_wallet_user,
        "prompt": "I want 1000 youtube watch hours https://youtube.com/channel/test",
        "language": "English",
    }
    response = test_client.post("/api/v1/campaign/prompt", json=payload)
    assert response.status_code == 402, response.text
    
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == "PAYMENT_REQUIRED"
    assert "insufficient funds" in data["message"].lower()


def test_fastapi_campaign_prompt_sufficient_funds(test_client: TestClient, temp_wallet_user: str) -> None:
    """Verify that calling /api/v1/campaign/prompt after crediting wallet returns 200 OK and plan verification."""
    # Credit user wallet first
    credit_payload = {
        "user_id": temp_wallet_user,
        "amount_ngn": 100000.0,
        "gateway_ref": f"REF_{uuid.uuid4().hex[:10]}",
    }
    r_credit = test_client.post("/api/v1/wallet/credit", json=credit_payload)
    assert r_credit.status_code == 200

    payload = {
        "user_id": temp_wallet_user,
        "prompt": "I want 1000 youtube watch hours https://youtube.com/channel/test",
        "language": "Pidgin",
    }
    response = test_client.post("/api/v1/campaign/prompt", json=payload)
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["financial_verification"]["status"] == "SUFFICIENT_FUNDS"
