import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RoleChecker, get_current_user
from src.db.main import get_session
from src.db.models import User
from src.errors import BookNotFound

from .schemas import Book, BookCreateModel, BookDetailModel, BookUpdateModel
from .service import BookService

book_router = APIRouter()
book_service = BookService()
role_checker = RoleChecker(["admin", "user"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@book_router.get("/", response_model=list[Book], dependencies=[Depends(role_checker)])
async def get_all_books(session: SessionDep) -> list[Book]:
    return await book_service.get_all_books(session)


@book_router.get(
    "/user/{user_uid}",
    response_model=list[Book],
    dependencies=[Depends(role_checker)],
)
async def get_user_book_submissions(
    user_uid: uuid.UUID,
    session: SessionDep,
) -> list[Book]:
    return await book_service.get_user_books(user_uid, session)


@book_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=Book,
    dependencies=[Depends(role_checker)],
)
async def create_a_book(
    book_data: BookCreateModel,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> Book:
    return await book_service.create_book(book_data, current_user.uid, session)


@book_router.get(
    "/{book_uid}",
    response_model=BookDetailModel,
    dependencies=[Depends(role_checker)],
)
async def get_book(book_uid: uuid.UUID, session: SessionDep) -> Book:
    book = await book_service.get_book(book_uid, session)
    if book is None:
        raise BookNotFound()
    return book


@book_router.patch(
    "/{book_uid}",
    response_model=Book,
    dependencies=[Depends(role_checker)],
)
async def update_book(
    book_uid: uuid.UUID,
    book_update_data: BookUpdateModel,
    session: SessionDep,
) -> Book:
    book = await book_service.update_book(book_uid, book_update_data, session)
    if book is None:
        raise BookNotFound()
    return book


@book_router.delete(
    "/{book_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(role_checker)],
)
async def delete_book(book_uid: uuid.UUID, session: SessionDep) -> Response:
    if not await book_service.delete_book(book_uid, session):
        raise BookNotFound()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
