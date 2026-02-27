import uuid

from sqlalchemy import Column, String, ForeignKey, Time
from sqlalchemy.orm import relationship

from app.db.base import Base


class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)
    # Optional default start/end times for activities (local time, stored as SQL Time)
    default_start_time = Column(Time, nullable=True)
    default_end_time = Column(Time, nullable=True)

    schedules = relationship("Schedule", cascade="all, delete")
