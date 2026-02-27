from pydantic import BaseModel
from typing import Optional
from datetime import time


class ActivityBase(BaseModel):
    name: str
    organization_id: Optional[str] = None
    default_start_time: Optional[time] = None
    default_end_time: Optional[time] = None


class ActivityCreate(ActivityBase):
    pass


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    organization_id: Optional[str] = None
    default_start_time: Optional[time] = None
    default_end_time: Optional[time] = None


class ActivityOut(ActivityBase):
    id: str
