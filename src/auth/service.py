from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User

from .schemas import UserCreateModel
from .utils import generate_passwd_hash


class UserService:
    async def get_user_by_email(self, email: str, session: AsyncSession) -> User | None:
        return await session.scalar(select(User).where(User.email == email))

    async def user_exists(self, email: str, session: AsyncSession) -> bool:
        return await self.get_user_by_email(email, session) is not None

    async def create_user(self, user_data: UserCreateModel, session: AsyncSession) -> User:
        values = user_data.model_dump(exclude={"password"})
        user = User(
            **values,
            password_hash=generate_passwd_hash(user_data.password),
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def update_user(self, user: User, user_data: dict, session: AsyncSession) -> User:
        for key, value in user_data.items():
            setattr(user, key, value)
        await session.commit()
        await session.refresh(user)
        return user
