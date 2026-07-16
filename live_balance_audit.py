#!/usr/bin/env python3
"""
live_balance_audit.py - Live Infrastructure Balance Audit across 11 Active SMM Wholesalers.
"""

from __future__ import annotations

import os
import sys
import json
import requests
from dotenv import load_dotenv

def get_provider_configs() -> list[dict[str, str]]:
    load_dotenv()
    
    providers = [
        {
            "name": "MTP (MoreThanPanel)",
            "key_env": "MTP_API_KEY",
            "url_env": "MTP_PROVIDER_URL",
            "default_key": "51139ff558f02990c1daf3f9a5a23da9",
            "default_url": "https://morethanpanel.com/api/v2"
        },
        {
            "name": "JASASMM",
            "key_env": "JASASMM_API_KEY",
            "url_env": "JASASMM_PROVIDER_URL",
            "default_key": "3ce3b8e2059ec5cc97fcb38ce8770fcd",
            "default_url": "https://jasasmm.com/api/v2"
        },
        {
            "name": "INDOSMM",
            "key_env": "INDOSMM_API_KEY",
            "url_env": "INDOSMM_PROVIDER_URL",
            "default_key": "5cdf4a20b7c58227f05d14c09efbca81",
            "default_url": "https://indosmm.co.id/api/v2"
        },
        {
            "name": "GODSMM",
            "key_env": "GODSMM_API_KEY",
            "url_env": "GODSMM_PROVIDER_URL",
            "default_key": "054533776b26d195c82dc31d731fe1517c90f81c5944f7cb9e917504a7a7d12e",
            "default_url": "https://godsmm.com/api/v2"
        },
        {
            "name": "SMMMAIN",
            "key_env": "SMMMAIN_API_KEY",
            "url_env": "SMMMAIN_PROVIDER_URL",
            "default_key": "76e212495c47d38e08cc8991299fc6ac",
            "default_url": "https://smmmain.com/api/v2"
        },
        {
            "name": "SMMKINGS",
            "key_env": "SMMKINGS_API_KEY",
            "url_env": "SMMKINGS_PROVIDER_URL",
            "default_key": "5802d5c9b5c03272de5c507b6de36a6c",
            "default_url": "https://smmkings.com/api/v2"
        },
        {
            "name": "JUSTANOTHERPANEL",
            "key_env": "JUSTANOTHERPANEL_API_KEY",
            "url_env": "JUSTANOTHERPANEL_PROVIDER_URL",
            "default_key": os.getenv("JAP_API_KEY", "e3348e1236ab3106f67cb7a21b5f0eb5"),
            "default_url": "https://justanotherpanel.com/api/v2"
        },
        {
            "name": "INSTANTFANS",
            "key_env": "INSTANTFANS_API_KEY",
            "url_env": "INSTANTFANS_PROVIDER_URL",
            "default_key": "18f616085df9edde3111887f09c72f59",
            "default_url": "https://instant-fans.com/api/v2"
        },
        {
            "name": "NICESMMPANEL",
            "key_env": "NICESMMPANEL_API_KEY",
            "url_env": "NICESMMPANEL_PROVIDER_URL",
            "default_key": "aaf66ec1cec36e5030a9f2daa48fb6ea",
            "default_url": "https://nicesmmpanel.com/api/v2"
        },
        {
            "name": "YOYOMEDIA",
            "key_env": "YOYOMEDIA_API_KEY",
            "url_env": "YOYOMEDIA_PROVIDER_URL",
            "default_key": os.getenv("YOYO_API_KEY", "6e6e26efb489ee38ed8228d159aff57d5e5d885fbc8792195a9ba220dd6c21a5"),
            "default_url": os.getenv("YOYO_PROVIDER_URL", "https://yoyomedia.com/api/v2")
        },
        {
            "name": "PEAKERR",
            "key_env": "PEAKERR_API_KEY",
            "url_env": "PEAKERR_PROVIDER_URL",
            "default_key": "f974254175d766a4d0611241dfa8952e",
            "default_url": "https://peakerr.com/api/v2"
        }
    ]

    results = []
    for p in providers:
        api_key = os.getenv(p["key_env"], p["default_key"])
        url = os.getenv(p["url_env"], p["default_url"])
        results.append({
            "name": p["name"],
            "api_key": api_key,
            "url": url
        })
    return results

