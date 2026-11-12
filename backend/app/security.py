"""Password/PIN hashing and signed access-token helpers."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
from .config import SECRET_KEY, ACCESS_TOKEN_MINUTES

ALGORITHM = "HS256"


def hash_secret(value: str) -> str:
    """Hash a PIN/password with PBKDF2; never store the original secret."""
    salt = secrets.token_bytes(16)
    iterations = 310000
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(iterations, salt.hex(), digest.hex())


def verify_secret(value: str, encoded: str) -> bool:
    """Safely compare a supplied secret with a stored PBKDF2 hash."""
    try:
        scheme, rounds, salt_hex, digest_hex = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError, AttributeError):
        return False


def create_token(subject: str, role: str, account_id=None) -> str:
    """Create a signed JWT with identity, role, expiry and unique token ID."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject), "role": role, "account_id": account_id,
        "jti": secrets.token_urlsafe(24), "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Verify signature and expiry before returning JWT claims."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
