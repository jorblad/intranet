import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class EntryBase(BaseModel):
    # Keep legacy `date` (date-only) for compatibility; prefer full datetimes `start`/`end` when available
    date: Optional[datetime.date] = None
    start: Optional[datetime.datetime] = None
    end: Optional[datetime.datetime] = None
    name: str
    description: Optional[str] = None
    notes: Optional[str] = None
    public_event: bool = False
    responsible_ids: List[str] = Field(default_factory=list)
    devotional_ids: List[str] = Field(default_factory=list)
    cant_come_ids: List[str] = Field(default_factory=list)


class EntryCreate(EntryBase):
    pass


class EntryUpdate(BaseModel):
    date: Optional[datetime.date] = None
    start: Optional[datetime.datetime] = None
    end: Optional[datetime.datetime] = None
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    public_event: Optional[bool] = None
    responsible_ids: Optional[List[str]] = None
    devotional_ids: Optional[List[str]] = None
    cant_come_ids: Optional[List[str]] = None


class EntryOut(EntryBase):
    id: str
    schedule_id: str
