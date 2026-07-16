"""
Paystack Live Production Payment Gateway Service (`services/payment_gateway.py`).

Handles official initialization of live checkout URLs via Paystack (`https://api.paystack.co/transaction/initialize`),
HMAC SHA-512 webhook verification, and transaction verification against `.env` live credentials.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PaystackGateway:
    """Production client for Paystack API checkout initialization and webhook verification."""

    INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"
    VERIFY_URL = "https://api.paystack.co/transaction/verify/{reference}"

    def __init__(self, secret_key: Optional[str] = None, public_key: Optional[str] = None) -> None:
        self.secret_key = secret_key or os.environ.get("PAYSTACK_SECRET_KEY", "")
        self.public_key = public_key or os.environ.get("PAYSTACK_PUBLIC_KEY", "")

    def initialize_transaction(
        self,
        user_id: str,
        amount_ngn: float,
        email: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiate an official API request to Paystack's initialize endpoint (`https://api.paystack.co/transaction/initialize`)
        to generate a real live payment authorization URL.
        """
        if amount_ngn <= 0:
            raise ValueError("Amount in NGN must be greater than zero.")
        if not self.secret_key:
            logger.warning("PAYSTACK_SECRET_KEY is missing from environment or .env file.")

        reference = f"PYS_LIVE_{uuid.uuid4().hex[:12].upper()}"
        amount_kobo = int(round(amount_ngn * 100))
        target_email = email or f"{user_id.lower().replace(' ', '_')}@naijaboost.ai"

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "email": target_email,
            "amount": amount_kobo,
            "reference": reference,
            "callback_url": callback_url or "http://127.0.0.1:8080/?payment=success",
            "metadata": {
                "user_id": user_id,
                "amount_ngn": amount_ngn,
                "integration": "NaijaBoost_Live_Production",
            },
        }

        logger.info(f"Initiating live Paystack transaction for user '{user_id}' with reference '{reference}' ({amount_ngn} NGN)...")
        try:
            response = requests.post(self.INITIALIZE_URL, headers=headers, json=payload, timeout=15)
            data = response.json() if response.text else {}
            if response.status_code in (200, 201) and data.get("status") is True:
                auth_data = data.get("data", {})
                return {
                    "status": "success",
                    "reference": auth_data.get("reference", reference),
                    "authorization_url": auth_data.get("authorization_url"),
                    "access_code": auth_data.get("access_code"),
                    "message": data.get("message", "Authorization URL created successfully"),
                }
            else:
                err_msg = data.get("message", f"Paystack API error status {response.status_code}")
                logger.error(f"Paystack initialization failed: {err_msg} | Body: {response.text}")
                return {
                    "status": "error",
                    "message": err_msg,
                    "raw_response": data,
                }
        except Exception as exc:
            logger.exception(f"Exception calling Paystack initialize endpoint for user '{user_id}': {exc}")
            return {
                "status": "error",
                "message": f"Network error connecting to Paystack gateway: {exc}",
            }

    def verify_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verify HMAC SHA-512 signature sent by Paystack webhook."""
        if not self.secret_key or not signature_header:
            return False
        computed_hmac = hmac.new(self.secret_key.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed_hmac, signature_header)

    def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """Verify a transaction reference directly against Paystack API (`https://api.paystack.co/transaction/verify/{reference}`)."""
        if not reference:
            raise ValueError("Reference is required for transaction verification.")
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        url = self.VERIFY_URL.format(reference=reference)
        try:
            response = requests.get(url, headers=headers, timeout=15)
            data = response.json() if response.text else {}
            if response.status_code == 200 and data.get("status") is True:
                return {"status": "success", "data": data.get("data", {})}
            return {"status": "error", "message": data.get("message", "Verification failed"), "data": data}
        except Exception as exc:
            logger.exception(f"Error verifying Paystack transaction '{reference}': {exc}")
            return {"status": "error", "message": str(exc)}
