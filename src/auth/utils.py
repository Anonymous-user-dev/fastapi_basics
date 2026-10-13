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
verification_serializer = URLSafeTimedSerializer(
    secret_key=settings.JWT_SECRET,
    salt="email-verification",
)
password_reset_serializer = URLSafeTimedSerializer(
    secret_key=settings.JWT_SECRET,
    salt="password-reset",
)


def generate_passwd_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    user_data: dict,
    expiry: timedelta | None = None,
    refresh: bool = False,
    session_id: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user": user_data,
        "iat": now,
        "exp": now + (expiry or timedelta(seconds=ACCESS_TOKEN_EXPIRY)),
        "jti": str(uuid.uuid4()),
        "sid": session_id or str(uuid.uuid4()),
        "refresh": refresh,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_verification_token(data: dict) -> str:
    return verification_serializer.dumps(data)


def decode_verification_token(token: str, max_age: int = URL_TOKEN_EXPIRY) -> dict | None:
    return _decode_url_token(verification_serializer, token, max_age)


def create_password_reset_token(data: dict) -> str:
    return password_reset_serializer.dumps({**data, "jti": str(uuid.uuid4())})


def decode_password_reset_token(token: str, max_age: int = URL_TOKEN_EXPIRY) -> dict | None:
    return _decode_url_token(password_reset_serializer, token, max_age)


def _decode_url_token(
    token_serializer: URLSafeTimedSerializer,
    token: str,
    max_age: int,
) -> dict | None:
    try:
        return token_serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        logger.info("Rejected invalid or expired URL token")
        return None
