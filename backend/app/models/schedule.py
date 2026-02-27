import uuid

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    term_id = Column(String, ForeignKey("terms.id"), nullable=False)
    activity_id = Column(String, ForeignKey("activities.id"), nullable=True)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)

    entries = relationship("ScheduleEntry", back_populates="schedule", cascade="all, delete")
    term = relationship("Term")
    activity = relationship("Activity", overlaps="schedules")
