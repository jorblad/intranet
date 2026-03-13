import os
import base64
import json
from typing import Optional

import requests

from app.crud import get_setting
from app.db.session import get_db


def _get_mailjet_config(db=None):
    # Prefer environment variables; fall back to stored settings
    key = os.getenv('MAILJET_API_KEY')
    secret = os.getenv('MAILJET_API_SECRET')
    sender = os.getenv('MAILJET_SENDER')
    if key and secret and sender:
        return key, secret, sender
    # if DB session not provided, acquire one via get_db() and ensure cleanup
    db_gen = None
    try:
        if not db:
            try:
                db_gen = get_db()
                db = next(db_gen)
            except Exception:
                db = None
        if db:
            sk = get_setting(db, 'mailjet_api_key')
            ss = get_setting(db, 'mailjet_api_secret')
            sd = get_setting(db, 'mailjet_sender')
            if sk and ss and sd:
                return sk, ss, sd
        return None, None, None
    finally:
        if db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass


def send_invite_mail(to_email: str, subject: str, html: str, text: str, db=None) -> bool:
    key, secret, sender = _get_mailjet_config(db)
    if not key or not secret or not sender:
        return False
    url = 'https://api.mailjet.com/v3.1/send'
    payload = {
        "Messages": [
            {
                "From": {"Email": sender},
                "To": [{"Email": to_email}],
                "Subject": subject,
                "HTMLPart": html,
                "TextPart": text,
            }
        ]
    }
    try:
        resp = requests.post(url, auth=(key, secret), json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False
