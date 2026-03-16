#!/usr/bin/env python3
"""
One-off helper to republish all schedules via the app PubSub channel.

Run inside the backend container so it uses the app environment:

  docker compose exec backend python /app/scripts/republish_schedules.py

This script builds the same `rows` transform used by the schedules bulk
endpoints and schedules a publish on the app's pubsub instance.
"""
import json
import os
import sys
import traceback

from app.db.session import SessionLocal
from app.crud import list_schedules, list_entries
from app.api.routes.schedules import _entry_to_dict
from app.api.routes.ws import _pubsub


def main() -> int:
    print("Republish: starting")
    db = SessionLocal()
    try:
        schedules = list_schedules(db)
        rows_map = {}
        total_entries = 0
        for s in schedules:
            entries = list_entries(db, s.id)
            rows_map[str(s.id)] = [_entry_to_dict(e) for e in entries]
            total_entries += len(entries)

        transform = {"rows": rows_map}
        payload = {"type": "transform", "transform": transform}
        envelope = json.dumps({"__origin_pid": os.getpid(), "payload": payload})

        print(f"Republish: prepared envelope for {len(rows_map)} schedules, {total_entries} entries (len={len(envelope)})")
        ok = _pubsub.schedule_publish(envelope)
        print("Republish: schedule_publish returned:", ok)
        if ok:
            print("Republish: scheduled successfully")
            return 0
        else:
            print("Republish: scheduling failed", file=sys.stderr)
            return 2
    except Exception as e:
        print("Republish: error", e, file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
