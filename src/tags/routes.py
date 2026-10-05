import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RoleChecker
from src.books.schemas import BookDetailModel
from src.db.main import get_session

from .schemas import TagAddModel, TagCreateModel, TagModel
from .service import TagService

tags_router = APIRouter()
tag_service = TagService()
role_checker = RoleChecker(["user", "admin"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@tags_router.get("/", response_model=list[TagModel], dependencies=[Depends(role_checker)])
async def get_all_tags(session: SessionDep) -> list[TagModel]:
    return await tag_service.get_tags(session)


@tags_router.post(
    "/",
    response_model=TagModel,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(role_checker)],
)
async def add_tag(tag_data: TagCreateModel, session: SessionDep) -> TagModel:
    return await tag_service.add_tag(tag_data, session)


@tags_router.post(
    "/book/{book_uid}/tags",
    response_model=BookDetailModel,
    dependencies=[Depends(role_checker)],
)
async def add_tags_to_book(
    book_uid: uuid.UUID,
    tag_data: TagAddModel,
    session: SessionDep,
) -> BookDetailModel:
    return await tag_service.add_tags_to_book(book_uid, tag_data, session)


@tags_router.put(
    "/{tag_uid}",
    response_model=TagModel,
    dependencies=[Depends(role_checker)],
)
async def update_tag(
    tag_uid: uuid.UUID,
    tag_update_data: TagCreateModel,
    session: SessionDep,
) -> TagModel:
    return await tag_service.update_tag(tag_uid, tag_update_data, session)


@tags_router.delete(
    "/{tag_uid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(role_checker)],
)
async def delete_tag(tag_uid: uuid.UUID, session: SessionDep) -> Response:
    await tag_service.delete_tag(tag_uid, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
