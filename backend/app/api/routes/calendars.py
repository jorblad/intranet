from fastapi import APIRouter, Depends, Response, Query
from typing import List, Optional
from sqlalchemy.orm import Session, selectinload

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models import ScheduleEntry, User
from app.crud.organization import list_organizations_for_user
import datetime

router = APIRouter()


def _fmt_dt_utc(dt: datetime.datetime) -> str:
    # format as UTC time for ICS (YYYYMMDDTHHMMSSZ)
    if dt is None:
        return None
    if dt.tzinfo is None:
        # assume naive datetimes are UTC
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    dt_utc = dt.astimezone(datetime.timezone.utc)
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")


def _fmt_date(d: datetime.date) -> str:
    return d.strftime("%Y%m%d")


def _ical_escape(value: Optional[str]) -> str:
    """
    Escape text for use in iCalendar (RFC 5545) text values.
    Characters to escape: backslash, comma, semicolon, and newline.
    """
    if value is None:
        return ""
    s = str(value)
    # The order of replacements matters: backslash must be escaped first.
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    s = s.replace(",", "\\,")
    s = s.replace(";", "\\;")
    return s


def _entry_to_vevent(entry: ScheduleEntry, public_only: bool = False, emoji_prefix: Optional[str] = None) -> str:
    lines = []
    lines.append("BEGIN:VEVENT")
    uid = f"{entry.id}@intranet"
    lines.append(f"UID:{uid}")
    dtstamp = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines.append(f"DTSTAMP:{dtstamp}")
    if entry.start:
        dtstart = _fmt_dt_utc(entry.start)
        lines.append(f"DTSTART:{dtstart}")
        if entry.end:
            dtend = _fmt_dt_utc(entry.end)
            lines.append(f"DTEND:{dtend}")
    else:
        # all-day event on entry.date
        lines.append(f"DTSTART;VALUE=DATE:{_fmt_date(entry.date)}")
        # DTEND is exclusive in iCal, so add one day
        end_date = entry.date + datetime.timedelta(days=1)
        lines.append(f"DTEND;VALUE=DATE:{_fmt_date(end_date)}")

    # summary and (optionally) description
    summary = entry.name or ""
    if emoji_prefix:
        # ensure a single space between prefix and name
        summary = f"{emoji_prefix} {summary}" if summary else emoji_prefix
    escaped_summary = _ical_escape(summary)
    lines.append(f"SUMMARY:{escaped_summary}")
    if not public_only:
        desc_parts = []
        if entry.description:
            desc_parts.append(entry.description)
        if entry.notes:
            desc_parts.append(entry.notes)
        if desc_parts:
            # join using real newlines; _ical_escape will convert to \n for ICS
            desc = "\n".join(desc_parts)
            escaped_desc = _ical_escape(desc)
            lines.append(f"DESCRIPTION:{escaped_desc}")

    lines.append("END:VEVENT")
    return "\r\n".join(lines)


@router.get("/calendars/public.ics")
def public_calendar(db: Session = Depends(get_db)):
    entries = db.query(ScheduleEntry).filter(ScheduleEntry.public_event == True).all()
    cal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Intranet//EN",
    ]
    for e in entries:
        cal_lines.append(_entry_to_vevent(e, public_only=True))
    cal_lines.append("END:VCALENDAR")
    ics = "\r\n".join(cal_lines) + "\r\n"
    return Response(content=ics, media_type="text/calendar")


