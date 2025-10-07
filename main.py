"""Main FastAPI backend application for NaijaBoost AI with Wallet & Financial Engine integration."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ai_brain_orchestrator import DualBrainOrchestrator, ParsedServicePlan
from wallet_engine import WalletEngine

logger = logging.getLogger(__name__)

app = FastAPI(title="NaijaBoost AI Backend", version="2.0")
orchestrator = DualBrainOrchestrator()
wallet_engine = WalletEngine()
templates = Jinja2Templates(directory="templates")


class CampaignPromptRequest(BaseModel):
    user_id: str
    prompt: str
    language: str = "English"


class WalletCreditRequest(BaseModel):
    user_id: str
    amount_ngn: float = Field(..., gt=0, description="Amount in NGN to credit to user wallet")
    gateway_ref: str
    gateway: str = "paystack"


def get_db_path() -> Path:
    """Resolve the location of mtp_campaigns.db."""
    local_db = Path("mtp_campaigns.db")
    if local_db.exists():
        return local_db
    desktop_db = Path("/Users/mac/Desktop/MTP_Matrix_Engine_v1.txt/mtp_campaigns.db")
    if desktop_db.exists():
        return desktop_db
    return local_db


def lookup_active_providers() -> List[Dict[str, Any]]:
    """Query provider_routes table from mtp_campaigns.db for active providers."""
    db_path = get_db_path()
    if not db_path.exists():
        logger.warning(f"Database not found at {db_path}")
        return []

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT provider_id, tier, api_endpoint, supports_drip_feed, priority_weight "
                "FROM provider_routes WHERE is_active = 1 ORDER BY priority_weight DESC"
            )
            rows = cursor.fetchall()
            return [
                {
                    "provider_id": row[0],
                    "tier": row[1],
                    "api_endpoint": row[2],
                    "supports_drip_feed": bool(row[3]),
                    "priority_weight": row[4],
                }
                for row in rows
            ]
    except Exception as exc:
        logger.exception(f"Failed to query provider_routes from {db_path}: {exc}")
        return []


def lookup_provider_route(provider_id: str) -> Optional[Dict[str, Any]]:
    """Look up a specific active provider route in mtp_campaigns.db."""
    db_path = get_db_path()
    if not db_path.exists():
        return None

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT provider_id, tier, api_endpoint, supports_drip_feed, priority_weight "
                "FROM provider_routes WHERE LOWER(provider_id) = ? AND is_active = 1",
                (provider_id.lower(),),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "provider_id": row[0],
                    "tier": row[1],
                    "api_endpoint": row[2],
                    "supports_drip_feed": bool(row[3]),
                    "priority_weight": row[4],
                }
    except Exception as exc:
        logger.exception(f"Failed to query provider route '{provider_id}' from {db_path}: {exc}")
    return None


def calculate_campaign_cost_usd(service_type: str, quantity: int) -> float:
    """Calculate wholesale USD cost for a campaign based on service type and quantity."""
    rates_per_1k = {
        "youtube_watch_time": 10.0,
        "music_streaming": 2.0,
        "social_followers": 1.5,
        "bulk_growth": 0.8,
    }
    rate = rates_per_1k.get(service_type.lower(), 1.0)
    cost_usd = round((quantity / 1000.0) * rate, 4)
    return max(0.01, cost_usd)


@app.get("/")
def read_root(request: Request) -> Any:
    """Render the single-page conversational UI template."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/v1/status")
def get_api_status() -> Dict[str, str]:
    return {"Status": "NaijaBoost AI Backend is Online"}


@app.get("/api/v1/wallet/balance/{user_id}")
def get_user_wallet_balance(user_id: str) -> Dict[str, Any]:
    """Retrieve current NGN and USD wallet balance for a user."""
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id must not be empty.")
    try:
        balance = wallet_engine.get_wallet_balance(user_id)
        return {"status": "success", "data": balance}
    except Exception as exc:
        logger.exception(f"Error fetching wallet balance for user '{user_id}'")
        raise HTTPException(status_code=500, detail="Internal error retrieving wallet balance.")


