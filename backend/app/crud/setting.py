from sqlalchemy.orm import Session

from app.models import AppSetting


def get_setting(db: Session, key: str) -> str | None:
    s = db.query(AppSetting).filter(AppSetting.key == key).first()
    return s.value if s else None


def set_setting(db: Session, key: str, value: str) -> AppSetting:
    s = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not s:
        s = AppSetting(key=key, value=value)
        db.add(s)
    else:
        s.value = value
    db.commit()
    db.refresh(s)
    return s


def list_settings(db: Session) -> dict:
    rows = db.query(AppSetting).all()
    return {r.key: r.value for r in rows}
