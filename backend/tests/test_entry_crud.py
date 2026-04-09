import uuid
import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models import User, Term, Schedule
from app.crud.entry import (
    create_entry,
    update_entry,
    bulk_create_entries,
    bulk_update_entries,
)


def _create_users_and_schedule(Session):
    db = Session()
    try:
        u1 = User(username="u1", display_name="User 1", hashed_password="x")
        u2 = User(username="u2", display_name="User 2", hashed_password="x")
        db.add_all([u1, u2])
        t = Term(id=str(uuid.uuid4()), name="T1")
        db.add(t)
        db.commit()
        s = Schedule(id=str(uuid.uuid4()), name="S1", term_id=t.id)
        db.add(s)
        db.commit()
        db.refresh(u1)
        db.refresh(u2)
        db.refresh(s)
        return str(u1.id), str(u2.id), str(s.id)
    finally:
        db.close()


def test_db_fixture_setup():
    # quick sanity check that the test DB can be created
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        assert db is not None
    finally:
        db.close()


def test_create_entry_cant_come_removes_assignments():
    # in-memory test DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    # prepare users and schedule
    u1_id, u2_id, schedule_id = _create_users_and_schedule(TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        entry = create_entry(
            db,
            schedule_id,
            datetime.date.today(),
            None,
            None,
            "Event",
            None,
            None,
            False,
            [u1_id, u2_id],
            [u1_id],
            [u1_id],
        )

        resp_ids = {str(u.id) for u in entry.responsible_users}
        devo_ids = {str(u.id) for u in entry.devotional_users}
        cant_ids = {str(u.id) for u in entry.cant_come_users}

        assert u1_id not in resp_ids
        assert u2_id in resp_ids
        assert u1_id not in devo_ids
        assert u1_id in cant_ids
    finally:
        db.close()


def test_update_entry_adding_cant_come_removes_assignments():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    u1_id, u2_id, schedule_id = _create_users_and_schedule(TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        entry = create_entry(
            db,
            schedule_id,
            datetime.date.today(),
            None,
            None,
            "Event2",
            None,
            None,
            False,
            [u1_id],
            [],
            [],
        )
        # now add cant_come for the same user
        updated = update_entry(db, entry, None, None, None, None, None, None, None, None, None, cant_come_ids=[u1_id])
        resp_ids = {str(u.id) for u in updated.responsible_users}
        cant_ids = {str(u.id) for u in updated.cant_come_users}

        assert u1_id not in resp_ids
        assert u1_id in cant_ids
    finally:
        db.close()


def test_bulk_create_entries_sanitizes():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    u1_id, u2_id, schedule_id = _create_users_and_schedule(TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        entries = [
            {
                "date": datetime.date.today(),
                "name": "E1",
                "responsible_ids": [u1_id, u2_id],
                "devotional_ids": [u1_id],
                "cant_come_ids": [u1_id],
            }
        ]
        created = bulk_create_entries(db, schedule_id, entries)
        assert len(created) == 1
        e = created[0]
        resp_ids = {str(u.id) for u in e.responsible_users}
        devo_ids = {str(u.id) for u in e.devotional_users}
        cant_ids = {str(u.id) for u in e.cant_come_users}

        assert u1_id not in resp_ids
        assert u2_id in resp_ids
        assert u1_id not in devo_ids
        assert u1_id in cant_ids
    finally:
        db.close()


def test_bulk_update_entries_sanitizes():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    u1_id, u2_id, schedule_id = _create_users_and_schedule(TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        entry = create_entry(
            db,
            schedule_id,
            datetime.date.today(),
            None,
            None,
            "E2",
            None,
            None,
            False,
            [u1_id],
            [],
            [],
        )
        updates = [{"id": entry.id, "cant_come_ids": [u1_id]}]
        updated = bulk_update_entries(db, schedule_id, updates)
        assert len(updated) == 1
        e = updated[0]
        resp_ids = {str(u.id) for u in e.responsible_users}
        cant_ids = {str(u.id) for u in e.cant_come_users}

        assert u1_id not in resp_ids
        assert u1_id in cant_ids
    finally:
        db.close()
