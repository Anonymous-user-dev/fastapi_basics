import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RoleChecker, get_current_user
from src.db.main import get_session
from src.db.models import User
from src.errors import BookNotFound, InsufficientPermission

from .schemas import Book, BookCreateModel, BookDetailModel, BookUpdateModel
from .service import BookService

book_router = APIRouter()
book_service = BookService()
role_checker = RoleChecker(["admin", "user"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]


@book_router.get("/", response_model=list[Book], dependencies=[Depends(role_checker)])
async def get_all_books(
    session: SessionDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> list[Book]:
    return await book_service.get_all_books(session, limit, offset)


@book_router.get(
    "/user/{user_uid}",
    response_model=list[Book],
    dependencies=[Depends(role_checker)],
)
async def get_user_book_submissions(
    user_uid: uuid.UUID,
    session: SessionDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> list[Book]:
    return await book_service.get_user_books(user_uid, session, limit, offset)


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
    current_user: CurrentUserDep,
) -> Book:
    book = await book_service.get_book(book_uid, session)
    if book is None:
        raise BookNotFound()
    if current_user.role != "admin" and book.user_uid != current_user.uid:
        raise InsufficientPermission()
    return await book_service.update_book(book, book_update_data, session)


@book_router.delete(
    "/{book_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(role_checker)],
)
async def delete_book(
    book_uid: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> Response:
    book = await book_service.get_book(book_uid, session)
    if book is None:
        raise BookNotFound()
    if current_user.role != "admin" and book.user_uid != current_user.uid:
        raise InsufficientPermission()
    await book_service.delete_book(book, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
