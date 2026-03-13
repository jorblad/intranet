from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, timezone

from app.models import AdminMessage


def create_admin_message(db: Session, title: str, body: str | None = None, organization_id: str | None = None,
                         start: datetime | None = None, end: datetime | None = None, created_by: str | None = None,
                         priority: int = 0, icon: str | None = None, title_i18n: dict | None = None, body_i18n: dict | None = None,
                         placement: str | None = 'banner') -> AdminMessage:
    msg = AdminMessage(
        title=title,
        body=body,
        title_i18n=title_i18n,
        body_i18n=body_i18n,
        placement=placement,
        organization_id=organization_id,
        start=start,
        end=end,
        created_by=created_by,
        priority=priority,
        icon=icon,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_admin_message(db: Session, msg_id: str):
    return db.query(AdminMessage).filter(AdminMessage.id == msg_id).first()


def list_admin_messages_for_org(db: Session, organization_id: str | None = None, active_only: bool = True, placement: str | None = None):
    # Now timestamp for active filtering
    now = datetime.now(timezone.utc)
    q = db.query(AdminMessage)
    if organization_id is None:
        # only global messages
        q = q.filter(AdminMessage.organization_id.is_(None))
    else:
        # include org-specific and global messages
        q = q.filter(or_(AdminMessage.organization_id == organization_id, AdminMessage.organization_id.is_(None)))

    if placement is not None:
        q = q.filter(AdminMessage.placement == placement)

    if active_only:
        q = q.filter(and_(
            or_(AdminMessage.start.is_(None), AdminMessage.start <= now),
            or_(AdminMessage.end.is_(None), AdminMessage.end >= now),
        ))

    return q.order_by(AdminMessage.priority.desc(), AdminMessage.start.asc()).all()


def update_admin_message(db: Session, msg: AdminMessage, **kwargs):
    for k, v in kwargs.items():
        # Apply all provided values, including None, so explicit nulls clear fields.
        # Callers should use exclude_unset (e.g. on Pydantic models) to avoid overwriting with missing fields.
        if hasattr(msg, k):
            setattr(msg, k, v)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def delete_admin_message(db: Session, msg: AdminMessage):
    db.delete(msg)
    db.commit()
