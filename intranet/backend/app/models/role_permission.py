import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)
    permission_id = Column(String, ForeignKey("permissions.id"), nullable=False)

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="role_permissions")
