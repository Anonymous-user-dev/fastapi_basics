import hashlib
import json
import uuid

from sqlalchemy import delete, desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Book, IdempotencyRecord, User, utc_now
from src.errors import IdempotencyKeyConflict, InsufficientPermission, StaleBookVersion

from .schemas import Book as BookSchema
from .schemas import BookCreateModel, BookUpdateModel

CREATE_BOOK_OPERATION = "books.create"


def _request_hash(book_data: BookCreateModel) -> str:
    canonical_payload = json.dumps(
        book_data.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode()).hexdigest()


def ensure_user_can_manage_book(user: User, book: Book) -> None:
    if user.role == "admin":
        return
    if user.role == "user" and book.user_uid == user.uid:
        return
    raise InsufficientPermission()


class BookService:
    async def get_all_books(
        self,
        session: AsyncSession,
        limit: int,
        offset: int,
    ) -> list[Book]:
        query = select(Book).order_by(desc(Book.created_at)).limit(limit).offset(offset)
        result = await session.scalars(query)
        return list(result.unique().all())

    async def get_user_books(
        self,
        user_uid: uuid.UUID,
        session: AsyncSession,
        limit: int,
        offset: int,
    ) -> list[Book]:
        query = (
            select(Book)
            .where(Book.user_uid == user_uid)
            .order_by(desc(Book.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await session.scalars(query)
        return list(result.unique().all())

    async def get_book(self, book_uid: uuid.UUID, session: AsyncSession) -> Book | None:
        result = await session.scalars(select(Book).where(Book.uid == book_uid))
        return result.unique().one_or_none()

    async def create_book(
        self,
        book_data: BookCreateModel,
        user_uid: uuid.UUID,
        session: AsyncSession,
        *,
        idempotency_key: str | None = None,
    ) -> tuple[Book | BookSchema, bool]:
        request_hash = _request_hash(book_data)
        if idempotency_key is not None:
            existing = await self._get_idempotency_record(
                session,
                user_uid,
                idempotency_key,
            )
            if existing is not None:
                return self._replay_idempotent_response(existing, request_hash)

        book = Book(**book_data.model_dump(), user_uid=user_uid)
        session.add(book)
        if idempotency_key is None:
            await session.commit()
            await session.refresh(book)
            return book, False

        await session.flush()
        response_payload = BookSchema.model_validate(book).model_dump(mode="json")
        session.add(
            IdempotencyRecord(
                user_uid=user_uid,
                operation=CREATE_BOOK_OPERATION,
                key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
                response_status=201,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await self._get_idempotency_record(
                session,
                user_uid,
                idempotency_key,
            )
            if existing is None:
                raise
            return self._replay_idempotent_response(existing, request_hash)

        return BookSchema.model_validate(response_payload), False

    async def _get_idempotency_record(
        self,
        session: AsyncSession,
        user_uid: uuid.UUID,
        key: str,
    ) -> IdempotencyRecord | None:
        return await session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_uid == user_uid,
                IdempotencyRecord.operation == CREATE_BOOK_OPERATION,
                IdempotencyRecord.key == key,
            )
        )

    def _replay_idempotent_response(
        self,
        record: IdempotencyRecord,
        request_hash: str,
    ) -> tuple[BookSchema, bool]:
        if record.request_hash != request_hash:
            raise IdempotencyKeyConflict()
        response_payload = {**record.response_payload}
        response_payload.setdefault("version", 1)
        return BookSchema.model_validate(response_payload), True

    async def update_book(
        self,
        book: Book,
        update_data: BookUpdateModel,
        session: AsyncSession,
        expected_version: int,
    ) -> Book:
        values = update_data.model_dump(exclude_unset=True)
        result = await session.execute(
            update(Book)
            .where(Book.uid == book.uid, Book.version == expected_version)
            .values(
                **values,
                version=Book.version + 1,
                update_at=utc_now(),
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            await session.rollback()
            raise StaleBookVersion()
        await session.commit()
        await session.refresh(book)
        return book

    async def delete_book(
        self,
        book: Book,
        session: AsyncSession,
        expected_version: int,
    ) -> None:
        result = await session.execute(
            delete(Book).where(
                Book.uid == book.uid,
                Book.version == expected_version,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            raise StaleBookVersion()
        await session.commit()
