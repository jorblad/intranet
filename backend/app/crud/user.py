from sqlalchemy.orm import Session

from app.core.security import get_password_hash
import uuid
from app.models import User
import json


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def list_users(db: Session) -> list[User]:
    return db.query(User).all()


def create_user(db: Session, username: str, display_name: str, password: str) -> User:
    user = User(
        username=username,
        display_name=display_name,
        hashed_password=get_password_hash(password),
        is_active=True,
    )
    # generate a calendar token for shareable personal calendar links
    user.calendar_token = str(uuid.uuid4())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user: User,
    display_name: str | None,
    password: str | None,
    is_active: bool | None,
    username: str | None = None,
    language: str | None = None,
    personal_calendar_activity_ids: list[str] | None = None,
) -> User:
    # allow username change if provided and not taken
    if username is not None and username != user.username:
        # ensure username uniqueness
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise ValueError("username_taken")
        user.username = username

    if display_name is not None:
        user.display_name = display_name
    if language is not None:
        user.language = language
    if password is not None:
        user.hashed_password = get_password_hash(password)
    if is_active is not None:
        user.is_active = is_active
    # persist selected activity ids as JSON string (or clear if None/empty)
    if personal_calendar_activity_ids is not None:
        try:
            if isinstance(personal_calendar_activity_ids, list):
                user.personal_calendar_activity_ids = json.dumps(personal_calendar_activity_ids)
            elif isinstance(personal_calendar_activity_ids, str):
                # allow passing raw JSON string
                user.personal_calendar_activity_ids = personal_calendar_activity_ids
            else:
                user.personal_calendar_activity_ids = None
        except Exception:
            user.personal_calendar_activity_ids = None
    db.commit()
    db.refresh(user)
    return user


def regenerate_calendar_token(db: Session, user: User) -> str:
    token = str(uuid.uuid4())
    user.calendar_token = token
    db.commit()
    db.refresh(user)
    return token


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()
