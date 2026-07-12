"""Core SMM logic engine components for NaijaBoost AI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

DripMode = Literal["drip-feed"]


class DeliveryRateValidationError(ValueError):
    """Raised when a drip-feed delivery rate is outside the allowed bounds."""


def validate_drip_feed_rate(delivery_rate: int) -> int:
    """Ensure the delivery rate keeps accounts safe via enforced drip-feed."""
    if not isinstance(delivery_rate, int):
        raise DeliveryRateValidationError("delivery_rate must be an integer representing units per hour")
    if delivery_rate < 100 or delivery_rate > 1000:
        raise DeliveryRateValidationError("delivery_rate must be between 100 and 1000 units per hour")
    return delivery_rate


@dataclass(frozen=True)
class ServicePlan:
    service_type: str
    quantity: int
    delivery_mode: DripMode
    delivery_rate: int
    priority: Literal["youtube", "standard"]


class SMM_Engine_Protocol:
    """Centralized logic driver responsible for orchestrating reseller automation."""

    _YOUTUBE_KEYWORDS = ("youtube", "yt")
    _WATCH_TIME_MARKERS = ("watch", "watchtime", "hours")

    def request_service(
        self,
        client_id: str,
        service_type: str,
        quantity: int,
        delivery_rate: int,
    ) -> Dict[str, object]:
        """
        Build a structured service request while enforcing drip-feed safety rails.

        :raises DeliveryRateValidationError: if the provided rate is unsafe.
        """

        # Business Infrastructure: this orchestrates NaijaBoost's core fulfillment commitments.
        safe_rate = validate_drip_feed_rate(delivery_rate)
        normalized = service_type.strip().lower()
        is_youtube_priority = self._is_youtube_watch_time(normalized)

        service_plan = ServicePlan(
            service_type=normalized if is_youtube_priority else "youtube_watch_time",
            quantity=quantity,
            delivery_mode="drip-feed",
            delivery_rate=safe_rate,
            priority="youtube" if is_youtube_priority else "standard",
        )

        return {
            "client_id": client_id,
            "plan": service_plan,
            "notes": self._build_notes(is_youtube_priority, normalized),
        }

    def _is_youtube_watch_time(self, normalized_service: str) -> bool:
        if any(keyword in normalized_service for keyword in self._YOUTUBE_KEYWORDS):
            return any(marker in normalized_service for marker in self._WATCH_TIME_MARKERS)
        return False

    def _build_notes(self, is_priority: bool, requested_service: str) -> str:
        if is_priority:
            return "Client request aligns with YouTube Watch Time priority lane."
        return (
            "Requested service '{0}' rerouted to managed YouTube Watch Time "
            "inventory to maintain monetization eligibility."
        ).format(requested_service)
