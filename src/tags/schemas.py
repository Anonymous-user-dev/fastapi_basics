import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    name: str
    created_at: datetime


class TagCreateModel(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()


class TagAddModel(BaseModel):
    tags: list[TagCreateModel] = Field(min_length=1)
