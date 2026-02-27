import uuid

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    language = Column(String, nullable=True)

    # relationships
    users = relationship("UserOrganizationRole", back_populates="organization")
