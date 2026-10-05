import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.books.service import BookService
from src.db.models import Review, User
from src.errors import BookNotFound, ReviewNotFound

from .schemas import ReviewCreateModel

book_service = BookService()


class ReviewService:
    async def add_review_to_book(
        self,
        user: User,
        book_uid: uuid.UUID,
        review_data: ReviewCreateModel,
        session: AsyncSession,
    ) -> Review:
        book = await book_service.get_book(book_uid, session)
        if book is None:
            raise BookNotFound()
        review = Review(
            **review_data.model_dump(),
            user_uid=user.uid,
            book_uid=book.uid,
        )
        session.add(review)
        await session.commit()
        await session.refresh(review)
        return review

    async def get_review(self, review_uid: uuid.UUID, session: AsyncSession) -> Review | None:
        return await session.scalar(select(Review).where(Review.uid == review_uid))

    async def get_review_or_404(self, review_uid: uuid.UUID, session: AsyncSession) -> Review:
        review = await self.get_review(review_uid, session)
        if review is None:
            raise ReviewNotFound()
        return review

    async def get_all_reviews(self, session: AsyncSession) -> list[Review]:
        result = await session.scalars(select(Review).order_by(desc(Review.created_at)))
        return list(result.all())

    async def delete_review_from_book(
        self,
        review_uid: uuid.UUID,
        user: User,
        session: AsyncSession,
    ) -> None:
        review = await self.get_review_or_404(review_uid, session)
        if review.user_uid != user.uid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete this review",
            )
        await session.delete(review)
        await session.commit()
