import uuid

from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import relationship

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    is_global = Column(Boolean, default=False)

    permissions = relationship("RolePermission", back_populates="role")
    user_assignments = relationship("UserOrganizationRole", back_populates="role")
