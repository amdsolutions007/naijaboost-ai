#!/usr/bin/env python3
"""
execute_live_campaign_launch.py - Live Production Campaign Launch for 'Simple Logic'.
Seeded with user 'ceo_solutions007' and link https://music.apple.com/ng/album/simple-logic-single/6773821382
"""

from __future__ import annotations

import json
import sqlite3
import requests
from wallet_engine import WalletEngine

TARGET_URL = "https://music.apple.com/ng/album/simple-logic-single/6773821382"
USER_ID = "ceo_solutions007"
API_PROMPT_URL = "http://127.0.0.1:8080/api/v1/campaign/prompt"

def run_campaign_launch() -> None:
    print("\n" + "=" * 104)
    print("      LIVE PRODUCTION CAMPAIGN LAUNCH: 'SIMPLE LOGIC' BY USER ceo_solutions007")
    print("=" * 104 + "\n")

    wallet_engine = WalletEngine()

    # Step 1: Fire live POST request to local FastAPI endpoint (/api/v1/campaign/prompt) for 5,000 Shazam Plays
    print(">>> STEP 1: Firing POST /api/v1/campaign/prompt for 5,000 Shazam Plays Campaign...")
    shazam_payload = {
        "user_id": USER_ID,
        "prompt": f"Configure 5000 Shazam plays campaign for single {TARGET_URL}",
        "language": "English"
    }

    try:
        resp1 = requests.post(API_PROMPT_URL, json=shazam_payload, timeout=10.0)
        shazam_response_data = resp1.json()
    except Exception as exc:
        shazam_response_data = {"error": str(exc), "status_code": getattr(resp1, "status_code", "N/A")}

    print("\n--- Raw API Response Block (Shazam Plays Campaign Configuration) ---")
    print(json.dumps(shazam_response_data, indent=4))
    print("-" * 104 + "\n")

    # Step 2: Verify wallet funds against JUSTANOTHERPANEL balance, log transaction, and push to wholesaler network
    print(">>> STEP 2: Verifying Wallet Funds against JUSTANOTHERPANEL Balance & Pushing Wholesale Order...")
    
    # Check JUSTANOTHERPANEL wholesale balance
    jap_balance_check = wallet_engine.check_provider_balance("justanotherpanel")
    print("\n[Wholesale Verification] JUSTANOTHERPANEL Live Balance Status:")
    print(json.dumps(jap_balance_check, indent=4))

    # Our verified wholesale service for Shazam on JAP is ID 784 (or 464) at $1.25 / 1k ($6.25 USD for 5,000)
    shazam_cost_usd = 6.25
    print(f"\n[Wallet Deduction] Atomically deducting ${shazam_cost_usd:.4f} USD equivalent for 5,000 Shazam Plays...")
    
    try:
        deduct_res = wallet_engine.deduct_order_cost(USER_ID, shazam_cost_usd, transaction_id="TXN_SHAZAM_SIMPLE_LOGIC_01")
        print("Deduction Log Result:")
        print(json.dumps(deduct_res, indent=4))
    except Exception as exc:
        print(f"Wallet deduction note/error: {exc}")

    print("\n[Wholesale Push] Dispatching order to JUSTANOTHERPANEL network (Service ID: 784, Quantity: 5000)...")
    push_res = wallet_engine.forward_order_to_provider(
        service_id="784",
        quantity=5000,
        target_url=TARGET_URL,
        provider_id="justanotherpanel"
    )
    print("Wholesale Order Forwarding Response:")
    print(json.dumps(push_res, indent=4))
    print("-" * 104 + "\n")

    # Step 3: Fire second POST request to configure 3,500 Apple Music streams campaign for the same link
    print(">>> STEP 3: Firing POST /api/v1/campaign/prompt for 3,500 Apple Music Streams Campaign...")
    apple_payload = {
        "user_id": USER_ID,
        "prompt": f"Configure 3500 Apple Music streams campaign for song {TARGET_URL}",
        "language": "English"
    }

    try:
        resp2 = requests.post(API_PROMPT_URL, json=apple_payload, timeout=10.0)
        apple_response_data = resp2.json()
    except Exception as exc:
        apple_response_data = {"error": str(exc), "status_code": getattr(resp2, "status_code", "N/A")}

    print("\n--- Raw API Response Block (Apple Music Streams Campaign Configuration) ---")
    print(json.dumps(apple_response_data, indent=4))
    print("-" * 104 + "\n")

    # Step 4: Verify transaction log status in database
    print(">>> STEP 4: Transaction Log Audit for User 'ceo_solutions007'...")
    with sqlite3.connect(wallet_engine.db_path) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT transaction_id, amount_ngn, amount_usd, type, status, created_at FROM wallet_transactions WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (USER_ID,)
        ).fetchall()
        print(f"{'Transaction ID':<28} | {'Amount (NGN)':<16} | {'Amount (USD)':<14} | {'Type':<12} | {'Status':<10} | {'Timestamp'}")
        print("-" * 104)
        for r in rows:
            print(f"{r[0]:<28} | {r[1]:<16.2f} | {r[2]:<14.4f} | {r[3]:<12} | {r[4]:<10} | {r[5]}")
    
    print("\n" + "=" * 104)
    print("                   LIVE CAMPAIGN LAUNCH EXECUTION COMPLETE")
    print("=" * 104 + "\n")

if __name__ == "__main__":
    run_campaign_launch()
