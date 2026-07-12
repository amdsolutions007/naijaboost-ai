"""Tests for Phase 4 Frontend Conversational UI and HTML template rendering."""
from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)


def test_frontend_template_file_exists() -> None:
    """Verify that templates/index.html exists and contains required Lagos Tech Aesthetic tokens."""
    template_file = Path("templates/index.html")
    assert template_file.exists(), "templates/index.html does not exist"

    content = template_file.read_text(encoding="utf-8")
    assert "#FB9129" in content or "var(--accent-orange)" in content, "Disruptive Orange accent missing"
    assert "#121218" in content or "var(--bg-dark)" in content, "Deep Charcoal/Violent Violet background missing"
    assert "NaijaBoost AI" in content and "Build your Brand. Boost your Hustle." in content, "Required header slogan missing"
    assert "balanceNgn" in content and "balanceUsd" in content, "Real-time wallet status bar IDs missing"
    assert "English" in content and "Pidgin" in content and "Yoruba" in content and "Hausa" in content and "Igbo" in content, "Multilingual language bar pills missing"
    assert "SpeechRecognition" in content or "webkitSpeechRecognition" in content, "Web Speech API voice-to-text hooks missing"
    assert "fundModal" in content and "paymentRequiredModal" in content, "Fund wallet and 402 payment required modals missing"


def test_fastapi_html_route_root(test_client: TestClient) -> None:
    """Verify GET / returns 200 OK and renders HTML single-page application."""
    response = test_client.get("/")
    assert response.status_code == 200, response.text
    assert "text/html" in response.headers.get("content-type", "").lower()
    assert "NaijaBoost AI" in response.text
    assert "Speak or Type Your SMM Goals" in response.text


def test_fastapi_status_endpoint(test_client: TestClient) -> None:
    """Verify GET /api/v1/status returns API status cleanly."""
    response = test_client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json()["Status"] == "NaijaBoost AI Backend is Online"