@router.get("/calendars/personal.ics")
def personal_calendar(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    activity_id: Optional[List[str]] = Query(None, description="Filter by activity id (repeatable)"),
):
    # include entries where user is responsible or devotional, but exclude if user can't come
    entries = (
        db.query(ScheduleEntry)
        .options(
            selectinload(ScheduleEntry.responsible_users),
            selectinload(ScheduleEntry.devotional_users),
            selectinload(ScheduleEntry.cant_come_users),
            selectinload(ScheduleEntry.schedule),
        )
        .all()
    )
    cal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Intranet//EN",
    ]
    # compute organizations the user belongs to so org-members can get schedule events
    try:
        assigned_orgs = {str(o.id) for o in list_organizations_for_user(db, _user.id)}
    except Exception:
        assigned_orgs = set()
    for e in entries:
        # relationships may be lazy; check membership
        user_id = _user.id
        responsible_ids = {u.id for u in e.responsible_users}
        devotional_ids = {u.id for u in e.devotional_users}
        cant_come_ids = {u.id for u in e.cant_come_users}
        # filter by activity if requested
        if activity_id:
            try:
                schedule_activity = getattr(e.schedule, 'activity_id', None)
            except Exception:
                schedule_activity = None
            if schedule_activity is None or str(schedule_activity) not in {str(a) for a in activity_id}:
                continue
        if user_id in cant_come_ids:
            continue
        # include if explicitly assigned to the entry, or if the entry belongs to a schedule
        # in an organization the user is a member of
        include = False
        if user_id in responsible_ids or user_id in devotional_ids:
            include = True
        else:
            schedule_org = getattr(e.schedule, 'organization_id', None)
            if schedule_org and str(schedule_org) in assigned_orgs:
                include = True
        if include:
            # add emoji prefixes for events where this user is responsible/devotional
            prefix_parts = []
            if user_id in responsible_ids:
                prefix_parts.append('👤')
            if user_id in devotional_ids:
                prefix_parts.append('🙏')
            prefix = ' '.join(prefix_parts) if prefix_parts else None
            cal_lines.append(_entry_to_vevent(e, emoji_prefix=prefix))
    cal_lines.append("END:VCALENDAR")
    ics = "\r\n".join(cal_lines) + "\r\n"
    return Response(content=ics, media_type="text/calendar")


@router.get("/calendars/personal/{token}.ics")
def personal_calendar_token(
    db: Session = Depends(get_db), token: str = None, activity_id: Optional[List[str]] = Query(None, description="Filter by activity id (repeatable)")
):
    # tokenized personal calendar (no auth required)
    if not token:
        return Response(content="", media_type="text/calendar", status_code=400)
    user = db.query(User).filter(User.calendar_token == token).first()
    if not user:
        return Response(content="", media_type="text/calendar", status_code=404)
    entries = db.query(ScheduleEntry).all()
    cal_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Intranet//EN",
    ]
    # include entries for org-members as well as explicit assignment
    try:
        assigned_orgs = {str(o.id) for o in list_organizations_for_user(db, user.id)}
    except Exception:
        assigned_orgs = set()
    for e in entries:
        user_id = user.id
        responsible_ids = {u.id for u in e.responsible_users}
        devotional_ids = {u.id for u in e.devotional_users}
        cant_come_ids = {u.id for u in e.cant_come_users}
        # filter by activity if requested
        if activity_id:
            try:
                schedule_activity = getattr(e.schedule, 'activity_id', None)
            except Exception:
                schedule_activity = None
            if schedule_activity is None or str(schedule_activity) not in {str(a) for a in activity_id}:
                continue
        if user_id in cant_come_ids:
            continue
        include = False
        if user_id in responsible_ids or user_id in devotional_ids:
            include = True
        else:
            schedule_org = getattr(e.schedule, 'organization_id', None)
            if schedule_org and str(schedule_org) in assigned_orgs:
                include = True
        if include:
            prefix_parts = []
            if user_id in responsible_ids:
                prefix_parts.append('👤')
            if user_id in devotional_ids:
                prefix_parts.append('🙏')
            prefix = ' '.join(prefix_parts) if prefix_parts else None
            cal_lines.append(_entry_to_vevent(e, emoji_prefix=prefix))
    cal_lines.append("END:VCALENDAR")
    ics = "\r\n".join(cal_lines) + "\r\n"
    return Response(content=ics, media_type="text/calendar")


@router.get('/calendars/activity/{activity_id}.ics')
def activity_public_calendar(activity_id: str, db: Session = Depends(get_db)):
    # public calendar per-activity: all public events for schedules linked to this activity
    entries = (
        db.query(ScheduleEntry)
        .join(ScheduleEntry.schedule)
        .filter(ScheduleEntry.public_event == True)
        .filter(ScheduleEntry.schedule.has(activity_id=activity_id))
        .all()
    )
    cal_lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Intranet//EN',
    ]
    for e in entries:
        cal_lines.append(_entry_to_vevent(e, public_only=True))
    cal_lines.append('END:VCALENDAR')
    ics = '\r\n'.join(cal_lines) + '\r\n'
    return Response(content=ics, media_type='text/calendar')
