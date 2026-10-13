import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Book(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    title: str
    author: str
    publisher: str
    published_date: date
    page_count: int
    language: str
    created_at: datetime
    update_at: datetime


class ReviewInBook(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    rating: int
    review_text: str
    user_uid: uuid.UUID
    book_uid: uuid.UUID
    created_at: datetime
    update_at: datetime


class TagInBook(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    name: str
    created_at: datetime


class BookDetailModel(Book):
    reviews: list[ReviewInBook] = Field(default_factory=list)
    tags: list[TagInBook] = Field(default_factory=list)


class BookCreateModel(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)
    publisher: str = Field(min_length=1, max_length=255)
    published_date: date
    page_count: int = Field(gt=0)
    language: str = Field(min_length=1, max_length=50)


class BookUpdateModel(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    author: str | None = Field(default=None, min_length=1, max_length=255)
    publisher: str | None = Field(default=None, min_length=1, max_length=255)
    published_date: date | None = None
    page_count: int | None = Field(default=None, gt=0)
    language: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        null_fields = [
            field_name
            for field_name in self.model_fields_set
            if getattr(self, field_name) is None
        ]
        if null_fields:
            raise ValueError("Book fields cannot be null")
        return self
