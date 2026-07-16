#!/usr/bin/env python3
"""
live_catalog_price_comparison.py - Live Wholesale Catalog Price Comparison for Apple Music & Shazam across 11 Wholesalers.
"""

from __future__ import annotations

import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from dotenv import load_dotenv

IDR_TO_USD_RATE = 16200.0

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

def fetch_services(provider: dict[str, str]) -> tuple[str, list[dict[str, Any]], str]:
    name = provider["name"]
    url = provider["url"]
    api_key = provider["api_key"]
    headers = {
        "User-Agent": "NaijaBoost-Catalog-Auditor/1.0",
        "Accept": "application/json"
    }
    payload = {
        "key": api_key,
        "action": "services"
    }

    try:
        resp = requests.post(url, data=payload, headers=headers, timeout=12.0)
        if resp.status_code in {405, 404}:
            resp = requests.get(url, params=payload, headers=headers, timeout=12.0)
        
        try:
            data = resp.json()
        except Exception:
            return name, [], f"Non-JSON response (HTTP {resp.status_code})"

        if isinstance(data, list):
            return name, data, "OK"
        elif isinstance(data, dict):
            if "error" in data:
                return name, [], f"API Error: {data['error']}"
            elif "services" in data and isinstance(data["services"], list):
                return name, data["services"], "OK"
            elif "data" in data and isinstance(data["data"], list):
                return name, data["data"], "OK"
            else:
                return name, [], f"Unexpected Dict: {str(data)[:40]}"
        else:
            return name, [], "Unexpected payload structure"
    except Exception as exc:
        return name, [], f"Connection error: {str(exc)[:40]}"

def run_price_comparison() -> None:
    print("\n" + "="*112)
    print("           LIVE WHOLESALE CATALOG PRICE COMPARISON: APPLE MUSIC & SHAZAM")
    print("="*112 + "\n")

    configs = get_provider_configs()
    apple_music_matches = []
    shazam_matches = []
    provider_status = {}

    print("Concurrent fetching of /api/v2 services catalogs across 11 wholesalers...")
    with ThreadPoolExecutor(max_workers=11) as executor:
        futures = {executor.submit(fetch_services, cfg): cfg["name"] for cfg in configs}
        for future in as_completed(futures):
            pname = futures[future]
            try:
                name, services, status = future.result()
                provider_status[name] = (len(services), status)
                
                is_idr_provider = name in {"JASASMM", "INDOSMM"}
                for srv in services:
                    if not isinstance(srv, dict):
                        continue
                    sid = str(srv.get("service", srv.get("id", "")))
                    sname = str(srv.get("name", srv.get("title", "")))
                    scat = str(srv.get("category", ""))
                    full_text = f"{scat} {sname}".lower()
                    
                    if not sid or not sname:
                        continue
                    
                    raw_rate = srv.get("rate", srv.get("price", 0.0))
                    try:
                        rate_num = float(raw_rate)
                    except (ValueError, TypeError):
                        continue
                    
                    # Determine currency
                    if is_idr_provider or rate_num > 500.0:
                        currency = "IDR"
                        rate_usd = round(rate_num / IDR_TO_USD_RATE, 6)
                    else:
                        currency = "USD"
                        rate_usd = rate_num

                    match_entry = {
                        "provider": name,
                        "service_id": sid,
                        "name": sname,
                        "category": scat,
                        "raw_rate": rate_num,
                        "currency": currency,
                        "rate_usd": rate_usd,
                        "min": srv.get("min", "N/A"),
                        "max": srv.get("max", "N/A")
                    }

                    # Filter for Apple Music
                    if "apple music" in full_text or "applemusic" in full_text:
                        apple_music_matches.append(match_entry)
                    
                    # Filter for Shazam
                    if "shazam" in full_text:
                        shazam_matches.append(match_entry)

            except Exception as exc:
                provider_status[pname] = (0, f"Error: {exc}")

    print("\n--- Catalog Scan Summary ---")
    for pname, (cnt, st) in provider_status.items():
        print(f"[{pname:<20}] Services Loaded: {cnt:<6} | Status: {st}")
    print("-" * 60)

    # Sort Apple Music by USD rate
    apple_music_matches.sort(key=lambda x: x["rate_usd"])
    
    print("\n" + "="*112)
    print(" 1. APPLE MUSIC STREAMS / PLAYS WORLDWIDE (Target Project: 3,500 Streams)")
    print("="*112)
    print(f"{'Provider':<18} | {'ID':<6} | {'Rate/1k':<12} | {'Cost (3.5k)':<13} | {'Service Name / Description':<54}")
    print("-" * 112)
    if not apple_music_matches:
        print("No exact 'Apple Music' services found across currently responding panels.")
    else:
        for item in apple_music_matches:
            rate_disp = f"{item['raw_rate']:.4f} {item['currency']}" if item['currency'] == "USD" else f"{item['raw_rate']:,.0f} {item['currency']}"
            cost_35k = round(item["rate_usd"] * 3.5, 4)
            cost_disp = f"${cost_35k:.4f} USD"
            # Trim name
            name_trim = item["name"][:54]
            print(f"{item['provider']:<18} | {item['service_id']:<6} | {rate_disp:<12} | {cost_disp:<13} | {name_trim:<54}")

    # Sort Shazam by USD rate
    shazam_matches.sort(key=lambda x: x["rate_usd"])
    
    print("\n" + "="*112)
    print(" 2. SHAZAM PLAYS / STREAMS / SAVES (Target Project: 5,000 Plays)")
    print("="*112)
    print(f"{'Provider':<18} | {'ID':<6} | {'Rate/1k':<12} | {'Cost (5.0k)':<13} | {'Service Name / Description':<54}")
    print("-" * 112)
    if not shazam_matches:
        print("No exact 'Shazam' services found across currently responding panels.")
    else:
        for item in shazam_matches:
            rate_disp = f"{item['raw_rate']:.4f} {item['currency']}" if item['currency'] == "USD" else f"{item['raw_rate']:,.0f} {item['currency']}"
            cost_5k = round(item["rate_usd"] * 5.0, 4)
            cost_disp = f"${cost_5k:.4f} USD"
            name_trim = item["name"][:54]
            print(f"{item['provider']:<18} | {item['service_id']:<6} | {rate_disp:<12} | {cost_disp:<13} | {name_trim:<54}")

    print("="*112 + "\n")

if __name__ == "__main__":
    run_price_comparison()
