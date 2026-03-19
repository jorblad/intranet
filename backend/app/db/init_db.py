import time
import uuid
import os
import secrets
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
            # Create only the admin user. Username/password can be provided
            # via environment variables `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
            admin_username = os.getenv("ADMIN_USERNAME", "admin")
            admin_password = os.getenv("ADMIN_PASSWORD")
            if not admin_password:
                admin_password = secrets.token_urlsafe(16)
                print(
                    "init_db: No ADMIN_PASSWORD provided; generated a temporary admin "
                    f"password for user '{admin_username}': {admin_password}. "
                    "Please change this password immediately after first login."
                )
            admin = User(
                id=str(uuid.uuid4()),
                username=admin_username,
                display_name="Admin",
                hashed_password=get_password_hash(admin_password),
                is_active=True,
            )
            db.add(admin)
            db.flush()
            admin_user = admin

        # Ensure a global `superadmin` role exists and assign it to the admin user
        try:
            super_role = db.query(Role).filter(Role.name == "superadmin").first()
            if not super_role:
                super_role = Role(name="superadmin", description="Default superadmin role", is_global=True)
                db.add(super_role)
                db.flush()

            # If the admin user isn't already globally assigned the superadmin role, assign it
            existing_assign = (
                db.query(UserOrganizationRole)
                .filter(
                    UserOrganizationRole.user_id == admin_user.id,
                    UserOrganizationRole.role_id == super_role.id,
                    UserOrganizationRole.organization_id == None,
                )
                .first()
            )
            if not existing_assign:
                assign = UserOrganizationRole(user_id=admin_user.id, role_id=super_role.id, organization_id=None)
                db.add(assign)
        except Exception:
            # best-effort: don't block startup on seeding errors
            pass

        db.commit()
    finally:
        db.close()
