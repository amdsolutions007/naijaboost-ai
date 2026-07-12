"""Tests for Dual-Brain AI Orchestrator and FastAPI endpoints."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from ai_brain_orchestrator import DualBrainOrchestrator, ParsedServicePlan
from main import app, get_db_path, lookup_active_providers, lookup_provider_route


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def test_database_provider_routes_instantiation_and_seeding() -> None:
    """Verify that mtp_campaigns.db has provider_routes schema correctly seeded without Category B."""
    db_path = get_db_path()
    assert db_path.exists(), f"Database not found at {db_path}"

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Verify schema table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='provider_routes'")
        assert cursor.fetchone() is not None, "provider_routes table does not exist"

        # Verify Category B is completely purged
        cursor.execute(
            "SELECT COUNT(*) FROM provider_routes WHERE LOWER(provider_id) IN "
            "('morethanpanel', 'godsmm', 'nicesmmpanel', 'prm4u', 'peakerrsmm', 'mtp', 'smmfollows')"
        )
        category_b_count = cursor.fetchone()[0]
        assert category_b_count == 0, "Category B providers found in provider_routes"

        # Verify Category A wholesalers are seeded
        cursor.execute("SELECT provider_id FROM provider_routes WHERE is_active = 1")
        providers = {row[0].lower() for row in cursor.fetchall()}
        expected = {"smmmain", "smmkings", "bulqfollowers", "secser", "justanotherpanel"}
        assert expected.issubset(providers), f"Expected providers {expected} not subset of {providers}"


def test_dual_brain_orchestrator_process_prompt() -> None:
    """Verify DualBrainOrchestrator extracts context, builds valid ServicePlan, and enforces safety bounds."""
    orchestrator = DualBrainOrchestrator()
    prompt = "I want 5000 music streams for my new Afrobeat song https://audiomack.com/song/123"
    
    plan: ParsedServicePlan = orchestrator.process_prompt(prompt, language="Pidgin")
    assert plan.service_type == "music_streaming"
    assert plan.quantity == 5000
    assert plan.target_url == "https://audiomack.com/song/123"
    assert plan.drip_feed is True
    assert 100 <= plan.delivery_rate <= 1000
    assert plan.recommended_provider in {"smmmain", "smmkings", "bulqfollowers", "secser", "justanotherpanel"}


def test_dual_brain_orchestrator_enforces_drip_feed_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that if an unsafe delivery rate is produced, safety validation normalizes or clamps it."""
    orchestrator = DualBrainOrchestrator()

    def fake_openai_run(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "service_type": "youtube_watch_time",
            "quantity": 1000,
            "target_url": "https://youtube.com/watch?v=abc",
            "drip_feed": True,
            "delivery_rate": 9999,  # Unsafe rate (> 1000)
            "recommended_provider": "secser",
        }

    monkeypatch.setattr(orchestrator, "_run_openai_brain", fake_openai_run)
    plan = orchestrator.process_prompt("Test prompt", language="English")
    assert 100 <= plan.delivery_rate <= 1000
    assert plan.delivery_rate == 1000


def test_fastapi_campaign_prompt_endpoint(test_client: TestClient) -> None:
    """Verify POST /api/v1/campaign/prompt returns structured plan and active provider route after crediting wallet."""
    # Ensure user has sufficient funds for campaign cost check
    test_client.post(
        "/api/v1/wallet/credit",
        json={"user_id": "ceo_solutions007", "amount_ngn": 50000.0, "gateway_ref": "REF_CEO_TEST_001"},
    )
    payload = {
        "user_id": "ceo_solutions007",
        "prompt": "Boost my YouTube channel with 1000 watch hours https://youtube.com/channel/naijaboost",
        "language": "Yoruba",
    }
    response = test_client.post("/api/v1/campaign/prompt", json=payload)
    assert response.status_code == 200, response.text
    
    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Auto-configured campaign plan generated and verified successfully."
    assert data["data"]["user_id"] == "ceo_solutions007"
    assert data["data"]["language"] == "Yoruba"
    
    plan = data["data"]["campaign_plan"]
    assert plan["service_type"] == "youtube_watch_time"
    assert plan["quantity"] == 1000
    assert plan["target_url"] == "https://youtube.com/channel/naijaboost"
    assert plan["drip_feed"] is True
    assert 100 <= plan["delivery_rate"] <= 1000
    
    route = data["data"]["provider_route"]
    assert route["provider_id"] in {"smmmain", "smmkings", "bulqfollowers", "secser", "justanotherpanel"}


def test_fastapi_campaign_prompt_empty_error(test_client: TestClient) -> None:
    """Verify POST /api/v1/campaign/prompt rejects empty prompts."""
    payload = {
        "user_id": "user_123",
        "prompt": "   ",
        "language": "English",
    }
    response = test_client.post("/api/v1/campaign/prompt", json=payload)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
