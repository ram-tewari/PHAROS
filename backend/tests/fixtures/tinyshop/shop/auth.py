"""Password hashing and session tokens."""

import hashlib
import hmac
import secrets
import time

from .db import fetch_user

TOKEN_TTL_SECONDS = 3600


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Derive a salted PBKDF2 hash for storing a user's password."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    """Check a plaintext password against a stored PBKDF2 hash in constant time."""
    salt_hex, digest_hex = stored.split(":", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate.split(":", 1)[1], digest_hex)


def authenticate(username: str, password: str) -> dict | None:
    """Log a user in: look them up and verify the password."""
    user = fetch_user(username)
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return user


class TokenSigner:
    """Issues and validates HMAC-signed session tokens."""

    def __init__(self, secret: bytes):
        self.secret = secret

    def issue(self, user_id: int, now: float | None = None) -> str:
        """Create a signed token that expires after TOKEN_TTL_SECONDS."""
        expires = int((now or time.time()) + TOKEN_TTL_SECONDS)
        payload = f"{user_id}.{expires}"
        return payload + "." + self._sign(payload)

    def verify(self, token: str, now: float | None = None) -> int | None:
        """Return the user id for a valid, unexpired token, else None."""
        try:
            user_id, expires, signature = token.rsplit(".", 2)
        except ValueError:
            return None
        if not hmac.compare_digest(signature, self._sign(f"{user_id}.{expires}")):
            return None
        if int(expires) < (now or time.time()):
            return None
        return int(user_id)

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
