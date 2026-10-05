import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Book

from .schemas import BookCreateModel, BookUpdateModel


class BookService:
    async def get_all_books(self, session: AsyncSession) -> list[Book]:
        result = await session.scalars(select(Book).order_by(desc(Book.created_at)))
        return list(result.unique().all())

    async def get_user_books(self, user_uid: uuid.UUID, session: AsyncSession) -> list[Book]:
        result = await session.scalars(
            select(Book).where(Book.user_uid == user_uid).order_by(desc(Book.created_at))
        )
        return list(result.unique().all())

    async def get_book(self, book_uid: uuid.UUID, session: AsyncSession) -> Book | None:
        result = await session.scalars(select(Book).where(Book.uid == book_uid))
        return result.unique().one_or_none()

    async def create_book(
        self,
        book_data: BookCreateModel,
        user_uid: uuid.UUID,
        session: AsyncSession,
    ) -> Book:
        book = Book(**book_data.model_dump(), user_uid=user_uid)
        session.add(book)
        await session.commit()
        await session.refresh(book)
        return book

    async def update_book(
        self,
        book_uid: uuid.UUID,
        update_data: BookUpdateModel,
        session: AsyncSession,
    ) -> Book | None:
        book = await self.get_book(book_uid, session)
        if book is None:
            return None
        for key, value in update_data.model_dump(exclude_unset=True).items():
            setattr(book, key, value)
        await session.commit()
        await session.refresh(book)
        return book

    async def delete_book(self, book_uid: uuid.UUID, session: AsyncSession) -> bool:
        book = await self.get_book(book_uid, session)
        if book is None:
            return False
        await session.delete(book)
        await session.commit()
        return True
