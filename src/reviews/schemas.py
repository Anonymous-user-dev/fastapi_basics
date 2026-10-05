import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    rating: int = Field(ge=1, le=5)
    review_text: str
    user_uid: uuid.UUID
    book_uid: uuid.UUID
    created_at: datetime
    update_at: datetime


class ReviewCreateModel(BaseModel):
    rating: int = Field(ge=1, le=5)
    review_text: str = Field(min_length=1, max_length=2000)
