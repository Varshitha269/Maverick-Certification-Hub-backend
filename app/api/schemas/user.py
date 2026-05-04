from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    avatar_url: str | None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole = UserRole.user
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None

