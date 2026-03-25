"""
auth.py — JWT utilities for both admin sessions and license tokens.

Admin tokens: HS256 signed with ADMIN_JWT_SECRET (short-lived session tokens).
License tokens: RS256 signed with RSA private key (stored on client for offline validation).
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Admin JWT (HS256)
# ---------------------------------------------------------------------------

ADMIN_JWT_SECRET: str = os.getenv("ADMIN_JWT_SECRET", "fallback-change-me-in-production")
ADMIN_JWT_ALGORITHM = "HS256"
ADMIN_JWT_EXPIRE_HOURS: int = int(os.getenv("ADMIN_JWT_EXPIRE_HOURS", "12"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")


def create_admin_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ADMIN_JWT_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "type": "admin",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm=ADMIN_JWT_ALGORITHM)


def decode_admin_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=[ADMIN_JWT_ALGORITHM])
        if payload.get("type") != "admin":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


def get_current_admin(token: str = Depends(oauth2_scheme)) -> str:
    """FastAPI dependency — verifies admin JWT and returns username."""
    payload = decode_admin_token(token)
    return payload["sub"]


# ---------------------------------------------------------------------------
# License JWT (RS256) — stored on client for offline validation
# ---------------------------------------------------------------------------

LICENSE_JWT_EXPIRE_DAYS: int = int(os.getenv("LICENSE_JWT_EXPIRE_DAYS", "7"))

RSA_PRIVATE_KEY_PATH = Path(os.getenv("RSA_PRIVATE_KEY_PATH", "/var/www/vp-license/keys/private.pem"))
RSA_PUBLIC_KEY_PATH = Path(os.getenv("RSA_PUBLIC_KEY_PATH", "/var/www/vp-license/keys/public.pem"))


def _load_private_key() -> str:
    if not RSA_PRIVATE_KEY_PATH.exists():
        raise RuntimeError(
            f"RSA private key not found at {RSA_PRIVATE_KEY_PATH}. "
            "Run: openssl genrsa -out keys/private.pem 2048"
        )
    return RSA_PRIVATE_KEY_PATH.read_text()


def _load_public_key() -> str:
    if not RSA_PUBLIC_KEY_PATH.exists():
        raise RuntimeError(
            f"RSA public key not found at {RSA_PUBLIC_KEY_PATH}. "
            "Run: openssl rsa -in keys/private.pem -pubout -out keys/public.pem"
        )
    return RSA_PUBLIC_KEY_PATH.read_text()


def create_license_token(
    license_key: str,
    machine_fingerprint: str,
    customer_name: str,
    license_expires_at: datetime | None,
) -> str:
    """
    Creates an RS256 JWT for offline validation.
    Token expiry is min(7 days, license_expires_at) so it's always refreshed before license ends.
    """
    now = datetime.now(timezone.utc)
    token_expire = now + timedelta(days=LICENSE_JWT_EXPIRE_DAYS)

    # If license has an expiry, token must not outlive it
    if license_expires_at is not None:
        if license_expires_at.tzinfo is None:
            license_expires_at = license_expires_at.replace(tzinfo=timezone.utc)
        token_expire = min(token_expire, license_expires_at)

    payload = {
        "sub": license_key,
        "fingerprint": machine_fingerprint,
        "customer_name": customer_name,
        "license_expires_at": license_expires_at.isoformat() if license_expires_at else None,
        "iat": now,
        "exp": token_expire,
        "type": "license",
    }
    private_key = _load_private_key()
    return jwt.encode(payload, private_key, algorithm="RS256")


def decode_license_token_offline(token: str) -> dict[str, Any]:
    """
    Verifies and decodes a license JWT using the RSA public key.
    Used by the VP CTRL client for offline validation.
    Raises jwt.InvalidTokenError subclasses on failure.
    """
    public_key = _load_public_key()
    return jwt.decode(token, public_key, algorithms=["RS256"])


def get_public_key_pem() -> str:
    """Returns the public key PEM string — embedded in the VP CTRL client."""
    return _load_public_key()
