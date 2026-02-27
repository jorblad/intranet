import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class UserOrganizationRole(Base):
    __tablename__ = "user_organization_roles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=True)
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)

    user = relationship("User", back_populates="organization_roles")
    organization = relationship("Organization", back_populates="users")
    role = relationship("Role", back_populates="user_assignments")