def audit_provider(name: str, url: str, api_key: str, session: requests.Session) -> dict[str, str]:
    headers = {
        "User-Agent": "NaijaBoost-SMM-Audit/1.0",
        "Accept": "application/json"
    }
    payload = {
        "key": api_key,
        "action": "balance"
    }

    # Try POST form-urlencoded first (standard SMM v2)
    try:
        resp = session.post(url, data=payload, headers=headers, timeout=10.0)
        # If POST failed with 405 Method Not Allowed or 404, try GET
        if resp.status_code in {405, 404}:
            resp = session.get(url, params=payload, headers=headers, timeout=10.0)
        
        status_code = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = resp.text

        if status_code == 200 and isinstance(data, dict):
            # Check if there's an error message inside the json
            if "error" in data and not any(k in data for k in ("balance", "money", "currency")):
                return {
                    "status": "FAILED (API Error)",
                    "balance": "N/A",
                    "currency": "N/A",
                    "raw_note": str(data.get("error", ""))[:45]
                }
            if data.get("status") in {"error", "fail", "failed"}:
                msg = data.get("message") or data.get("error") or "Unknown error"
                return {
                    "status": "FAILED (API Error)",
                    "balance": "N/A",
                    "currency": "N/A",
                    "raw_note": str(msg)[:45]
                }

            # Extract balance
            bal_val = data.get("balance", data.get("money", data.get("funds", "N/A")))
            curr_val = data.get("currency", "")
            
            # If currency is not returned explicitly, infer or default based on provider/value
            if not curr_val:
                if "Rp" in str(bal_val) or "IDR" in str(bal_val) or name in {"JASASMM", "INDOSMM"}:
                    curr_val = "IDR"
                else:
                    curr_val = "USD"
            
            # Clean up balance string
            bal_clean = str(bal_val).replace("Rp", "").replace("$", "").replace(",", "").strip()
            return {
                "status": "SUCCESS (Connected)",
                "balance": bal_clean,
                "currency": str(curr_val).upper(),
                "raw_note": "OK"
            }
        elif isinstance(data, dict) and ("error" in data or "message" in data):
            msg = data.get("error") or data.get("message") or f"HTTP {status_code}"
            return {
                "status": f"HTTP {status_code}",
                "balance": "N/A",
                "currency": "N/A",
                "raw_note": str(msg)[:45]
            }
        else:
            return {
                "status": f"HTTP {status_code}",
                "balance": "N/A",
                "currency": "N/A",
                "raw_note": str(data)[:45] if isinstance(data, str) else "Invalid JSON"
            }
    except requests.exceptions.Timeout:
        return {
            "status": "TIMEOUT (10s)",
            "balance": "N/A",
            "currency": "N/A",
            "raw_note": "Request timed out"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "CONN ERROR",
            "balance": "N/A",
            "currency": "N/A",
            "raw_note": "Failed to establish connection"
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "balance": "N/A",
            "currency": "N/A",
            "raw_note": str(exc)[:45]
        }

def run_audit() -> None:
    print("\n" + "="*96)
    print("      LIVE INFRASTRUCTURE BALANCE AUDIT ACROSS ACTIVE SMM WHOLESALER NETWORK")
    print("="*96 + "\n")

    configs = get_provider_configs()
    session = requests.Session()

    # Table Header
    print(f"{'Provider Name':<22} | {'Connection Status':<22} | {'Available Balance':<18} | {'Currency':<10} | {'Notes / Details':<18}")
    print("-" * 96)

    success_count = 0
    funded_count = 0

    for cfg in configs:
        res = audit_provider(cfg["name"], cfg["url"], cfg["api_key"], session)
        bal_str = res["balance"]
        
        # Check if funded (> 0)
        try:
            val = float(bal_str)
            if val > 0:
                funded_count += 1
        except (ValueError, TypeError):
            pass

        if "SUCCESS" in res["status"]:
            success_count += 1

        print(f"{cfg['name']:<22} | {res['status']:<22} | {bal_str:<18} | {res['currency']:<10} | {res['raw_note']:<18}")

    print("-" * 96)
    print(f"\nAudit Summary: {success_count}/{len(configs)} Panels Successfully Reached | {funded_count} Panels Live & Funded")
    print("="*96 + "\n")

if __name__ == "__main__":
    run_audit()
