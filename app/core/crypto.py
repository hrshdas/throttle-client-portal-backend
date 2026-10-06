import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import get_settings

settings = get_settings()


def _build_fernet() -> Fernet:
    """Build Fernet cipher from the dedicated encryption key or derive from SECRET_KEY."""
    if settings.META_ENCRYPTION_KEY:
        # Use dedicated encryption key if provided.
        # Must be a valid Fernet key (32 url-safe base64 bytes).
        # Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        key = settings.META_ENCRYPTION_KEY.encode()
        # Validate it is a proper Fernet key; if not, derive from it.
        try:
            Fernet(key)
            return Fernet(key)
        except Exception:
            # Treat as raw passphrase — derive 32-byte key
            key_bytes = hashlib.sha256(settings.META_ENCRYPTION_KEY.encode()).digest()
            return Fernet(base64.urlsafe_b64encode(key_bytes))
    else:
        # Fallback: derive from SECRET_KEY (backward compatible)
        key_bytes = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(key_bytes))


_fernet = _build_fernet()

PREFIX = "enc:v1:"


def encrypt_message(plain_text: str) -> str:
    """Encrypt plain text string. Returns prefixed ciphertext."""
    if not plain_text:
        return ""
    if plain_text.startswith(PREFIX):
        return plain_text  # Already encrypted
    encrypted_bytes = _fernet.encrypt(plain_text.encode("utf-8"))
    return f"{PREFIX}{encrypted_bytes.decode('utf-8')}"


def decrypt_message(cipher_text: str) -> str:
    """Decrypt enc:v1: prefixed ciphertext back to plain text."""
    if not cipher_text:
        return ""
    if not cipher_text.startswith(PREFIX):
        return cipher_text  # Not encrypted (legacy plain text)
    
    raw_cipher = cipher_text[len(PREFIX):]
    
    # Try primary Fernet instance first
    try:
        decrypted_bytes = _fernet.decrypt(raw_cipher.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception:
        pass

    # Fallback attempt: derive key from SECRET_KEY
    try:
        fallback_bytes = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        fallback_fernet = Fernet(base64.urlsafe_b64encode(fallback_bytes))
        decrypted_bytes = fallback_fernet.decrypt(raw_cipher.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception:
        pass

    # Fallback attempt 2: try default dev key
    try:
        dev_bytes = hashlib.sha256(b"your-super-secret-key-change-in-production-minimum-64-chars-long-xxxx").digest()
        dev_fernet = Fernet(base64.urlsafe_b64encode(dev_bytes))
        decrypted_bytes = dev_fernet.decrypt(raw_cipher.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception:
        pass

    return "[Encrypted Message]"
