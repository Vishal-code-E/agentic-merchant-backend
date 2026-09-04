"""
Unit tests for data sanitization, policy guardrail validation, and deactivation logic.
"""
import uuid
import pytest
from pydantic import ValidationError

from app.schemas.policy import PolicyUpdate
from app.schemas.merchant import OnboardMerchantRequest
from app.services.data_sanitizer import sanitize_data, sanitize_string, is_sensitive_key


def test_sanitize_string_masks_pans():
    # Visa 16 digits
    visa = "Customer attempted payment with card 4111 2222 3333 4444 on checkout"
    sanitized = sanitize_string(visa)
    assert "4111" not in sanitized
    assert "XXXX-XXXX-XXXX-4444" in sanitized

    # Mastercard 16 digits without spaces
    mc = "Card 5500000000001234 charged"
    sanitized_mc = sanitize_string(mc)
    assert "550000000000" not in sanitized_mc
    assert "XXXX-XXXX-XXXX-1234" in sanitized_mc


def test_sanitize_string_masks_cvv_and_expiry():
    text = "card details: cvv: 987, exp: 12/28"
    sanitized = sanitize_string(text)
    assert "987" not in sanitized
    assert "12/28" not in sanitized
    assert "cvv: ***" in sanitized
    assert "exp: **/**" in sanitized


def test_sanitize_data_redacts_sensitive_keys():
    payload = {
        "merchant_name": "Test Store",
        "razorpay_key_secret": "super_secret_shhh",
        "nested": {
            "api_key": "agent_key_12345",
            "customer_pan": "4111111111111111",
            "order_id": "order_test_99",
        },
        "safe_list": ["apple", "banana", "token_value_in_list"],
    }
    cleaned = sanitize_data(payload)
    assert cleaned["razorpay_key_secret"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["api_key"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["customer_pan"] == "[REDACTED_SECRET]"
    assert cleaned["nested"]["order_id"] == "order_test_99"
    assert cleaned["merchant_name"] == "Test Store"


def test_policy_update_rejects_excessive_discount():
    # Valid discount
    valid = PolicyUpdate(max_discount_pct=25.0)
    assert valid.max_discount_pct == 25.0

    # Discount > 50% must raise ValidationError
    with pytest.raises(ValidationError) as exc:
        PolicyUpdate(max_discount_pct=60.0)
    assert "max_discount_pct" in str(exc.value)

    # Negative discount must raise ValidationError
    with pytest.raises(ValidationError) as exc:
        PolicyUpdate(max_discount_pct=-5.0)
    assert "max_discount_pct" in str(exc.value)


def test_policy_update_rejects_user_limit_exceeding_max_amount():
    with pytest.raises(ValidationError) as exc:
        PolicyUpdate(max_amount=500.0, per_user_limit=1000.0)
    assert "per_user_limit cannot exceed max_amount" in str(exc.value)

    # Valid limits
    valid = PolicyUpdate(max_amount=1000.0, per_user_limit=500.0)
    assert valid.max_amount == 1000.0
    assert valid.per_user_limit == 500.0


def test_onboard_merchant_request_limits_validation():
    with pytest.raises(ValidationError) as exc:
        OnboardMerchantRequest(
            name="Store",
            razorpay_key_id="rzp_test_123",
            razorpay_key_secret="secret",
            max_amount=200.0,
            per_user_limit=500.0,
            max_discount_pct=20.0,
        )
    assert "per_user_limit cannot exceed max_amount" in str(exc.value)
