"""
ai_brain_orchestrator.py - Dual-Brain AI Automation Layer for NaijaBoost AI.

Orchestrates a dual-client parser combining:
1. Google AI Engine (Gemini via `google-generativeai`):
   Processes multilingual user prompts (English, Pidgin, Yoruba, Hausa, Igbo) and extracts broad context, platform goals, and localized nuances.
2. OpenAI Engine (GPT-4o/Mini via `openai`):
   Takes the parsed context and outputs a strictly validated JSON payload matching the ServicePlan schema:
   {"service_type": str, "quantity": int, "target_url": str, "drip_feed": bool, "delivery_rate": int, "recommended_provider": str}.
3. Safety & Drip-Feed Validation:
   Integrates `validate_drip_feed_rate` from `smm_logic_engine.py` to enforce safety bounds (100 - 1,000 units/hr).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from smm_logic_engine import validate_drip_feed_rate, DeliveryRateValidationError

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import openai
    from openai import OpenAI
except ImportError:
    openai = None
    OpenAI = None


@dataclass
class ParsedServicePlan:
    service_type: str
    quantity: int
    target_url: str
    drip_feed: bool
    delivery_rate: int
    recommended_provider: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_type": self.service_type,
            "quantity": self.quantity,
            "target_url": self.target_url,
            "drip_feed": self.drip_feed,
            "delivery_rate": self.delivery_rate,
            "recommended_provider": self.recommended_provider,
        }


class DualBrainOrchestrator:
    """
    Dual-Brain AI Orchestrator combining Gemini (Context & Multilingual Parsing)
    and OpenAI (Strict JSON ServicePlan Generation & Provider Selection).
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.5-pro",
        openai_model: str = "gpt-4o-mini",
    ) -> None:
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.gemini_model_name = gemini_model
        self.openai_model_name = openai_model

        if genai and self.gemini_api_key:
            try:
                genai.configure(api_key=self.gemini_api_key)
            except Exception as exc:
                logger.warning(f"Could not configure Gemini API: {exc}")

        self._openai_client: Optional[Any] = None
        if OpenAI and self.openai_api_key:
            try:
                self._openai_client = OpenAI(api_key=self.openai_api_key)
            except Exception as exc:
                logger.warning(f"Could not initialize OpenAI client: {exc}")

    def process_prompt(
        self,
        prompt: str,
        language: str = "English",
        available_providers: Optional[List[Dict[str, Any]]] = None,
    ) -> ParsedServicePlan:
        """
        Process the user prompt through the Dual-Brain layer:
        Step 1 (Gemini): Multilingual analysis & intent recognition.
        Step 2 (OpenAI): Strict JSON payload generation according to ServicePlan schema.
        Step 3: Safety validation (`validate_drip_feed_rate`) & fallback standardization.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        # Step 1: Google AI Engine (Gemini) Context Extraction
        context_summary = self._run_gemini_brain(prompt, language)

        # Step 2: OpenAI Engine (GPT-4o/Mini) JSON Payload Generation
        raw_plan = self._run_openai_brain(prompt, language, context_summary, available_providers)

        # Step 3: Safety Validation & Enforced Drip-Feed Bounds
        validated_plan = self._validate_and_normalize_plan(raw_plan, available_providers)
        return validated_plan

    def _run_gemini_brain(self, prompt: str, language: str) -> str:
        """
        Google AI Engine (Gemini): Processes multilingual user text/prompt and extracts
        broad context, platform goals, and localized nuances.
        """
        if genai and self.gemini_api_key:
            try:
                model = genai.GenerativeModel(self.gemini_model_name)
                gemini_prompt = (
                    f"Analyze this request for NaijaBoost AI in {language}.\n"
                    f"User Prompt: '{prompt}'\n"
                    f"Extract broad context, platform goals (e.g. YouTube watch time, music streams, Instagram followers), "
                    f"and localized Nigerian market nuances (Pidgin, Yoruba, Hausa, Igbo slang if present)."
                )
                response = model.generate_content(gemini_prompt)
                if response and hasattr(response, "text") and response.text:
                    return response.text.strip()
            except Exception as exc:
                logger.warning(f"Gemini API invocation failed or unavailable ({exc}); falling back to heuristic extraction.")

        # Heuristic fallback if offline or no API key
        lower_prompt = prompt.lower()
        goals = []
        if any(w in lower_prompt for w in ("youtube", "yt", "watch time", "watchtime")):
            goals.append("Platform Goal: YouTube Watch Time / Monetization")
        if any(w in lower_prompt for w in ("spotify", "audiomack", "stream", "music", "shazam", "song")):
            goals.append("Platform Goal: Music Streaming / Shazam Trends")
        if any(w in lower_prompt for w in ("instagram", "ig", "tiktok", "follower", "like")):
            goals.append("Platform Goal: Social Media Followers / Engagement")

        goal_str = "; ".join(goals) if goals else "Platform Goal: General SMM Brand Boosting"
        return f"Language: {language}. {goal_str}. Context: User requesting growth and engagement boost with safe delivery."

    def _run_openai_brain(
        self,
        prompt: str,
        language: str,
        context_summary: str,
        available_providers: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        OpenAI Engine (GPT-4o/Mini): Takes the context and outputs a strictly validated JSON payload:
        {"service_type": str, "quantity": int, "target_url": str, "drip_feed": bool, "delivery_rate": int, "recommended_provider": str}
        """
        provider_list = [p["provider_id"] for p in available_providers] if available_providers else [
            "smmmain", "smmkings", "bulqfollowers", "secser", "justanotherpanel"
        ]

        if self._openai_client and self.openai_api_key:
            try:
                system_instruction = (
                    "You are the OpenAI Structural JSON Engine for NaijaBoost AI.\n"
                    "Your job is to take the user prompt and Gemini context analysis, then output EXACTLY AND ONLY a JSON object matching this exact schema:\n"
                    '{"service_type": str, "quantity": int, "target_url": str, "drip_feed": bool, "delivery_rate": int, "recommended_provider": str}\n\n'
                    "Rules:\n"
                    "- delivery_rate must be an integer between 100 and 1000 units per hour.\n"
                    "- drip_feed should be true by default to protect client accounts.\n"
                    f"- recommended_provider must be chosen from this approved Category A whitelist: {provider_list}\n"
                    "- Output strictly JSON without markdown backticks if possible."
                )
                user_msg = f"User Prompt: '{prompt}'\nLanguage: '{language}'\nGemini Context Analysis:\n{context_summary}"
                response = self._openai_client.chat.completions.create(
                    model=self.openai_model_name,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = response.choices[0].message.content
                if content:
                    return json.loads(content)
            except Exception as exc:
                logger.warning(f"OpenAI API invocation failed or unavailable ({exc}); falling back to heuristic JSON structuring.")

        # Heuristic fallback JSON structuring
        lower_prompt = prompt.lower()
        service_type = "youtube_watch_time"
        recommended_provider = "bulqfollowers"
        quantity = 1000
        delivery_rate = 250
        target_url = "https://youtube.com/channel/naijaboost_default"

        # Extract target url if present
        for word in prompt.split():
            if word.startswith("http://") or word.startswith("https://"):
                target_url = word.strip(".,!?;:\"'")
                break

        # Determine service and provider from prompt keywords
        if any(w in lower_prompt for w in ("stream", "spotify", "audiomack", "shazam", "song", "music")):
            service_type = "music_streaming"
            recommended_provider = "smmmain" if "smmmain" in provider_list else provider_list[0]
            quantity = 5000
        elif any(w in lower_prompt for w in ("youtube", "yt", "watch time", "watchtime")):
            service_type = "youtube_watch_time"
            recommended_provider = "secser" if "secser" in provider_list else provider_list[0]
            quantity = 1000
        elif any(w in lower_prompt for w in ("follower", "ig", "instagram", "tiktok", "like")):
            service_type = "social_followers"
            recommended_provider = "smmkings" if "smmkings" in provider_list else provider_list[0]
            quantity = 2000
        elif any(w in lower_prompt for w in ("volume", "bulk", "cheap", "fast")):
            service_type = "bulk_growth"
            recommended_provider = "justanotherpanel" if "justanotherpanel" in provider_list else provider_list[0]
            quantity = 3000

        # Extract numeric quantity if specified
        for token in prompt.replace(",", "").split():
            if token.isdigit():
                val = int(token)
                if val >= 50:
                    quantity = val
                    break

        return {
            "service_type": service_type,
            "quantity": quantity,
            "target_url": target_url,
            "drip_feed": True,
            "delivery_rate": delivery_rate,
            "recommended_provider": recommended_provider,
        }

    def _validate_and_normalize_plan(
        self,
        raw_plan: Dict[str, Any],
        available_providers: Optional[List[Dict[str, Any]]] = None,
    ) -> ParsedServicePlan:
        """
        Integrate safety validation using `validate_drip_feed_rate` from `smm_logic_engine.py`
        and verify `recommended_provider` is in our Category A whitelist (`provider_routes`).
        """
        service_type = str(raw_plan.get("service_type", "youtube_watch_time")).strip() or "youtube_watch_time"
        
        try:
            quantity = int(raw_plan.get("quantity", 1000))
            if quantity <= 0:
                quantity = 1000
        except (ValueError, TypeError):
            quantity = 1000

        target_url = str(raw_plan.get("target_url", "https://naijaboost.ai/campaign/target")).strip() or "https://naijaboost.ai/campaign/target"
        drip_feed = bool(raw_plan.get("drip_feed", True))

        # Enforce safety validation via smm_logic_engine.py
        raw_rate = raw_plan.get("delivery_rate", 250)
        try:
            delivery_rate = validate_drip_feed_rate(int(raw_rate))
        except (DeliveryRateValidationError, ValueError, TypeError):
            # If the rate provided by LLM or prompt is outside [100, 1000], clamp into safe bounds
            try:
                rate_int = int(raw_rate)
                delivery_rate = max(100, min(1000, rate_int))
            except (ValueError, TypeError):
                delivery_rate = 250
            # Ensure final validation passes cleanly
            delivery_rate = validate_drip_feed_rate(delivery_rate)

        # Validate provider against provider_routes whitelist
        provider_list = [p["provider_id"] for p in available_providers] if available_providers else [
            "smmmain", "smmkings", "bulqfollowers", "secser", "justanotherpanel"
        ]
        recommended_provider = str(raw_plan.get("recommended_provider", "")).strip().lower()
        if not recommended_provider or recommended_provider not in provider_list:
            recommended_provider = provider_list[0] if provider_list else "bulqfollowers"

        return ParsedServicePlan(
            service_type=service_type,
            quantity=quantity,
            target_url=target_url,
            drip_feed=drip_feed,
            delivery_rate=delivery_rate,
            recommended_provider=recommended_provider,
        )
