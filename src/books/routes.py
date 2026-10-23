import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RoleChecker, get_current_user
from src.db.main import get_session
from src.db.models import User
from src.errors import BookNotFound, PreconditionRequired, StaleBookVersion

from .schemas import Book, BookCreateModel, BookDetailModel, BookUpdateModel
from .service import BookService, ensure_user_can_manage_book

book_router = APIRouter()
book_service = BookService()
role_checker = RoleChecker(["admin", "user"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=1, max_length=255),
]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _parse_if_match(value: str | None) -> int:
    if value is None:
        raise PreconditionRequired()
    token = value.strip()
    if token.startswith("W/"):
        raise StaleBookVersion()
    if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    try:
        version = int(token)
    except ValueError as error:
        raise StaleBookVersion() from error
    if version < 1:
        raise StaleBookVersion()
    return version


def _set_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


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
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> Book:
    book, replayed = await book_service.create_book(
        book_data,
        current_user.uid,
        session,
        idempotency_key=idempotency_key,
    )
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    _set_etag(response, book.version)
    return book


@book_router.get(
    "/{book_uid}",
    response_model=BookDetailModel,
    dependencies=[Depends(role_checker)],
)
async def get_book(
    book_uid: uuid.UUID,
    session: SessionDep,
    response: Response,
) -> Book:
    book = await book_service.get_book(book_uid, session)
    if book is None:
        raise BookNotFound()
    _set_etag(response, book.version)
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
    response: Response,
    if_match: IfMatch = None,
) -> Book:
    book = await book_service.get_book(book_uid, session)
    if book is None:
        raise BookNotFound()
    ensure_user_can_manage_book(current_user, book)
    updated_book = await book_service.update_book(
        book,
        book_update_data,
        session,
        _parse_if_match(if_match),
    )
    _set_etag(response, updated_book.version)
    return updated_book


@book_router.delete(
    "/{book_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(role_checker)],
)
async def delete_book(
    book_uid: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    if_match: IfMatch = None,
) -> Response:
    book = await book_service.get_book(book_uid, session)
    if book is None:
        raise BookNotFound()
    ensure_user_can_manage_book(current_user, book)
    await book_service.delete_book(book, session, _parse_if_match(if_match))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
