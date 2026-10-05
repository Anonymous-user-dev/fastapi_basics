import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.books.service import BookService
from src.db.models import Book, Tag
from src.errors import BookNotFound, TagAlreadyExists, TagNotFound

from .schemas import TagAddModel, TagCreateModel

book_service = BookService()


class TagService:
    async def get_tags(self, session: AsyncSession) -> list[Tag]:
        result = await session.scalars(select(Tag).order_by(desc(Tag.created_at)))
        return list(result.unique().all())

    async def get_tag_by_uid(self, tag_uid: uuid.UUID, session: AsyncSession) -> Tag | None:
        result = await session.scalars(select(Tag).where(Tag.uid == tag_uid))
        return result.unique().one_or_none()

    async def get_tag_by_name(self, name: str, session: AsyncSession) -> Tag | None:
        result = await session.scalars(select(Tag).where(Tag.name == name))
        return result.unique().one_or_none()

    async def add_tag(self, tag_data: TagCreateModel, session: AsyncSession) -> Tag:
        if await self.get_tag_by_name(tag_data.name, session):
            raise TagAlreadyExists()
        tag = Tag(name=tag_data.name)
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
        return tag

    async def add_tags_to_book(
        self,
        book_uid: uuid.UUID,
        tag_data: TagAddModel,
        session: AsyncSession,
    ) -> Book:
        book = await book_service.get_book(book_uid, session)
        if book is None:
            raise BookNotFound()
        for tag_item in tag_data.tags:
            tag = await self.get_tag_by_name(tag_item.name, session)
            if tag is None:
                tag = Tag(name=tag_item.name)
                session.add(tag)
            if all(existing.name != tag.name for existing in book.tags):
                book.tags.append(tag)
        await session.commit()
        return await book_service.get_book(book_uid, session)

    async def update_tag(
        self,
        tag_uid: uuid.UUID,
        tag_data: TagCreateModel,
        session: AsyncSession,
    ) -> Tag:
        tag = await self.get_tag_by_uid(tag_uid, session)
        if tag is None:
            raise TagNotFound()
        existing = await self.get_tag_by_name(tag_data.name, session)
        if existing is not None and existing.uid != tag_uid:
            raise TagAlreadyExists()
        tag.name = tag_data.name
        await session.commit()
        await session.refresh(tag)
        return tag

    async def delete_tag(self, tag_uid: uuid.UUID, session: AsyncSession) -> None:
        tag = await self.get_tag_by_uid(tag_uid, session)
        if tag is None:
            raise TagNotFound()
        await session.delete(tag)
        await session.commit()
