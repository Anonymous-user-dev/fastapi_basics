from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

from src.db.models import Base


def test_models_use_sqlalchemy_declarative_base():
    assert issubclass(Base, DeclarativeBase)
    assert set(Base.metadata.tables) == {
        "users",
        "books",
        "reviews",
        "tags",
        "book_tags",
    }


def test_schema_can_be_created_without_sqlmodel():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)

    assert set(Base.metadata.tables) == {
        "users",
        "books",
        "reviews",
        "tags",
        "book_tags",
    }
