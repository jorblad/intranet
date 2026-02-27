import uuid

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    codename = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    role_permissions = relationship("RolePermission", back_populates="permission")
