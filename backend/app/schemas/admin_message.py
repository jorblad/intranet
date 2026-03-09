from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime


class AdminMessageBase(BaseModel):
    title: str
    body: Optional[str] = None
    title_i18n: Optional[Dict[str, str]] = None
    body_i18n: Optional[Dict[str, str]] = None
    organization_id: Optional[str] = None
    icon: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    priority: Optional[int] = 0


class AdminMessageCreate(AdminMessageBase):
    pass


class AdminMessageUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    organization_id: Optional[str] = None
    icon: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    priority: Optional[int] = None


class AdminMessageOut(AdminMessageBase):
    id: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
