"""
wallet_engine.py - Local Payment & Wallet Engine Integration for NaijaBoost AI.

Provides:
- Dynamic USD/NGN exchange rate fetching with configurable fallback rate.
- `credit_wallet(user_id, amount_ngn, gateway_ref)`: Local deposit verification/simulation.
- `deduct_order_cost(user_id, cost_usd)`: Atomic balance verification and deduction.
- Atomic SQLite transactions updating `user_wallets` and `wallet_transactions` tables.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from services.smm_partners.base import InsufficientFundsError

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_RATE: float = 1500.0


def get_db_path() -> Path:
    """Resolve the location of mtp_campaigns.db."""
    local_db = Path("mtp_campaigns.db")
    if local_db.exists():
        return local_db
    desktop_db = Path("/Users/mac/Desktop/MTP_Matrix_Engine_v1.txt/mtp_campaigns.db")
    if desktop_db.exists():
        return desktop_db
    return local_db


class WalletEngine:
    """
    Core Wallet & Exchange Engine managing multi-currency (NGN/USD) balances,
    deposits, dynamic FX conversions, and atomic order deductions.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        fallback_rate: float = DEFAULT_FALLBACK_RATE,
        timeout: float = 4.0,
    ) -> None:
        self.db_path = db_path or get_db_path()
        try:
            env_rate = os.getenv("FALLBACK_USD_NGN_RATE")
            self.fallback_rate = float(env_rate) if env_rate else fallback_rate
        except (ValueError, TypeError):
            self.fallback_rate = fallback_rate
        self.timeout = timeout
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensure `user_wallets` and `wallet_transactions` tables exist."""
        if not self.db_path.exists():
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_wallets (
                        user_id TEXT PRIMARY KEY,
                        balance_ngn REAL NOT NULL DEFAULT 0.0,
                        balance_usd REAL NOT NULL DEFAULT 0.0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wallet_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        transaction_id TEXT UNIQUE NOT NULL,
                        user_id TEXT NOT NULL,
                        amount_ngn REAL NOT NULL,
                        amount_usd REAL NOT NULL,
                        exchange_rate REAL NOT NULL,
                        gateway TEXT NOT NULL,
                        type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user_wallets(user_id)
                    );
                    """
                )
        except Exception as exc:
            logger.exception(f"Error ensuring wallet tables in {self.db_path}: {exc}")

    def get_exchange_rate(self) -> float:
        """
        Fetch dynamic USD/NGN exchange rate from live rate API.
        Falls back to configurable fallback rate (default 1,500 NGN/USD) on network/API failure.
        """
        urls = [
            "https://open.er-api.com/v6/latest/USD",
            "https://api.exchangerate-api.com/v4/latest/USD",
        ]
        for url in urls:
            try:
                resp = requests.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    rates = data.get("rates", {})
                    ngn_rate = rates.get("NGN")
                    if ngn_rate and isinstance(ngn_rate, (int, float)) and ngn_rate > 0:
                        logger.debug(f"Fetched live USD/NGN rate: {ngn_rate} from {url}")
                        return float(ngn_rate)
            except Exception as exc:
                logger.debug(f"Could not fetch rate from {url}: {exc}")
        
        logger.debug(f"Using fallback USD/NGN rate: {self.fallback_rate}")
        return self.fallback_rate

    def get_wallet_balance(self, user_id: str) -> Dict[str, Any]:
        """Retrieve current wallet balance for `user_id`."""
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        if not self.db_path.exists():
            return {"user_id": user_id, "balance_ngn": 0.0, "balance_usd": 0.0}

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance_ngn, balance_usd FROM user_wallets WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return {"user_id": user_id, "balance_ngn": float(row[0]), "balance_usd": float(row[1])}
        return {"user_id": user_id, "balance_ngn": 0.0, "balance_usd": 0.0}

    def credit_wallet(
        self,
        user_id: str,
        amount_ngn: float,
        gateway_ref: str,
        gateway: str = "paystack",
    ) -> Dict[str, Any]:
        """
        Simulate/verify local deposit webhook (Paystack/Flutterwave), credit `balance_ngn`,
        and calculate USD equivalent using dynamic exchange rate.
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id must be provided.")
        if not gateway_ref or not gateway_ref.strip():
            raise ValueError("gateway_ref must be provided.")
        if amount_ngn <= 0:
            raise ValueError("amount_ngn must be greater than zero.")

        if not self.db_path.exists():
            raise RuntimeError(f"Database not found at {self.db_path}")

        exchange_rate = self.get_exchange_rate()
        amount_usd = round(amount_ngn / exchange_rate, 4)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Check if transaction already processed (idempotency)
            cursor.execute("SELECT id FROM wallet_transactions WHERE transaction_id = ?", (gateway_ref,))
            if cursor.fetchone():
                logger.warning(f"Transaction '{gateway_ref}' already processed.")
                # Return existing balance
                cursor.execute("SELECT balance_ngn, balance_usd FROM user_wallets WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return {
                    "user_id": user_id,
                    "balance_ngn": float(row[0]) if row else 0.0,
                    "balance_usd": float(row[1]) if row else 0.0,
                    "transaction_id": gateway_ref,
                    "exchange_rate": exchange_rate,
                    "status": "already_processed",
                }

            # Upsert wallet balance
            cursor.execute("SELECT balance_ngn, balance_usd FROM user_wallets WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                new_ngn = round(float(row[0]) + amount_ngn, 2)
                new_usd = round(float(row[1]) + amount_usd, 4)
                cursor.execute(
                    "UPDATE user_wallets SET balance_ngn = ?, balance_usd = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (new_ngn, new_usd, user_id),
                )
            else:
                new_ngn = round(amount_ngn, 2)
                new_usd = amount_usd
                cursor.execute(
                    "INSERT INTO user_wallets (user_id, balance_ngn, balance_usd, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (user_id, new_ngn, new_usd),
                )

            # Record transaction
            cursor.execute(
                """
                INSERT INTO wallet_transactions (
                    transaction_id, user_id, amount_ngn, amount_usd, exchange_rate, gateway, type, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'deposit', 'success', CURRENT_TIMESTAMP)
                """,
                (gateway_ref, user_id, amount_ngn, amount_usd, exchange_rate, gateway),
            )
            conn.commit()

        logger.info(
            f"Credited wallet for user '{user_id}': +{amount_ngn:,.2f} NGN (+${amount_usd:,.2f} USD) via {gateway} ({gateway_ref})"
        )
        return {
            "user_id": user_id,
            "balance_ngn": new_ngn,
            "balance_usd": new_usd,
            "transaction_id": gateway_ref,
            "exchange_rate": exchange_rate,
            "status": "success",
        }

    def deduct_order_cost(
        self,
        user_id: str,
        cost_usd: float,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert wholesale order USD cost into NGN, verify sufficient wallet funds,
        and atomically deduct the balance.
        Raises InsufficientFundsError if balance is too low.
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id must be provided.")
        if cost_usd <= 0:
            raise ValueError("cost_usd must be greater than zero.")

        if not self.db_path.exists():
            raise RuntimeError(f"Database not found at {self.db_path}")

        exchange_rate = self.get_exchange_rate()
        cost_ngn = round(cost_usd * exchange_rate, 2)
        txn_ref = transaction_id or f"ORDER_DEDUCT_{uuid.uuid4().hex[:14].upper()}"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Begin atomic check-and-deduct
            cursor.execute("SELECT balance_ngn, balance_usd FROM user_wallets WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            current_ngn = float(row[0]) if row else 0.0
            current_usd = float(row[1]) if row else 0.0

            # Check if sufficient NGN balance (with tiny 1e-4 tolerance for floating point rounding)
            if not row or current_ngn < (cost_ngn - 1e-4):
                deficit_ngn = cost_ngn - current_ngn
                logger.warning(
                    f"Insufficient funds for user '{user_id}'. Required: {cost_ngn:,.2f} NGN (${cost_usd:,.2f} USD). "
                    f"Current: {current_ngn:,.2f} NGN. Deficit: {deficit_ngn:,.2f} NGN."
                )
                raise InsufficientFundsError(
                    f"Insufficient funds in user wallet '{user_id}'. Required: NGN {cost_ngn:,.2f} (${cost_usd:,.2f} USD). "
                    f"Current Balance: NGN {current_ngn:,.2f}."
                )

            new_ngn = round(current_ngn - cost_ngn, 2)
            new_usd = round(max(0.0, current_usd - cost_usd), 4)

            cursor.execute(
                "UPDATE user_wallets SET balance_ngn = ?, balance_usd = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (new_ngn, new_usd, user_id),
            )

            # Record deduction in transaction table
            cursor.execute(
                """
                INSERT INTO wallet_transactions (
                    transaction_id, user_id, amount_ngn, amount_usd, exchange_rate, gateway, type, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'system', 'deduction', 'success', CURRENT_TIMESTAMP)
                """,
                (txn_ref, user_id, -cost_ngn, -cost_usd, exchange_rate),
            )
            conn.commit()

        logger.info(
            f"Atomically deducted order cost for user '{user_id}': -{cost_ngn:,.2f} NGN (-${cost_usd:,.2f} USD). "
            f"New Balance: {new_ngn:,.2f} NGN ({txn_ref})"
        )
        return {
            "user_id": user_id,
            "deducted_ngn": cost_ngn,
            "deducted_usd": cost_usd,
            "exchange_rate": exchange_rate,
            "new_balance_ngn": new_ngn,
            "new_balance_usd": new_usd,
            "transaction_id": txn_ref,
            "status": "success",
        }
