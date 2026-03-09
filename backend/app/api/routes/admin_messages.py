from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
import os
import json

from app.api.routes.auth import get_current_user
from app.core.rbac import require_org_admin_or_superadmin, is_superadmin
from app.db.session import get_db
from app.crud.admin_message import (
    create_admin_message,
    get_admin_message,
    list_admin_messages_for_org,
    update_admin_message,
    delete_admin_message,
)
from app.schemas.admin_message import AdminMessageCreate, AdminMessageUpdate, AdminMessageOut
# reuse the ws pubsub instance so published messages are forwarded to connected websockets
from app.api.routes.ws import _pubsub

router = APIRouter()


def _has_global_org_admin(user) -> bool:
    # superadmin qualifies
    if is_superadmin(user):
        return True
    # check for assigned global org_admin
    for a in getattr(user, "organization_roles", []) or []:
        if a.role and a.role.name == "org_admin" and a.role.is_global:
            return True
    return False


@router.get("/admin/messages")
def admin_messages_index(organization_id: str | None = None, active: bool = True, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # Anyone may read messages for an organization they are assigned to or global messages
    # if organization_id provided, ensure the user is assigned to the org (or allow superadmin)
    if organization_id is not None:
        # allow viewing org messages for assigned users or admins
        try:
            require_org_admin_or_superadmin(_user, organization_id)
        except Exception:
            # non-admin users may still view messages for orgs they belong to
            from app.core.rbac import user_assigned_to_org

            if not user_assigned_to_org(_user, organization_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to view messages for this organization")

    items = list_admin_messages_for_org(db, organization_id, active_only=active)
    return [AdminMessageOut(**{
        "id": i.id,
        "title": i.title,
        "body": i.body,
        "title_i18n": getattr(i, 'title_i18n', None),
        "body_i18n": getattr(i, 'body_i18n', None),
        "icon": i.icon,
        "organization_id": i.organization_id,
        "start": i.start,
        "end": i.end,
        "priority": i.priority,
        "created_by": i.created_by,
        "created_at": i.created_at,
        "updated_at": i.updated_at,
    }) for i in items]


@router.post("/admin/messages", status_code=status.HTTP_201_CREATED)
def admin_messages_create(payload: AdminMessageCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    org_id = payload.organization_id
    if org_id is None:
        # Creating a global message: require global org_admin or superadmin
        if not _has_global_org_admin(_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires global organization admin or superadmin to create global messages")
    else:
        require_org_admin_or_superadmin(_user, org_id)
        # validate organization exists
        from app.crud.organization import get_organization

        org = get_organization(db, org_id)
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    msg = create_admin_message(
        db,
        title=payload.title,
        body=payload.body,
        title_i18n=getattr(payload, 'title_i18n', None),
        body_i18n=getattr(payload, 'body_i18n', None),
        organization_id=org_id,
        start=payload.start,
        end=payload.end,
        created_by=getattr(_user, 'id', None),
        priority=payload.priority or 0,
        icon=getattr(payload, 'icon', None),
    )
    # publish event for realtime clients
    try:
        payload_event = {"type": "admin_message", "action": "create", "message": {
            "id": msg.id,
            "title": msg.title,
            "body": msg.body,
            "title_i18n": getattr(msg, 'title_i18n', None),
            "body_i18n": getattr(msg, 'body_i18n', None),
            "icon": msg.icon,
            "organization_id": msg.organization_id,
            "start": msg.start.isoformat() if getattr(msg, 'start', None) else None,
            "end": msg.end.isoformat() if getattr(msg, 'end', None) else None,
            "priority": msg.priority,
            "created_by": msg.created_by,
            "created_at": msg.created_at.isoformat() if getattr(msg, 'created_at', None) else None,
            "updated_at": msg.updated_at.isoformat() if getattr(msg, 'updated_at', None) else None,
        }}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": payload_event})
        try:
            _pubsub.schedule_publish(envelope)
        except Exception:
            pass
    except Exception:
        pass
    return AdminMessageOut(**{
        "id": msg.id,
        "title": msg.title,
        "body": msg.body,
        "title_i18n": getattr(msg, 'title_i18n', None),
        "body_i18n": getattr(msg, 'body_i18n', None),
        "icon": msg.icon,
        "organization_id": msg.organization_id,
        "start": msg.start,
        "end": msg.end,
        "priority": msg.priority,
        "created_by": msg.created_by,
        "created_at": msg.created_at,
        "updated_at": msg.updated_at,
    })


@router.get("/admin/messages/{msg_id}")
def admin_messages_detail(msg_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    msg = get_admin_message(db, msg_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    # Viewing rules: if org-specific, ensure user assigned or admin, otherwise allowed
    if msg.organization_id is not None:
        from app.core.rbac import user_assigned_to_org

        if not (_user and (getattr(_user, 'id', None) and user_assigned_to_org(_user, msg.organization_id))) and not is_superadmin(_user):
            # allow org admins (require_org_admin_or_superadmin will raise if not)
            try:
                require_org_admin_or_superadmin(_user, msg.organization_id)
            except Exception:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to view this message")

    return AdminMessageOut(**{
        "id": msg.id,
        "title": msg.title,
        "body": msg.body,
        "icon": msg.icon,
        "organization_id": msg.organization_id,
        "start": msg.start,
        "end": msg.end,
        "priority": msg.priority,
        "created_by": msg.created_by,
        "created_at": msg.created_at,
        "updated_at": msg.updated_at,
    })


@router.patch("/admin/messages/{msg_id}")
def admin_messages_update(msg_id: str, payload: AdminMessageUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    msg = get_admin_message(db, msg_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    # Permission: org-specific requires org_admin for that org (or superadmin). Global requires global org_admin or superadmin
    if msg.organization_id is None:
        if not _has_global_org_admin(_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires global org admin or superadmin to modify global messages")
    else:
        require_org_admin_or_superadmin(_user, msg.organization_id)

    # If changing target organization, validate the target org and require permission for it
    if payload.organization_id is not None and payload.organization_id != msg.organization_id:
        # require permission on new organization
        require_org_admin_or_superadmin(_user, payload.organization_id)
        from app.crud.organization import get_organization

        if not get_organization(db, payload.organization_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    updated = update_admin_message(db, msg, **payload.dict())
    # publish update event for realtime clients
    try:
        payload_event = {"type": "admin_message", "action": "update", "message": {
            "id": updated.id,
            "title": updated.title,
            "body": updated.body,
            "title_i18n": getattr(updated, 'title_i18n', None),
            "body_i18n": getattr(updated, 'body_i18n', None),
            "icon": updated.icon,
            "organization_id": updated.organization_id,
            "start": updated.start.isoformat() if getattr(updated, 'start', None) else None,
            "end": updated.end.isoformat() if getattr(updated, 'end', None) else None,
            "priority": updated.priority,
            "created_by": updated.created_by,
            "created_at": updated.created_at.isoformat() if getattr(updated, 'created_at', None) else None,
            "updated_at": updated.updated_at.isoformat() if getattr(updated, 'updated_at', None) else None,
        }}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": payload_event})
        try:
            _pubsub.schedule_publish(envelope)
        except Exception:
            pass
    except Exception:
        pass
    return AdminMessageOut(**{
        "id": updated.id,
        "title": updated.title,
        "body": updated.body,
        "title_i18n": getattr(updated, 'title_i18n', None),
        "body_i18n": getattr(updated, 'body_i18n', None),
        "icon": updated.icon,
        "organization_id": updated.organization_id,
        "start": updated.start,
        "end": updated.end,
        "priority": updated.priority,
        "created_by": updated.created_by,
        "created_at": updated.created_at,
        "updated_at": updated.updated_at,
    })


@router.delete("/admin/messages/{msg_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_messages_delete(msg_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    msg = get_admin_message(db, msg_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.organization_id is None:
        if not _has_global_org_admin(_user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires global org admin or superadmin to delete global messages")
    else:
        require_org_admin_or_superadmin(_user, msg.organization_id)
    # publish delete event before removing so we can include id/org
    try:
        payload_event = {"type": "admin_message", "action": "delete", "message": {"id": msg.id, "organization_id": msg.organization_id}}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": payload_event})
        try:
            _pubsub.schedule_publish(envelope)
        except Exception:
            pass
    except Exception:
        pass

    delete_admin_message(db, msg)
    return None
