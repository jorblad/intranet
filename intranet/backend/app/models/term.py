import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class Term(Base):
    __tablename__ = "terms"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)

