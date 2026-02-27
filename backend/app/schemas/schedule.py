from pydantic import BaseModel


class ScheduleBase(BaseModel):
    name: str
    term_id: str
    activity_id: str
    organization_id: str | None = None


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    name: str | None = None
    term_id: str | None = None
    activity_id: str | None = None


class ScheduleOut(ScheduleBase):
    id: str
    organization_id: str | None = None
