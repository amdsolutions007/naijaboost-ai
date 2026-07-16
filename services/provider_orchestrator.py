"""
provider_orchestrator.py - Provider Fulfillment Orchestrator for NaijaBoost AI.

Orchestrates automated connection mapping, balance checking, and order forwarding
for all Category A SMM wholesale providers, with MoreThanPanel (MTP) integrated
as our primary fulfillment provider.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Mapping, Optional

import requests
from dotenv import load_dotenv

from services.smm_partners.base import BaseSMMClient, InsufficientFundsError, SMMServiceError
from services.smm_partners.godsmm_client import GodSMMClient
from services.smm_partners.indosmm_client import IndoSMMClient
from services.smm_partners.instantfans_client import InstantFansClient
from services.smm_partners.jap_client import JustAnotherPanelClient
from services.smm_partners.jasasmm_client import JasaSMMClient
from services.smm_partners.likesng_client import LikesNgClient
from services.smm_partners.mtp_client import MoreThanPanelClient
from services.smm_partners.nicesmmpanel_client import NiceSMMPanelClient
from services.smm_partners.owlet_client import OwletClient
from services.smm_partners.peakerr_client import PeakerrClient
from services.smm_partners.prm4u_client import PRM4UClient
from services.smm_partners.smmkings_client import SMMKingsClient
from services.smm_partners.smmmain_client import SMMMainClient
from services.smm_partners.yoyomedia_client import YoYoMediaClient

logger = logging.getLogger(__name__)

# Ensure .env is loaded when provider orchestrator initializes
load_dotenv()


class ProviderOrchestrator:
    """
    Orchestrates connection mapping, balance queries, and order forwarding across
    our Category A fulfillment network. MoreThanPanel (MTP) serves as the primary
    fulfillment provider endpoint, with JasaSMM, IndoSMM, GodSMM, SMMMain, SMMKings, JustAnotherPanel, Instant-Fans, NiceSMMPanel, YoYoMedia, and Peakerr as our secondary fulfillment providers.
    """

    DEFAULT_FALLBACK_IDR_RATE: float = 16200.0

    def __init__(self) -> None:
        load_dotenv()
        self.mtp_api_key = os.getenv("MTP_API_KEY", "51139ff558f02990c1daf3f9a5a23da9")
        self.mtp_provider_url = os.getenv("MTP_PROVIDER_URL", "https://morethanpanel.com/api/v2")
        self.jasasmm_api_key = os.getenv("JASASMM_API_KEY", "3ce3b8e2059ec5cc97fcb38ce8770fcd")
        self.jasasmm_provider_url = os.getenv("JASASMM_PROVIDER_URL", "https://jasasmm.com/api/v2")
        self.indosmm_api_key = os.getenv("INDOSMM_API_KEY", "5cdf4a20b7c58227f05d14c09efbca81")
        self.indosmm_provider_url = os.getenv("INDOSMM_PROVIDER_URL", "https://indosmm.id/api/v2")
        self.godsmm_api_key = os.getenv("GODSMM_API_KEY", "054533776b26d195c82dc31d731fe1517c90f81c5944f7cb9e917504a7a7d12e")
        self.godsmm_provider_url = os.getenv("GODSMM_PROVIDER_URL", "https://godsmm.com/api/v2")
        self.smmmain_api_key = os.getenv("SMMMAIN_API_KEY", "76e212495c47d38e08cc8991299fc6ac")
        self.smmmain_provider_url = os.getenv("SMMMAIN_PROVIDER_URL", "https://smmmain.com/api/v2")
        self.smmkings_api_key = os.getenv("SMMKINGS_API_KEY", "5802d5c9b5c03272de5c507b6de36a6c")
        self.smmkings_provider_url = os.getenv("SMMKINGS_PROVIDER_URL", "https://smmkings.com/api/v2")
        self.justanotherpanel_api_key = os.getenv("JUSTANOTHERPANEL_API_KEY", "e3348e1236ab3106f67cb7a21b5f0eb5")
        self.justanotherpanel_provider_url = os.getenv("JUSTANOTHERPANEL_PROVIDER_URL", "https://justanotherpanel.com/api/v2")
        self.instantfans_api_key = os.getenv("INSTANTFANS_API_KEY", "18f616085df9edde3111887f09c72f59")
        self.instantfans_provider_url = os.getenv("INSTANTFANS_PROVIDER_URL", "https://instant-fans.com/api/v2")
        self.nicesmmpanel_api_key = os.getenv("NICESMMPANEL_API_KEY", "aaf66ec1cec36e5030a9f2daa48fb6ea")
        self.nicesmmpanel_provider_url = os.getenv("NICESMMPANEL_PROVIDER_URL", "https://nicesmmpanel.com/api/v2")
        self.yoyomedia_api_key = os.getenv("YOYOMEDIA_API_KEY", "6e6e26efb489ee38ed8228d159aff57d5e5d885fbc8792195a9ba220dd6c21a5")
        self.yoyomedia_provider_url = os.getenv("YOYOMEDIA_PROVIDER_URL", "https://yoyomedia.com/api/v2")
        self.peakerr_api_key = os.getenv("PEAKERR_API_KEY", "f974254175d766a4d0611241dfa8952e")
        self.peakerr_provider_url = os.getenv("PEAKERR_PROVIDER_URL", "https://peakerr.com/api/v2")
        self.likesng_api_key = os.getenv("LIKESNG_API_KEY", os.getenv("MTP_API_KEY", self.mtp_api_key))
        self.likesng_provider_url = os.getenv("LIKESNG_PROVIDER_URL", "https://likes.ng/api/v2")
        self.owlet_api_key = os.getenv("OWLET_API_KEY", os.getenv("MTP_API_KEY", self.mtp_api_key))
        self.owlet_provider_url = os.getenv("OWLET_PROVIDER_URL", "https://theowlet.com/api/v2")
        try:
            env_idr = os.getenv("FALLBACK_USD_IDR_RATE")
            self.fallback_idr_rate = float(env_idr) if env_idr else self.DEFAULT_FALLBACK_IDR_RATE
        except (ValueError, TypeError):
            self.fallback_idr_rate = self.DEFAULT_FALLBACK_IDR_RATE

    @staticmethod
    def _parse_raw_balance(val: Any) -> float:
        """Cleanly strip currency symbols (Rp, $, IDR, USD) and commas to extract numeric balance."""
        if isinstance(val, (int, float)):
            return float(val)
        if not isinstance(val, str):
            return 0.0
        clean = (
            val.replace("Rp", "")
            .replace("IDR", "")
            .replace("$", "")
            .replace("USD", "")
            .replace(",", "")
            .strip()
        )
        try:
            return float(clean)
        except (ValueError, TypeError):
            return 0.0

    def get_idr_usd_rate(self) -> float:
        """Fetch dynamic USD to IDR exchange rate, falling back to clean configured IDR/USD rate if unreachable."""
        urls = [
            "https://open.er-api.com/v6/latest/USD",
            "https://api.exchangerate-api.com/v4/latest/USD",
        ]
        for url in urls:
            try:
                resp = requests.get(url, timeout=3.0)
                if resp.status_code == 200:
                    data = resp.json()
                    rates = data.get("rates", {})
                    rate_idr = rates.get("IDR")
                    if isinstance(rate_idr, (int, float)) and rate_idr > 0:
                        return float(rate_idr)
            except Exception as exc:
                logger.debug(f"Transient error fetching USD/IDR rate from {url}: {exc}")
        return self.fallback_idr_rate

    def get_provider_client(self, provider_id: str = "mtp", session: Optional[Any] = None) -> BaseSMMClient:
        """
        Map a provider_id string to the corresponding concrete SMM client instance.
        Routes to primary fulfillment provider MTP or secondary backup providers JasaSMM / IndoSMM / GodSMM / SMMMain / SMMKings / JustAnotherPanel / Instant-Fans / NiceSMMPanel / YoYoMedia / Peakerr.
        """
        load_dotenv()
        pid = (provider_id or "mtp").strip().lower()

        if pid in ("mtp", "morethanpanel"):
            api_key = os.getenv("MTP_API_KEY", self.mtp_api_key)
            provider_url = os.getenv("MTP_PROVIDER_URL", self.mtp_provider_url)
            return MoreThanPanelClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("jasasmm", "jasa"):
            api_key = os.getenv("JASASMM_API_KEY", self.jasasmm_api_key)
            provider_url = os.getenv("JASASMM_PROVIDER_URL", self.jasasmm_provider_url)
            return JasaSMMClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("indosmm", "indo"):
            api_key = os.getenv("INDOSMM_API_KEY", self.indosmm_api_key)
            provider_url = os.getenv("INDOSMM_PROVIDER_URL", self.indosmm_provider_url)
            return IndoSMMClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("godsmm", "god"):
            api_key = os.getenv("GODSMM_API_KEY", self.godsmm_api_key)
            provider_url = os.getenv("GODSMM_PROVIDER_URL", self.godsmm_provider_url)
            return GodSMMClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("smmmain", "smm_main"):
            api_key = os.getenv("SMMMAIN_API_KEY", self.smmmain_api_key)
            provider_url = os.getenv("SMMMAIN_PROVIDER_URL", self.smmmain_provider_url)
            return SMMMainClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("smmkings", "smm_kings"):
            api_key = os.getenv("SMMKINGS_API_KEY", self.smmkings_api_key)
            provider_url = os.getenv("SMMKINGS_PROVIDER_URL", self.smmkings_provider_url)
            return SMMKingsClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("justanotherpanel", "jap"):
            api_key = os.getenv("JUSTANOTHERPANEL_API_KEY", self.justanotherpanel_api_key)
            provider_url = os.getenv("JUSTANOTHERPANEL_PROVIDER_URL", self.justanotherpanel_provider_url)
            return JustAnotherPanelClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("instantfans", "instant-fans"):
            api_key = os.getenv("INSTANTFANS_API_KEY", self.instantfans_api_key)
            provider_url = os.getenv("INSTANTFANS_PROVIDER_URL", self.instantfans_provider_url)
            return InstantFansClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("nicesmmpanel", "nicesmm"):
            api_key = os.getenv("NICESMMPANEL_API_KEY", self.nicesmmpanel_api_key)
            provider_url = os.getenv("NICESMMPANEL_PROVIDER_URL", self.nicesmmpanel_provider_url)
            return NiceSMMPanelClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("yoyomedia", "yoyo"):
            api_key = os.getenv("YOYOMEDIA_API_KEY", os.getenv("YOYO_API_KEY", self.yoyomedia_api_key))
            provider_url = os.getenv("YOYOMEDIA_PROVIDER_URL", os.getenv("YOYO_PROVIDER_URL", self.yoyomedia_provider_url))
            return YoYoMediaClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("peakerr", "peakerrsmm"):
            api_key = os.getenv("PEAKERR_API_KEY", self.peakerr_api_key)
            provider_url = os.getenv("PEAKERR_PROVIDER_URL", self.peakerr_provider_url)
            return PeakerrClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid == "prm4u":
            api_key = os.getenv("PRM4U_API_KEY", os.getenv("MTP_API_KEY", self.mtp_api_key))
            provider_url = os.getenv("PRM4U_PROVIDER_URL", "https://prm4u.com/api/v2")
            return PRM4UClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("likesng", "likes.ng", "likes_ng"):
            api_key = os.getenv("LIKESNG_API_KEY", self.likesng_api_key)
            provider_url = os.getenv("LIKESNG_PROVIDER_URL", self.likesng_provider_url)
            return LikesNgClient(base_url=provider_url, api_key=api_key, session=session)

        elif pid in ("owlet", "theowlet", "owletsmm"):
            api_key = os.getenv("OWLET_API_KEY", self.owlet_api_key)
            provider_url = os.getenv("OWLET_PROVIDER_URL", self.owlet_provider_url)
            return OwletClient(base_url=provider_url, api_key=api_key, session=session)

        else:
            # For Category A Wholesalers ('smmmain', 'smmkings', 'bulqfollowers', 'secser', 'justanotherpanel')
            # Check if explicit specific env var is defined (e.g. SMMMAIN_API_KEY / SMMMAIN_PROVIDER_URL)
            # Otherwise fall back cleanly to primary fulfillment provider MoreThanPanel (MTP)
            env_prefix = pid.upper()
            specific_key = os.getenv(f"{env_prefix}_API_KEY")
            specific_url = os.getenv(f"{env_prefix}_PROVIDER_URL")
            if specific_key and specific_url:
                return MoreThanPanelClient(base_url=specific_url, api_key=specific_key, session=session)

            # Primary fulfillment fallback to MoreThanPanel (MTP)
            api_key = os.getenv("MTP_API_KEY", self.mtp_api_key)
            provider_url = os.getenv("MTP_PROVIDER_URL", self.mtp_provider_url)
            return MoreThanPanelClient(base_url=provider_url, api_key=api_key, session=session)

    def check_provider_balance(self, provider_id: str = "mtp", session: Optional[Any] = None) -> Dict[str, Any]:
        """Look up current balance from the mapped SMM provider API endpoint with currency rate conversion."""
        pid = (provider_id or "mtp").strip().lower()
        client = self.get_provider_client(pid, session=session)
        try:
            res = client.get_balance()
            if isinstance(res, Mapping):
                raw_bal = res.get("balance", 0.0)
                raw_curr = str(res.get("currency", "") if res.get("currency") is not None else "").strip().upper()
                native_balance = self._parse_raw_balance(raw_bal)

                # Determine whether response is Indonesian IDR (either via currency code or 'Rp' in raw string)
                is_idr = (
                    raw_curr in ("IDR", "RP")
                    or (isinstance(raw_bal, str) and "RP" in raw_bal.upper())
                    or pid in ("jasasmm", "jasa", "indosmm", "indo")
                )
                if not raw_curr:
                    raw_curr = "IDR" if is_idr else "USD"

                if is_idr or raw_curr == "IDR":
                    idr_rate = self.get_idr_usd_rate()
                    balance_usd = round(native_balance / idr_rate, 6) if idr_rate > 0 else 0.0
                else:
                    balance_usd = native_balance

                return {
                    "provider_id": pid,
                    "status": "success",
                    "balance": balance_usd,
                    "balance_usd": balance_usd,
                    "balance_native": native_balance,
                    "currency": raw_curr,
                    "raw": dict(res),
                }
            return {
                "provider_id": pid,
                "status": "success",
                "balance": 0.0,
                "balance_usd": 0.0,
                "balance_native": 0.0,
                "currency": "USD" if pid not in ("jasasmm", "jasa", "indosmm", "indo") else "IDR",
                "raw": res,
            }
        except Exception as exc:
            logger.exception(f"Failed to fetch balance for provider '{pid}'")
            return {
                "provider_id": pid,
                "status": "error",
                "error": str(exc),
            }

    def forward_order_to_provider(
        self,
        service_id: str,
        quantity: int,
        target_url: str,
        provider_id: str = "mtp",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Forward incoming client order automatically to the mapped fulfillment endpoint."""
        client = self.get_provider_client(provider_id)
        try:
            order_res = client.create_order(
                service_id=str(service_id),
                quantity=int(quantity),
                link=target_url,
                **kwargs,
            )
            order_id = ""
            if isinstance(order_res, Mapping):
                order_id = str(order_res.get("order", order_res.get("order_id", "")))
            return {
                "provider_id": provider_id,
                "status": "success",
                "order_id": order_id,
                "raw": dict(order_res) if isinstance(order_res, Mapping) else order_res,
            }
        except InsufficientFundsError as exc:
            logger.warning(f"Provider '{provider_id}' reported insufficient wholesale funds: {exc}")
            return {
                "provider_id": provider_id,
                "status": "error",
                "error_code": "PROVIDER_INSUFFICIENT_FUNDS",
                "error": str(exc),
            }
        except Exception as exc:
            logger.exception(f"Order submission failed for provider '{provider_id}'")
            return {
                "provider_id": provider_id,
                "status": "error",
                "error_code": "PROVIDER_ORDER_FAILED",
                "error": str(exc),
            }
