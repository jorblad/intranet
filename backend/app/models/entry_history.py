import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


class EntryHistory(Base):
    __tablename__ = "entry_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entry_id = Column(String, ForeignKey("schedule_entries.id", ondelete="SET NULL"), nullable=True)
    schedule_id = Column(String, ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    changed_by_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # "create", "update", "delete", or "revert"
    action = Column(String, nullable=False)
    # JSON snapshot of the entry state at time of change
    snapshot = Column(Text, nullable=False)

    changed_by = relationship("User")
