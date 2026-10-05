import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


book_tags = Table(
    "book_tags",
    Base.metadata,
    Column("book_id", Uuid(as_uuid=True), ForeignKey("books.uid", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Uuid(as_uuid=True), ForeignKey("tags.uid", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    uid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    update_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    books: Mapped[list["Book"]] = relationship(back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    reviews: Mapped[list["Review"]] = relationship(back_populates="user", cascade="all, delete-orphan", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Book(Base):
    __tablename__ = "books"

    uid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(255))
    published_date: Mapped[date] = mapped_column(Date)
    page_count: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(50))
    user_uid: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.uid", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    update_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped[User | None] = relationship(back_populates="books")
    reviews: Mapped[list["Review"]] = relationship(back_populates="book", cascade="all, delete-orphan", lazy="selectin")
    tags: Mapped[list["Tag"]] = relationship(secondary=book_tags, back_populates="books", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Book {self.title}>"


class Tag(Base):
    __tablename__ = "tags"

    uid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    books: Mapped[list[Book]] = relationship(secondary=book_tags, back_populates="tags", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),)

    uid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rating: Mapped[int] = mapped_column(Integer)
    review_text: Mapped[str] = mapped_column(String(2000))
    user_uid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.uid", ondelete="CASCADE"))
    book_uid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("books.uid", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    update_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped[User] = relationship(back_populates="reviews")
    book: Mapped[Book] = relationship(back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review for book {self.book_uid} by user {self.user_uid}>"
