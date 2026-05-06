import time
import uuid
import os
import secrets
import logging

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

logger = logging.getLogger(__name__)

# Standard permissions seeded on every fresh install so the role editor works
# out-of-the-box without requiring manual permission creation.
DEFAULT_PERMISSIONS = [
    ("activity.read", "Read access to activities"),
    ("activity.write", "Write access to activities"),
    ("schedule.read", "Read access to schedules"),
    ("schedule.write", "Write access to schedules"),
]


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
    # Determine the intended admin username (used both for lookup and creation)
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    try:
        had_existing_users = None
        admin_was_first_user = False
        try:
            # Determine whether any users exist before creating the admin user.
            had_existing_users = db.query(User.id).first() is not None

            # Look up the intended admin user explicitly by username instead of using an
            # arbitrary first() result, which has no deterministic ordering.
            admin_user = db.query(User).filter(User.username == admin_username).first()
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
            # Only treat this admin as the "first user" if there were no users before.
            if had_existing_users is not None:
                admin_was_first_user = not had_existing_users

        # Commit core seeding (e.g., admin user creation) before best-effort role seeding
        db.commit()

        # Determine whether this database had already been initialised before this
        # invocation started inserting default RBAC data. We check four RBAC tables
        # so that the signal remains True even after an admin deletes all users: as
        # long as any role, permission, role-permission link, or user-org-role row
        # exists the database is considered previously initialised.  We intentionally
        # do NOT use `had_existing_users` here because users can be deleted (including
        # the last admin), which would otherwise falsely signal a fresh install.
        previously_initialized = (
            db.query(Role.id).first() is not None
            or db.query(Permission.id).first() is not None
            or db.query(RolePermission.role_id).first() is not None
            or db.query(UserOrganizationRole.user_id).first() is not None
        )

        # Ensure a global `superadmin` role exists and, on a fresh DB, assign it to
        # the newly created admin user. Avoid granting superadmin to an arbitrary
        # existing user on a non-empty database.
        try:
            super_role = db.query(Role).filter(Role.name == "superadmin").first()
            if not super_role:
                super_role = Role(
                    name="superadmin",
                    description="Default superadmin role",
                    is_global=True,
                )
                try:
                    db.add(super_role)
                    db.flush()
                except sa_exc.IntegrityError:
                    # Another concurrent initializer may have created the superadmin
                    # role after our initial existence check but before this flush.
                    # Roll back this failed insert and re-query the role so we can
                    # continue with assignment logic using the existing row.
                    db.rollback()
                    super_role = (
                        db.query(Role).filter(Role.name == "superadmin").first()
                    )
                    if not super_role:
                        # If the role still does not exist, propagate the error so the
                        # outer handler can log and handle it as before.
                        raise
                    elif not getattr(super_role, "is_global", False):
                        # A concurrent initializer may have created a non-global 'superadmin' role.
                        # Ensure the existing role is marked as global so permission checks work correctly.
                        super_role.is_global = True
                        db.add(super_role)
            elif not getattr(super_role, "is_global", False):
                # Legacy databases might have a non-global 'superadmin' role.
                # Ensure the existing role is marked as global so permission checks work correctly.
                super_role.is_global = True
                db.add(super_role)

            # Decide whether we should grant the superadmin role to the admin user.
            # Normally this is only when the admin was created as the first user in
            # this init run, but we also want to repair a partial seed where the
            # admin exists as the only user but lacks the superadmin assignment.
            should_grant_superadmin = admin_was_first_user and admin_user is not None
            if not should_grant_superadmin and admin_user:
                try:
                    # Check if there exists any user other than the admin; avoid a full COUNT(*).
                    other_user = (
                        db.query(User.id)
                        .filter(User.id != admin_user.id)
                        .first()
                    )
                    if other_user is None:
                        # The admin is the only user in the system; treat this as a
                        # "fresh DB" and ensure they get superadmin.
                        should_grant_superadmin = True
                except Exception:
                    # If checking for additional users fails (e.g., during migrations),
                    # skip this best-effort repair and let startup continue.
                    pass

            if should_grant_superadmin:
                # If the admin user isn't already globally assigned the superadmin role, assign it.
                existing_assign = (
                    db.query(UserOrganizationRole)
                        .filter(
                            UserOrganizationRole.user_id == admin_user.id,
                            UserOrganizationRole.role_id == super_role.id,
                            UserOrganizationRole.organization_id.is_(None),
                        )
                        .first()
                )
                if not existing_assign:
                    assign = UserOrganizationRole(
                        user_id=admin_user.id,
                        role_id=super_role.id,
                        organization_id=None,
                    )
                    try:
                        # Attempt to insert the global superadmin assignment. In a concurrent
                        # init scenario another process may do the same, so we flush here
                        # to surface any integrity errors immediately.
                        db.add(assign)
                        db.flush()
                    except sa_exc.IntegrityError:
                        # A concurrent initializer may have created the same assignment
                        # after our existence check but before this flush. Roll back the
                        # failed insert and re-query to confirm the assignment exists.
                        db.rollback()
                        existing_assign = (
                            db.query(UserOrganizationRole)
                            .filter(
                                UserOrganizationRole.user_id == admin_user.id,
                                UserOrganizationRole.role_id == super_role.id,
                                UserOrganizationRole.organization_id.is_(None),
                            )
                            .first()
                        )
                        if not existing_assign:
                            # If the assignment still does not exist, propagate the error
                            # so the outer handler can log and handle it as before.
                            raise
        except Exception:
            # If this best-effort seeding fails, roll back just this part so the
            # session is usable for the final commit, and log for diagnosis.
            db.rollback()
            logger.exception(
                "Failed to ensure superadmin role and assignment during DB init; startup will continue."
            )

        # Ensure standard roles exist (organization-level roles like org_admin and member)
        default_roles = [
            ("org_admin", "Organization administrator", False),
            ("member", "Default organization member", False),
        ]
        try:
            # Use a nested transaction so failures here don't roll back earlier
            # uncommitted work in the outer transaction (for example, superadmin seeding).
            with db.begin_nested():
                for name, desc, is_global in default_roles:
                    r = db.query(Role).filter(Role.name == name).first()
                    if not r:
                        r = Role(name=name, description=desc, is_global=is_global)
                        db.add(r)
                db.flush()
        except sa_exc.IntegrityError:
            # Concurrent init may have inserted roles — the nested transaction has
            # been rolled back; re-check each default role and insert any still missing.
            try:
                with db.begin_nested():
                    for name, desc, is_global in default_roles:
                        existing_role = db.query(Role).filter(Role.name == name).first()
                        if not existing_role:
                            db.add(Role(name=name, description=desc, is_global=is_global))
                    db.flush()
            except sa_exc.IntegrityError:
                # Another concurrent initializer may still be racing. Log the failure of
                # this retry, then verify that the expected roles exist before continuing.
                logger.exception(
                    "IntegrityError while retrying to ensure default roles; "
                    "verifying role existence before continuing DB init."
                )
                missing_roles = []
                for name, desc, is_global in default_roles:
                    existing_role = db.query(Role).filter(Role.name == name).first()
                    if not existing_role:
                        missing_roles.append(name)
                if missing_roles:
                    logger.error(
                        "Default roles could not be fully ensured during DB init; "
                        "missing roles: %s. Startup will continue with a potentially "
                        "partially-seeded state.",
                        ", ".join(missing_roles),
                    )
        except Exception:
            # begin_nested() auto-rolls back its savepoint on exception; do not call
            # db.rollback() here as that would abort the whole outer transaction and
            # undo earlier best-effort seeding work.
            logger.exception("Failed to ensure default roles during DB init; startup will continue.")

        # Seed standard permissions only on a truly fresh install — indicated by
        # `previously_initialized` being False (no role, permission, role-permission,
        # or user-org-role rows existed before this invocation). Even then, only seed
        # when the permissions table is still empty so an admin who manually deleted
        # all permissions on an already-initialised DB does not have them resurrected.
        if not previously_initialized and db.query(Permission.id).first() is None:
            try:
                with db.begin_nested():
                    for codename, description in DEFAULT_PERMISSIONS:
                        db.add(Permission(codename=codename, description=description))
                    db.flush()
            except sa_exc.IntegrityError:
                # A concurrent init beat us to it; savepoint is already rolled back.
                logger.warning(
                    "Default permissions already seeded by a concurrent init; skipping."
                )
            except Exception:
                # begin_nested() auto-rolls back its savepoint on exception; do not call
                # db.rollback() here as that would abort the whole outer transaction.
                logger.exception("Failed to seed default permissions during DB init; startup will continue.")

        db.commit()
    finally:
        db.close()
