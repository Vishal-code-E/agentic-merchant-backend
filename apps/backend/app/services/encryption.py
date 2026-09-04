"""
Fernet-based symmetric encryption for secrets stored at rest (currently:
merchant.razorpay_key_secret). Never use this for anything that needs to be
searched/indexed in the DB — Fernet ciphertext is non-deterministic.
"""
from cryptography.fernet import Fernet

from app.config.settings import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    if not settings.encryption_key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.encryption_key.encode("utf-8"))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
