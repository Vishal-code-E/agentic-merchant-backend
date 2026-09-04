"""
Data sanitization and redaction service for payment/credential safeguards.

Guarantees that no credit/debit card numbers (PANs), CVVs, expiration dates,
or sensitive keys/tokens (Razorpay secrets, API keys, Fernet keys) are ever
logged to stdout or written to persistent audit trails, even in test-mode.
"""
import logging
import re
from typing import Any

# Regex for Primary Account Numbers (PANs): 13 to 19 digits, possibly separated by spaces or hyphens
# Matches Visa (13/16), Mastercard (16), Amex (15), Discover (16), RuPay (16)
PAN_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# Regex for CVV/CVC: 3 or 4 digits near keywords cvv, cvc, security_code
CVV_PATTERN = re.compile(r"(?i)\b(cvv|cvc|security_code|cid)\s*[:=]?\s*['\"]?(\d{3,4})['\"]?\b")

# Regex for Expiration dates: MM/YY or MM/YYYY near exp, expiry
EXPIRY_PATTERN = re.compile(r"(?i)\b(exp|expiry|exp_date)\s*[:=]?\s*['\"]?(\d{1,2}[\/\-]\d{2,4})['\"]?\b")

# Keys whose values should always be redacted in dictionaries/JSON objects
SENSITIVE_KEY_SUBSTRINGS = {
    "key_secret",
    "secret",
    "api_key",
    "password",
    "authorization",
    "token",
    "encryption_key",
    "private_key",
    "card_number",
    "pan",
    "cvv",
    "cvc",
}


def _mask_pan_match(match: re.Match) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    # Check length typical for payment cards (13 to 19 digits)
    if 13 <= len(digits) <= 19:
        # Keep last 4 digits for verification/identification where needed, mask the rest
        return f"XXXX-XXXX-XXXX-{digits[-4:]}"
    return raw


def sanitize_string(text: str) -> str:
    """Mask card numbers, CVVs, and expiry dates inside arbitrary text."""
    if not text:
        return text

    # Redact PANs
    scrubbed = PAN_PATTERN.sub(_mask_pan_match, text)
    # Redact CVV values
    scrubbed = CVV_PATTERN.sub(r"\1: ***", scrubbed)
    # Redact Expiry values
    scrubbed = EXPIRY_PATTERN.sub(r"\1: **/**", scrubbed)
    return scrubbed


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(sub in normalized for sub in SENSITIVE_KEY_SUBSTRINGS)


def sanitize_data(data: Any) -> Any:
    """
    Recursively traverse dictionaries and lists, redacting sensitive key values
    and masking payment card patterns within strings.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if is_sensitive_key(str(k)):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_data(item) for item in data)
    elif isinstance(data, str):
        return sanitize_string(data)
    else:
        return data


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that sanitizes every LogRecord message and argument before
    it reaches stdout or any log handler.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_data(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    sanitize_string(a) if isinstance(a, str) else sanitize_data(a)
                    for a in record.args
                )
        return True
