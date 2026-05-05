from pydantic import BaseModel
from typing import Optional


class OrganizationBase(BaseModel):
    name: str
    language: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None


class OrganizationOut(OrganizationBase):
    id: str
    language: Optional[str] = None


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_global: Optional[bool] = False


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_global: Optional[bool] = None


class RoleOut(RoleBase):
    id: str


class PermissionBase(BaseModel):
    codename: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    codename: Optional[str] = None
    description: Optional[str] = None


class PermissionOut(PermissionBase):
    id: str


class AssignmentCreate(BaseModel):
    user_id: str
    role_id: str
    organization_id: Optional[str] = None


class AssignmentOut(BaseModel):
    id: str
    user_id: str
    role_id: str
    organization_id: Optional[str] = None

class AssignmentUpdate(BaseModel):
    role_id: Optional[str] = None
    organization_id: Optional[str] = None


class RolePermissionsOut(BaseModel):
    role_id: str
    permission_ids: list[str]
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None


class RolePermissionsUpdate(BaseModel):
    permission_ids: list[str]
    # resource_type/resource_id are passed as query params to the API; kept optional here for clarity


class ApplyProgramPreset(BaseModel):
    preset: str
    apply_to_existing: bool | None = False
    # optional list of specific resource ids to apply to (e.g. program ids)
    # new: activity_ids (preferred)
    activity_ids: list[str] | None = None
    resource_ids: list[str] | None = None
    # optional resource type (defaults to 'program' in UI flows)
    resource_type: str | None = None
