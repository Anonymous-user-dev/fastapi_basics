from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.celery_tasks import send_email
from src.config import settings
from src.db.main import get_session
from src.db.models import User
from src.db.redis import add_jti_to_blocklist
from src.errors import InvalidCredentials, InvalidToken, UserAlreadyExists, UserNotFound

from .dependencies import (
    AccessTokenBearer,
    RefreshTokenBearer,
    RoleChecker,
    get_current_user,
)
from .schemas import (
    EmailModel,
    PasswordResetConfirmModel,
    PasswordResetRequestModel,
    SignupResponse,
    UserBooksModel,
    UserCreateModel,
    UserLoginModel,
)
from .service import UserService
from .utils import (
    create_access_token,
    create_url_safe_token,
    decode_url_safe_token,
    generate_passwd_hash,
    verify_password,
)

auth_router = APIRouter()
user_service = UserService()
role_checker = RoleChecker(["admin", "user"])
access_token_bearer = AccessTokenBearer()
refresh_token_bearer = RefreshTokenBearer()
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AccessTokenDep = Annotated[dict, Depends(access_token_bearer)]
RefreshTokenDep = Annotated[dict, Depends(refresh_token_bearer)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
RoleDep = Annotated[bool, Depends(role_checker)]
REFRESH_TOKEN_EXPIRY = 2


@auth_router.post("/send_mail")
async def send_mail(emails: EmailModel) -> dict:
    send_email.delay([str(address) for address in emails.addresses], "Welcome to our app", "<h1>Welcome to the app</h1>")
    return {"message": "Email sent successfully"}


@auth_router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=SignupResponse)
async def create_user_account(
    user_data: UserCreateModel,
    session: SessionDep,
) -> dict:
    if await user_service.user_exists(str(user_data.email), session):
        raise UserAlreadyExists()
    new_user = await user_service.create_user(user_data, session)
    token = create_url_safe_token({"email": str(user_data.email)})
    link = f"http://{settings.DOMAIN}/api/v1/auth/verify/{token}"
    send_email.delay(
        [str(user_data.email)],
        "Verify Your email",
        f'<h1>Verify your Email</h1><p>Please click this <a href="{link}">link</a> to verify your email</p>',
    )
    return {"message": "Account Created! Check email to verify your account", "user": new_user}


@auth_router.get("/verify/{token}")
async def verify_user_account(token: str, session: SessionDep) -> JSONResponse:
    token_data = decode_url_safe_token(token)
    if not token_data or not token_data.get("email"):
        raise InvalidToken()
    user = await user_service.get_user_by_email(token_data["email"], session)
    if user is None:
        raise UserNotFound()
    await user_service.update_user(user, {"is_verified": True}, session)
    return JSONResponse({"message": "Account verified successfully"})


@auth_router.post("/login")
async def login_users(
    login_data: UserLoginModel,
    session: SessionDep,
) -> JSONResponse:
    user = await user_service.get_user_by_email(str(login_data.email), session)
    if user is None or not verify_password(login_data.password, user.password_hash):
        raise InvalidCredentials()
    user_data = {"email": user.email, "user_uid": str(user.uid), "role": user.role}
    access_token = create_access_token(user_data=user_data)
    refresh_token = create_access_token(
        user_data=user_data,
        refresh=True,
        expiry=timedelta(days=REFRESH_TOKEN_EXPIRY),
    )
    return JSONResponse(
        {
            "message": "Login successful",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"email": user.email, "uid": str(user.uid)},
        }
    )


@auth_router.get("/refresh_token")
async def get_new_access_token(token_details: RefreshTokenDep) -> JSONResponse:
    return JSONResponse({"access_token": create_access_token(token_details["user"])})


@auth_router.get("/me", response_model=UserBooksModel)
async def current_user_profile(
    user: CurrentUserDep,
    _: RoleDep,
):
    return user


@auth_router.get("/logout")
async def revoke_token(token_details: AccessTokenDep) -> JSONResponse:
    await add_jti_to_blocklist(token_details["jti"])
    return JSONResponse({"message": "Logged Out Successfully"})


@auth_router.post("/password-reset-request")
async def password_reset_request(email_data: PasswordResetRequestModel) -> JSONResponse:
    token = create_url_safe_token({"email": str(email_data.email)})
    link = f"http://{settings.DOMAIN}/api/v1/auth/password-reset-confirm/{token}"
    send_email.delay(
        [str(email_data.email)],
        "Reset Your Password",
        f'<h1>Reset Your Password</h1><p>Please click this <a href="{link}">link</a> to reset your password</p>',
    )
    return JSONResponse({"message": "Please check your email for instructions to reset your password"})


@auth_router.post("/password-reset-confirm/{token}")
async def reset_account_password(
    token: str,
    passwords: PasswordResetConfirmModel,
    session: SessionDep,
) -> JSONResponse:
    if passwords.new_password != passwords.confirm_new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    token_data = decode_url_safe_token(token)
    if not token_data or not token_data.get("email"):
        raise InvalidToken()
    user = await user_service.get_user_by_email(token_data["email"], session)
    if user is None:
        raise UserNotFound()
    await user_service.update_user(
        user,
        {"password_hash": generate_passwd_hash(passwords.new_password)},
        session,
    )
    return JSONResponse({"message": "Password reset Successfully"})
