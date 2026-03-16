import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Integer, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class AdminMessage(Base):
    __tablename__ = "admin_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Nullable organization: when null the message is global (applies to all orgs)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    # optional per-locale translations for title/body stored as JSON map { 'en-US': 'Title', 'sv-SE': 'Titel' }
    title_i18n = Column(JSON, nullable=True)
    body_i18n = Column(JSON, nullable=True)
    # optional icon name (Quasar/material icon name) to display with the banner
    icon = Column(String, nullable=True)
    # optional start/end to control visibility
    start = Column(DateTime(timezone=True), nullable=True)
    end = Column(DateTime(timezone=True), nullable=True)
    # optional priority to order messages
    priority = Column(Integer, default=0)
    # placement indicates where the message should be shown (e.g. 'banner', 'frontpage', etc.)
    placement = Column(String, nullable=False, default='banner')
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")
    author = relationship("User")
