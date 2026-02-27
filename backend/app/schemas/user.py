from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    display_name: str


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    display_name: str | None = None
    password: str | None = None
    is_active: bool | None = None
    username: str | None = None
    language: str | None = None


class UserSelfUpdate(BaseModel):
    username: str | None = None
    display_name: str | None = None
    password: str | None = None
    language: str | None = None


class UserOut(UserBase):
    id: str
    is_active: bool
