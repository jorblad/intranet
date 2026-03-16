#!/usr/bin/env python3
"""Deduplicate schedules in the database.

Find schedules with the same (name, term_id, activity_id, organization_id)
and delete duplicate rows while keeping a single representative. Uses the
SQLAlchemy ORM so related `Schedule.entries` are cascaded/deleted safely.

Run from the repo root inside the backend container:

  docker compose -f docker-compose.dev.yml exec backend python tools/dedupe_schedules.py

Or locally (if your PYTHONPATH is configured):

  python backend/tools/dedupe_schedules.py

This script is idempotent and prints the changes it makes.
"""

from sqlalchemy import func
from app.db.session import SessionLocal
from app.models import Schedule


def main():
    session = SessionLocal()
    try:
        dup_groups = (
            session.query(
                Schedule.name,
                Schedule.term_id,
                Schedule.activity_id,
                Schedule.organization_id,
                func.count(Schedule.id).label('cnt'),
            )
            .group_by(
                Schedule.name,
                Schedule.term_id,
                Schedule.activity_id,
                Schedule.organization_id,
            )
            .having(func.count(Schedule.id) > 1)
            .all()
        )

        if not dup_groups:
            print('No duplicate schedules found.')
            return

        print(f'Found {len(dup_groups)} duplicate schedule groups. Processing...')

        for grp in dup_groups:
            name, term_id, activity_id, org_id, cnt = grp
            print(f"Group: name={name!r}, term_id={term_id}, activity_id={activity_id}, organization_id={org_id} -> {cnt} rows")

            # Build query to fetch all schedules in this group
            q = session.query(Schedule).filter(Schedule.name == name).filter(Schedule.term_id == term_id).filter(Schedule.activity_id == activity_id)
            if org_id is None:
                q = q.filter(Schedule.organization_id.is_(None))
            else:
                q = q.filter(Schedule.organization_id == org_id)

            schedules = q.order_by(Schedule.id).all()
            # Keep the first one, delete the rest
            keeper = schedules[0]
            to_delete = schedules[1:]
            print(f"  Keeping id={keeper.id}; deleting {len(to_delete)} duplicates")
            for s in to_delete:
                print(f"    Deleting schedule id={s.id}")
                session.delete(s)
        session.commit()
        print('Deduplication complete.')
    finally:
        session.close()


if __name__ == '__main__':
    main()
