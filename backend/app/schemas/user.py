from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    display_name: str
    email: str | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    display_name: str | None = None
    password: str | None = None
    is_active: bool | None = None
    username: str | None = None
    language: str | None = None
    email: str | None = None


class UserSelfUpdate(BaseModel):
    username: str | None = None
    display_name: str | None = None
    password: str | None = None
    language: str | None = None
    personal_calendar_activity_ids: list[str] | None = None
    email: str | None = None


class UserOut(UserBase):
    id: str
    is_active: bool


class InviteAssignment(BaseModel):
    organization_id: str | None = None
    role_id: str


class InviteCreate(BaseModel):
    username: str
    display_name: str | None = None
    email: str | None = None
    language: str | None = None
    assignments: list[InviteAssignment] | None = None
    send_email: bool | None = True
    expires_hours: int | None = 48


class InviteAccept(BaseModel):
    token: str
    password: str
