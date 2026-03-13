from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_superadmin
from app.db.session import get_db
from app.crud import list_settings, set_setting, get_setting
from app.core.mailer import send_invite_mail
import secrets
from urllib.parse import urlparse

router = APIRouter()


def _normalize_setting_value(value):
    """
    Normalize stored setting values so that an empty string used as a
    sentinel for "no value" is exposed to API clients as None.
    """
    return None if value == '' else value


@router.get('/admin/settings')
def admin_settings(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    # Return all stored settings (superadmins will see and may change them via PATCH)
    settings = list_settings(db)
    # Normalize any sentinel empty-string values to None for clients
    normalized = {
        key: _normalize_setting_value(value)
        for key, value in (settings or {}).items()
    }
    return {"data": normalized}


@router.get('/public/settings')
def public_settings(db: Session = Depends(get_db)):
    # Minimal, public settings useful for unauthenticated pages (login)
    keys = ['default_user_language', 'invite_default_language']
    out = {}
    for k in keys:
        try:
            out[k] = _normalize_setting_value(get_setting(db, k))
        except Exception:
            out[k] = None
    return {"data": out}


@router.patch('/admin/settings')
def admin_update_settings(payload: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    updated = {}
    for k, v in (payload or {}).items():
        try:
            # Preserve existing behavior of stringifying non-None values, but
            # store None directly when the client sends null instead of using ''.
            value_to_store = None if v is None else str(v)
            s = set_setting(db, k, value_to_store)
            updated[k] = _normalize_setting_value(getattr(s, 'value', None))
        except Exception:
            pass
    return {"data": updated}


@router.post('/admin/settings/test_send')
def admin_test_send(payload: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    to_email = (payload or {}).get('to_email')
    if not to_email:
        raise HTTPException(status_code=400, detail='to_email is required')

    subject = 'Intranet: test email'
    html = '<p>This is a test email from your Intranet installation.</p>'
    text = 'This is a test email from your Intranet installation.'
    sent = send_invite_mail(to_email, subject, html, text, db=db)
    if not sent:
        raise HTTPException(status_code=500, detail='Failed to send test email. Ensure Mailjet settings are configured.')
    return {"data": {"sent": True}}


@router.post('/admin/settings/test_send_reset')
def admin_test_send_reset(payload: dict, request: Request, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    to_email = (payload or {}).get('to_email')
    lang = (payload or {}).get('language')
    display = (payload or {}).get('display') or 'Test user'
    username = (payload or {}).get('username') or 'testuser'
    if not to_email:
        raise HTTPException(status_code=400, detail='to_email is required')

    # determine frontend_base
    frontend_base = get_setting(db, 'frontend_base_url') or ''
    frontend_base = (frontend_base or '').strip()
    if not frontend_base:
        origin = request.headers.get('origin') or request.headers.get('referer') or ''
        if origin:
            try:
                p = urlparse(origin)
                if p.scheme and p.netloc:
                    frontend_base = f"{p.scheme}://{p.netloc}"
            except Exception:
                frontend_base = origin
    if frontend_base:
        frontend_base = frontend_base.rstrip('/')

    def _get_template(key_base: str, lg: str | None):
        if lg:
            key = f"{key_base}_{lg}"
            v = get_setting(db, key)
            if v:
                return v, key
            base = (lg.split('-')[0] if '-' in lg else lg)
            if base and base != lg:
                key2 = f"{key_base}_{base}"
                v2 = get_setting(db, key2)
                if v2:
                    return v2, key2
        v3 = get_setting(db, key_base)
        if v3:
            return v3, key_base
        return None, None

    subject_tpl, subject_key = _get_template('password_reset_subject', lang)
    html_tpl, html_key = _get_template('password_reset_html', lang)
    text_tpl, text_key = _get_template('password_reset_text', lang)

    if not subject_tpl:
        subject_tpl = 'Återställ ditt lösenord' if (lang and str(lang).lower().startswith('sv')) else 'Reset your password'
    if not html_tpl:
        html_tpl = '<p>Hej {display},</p><p>Klicka <a href="{link}">här</a> för att återställa ditt lösenord.</p>' if (lang and str(lang).lower().startswith('sv')) else '<p>Hello {display},</p><p>Click <a href="{link}">this link</a> to reset your password.</p>'
    if not text_tpl:
        text_tpl = 'Hej {display},\n\nÖppna följande länk för att återställa ditt lösenord: {link}\n' if (lang and str(lang).lower().startswith('sv')) else 'Hello {display},\n\nOpen the following link to reset your password: {link}\n'

    demo_token = secrets.token_urlsafe(8)
    link = f"{frontend_base}/#/invite/accept?token={demo_token}" if frontend_base else f"#/invite/accept?token={demo_token}"

    try:
        subject = subject_tpl.format(display=display, username=username, link=link)
    except Exception:
        subject = subject_tpl
    try:
        html = html_tpl.format(display=display, username=username, link=link)
    except Exception:
        html = html_tpl
    try:
        text = text_tpl.format(display=display, username=username, link=link)
    except Exception:
        text = text_tpl

    sent = send_invite_mail(to_email, subject, html, text, db=db)
    if not sent:
        raise HTTPException(status_code=500, detail='Failed to send test reset email. Ensure Mailjet settings are configured.')
    return {"data": {"sent": True, "language_used": lang or None, "template_keys": {"subject": subject_key, "html": html_key, "text": text_key}}}
