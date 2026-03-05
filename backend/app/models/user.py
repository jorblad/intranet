import uuid

from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    language = Column(String, nullable=True)
    # persistent token for shareable personal calendar links
    calendar_token = Column(String, unique=True, index=True, nullable=True)
    # JSON-encoded list of activity ids the user prefers for their personal calendar URL
    personal_calendar_activity_ids = Column(String, nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user")
    organization_roles = relationship("UserOrganizationRole", back_populates="user")
