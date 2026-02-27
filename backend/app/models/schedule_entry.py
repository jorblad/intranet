import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import relationship

from app.db.base import Base

entry_responsible = Table(
    "entry_responsible",
    Base.metadata,
    Column("entry_id", ForeignKey("schedule_entries.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)

entry_devotional = Table(
    "entry_devotional",
    Base.metadata,
    Column("entry_id", ForeignKey("schedule_entries.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)

entry_cant_come = Table(
    "entry_cant_come",
    Base.metadata,
    Column("entry_id", ForeignKey("schedule_entries.id"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
)


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id = Column(String, ForeignKey("schedules.id"), nullable=False)
    date = Column(Date, nullable=False)
    # New timezone-aware start/end datetimes to support calendar events; keep `date` for compatibility
    start = Column(DateTime(timezone=True), nullable=True)
    end = Column(DateTime(timezone=True), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    public_event = Column(Boolean, default=False)

    schedule = relationship("Schedule", back_populates="entries")
    responsible_users = relationship("User", secondary=entry_responsible)
    devotional_users = relationship("User", secondary=entry_devotional)
    cant_come_users = relationship("User", secondary=entry_cant_come)
