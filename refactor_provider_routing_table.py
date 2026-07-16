#!/usr/bin/env python3
"""
refactor_provider_routing_table.py - Refactor Provider Routing Table into Multi-Tier Fallback Architecture.
Option A (Direct Source): 5 Core Wholesalers (is_active=1)
Option B/C (Reseller Cache): Legacy panels (is_active=0, priority_weight=0.1)
"""

from __future__ import annotations

import sqlite3

def refactor_routing_table() -> None:
    print("\n" + "=" * 104)
    print("      REFACTORING PROVIDER ROUTING TABLE: MULTI-TIER FALLBACK ARCHITECTURE")
    print("=" * 104 + "\n")

    db_path = "mtp_campaigns.db"

    option_a_providers = {
        "smmmain": ("https://smmmain.com/api/v2", 1.0),
        "smmkings": ("https://smmkings.com/api/v2", 0.9),
        "bulqfollowers": ("https://bulqfollowers.com/api/v2", 0.9),
        "secser": ("https://secser.com/api/v2", 0.85),
        "justanotherpanel": ("https://justanotherpanel.com/api/v2", 0.8),
    }

    legacy_reseller_providers = {
        "morethanpanel": "https://morethanpanel.com/api/v2",
        "mtp": "https://morethanpanel.com/api/v2",
        "godsmm": "https://godsmm.com/api/v2",
        "nicesmmpanel": "https://nicesmmpanel.com/api/v2",
        "prm4u": "https://prm4u.com/api/v2",
        "peakerrsmm": "https://peakerr.com/api/v2",
        "peakerr": "https://peakerr.com/api/v2",
        "yoyomedia": "https://yoyomedia.com/api/v2",
        "owlet": "https://owlet.com/api/v2",
        "likes_ng": "https://likes.ng/api/v2",
        "likesng": "https://likes.ng/api/v2",
        "jasasmm": "https://jasasmm.com/api/v2",
        "indosmm": "https://indosmm.co.id/api/v2",
        "instantfans": "https://instantfans.com/api/v2",
    }

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()

        # Step 1: Re-verify provider_routes table schema
        print(">>> STEP 1: Verifying `provider_routes` Table Schema...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS provider_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT UNIQUE NOT NULL,
                tier TEXT NOT NULL,
                api_endpoint TEXT NOT NULL,
                supports_drip_feed BOOLEAN NOT NULL DEFAULT 1,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                priority_weight REAL NOT NULL DEFAULT 0.5
            )
        """)

        # Step 2: Update 5 Core Wholesalers explicitly to Tier = 'Option A (Direct Source)' and set is_active = 1
        print(">>> STEP 2: Updating 5 Core Wholesalers to `Option A (Direct Source)` (is_active = 1)...")
        for pid, (url, weight) in option_a_providers.items():
            cur.execute("""
                INSERT INTO provider_routes (provider_id, tier, api_endpoint, supports_drip_feed, is_active, priority_weight)
                VALUES (?, ?, ?, 1, 1, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    tier = 'Option A (Direct Source)',
                    api_endpoint = excluded.api_endpoint,
                    is_active = 1,
                    priority_weight = excluded.priority_weight
            """, (pid, "Option A (Direct Source)", url, weight))

        # Step 3: Add/update legacy panels to Tier = 'Option B/C (Reseller Cache)', is_active = 0, priority_weight = 0.1
        print(">>> STEP 3: Updating Legacy & Reseller Panels to `Option B/C (Reseller Cache)` (is_active = 0, weight = 0.1)...")
        for pid, url in legacy_reseller_providers.items():
            cur.execute("""
                INSERT INTO provider_routes (provider_id, tier, api_endpoint, supports_drip_feed, is_active, priority_weight)
                VALUES (?, 'Option B/C (Reseller Cache)', ?, 1, 0, 0.1)
                ON CONFLICT(provider_id) DO UPDATE SET
                    tier = 'Option B/C (Reseller Cache)',
                    api_endpoint = excluded.api_endpoint,
                    is_active = 0,
                    priority_weight = 0.1
            """, (pid, url))

        # Also make sure any other provider currently in provider_routes not in Option A is updated to Option B/C
        cur.execute("""
            UPDATE provider_routes
            SET tier = 'Option B/C (Reseller Cache)', is_active = 0, priority_weight = 0.1
            WHERE provider_id NOT IN ('smmmain', 'smmkings', 'bulqfollowers', 'secser', 'justanotherpanel')
        """)

        conn.commit()

        # Step 4: Display complete, newly organized Provider Routing Table directly to console
        print(">>> STEP 4: Complete Multi-Tier Provider Routing Table Verification Audit...\n")
        rows = cur.execute("""
            SELECT id, provider_id, tier, is_active, priority_weight, api_endpoint
            FROM provider_routes
            ORDER BY is_active DESC, priority_weight DESC, provider_id ASC
        """).fetchall()

        print(f"{'ID':<4} | {'Provider ID':<18} | {'Tier Architecture':<30} | {'Active':<8} | {'Weight':<8} | {'API Endpoint'}")
        print("-" * 104)
        for r in rows:
            active_str = "YES (1)" if r[3] else "NO (0)"
            print(f"{r[0]:<4} | {r[1]:<18} | {r[2]:<30} | {active_str:<8} | {r[4]:<8.2f} | {r[5]}")

    print("\n" + "=" * 104)
    print("               PROVIDER ROUTING TABLE REFACTORING COMPLETE")
    print("=" * 104 + "\n")

if __name__ == "__main__":
    refactor_routing_table()
