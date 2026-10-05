from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.main import get_session
from src.db.models import User
from src.db.redis import token_in_blocklist
from src.errors import (
    AccessTokenRequired,
    AccountNotVerified,
    InsufficientPermission,
    InvalidToken,
    RefreshTokenRequired,
    RevokedToken,
    UserNotFound,
)

from .service import UserService
from .utils import decode_token

user_service = UserService()


class TokenBearer(HTTPBearer):
    async def __call__(self, request: Request) -> dict:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        token_data = decode_token(credentials.credentials)
        if token_data is None:
            raise InvalidToken()
        if await token_in_blocklist(token_data["jti"]):
            raise RevokedToken()
        self.verify_token_data(token_data)
        return token_data

    def verify_token_data(self, token_data: dict) -> None:
        raise NotImplementedError


class AccessTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if token_data.get("refresh"):
            raise AccessTokenRequired()


class RefreshTokenBearer(TokenBearer):
    def verify_token_data(self, token_data: dict) -> None:
        if not token_data.get("refresh"):
            raise RefreshTokenRequired()


access_token_bearer = AccessTokenBearer()


async def get_current_user(
    token_details: Annotated[dict, Depends(access_token_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    user = await user_service.get_user_by_email(token_details["user"]["email"], session)
    if user is None:
        raise UserNotFound()
    return user


class RoleChecker:
    def __init__(self, allowed_roles: list[str]) -> None:
        self.allowed_roles = allowed_roles

    def __call__(
        self,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> Any:
        if not current_user.is_verified:
            raise AccountNotVerified()
        if current_user.role not in self.allowed_roles:
            raise InsufficientPermission()
        return True
