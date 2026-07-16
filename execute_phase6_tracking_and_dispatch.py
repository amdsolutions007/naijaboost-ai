#!/usr/bin/env python3
"""
execute_phase6_tracking_and_dispatch.py - Continuous Tracking Engine Loop & Phase 6 Apple Music Dispatch.
"""

from __future__ import annotations

import json
import sqlite3
import requests
from wallet_engine import WalletEngine
from services.provider_orchestrator import ProviderOrchestrator

TARGET_URL = "https://music.apple.com/ng/album/simple-logic-single/6773821382"
USER_ID = "ceo_solutions007"
API_PROMPT_URL = "http://127.0.0.1:8080/api/v1/campaign/prompt"
SHAZAM_ORDER_ID = "985511906"

def run_phase6() -> None:
    print("\n" + "=" * 104)
    print("    CONTINUOUS TRACKING ENGINE LOOP & PHASE 6 APPLE MUSIC CAMPAIGN DISPATCH")
    print("=" * 104 + "\n")

    wallet_engine = WalletEngine()
    orchestrator = ProviderOrchestrator()

    # Step 1: Run dynamic status lookup via API client for Shazam Order ID #985511906 on JUSTANOTHERPANEL
    print(f">>> STEP 1: Dynamic Status Lookup for Shazam Order ID #{SHAZAM_ORDER_ID} on JUSTANOTHERPANEL...")
    try:
        jap_client = orchestrator.get_provider_client("justanotherpanel")
        shazam_status = jap_client.get_status(order_id=SHAZAM_ORDER_ID)
    except Exception as exc:
        shazam_status = {"status": "error", "message": str(exc)}

    print("\n--- Raw API Response Block (Shazam Live Order Status) ---")
    print(json.dumps(shazam_status, indent=4))
    print("-" * 104 + "\n")

    # Step 2: Fire live production POST request to FastAPI endpoint (/api/v1/campaign/prompt) for 3,500 Apple Music Streams
    print(">>> STEP 2: Firing POST /api/v1/campaign/prompt for Phase 6 Apple Music Streams Campaign...")
    apple_payload = {
        "user_id": USER_ID,
        "prompt": f"Dispatch Phase 6 campaign: 3500 Apple Music streams for verified link {TARGET_URL} routing via smmmain",
        "language": "English"
    }

    try:
        resp = requests.post(API_PROMPT_URL, json=apple_payload, timeout=10.0)
        apple_prompt_res = resp.json()
    except Exception as exc:
        apple_prompt_res = {"error": str(exc), "status_code": getattr(resp, "status_code", "N/A")}

    print("\n--- Raw API Response Block (Apple Music Campaign Configuration & Route Verification) ---")
    print(json.dumps(apple_prompt_res, indent=4))
    print("-" * 104 + "\n")

    # Step 3: Ensure strict routing to Category A Wholesaler (smmmain) and verify WalletEngine atomic deduction
    print(">>> STEP 3: Verifying SMMMain Route & Performing Atomic Wallet Deduction for Phase 6...")
    
    # Check SMMMain wholesale balance
    smmmain_bal = wallet_engine.check_provider_balance("smmmain")
    print("\n[Wholesale Status Check] SMMMain Live Wholesaler Balance:")
    print(json.dumps(smmmain_bal, indent=4))

    # The financial verification returned $7.00 USD cost for 3,500 Apple Music Streams
    cost_usd = 7.0
    print(f"\n[Wallet Deduction] Atomically deducting ${cost_usd:.4f} USD from user '{USER_ID}' wallet...")
    try:
        deduct_res = wallet_engine.deduct_order_cost(
            user_id=USER_ID,
            cost_usd=cost_usd,
            transaction_id="TXN_APPLE_MUSIC_SIMPLE_LOGIC_06"
        )
        print("Atomic Deduction Verification Block:")
        print(json.dumps(deduct_res, indent=4))
    except Exception as exc:
        print(f"Deduction exception block: {exc}")

    # Forwarding check to smmmain network (Service ID for Apple Music: 9250 or 1 on SMMMain)
    print("\n[Wholesale Dispatch Check] Attempting order dispatch to SMMMain network...")
    push_res = wallet_engine.forward_order_to_provider(
        service_id="9250",
        quantity=3500,
        target_url=TARGET_URL,
        provider_id="smmmain"
    )
    print("SMMMain Wholesale Order Push Response Block:")
    print(json.dumps(push_res, indent=4))
    print("-" * 104 + "\n")

    # Step 4: Output complete wallet transaction ledger for verification
    print(">>> STEP 4: Live Ledger Verification (Latest Transactions for 'ceo_solutions007')...")
    with sqlite3.connect(wallet_engine.db_path) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT transaction_id, amount_ngn, amount_usd, type, status, created_at FROM wallet_transactions WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (USER_ID,)
        ).fetchall()
        print(f"{'Transaction ID':<32} | {'Amount (NGN)':<16} | {'Amount (USD)':<14} | {'Type':<12} | {'Status':<10} | {'Timestamp'}")
        print("-" * 104)
        for r in rows:
            print(f"{r[0]:<32} | {r[1]:<16.2f} | {r[2]:<14.4f} | {r[3]:<12} | {r[4]:<10} | {r[5]}")

    print("\n" + "=" * 104)
    print("                 PHASE 6 APPLE MUSIC CAMPAIGN EXECUTION COMPLETE")
    print("=" * 104 + "\n")

if __name__ == "__main__":
    run_phase6()
