import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class RolePermissionResource(Base):
    __tablename__ = "role_permission_resources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)
    permission_id = Column(String, ForeignKey("permissions.id"), nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)

    role = relationship("Role")
    permission = relationship("Permission")
