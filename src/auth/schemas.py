import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.books.schemas import Book, ReviewInBook


class UserCreateModel(BaseModel):
    first_name: str = Field(min_length=1, max_length=25)
    last_name: str = Field(min_length=1, max_length=25)
    username: str = Field(min_length=1, max_length=32)
    email: EmailStr
    password: str = Field(min_length=6)


class UserModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_verified: bool
    created_at: datetime
    update_at: datetime


class UserBooksModel(UserModel):
    books: list[Book] = Field(default_factory=list)
    reviews: list[ReviewInBook] = Field(default_factory=list)


class SignupResponse(BaseModel):
    message: str
    user: UserModel


class UserLoginModel(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class EmailModel(BaseModel):
    addresses: list[EmailStr]


class PasswordResetRequestModel(BaseModel):
    email: EmailStr


class PasswordResetConfirmModel(BaseModel):
    new_password: str = Field(min_length=6)
    confirm_new_password: str = Field(min_length=6)
