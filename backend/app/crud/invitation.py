from datetime import datetime, timedelta
import secrets

from sqlalchemy.orm import Session

from app.models import Invitation


def create_invitation(db: Session, user_id: str, expires_hours: int | None = 48) -> Invitation:
    token = secrets.token_urlsafe(32)
    inv = Invitation(token=token, user_id=user_id)
    if expires_hours:
        inv.expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def get_invitation_by_token(db: Session, token: str) -> Invitation | None:
    return db.query(Invitation).filter(Invitation.token == token).first()


def mark_invitation_used(db: Session, inv: Invitation) -> None:
    inv.used = True
    db.add(inv)
    db.commit()
    db.refresh(inv)
