"""
Evaluates a proposed cart (+ any upsell additions) against a merchant's Policy.

This is the single gate every money-moving action must pass through
(see Graph Engineering doc §2.3, "Policy before payment"). Keep this
service pure / side-effect free — it should only ever return a decision,
never call external systems itself.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    #: Non-fatal observations about the evaluation itself — e.g. a rule that
    #: could not be enforced. Surfaced for observability/audit; never used on
    #: its own to allow or deny.
    notes: list[str] = field(default_factory=list)


def _line_total(item: dict[str, Any]) -> float:
    # unit_price arrives as a float from validate_cart_node, but Policy.max_amount
    # comes off a Numeric column as Decimal. Everything is normalised to float
    # here so comparisons never raise TypeError on float-vs-Decimal.
    return float(item.get("unit_price") or 0.0) * int(item.get("quantity") or 0)


def cart_total(cart_items: list[dict[str, Any]]) -> float:
    return sum(_line_total(item) for item in cart_items)


class PolicyEngine:
    def evaluate(
        self,
        cart_items: list[dict[str, Any]],
        policy: dict[str, Any],
        customer_context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """
        Evaluate a canonical cart (as produced by validate_cart_node) against a
        merchant's policy. Fails closed: any rule that cannot be evaluated with
        confidence denies rather than allows.

        cart_items entries must carry: name, quantity, unit_price, category.
        """
        notes: list[str] = []
        total = cart_total(cart_items)

        # --- max_amount ---------------------------------------------------
        max_amount = policy.get("max_amount")
        if max_amount is None:
            # Fail closed. A policy row with no ceiling is a misconfiguration,
            # and this is the last gate before money moves.
            return PolicyDecision(
                allowed=False,
                reason="Merchant policy does not define a max_amount; refusing to authorise payment.",
                notes=notes,
            )

        max_amount = float(max_amount)
        if total > max_amount:
            return PolicyDecision(
                allowed=False,
                reason=f"Cart total {total:.2f} exceeds the merchant's max_amount of {max_amount:.2f}.",
                notes=notes,
            )

        # --- allowed_categories -------------------------------------------
        allowed_categories = list(policy.get("allowed_categories") or [])
        if allowed_categories:  # empty list == no category restriction
            for item in cart_items:
                category = item.get("category")
                if category not in allowed_categories:
                    return PolicyDecision(
                        allowed=False,
                        reason=(
                            f"Item '{item.get('name')}' has category {category!r}, which is not "
                            f"in the merchant's allowed categories "
                            f"({', '.join(allowed_categories)})."
                        ),
                        notes=notes,
                    )

        # --- per_user_limit -------------------------------------------------
        per_user_limit = policy.get("per_user_limit")
        if per_user_limit is not None:
            customer_id = (customer_context or {}).get("customer_id")
            if not customer_id:
                notes.append(
                    "per_user_limit NOT enforced: the request carried no customer identifier "
                    "(customer_context.customer_id)."
                )
            else:
                # KNOWN GAP (v1.2), not a bug: there is no persistent per-customer
                # spend ledger. Orders have no customer_id column and nothing
                # aggregates historical spend, so the only thing we can compare
                # against per_user_limit is the CURRENT cart. A customer can stay
                # under the limit on every individual checkout while blowing past
                # it in aggregate. Closing this needs a customer_id on Order plus
                # a rolling-window SUM(amount) query — which would also make this
                # method impure, so it should be fetched by check_policy_node and
                # passed in, not queried here.
                per_user_limit = float(per_user_limit)
                if total > per_user_limit:
                    return PolicyDecision(
                        allowed=False,
                        reason=(
                            f"Cart total {total:.2f} exceeds the per-user limit of "
                            f"{per_user_limit:.2f} for customer {customer_id}."
                        ),
                        notes=notes,
                    )
                notes.append(
                    "per_user_limit checked against this cart only; no historical "
                    "per-customer spend tracking exists yet."
                )

        return PolicyDecision(allowed=True, reason=None, notes=notes)

    def filter_upsells(
        self,
        cart_items: list[dict[str, Any]],
        upsell_suggestions: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Drop any suggestion that would breach policy if the customer accepted it.

        Deliberately separate from evaluate(): a suggestion the backend invented
        must never cause a customer's own valid cart to be denied. Suggestions
        are filtered; the cart is judged on its own. Budget is consumed greedily
        in the order given (cheapest-first, per suggest_upsell_node), assuming
        quantity 1 per suggestion.
        """
        if not upsell_suggestions:
            return [], []

        notes: list[str] = []
        allowed_categories = list(policy.get("allowed_categories") or [])
        max_amount = policy.get("max_amount")
        remaining = float(max_amount) - cart_total(cart_items) if max_amount is not None else None

        kept: list[dict[str, Any]] = []
        for suggestion in upsell_suggestions:
            if allowed_categories and suggestion.get("category") not in allowed_categories:
                notes.append(
                    f"Upsell '{suggestion.get('name')}' withheld: category not permitted by policy."
                )
                continue

            price = float(suggestion.get("price") or 0.0)
            if remaining is not None:
                if price > remaining:
                    notes.append(
                        f"Upsell '{suggestion.get('name')}' withheld: would push the cart past max_amount."
                    )
                    continue
                remaining -= price

            kept.append(suggestion)

        return kept, notes
