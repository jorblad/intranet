import time
import uuid
from datetime import date

from sqlalchemy import exc as sa_exc

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import SessionLocal, engine
from sqlalchemy import inspect, text
from app.models import (
    Schedule,
    ScheduleEntry,
    Term,
    User,
    Organization,
    Role,
    Permission,
    RolePermission,
    UserOrganizationRole,
    Activity,
)


def init_db() -> None:
    # Wait for the database to be available (useful in Docker dev where DB may start after backend)
    max_attempts = 12
    attempt = 0
    while attempt < max_attempts:
        try:
            with engine.connect():
                break
        except sa_exc.OperationalError:
            attempt += 1
            time.sleep(2)
    # If still not connected, let the following create_all raise the error to surface it
    Base.metadata.create_all(bind=engine)

    # Ensure legacy DBs get the new `activity_id` column if it's missing.
    try:
        inspector = inspect(engine)
        if 'schedules' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('schedules')]
            if 'activity_id' not in cols:
                # Add the nullable activity_id column without enforcing FK to avoid migration tooling here.
                with engine.begin() as conn:
                    conn.execute(text('ALTER TABLE schedules ADD COLUMN activity_id VARCHAR'))
            # If legacy program_id column exists, drop it to match the current model
            if 'program_id' in cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE schedules DROP COLUMN program_id'))
                except Exception:
                    # best-effort: if drop fails, attempt to make it nullable
                    try:
                        with engine.begin() as conn:
                            conn.execute(text('ALTER TABLE schedules ALTER COLUMN program_id DROP NOT NULL'))
                    except Exception:
                        pass
    except Exception:
        # If any DB-specific issue occurs, continue and let later operations surface errors.
        pass

    db = SessionLocal()
    skip_seeding = False
    try:
        try:
            admin_user = db.query(User).first()
        except Exception as e:
            # If the users table or new columns are missing (during migration),
            # rollback the session to clear any aborted transaction and skip all
            # seeding to allow migrations to run. The app will retry seeding on
            # next startup after migrations are applied.
            try:
                db.rollback()
            except Exception:
                pass
            admin_user = None
            skip_seeding = True
            print('init_db: skipping DB seeding due to DB state:', e)

        if skip_seeding:
            # Close session and return early so migrations can be applied.
            return

        if not admin_user:
            admin = User(
                id=str(uuid.uuid4()),
                username="admin",
                display_name="Admin",
                hashed_password=get_password_hash("password"),
                is_active=True,
            )
            db.add(admin)
            db.flush()
            admin_user = admin

        # Seed basic roles and permissions
        if not db.query(Role).filter(Role.name == 'superadmin').first():
            super_r = Role(id=str(uuid.uuid4()), name='superadmin', description='Full access to all organizations', is_global=True)
            org_admin_r = Role(id=str(uuid.uuid4()), name='org_admin', description='Organization administrator')
            member_r = Role(id=str(uuid.uuid4()), name='member', description='Organization member')
            db.add_all([super_r, org_admin_r, member_r])
            db.flush()

            # assign admin_user as superadmin (global role with no organization)
            if admin_user:
                uar = UserOrganizationRole(id=str(uuid.uuid4()), user_id=admin_user.id, organization_id=None, role_id=super_r.id)
                db.add(uar)


        activity_a = None
        activity_b = None
        if not db.query(Term).first():
            term_fall = Term(id=str(uuid.uuid4()), name="Host 2023")
            term_winter = Term(id=str(uuid.uuid4()), name="Vinter 2024")
            db.add_all([term_fall, term_winter])
            db.flush()

            activity_a = Activity(
                id=str(uuid.uuid4()),
                name="Ungdomskvall",
                organization_id=None,
            )
            activity_b = Activity(
                id=str(uuid.uuid4()),
                name="Junior",
                organization_id=None,
            )
            db.add_all([activity_a, activity_b])

        if not db.query(Schedule).first():
            if not activity_a:
                activity_a = db.query(Activity).first()
            if activity_a:
                schedule = Schedule(
                    id=str(uuid.uuid4()),
                    name=f"Schema {activity_a.name}",
                    term_id=term_fall.id,
                    activity_id=activity_a.id,
                )
                db.add(schedule)
                db.flush()

                entry = ScheduleEntry(
                    id=str(uuid.uuid4()),
                    schedule_id=schedule.id,
                    date=date(2023, 9, 6),
                    name="Start",
                    description="Kickoff",
                    notes="",
                    public_event=True,
                )
                if admin_user:
                    entry.responsible_users = [admin_user]
                db.add(entry)

        db.commit()
    finally:
        db.close()
