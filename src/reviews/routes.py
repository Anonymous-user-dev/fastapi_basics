import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RoleChecker, get_current_user
from src.db.main import get_session
from src.db.models import User

from .schemas import ReviewCreateModel, ReviewModel
from .service import ReviewService

review_service = ReviewService()
review_router = APIRouter()
admin_role_checker = RoleChecker(["admin"])
user_role_checker = RoleChecker(["user", "admin"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@review_router.get(
    "/",
    response_model=list[ReviewModel],
    dependencies=[Depends(admin_role_checker)],
)
async def get_all_reviews(session: SessionDep) -> list[ReviewModel]:
    return await review_service.get_all_reviews(session)


@review_router.get(
    "/{review_uid}",
    response_model=ReviewModel,
    dependencies=[Depends(user_role_checker)],
)
async def get_review(review_uid: uuid.UUID, session: SessionDep) -> ReviewModel:
    return await review_service.get_review_or_404(review_uid, session)


@review_router.post(
    "/book/{book_uid}",
    response_model=ReviewModel,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_role_checker)],
)
async def add_review_to_book(
    book_uid: uuid.UUID,
    review_data: ReviewCreateModel,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> ReviewModel:
    return await review_service.add_review_to_book(
        current_user,
        book_uid,
        review_data,
        session,
    )


@review_router.delete(
    "/{review_uid}",
    dependencies=[Depends(user_role_checker)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_review(
    review_uid: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> Response:
    await review_service.delete_review_from_book(review_uid, current_user, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
