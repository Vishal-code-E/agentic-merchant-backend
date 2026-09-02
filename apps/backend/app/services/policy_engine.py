"""
Evaluates a proposed cart (+ any upsell additions) against a merchant's Policy.

This is the single gate every money-moving action must pass through
(see Graph Engineering doc §2.3, "Policy before payment"). Keep this
service pure / side-effect free — it should only ever return a decision,
never call external systems itself.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None


class PolicyEngine:
    def evaluate(
        self,
        cart_items: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> PolicyDecision:
        """
        TODO(v1.2): implement checks for max_amount, allowed_categories,
        and per_user_limit against the given cart_items + policy.
        """
        raise NotImplementedError
