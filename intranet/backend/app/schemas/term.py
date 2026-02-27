from pydantic import BaseModel


class TermBase(BaseModel):
    name: str


class TermCreate(TermBase):
    organization_id: str | None = None


class TermUpdate(BaseModel):
    name: str | None = None
    organization_id: str | None = None


class TermOut(TermBase):
    id: str
    organization_id: str | None = None
