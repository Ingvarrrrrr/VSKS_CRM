"""
Шифрование/дешифрование паролей площадок (Fernet symmetric encryption).

Ключ: env PLATFORM_CRED_KEY (URL-safe base64 из 32 байт, т.е. 44 символа).
Fallback: детерминированный ключ из SECRET_KEY приложения (sha256 → base64).
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.getenv("PLATFORM_CRED_KEY", "").strip()
    if not key:
        # Fallback: sha256 от SECRET_KEY приложения → 32 байта → URL-safe base64
        from app.config import settings
        digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def encrypt_password(plain: str) -> str:
    """Шифрует пароль, возвращает base64-строку."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_password(token: str) -> str:
    """Дешифрует ранее зашифрованный пароль."""
    return _get_fernet().decrypt(token.encode()).decode()