@app.post("/api/v1/wallet/credit")
def credit_user_wallet(request: WalletCreditRequest) -> Dict[str, Any]:
    """Verify deposit webhook / credit user wallet with NGN and calculate USD equivalent."""
    try:
        result = wallet_engine.credit_wallet(
            user_id=request.user_id,
            amount_ngn=request.amount_ngn,
            gateway_ref=request.gateway_ref,
            gateway=request.gateway,
        )
        return {"status": "success", "message": "Wallet credited successfully.", "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Error crediting user wallet")
        raise HTTPException(status_code=500, detail="Internal server error during wallet credit.")


@app.post("/api/v1/campaign/prompt")
def create_campaign_from_prompt(request: CampaignPromptRequest) -> Any:
    """
    Route incoming prompt through DualBrainOrchestrator, look up active provider
    in provider_routes, verify user wallet balance against calculated campaign cost,
    and return structured confirmation (or 402 Payment Required if funds are low).
    """
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    active_providers = lookup_active_providers()
    try:
        plan: ParsedServicePlan = orchestrator.process_prompt(
            prompt=request.prompt,
            language=request.language,
            available_providers=active_providers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Error processing prompt through DualBrainOrchestrator")
        raise HTTPException(status_code=500, detail="Internal server error while processing campaign prompt.")

    # Look up active provider route
    provider_details = lookup_provider_route(plan.recommended_provider)
    if not provider_details and active_providers:
        provider_details = active_providers[0]
        plan.recommended_provider = provider_details["provider_id"]

    # Calculate wholesale campaign cost and verify wallet balance
    cost_usd = calculate_campaign_cost_usd(plan.service_type, plan.quantity)
    exchange_rate = wallet_engine.get_exchange_rate()
    required_ngn = round(cost_usd * exchange_rate, 2)

    wallet = wallet_engine.get_wallet_balance(request.user_id)
    current_balance_ngn = wallet.get("balance_ngn", 0.0)

    # If wallet balance is less than required cost (with 1e-4 tolerance for float precision)
    if current_balance_ngn < (required_ngn - 1e-4):
        deficit_ngn = round(required_ngn - current_balance_ngn, 2)
        logger.warning(
            f"User '{request.user_id}' has insufficient balance. Required: NGN {required_ngn:,.2f} (${cost_usd:,.2f} USD). "
            f"Current: NGN {current_balance_ngn:,.2f}. Deficit: NGN {deficit_ngn:,.2f}."
        )
        return JSONResponse(
            status_code=402,
            content={
                "status": "error",
                "error_code": "PAYMENT_REQUIRED",
                "message": (
                    f"Insufficient funds in wallet for user '{request.user_id}'. "
                    f"Required: NGN {required_ngn:,.2f} (${cost_usd:,.2f} USD). "
                    f"Current Balance: NGN {current_balance_ngn:,.2f}."
                ),
                "data": {
                    "user_id": request.user_id,
                    "required_usd": cost_usd,
                    "required_ngn": required_ngn,
                    "current_balance_ngn": current_balance_ngn,
                    "current_balance_usd": wallet.get("balance_usd", 0.0),
                    "deficit_ngn": deficit_ngn,
                    "exchange_rate": exchange_rate,
                    "campaign_plan": plan.to_dict(),
                },
            },
        )

    return {
        "status": "success",
        "message": "Auto-configured campaign plan generated and verified successfully.",
        "data": {
            "user_id": request.user_id,
            "language": request.language,
            "campaign_plan": plan.to_dict(),
            "provider_route": provider_details or {
                "provider_id": plan.recommended_provider,
                "tier": "Tier 1 - Default",
                "api_endpoint": "https://api.naijaboost.ai/v2",
                "supports_drip_feed": True,
                "priority_weight": 1.0,
            },
            "financial_verification": {
                "cost_usd": cost_usd,
                "cost_ngn": required_ngn,
                "exchange_rate": exchange_rate,
                "wallet_balance_ngn": current_balance_ngn,
                "status": "SUFFICIENT_FUNDS",
            },
        },
    }