import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pwdlib import PasswordHash

from src.config import settings

ACCESS_TOKEN_EXPIRY = 3600
URL_TOKEN_EXPIRY = 3600
logger = logging.getLogger(__name__)
password_hash = PasswordHash.recommended()
serializer = URLSafeTimedSerializer(
    secret_key=settings.JWT_SECRET,
    salt="email-configuration",
)


def generate_passwd_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    user_data: dict,
    expiry: timedelta | None = None,
    refresh: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user": user_data,
        "iat": now,
        "exp": now + (expiry or timedelta(seconds=ACCESS_TOKEN_EXPIRY)),
        "jti": str(uuid.uuid4()),
        "refresh": refresh,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_url_safe_token(data: dict) -> str:
    return serializer.dumps(data)


def decode_url_safe_token(token: str, max_age: int = URL_TOKEN_EXPIRY) -> dict | None:
    try:
        return serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        logger.info("Rejected invalid or expired URL token")
        return None
