from sqlalchemy.orm import Session

from app.models import Activity


def list_activities(db: Session, organization_id: str | None = None):
    q = db.query(Activity)
    if organization_id is not None:
        q = q.filter(Activity.organization_id == organization_id)
    return q.all()


def get_activity(db: Session, activity_id: str):
    return db.query(Activity).filter(Activity.id == activity_id).first()


def create_activity(db: Session, name: str, organization_id: str | None = None, default_start_time=None, default_end_time=None) -> Activity:
    act = Activity(name=name, organization_id=organization_id)
    if default_start_time is not None:
        act.default_start_time = default_start_time
    if default_end_time is not None:
        act.default_end_time = default_end_time
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


def update_activity(db: Session, activity: Activity, name: str | None = None, organization_id: str | None = None, default_start_time=None, default_end_time=None):
    if name is not None:
        activity.name = name
    if organization_id is not None:
        activity.organization_id = organization_id
    if default_start_time is not None:
        activity.default_start_time = default_start_time
    if default_end_time is not None:
        activity.default_end_time = default_end_time
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def delete_activity(db: Session, activity: Activity) -> None:
    db.delete(activity)
    db.commit()
