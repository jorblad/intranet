from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_superadmin
from app.core.rbac import require_org_admin_or_superadmin
from app.crud import (
    create_user,
    delete_user,
    get_user_by_id,
    list_users,
    update_user,
    create_invitation,
    get_invitation_by_token,
    mark_invitation_used,
    get_setting,
)
from app.crud import assign_role
from app.core.mailer import send_invite_mail
from app.models import User
from app.db.session import get_db
from app.schemas.user import UserCreate, UserUpdate
from app.schemas.user import UserSelfUpdate, InviteCreate, InviteAccept
from app.crud.user import regenerate_calendar_token
import os
from datetime import datetime, timezone

router = APIRouter()


@router.get("/user/user")
def users_index(organization_id: str | None = None, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # If an organization_id filter is provided, only return users assigned to that org
    # and ensure the requester is assigned to that org or is superadmin.
    from app.core.rbac import is_superadmin, user_assigned_to_org
    from app.models import UserOrganizationRole

    if organization_id is not None:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view users for this organization")
        users = (
            db.query(User)
            .join(UserOrganizationRole, UserOrganizationRole.user_id == User.id)
            .filter(UserOrganizationRole.organization_id == organization_id)
            .all()
        )
    else:
        users = list_users(db)

    return {
        "data": [
            {
                "id": user.id,
                "type": "user",
                "attributes": {"display_name": user.display_name, "username": user.username, "email": getattr(user, 'email', None), "language": getattr(user, 'language', None)},
            }
            for user in users
        ]
    }


@router.get("/user/user/{user_id}")
def users_detail(
    user_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {
        "data": {
            "id": user.id,
            "type": "user",
            "attributes": {"display_name": user.display_name, "username": user.username, "email": getattr(user, 'email', None), "language": getattr(user, 'language', None)},
        }
    }



@router.get("/user/me")
def users_me(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # return current user with role assignments
    assignments = []
    for a in getattr(_user, "organization_roles", []) or []:
        assignments.append(
            {
                "id": a.id,
                "role": {"id": a.role.id, "name": a.role.name, "is_global": a.role.is_global} if a.role else None,
                "organization_id": a.organization_id,
            }
        )

    is_super = any((a.role and a.role.name == "superadmin" and a.role.is_global) for a in getattr(_user, "organization_roles", []) or [])

    # attempt to decode stored JSON activity ids
    import json
    pca = None
    try:
        raw = getattr(_user, 'personal_calendar_activity_ids', None)
        if raw:
            pca = json.loads(raw)
    except Exception:
        pca = None

    return {
        "data": {
            "id": _user.id,
            "type": "user",
            "attributes": {
                "username": _user.username,
                "display_name": _user.display_name,
                "calendar_token": getattr(_user, 'calendar_token', None),
                "is_superadmin": is_super,
                "language": getattr(_user, 'language', None),
                "personal_calendar_activity_ids": pca,
                "assignments": assignments,
            },
        }
    }



@router.post("/user/user", status_code=status.HTTP_201_CREATED)
def users_create(
    payload: UserCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    require_superadmin(_user)
    try:
        user = create_user(db, payload.username, payload.display_name, payload.password, email=getattr(payload, 'email', None))
    except ValueError as e:
        if str(e) == 'username_taken':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        if str(e) == 'email_taken':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already taken")
        raise
    return {
        "data": {
            "id": user.id,
            "type": "user",
            "attributes": {"display_name": user.display_name, "username": user.username},
        }
    }


@router.patch("/user/user/{user_id}")
def users_update(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    require_superadmin(_user)
    try:
        user = update_user(
            db,
            user,
            payload.display_name,
            payload.password,
            payload.is_active,
            username=payload.username,
            language=payload.language,
            email=payload.email,
        )
    except ValueError as e:
        if str(e) == "username_taken":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        if str(e) == "email_taken":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already taken")
        raise
    return {
        "data": {
            "id": user.id,
            "type": "user",
            "attributes": {"display_name": user.display_name},
        }
    }



@router.post('/user/user/{user_id}/reset_password')
def users_reset_password(user_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # generate a random password (uuid4 hex substring)
    import uuid
    new_pw = uuid.uuid4().hex[:12]
    user = update_user(db, user, None, new_pw, None)
    return {"data": {"id": user.id, "new_password": new_pw}}


@router.post('/user/user/{user_id}/send_reset_link')
def users_send_reset_link(user_id: str, request: Request, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Admin-only: create a short-lived reset invitation and email it to the user."""
    require_superadmin(_user)
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # create a short-lived invitation token for password reset
    inv = create_invitation(db, user.id, expires_hours=48)

    # determine frontend link
    frontend_base = get_setting(db, 'frontend_base_url') or os.getenv('FRONTEND_BASE_URL', '')
    frontend_base = (frontend_base or '').strip()
    if not frontend_base:
        origin = request.headers.get('origin') or request.headers.get('referer') or ''
        if origin:
            try:
                from urllib.parse import urlparse
                p = urlparse(origin)
                if p.scheme and p.netloc:
                    frontend_base = f"{p.scheme}://{p.netloc}"
            except Exception:
                frontend_base = origin
    if frontend_base:
        frontend_base = frontend_base.rstrip('/')
        link = f"{frontend_base}/#/invite/accept?token={inv.token}"
    else:
        link = f"#/invite/accept?token={inv.token}"

    # resolve templates (use user's language when available)
    def _get_template_and_key(key_base: str):
        lang = getattr(user, 'language', None)
        if lang:
            key = f"{key_base}_{lang}"
            v = get_setting(db, key)
            if v:
                return v, key
            base = (lang.split('-')[0] if '-' in lang else lang)
            if base and base != lang:
                key2 = f"{key_base}_{base}"
                v2 = get_setting(db, key2)
                if v2:
                    return v2, key2
        v3 = get_setting(db, key_base)
        if v3:
            return v3, key_base
        return None, None

    subject_template, subject_key = _get_template_and_key('password_reset_subject')
    html_template, html_key = _get_template_and_key('password_reset_html')
    text_template, text_key = _get_template_and_key('password_reset_text')

    if not subject_template:
        if getattr(user, 'language', None) and str(user.language).lower().startswith('sv'):
            subject_template = 'Återställ ditt lösenord'
        else:
            subject_template = 'Reset your password'
    if not html_template:
        if getattr(user, 'language', None) and str(user.language).lower().startswith('sv'):
            html_template = '<p>Hej {display} ({username}),</p><p>Klicka <a href="{link}">här</a> för att återställa ditt lösenord.</p><p>Ditt användarnamn är <strong>{username}</strong>.</p>'
        else:
            html_template = '<p>Hello {display},</p><p>Click <a href="{link}">this link</a> to reset your password.</p>'
    if not text_template:
        if getattr(user, 'language', None) and str(user.language).lower().startswith('sv'):
            text_template = 'Hej {display} ({username}),\n\nÖppna följande länk för att återställa ditt lösenord: {link}\n\nDitt användarnamn: {username}\n'
        else:
            text_template = 'Hello {display},\n\nOpen the following link to reset your password: {link}\n'

    display = user.display_name or user.username
    try:
        subject = subject_template.format(display=display, username=user.username, link=link)
    except Exception:
        subject = subject_template
    try:
        html = html_template.format(display=display, username=user.username, link=link)
    except Exception:
        html = html_template
    try:
        text = text_template.format(display=display, username=user.username, link=link)
    except Exception:
        text = text_template

    sent = False
    try:
        to_addr = getattr(user, 'email', None) or user.username
        sent = send_invite_mail(to_addr, subject, html, text, db=db)
    except Exception:
        sent = False

    return {"data": {"email_sent": bool(sent), "invite_link": link, "template_keys": {"subject": subject_key, "html": html_key, "text": text_key}}}



@router.post('/user/invite', status_code=status.HTTP_201_CREATED)
def invite_user(payload: InviteCreate, request: Request, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # allow org admins to invite users to their organization(s); global (organization_id=None) assignments require superadmin
    from app.core.rbac import is_superadmin, user_assigned_to_org

    # validate assignment permissions
    assignments = payload.assignments or []
    for a in assignments:
        if a.organization_id is None:
            require_superadmin(_user)
        else:
            if not (is_superadmin(_user) or user_assigned_to_org(_user, a.organization_id)):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to assign users to this organization")

    # determine language to use for templates
    lang = payload.language
    if not lang:
        # prefer an explicit invite default language, then fall back to server default
        default_lang = get_setting(db, 'invite_default_language') or get_setting(db, 'default_user_language')
        if default_lang:
            lang = default_lang

    # create user with a temporary random password
    import secrets
    temp_pw = secrets.token_urlsafe(12)
    display = payload.display_name or payload.username
    try:
        user = create_user(db, payload.username, display, temp_pw, email=getattr(payload, 'email', None))
    except ValueError as e:
        if str(e) == 'username_taken':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        if str(e) == 'email_taken':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already taken")
        raise
    # apply language if provided
    if lang:
        user.language = lang
        db.add(user)
        db.commit()
        db.refresh(user)

    # apply assignments
    for a in assignments:
        assign_role(db, user.id, a.role_id, a.organization_id)

    # create invitation token
    inv = create_invitation(db, user.id, expires_hours=payload.expires_hours)

    # determine frontend link (available in response regardless of email send)
    frontend_base = get_setting(db, 'frontend_base_url') or os.getenv('FRONTEND_BASE_URL', '')
    frontend_base = (frontend_base or '').strip()
    if not frontend_base:
        origin = request.headers.get('origin') or request.headers.get('referer') or ''
        if origin:
            try:
                from urllib.parse import urlparse
                p = urlparse(origin)
                if p.scheme and p.netloc:
                    frontend_base = f"{p.scheme}://{p.netloc}"
            except Exception:
                frontend_base = origin
    if frontend_base:
        frontend_base = frontend_base.rstrip('/')
        try:
            # remove any existing hash fragment from the base so we can append a canonical hash route
            if '#' in frontend_base:
                frontend_base = frontend_base.split('#', 1)[0].rstrip('/')
        except Exception:
            pass
        # Use a hash-based route by default so SPA routers in hash mode land on the correct page
        link = f"{frontend_base}/#/invite/accept?token={inv.token}"
    else:
        # when no absolute base is available, provide a hash-only path which works when clicked
        link = f"#/invite/accept?token={inv.token}"

    # send email if requested and configured
    sent = False
    rendered_preview = None
    subject_key = html_key = text_key = None
    if payload.send_email:
        # resolve templates and which keys were used (exact lang, base lang, or generic)
        def _get_template_and_key(key_base: str):
            if lang:
                key = f"{key_base}_{lang}"
                v = get_setting(db, key)
                if v:
                    return v, key
                base = (lang.split('-')[0] if '-' in lang else lang)
                if base and base != lang:
                    key2 = f"{key_base}_{base}"
                    v2 = get_setting(db, key2)
                    if v2:
                        return v2, key2
            v3 = get_setting(db, key_base)
            if v3:
                return v3, key_base
            return None, None

        subject_template, subject_key = _get_template_and_key('invite_subject')
        html_template, html_key = _get_template_and_key('invite_html')
        text_template, text_key = _get_template_and_key('invite_text')

        if not subject_template:
            if lang and str(lang).lower().startswith('sv'):
                subject_template = 'Du är inbjuden till Intranätet'
            else:
                subject_template = "You're invited to the Intranet"
            subject_key = 'default'
        if not html_template:
            if lang and str(lang).lower().startswith('sv'):
                html_template = '<p>Hej {display},</p><p>Du har blivit inbjuden till intranätet. Klicka <a href="{link}">här</a> för att ange ditt lösenord och logga in.</p>'
            else:
                html_template = "<p>Hello {display},</p><p>You were invited to the intranet. Click <a href=\"{link}\">this link</a> to set your password and sign in.</p>"
            html_key = 'default'
        if not text_template:
            if lang and str(lang).lower().startswith('sv'):
                text_template = 'Hej {display},\n\nÖppna följande länk för att ange ditt lösenord: {link}\n'
            else:
                text_template = "Hello {display},\n\nOpen the following link to set your password: {link}\n"
            text_key = 'default'

        try:
            subject = subject_template.format(display=display, username=payload.username, link=link)
        except Exception:
            subject = subject_template
        try:
            html = html_template.format(display=display, username=payload.username, link=link)
        except Exception:
            html = html_template
        try:
            text = text_template.format(display=display, username=payload.username, link=link)
        except Exception:
            text = text_template

        rendered_preview = {"subject": subject, "html": html, "text": text}

        try:
            to_addr = getattr(payload, 'email', None) or payload.username
            sent = send_invite_mail(to_addr, subject, html, text, db=db)
        except Exception:
            sent = False

    response_data = {"user_id": user.id, "invitation_id": inv.id, "email_sent": bool(sent), "lang_used": lang or None, "invite_link": link}
    try:
        if rendered_preview is not None:
            response_data['rendered_email'] = rendered_preview
        response_data['template_keys'] = {"subject": subject_key, "html": html_key, "text": text_key}
    except Exception:
        pass
    return {"data": response_data}


@router.get('/user/invite')
def get_invite_info(token: str, db: Session = Depends(get_db)):
    """Public endpoint returning basic invite info for a given token.

    This endpoint is tolerant to minor URL-encoding or normalization issues
    caused by client-side hash routing. It will attempt multiple lookup
    strategies and include debug info about which token was matched.
    """
    from urllib.parse import unquote
    from app.models import Invitation as InvitationModel

    token_raw = (token or '').strip()
    tried = []

    def _found(inv, method):
        user = get_user_by_id(db, inv.user_id) if inv else None
        return {
            "data": {
                "token_received": token_raw,
                "matched_token": inv.token if inv else None,
                "match_method": method,
                "invitation_id": inv.id if inv else None,
                "used": bool(inv.used) if inv else None,
                "expires_at": inv.expires_at.isoformat() if (inv and getattr(inv, 'expires_at', None)) else None,
                "user": {
                    "id": user.id if user else None,
                    "username": user.username if user else None,
                    "display_name": user.display_name if user else None,
                    "email": getattr(user, 'email', None) if user else None,
                    "language": getattr(user, 'language', None) if user else None,
                },
            }
        }

    # 1) exact
    tried.append(('exact', token_raw))
    inv = get_invitation_by_token(db, token_raw)
    if inv:
        return _found(inv, 'exact')

    # 2) url-unquote once and twice
    try:
        u1 = unquote(token_raw)
        if u1 != token_raw:
            tried.append(('unquote1', u1))
            inv = get_invitation_by_token(db, u1)
            if inv:
                return _found(inv, 'unquote1')
        u2 = unquote(u1)
        if u2 != u1:
            tried.append(('unquote2', u2))
            inv = get_invitation_by_token(db, u2)
            if inv:
                return _found(inv, 'unquote2')
    except Exception:
        pass

    # 3) strip common noise (fragments, slashes)
    try:
        candidate = token_raw
        if '#' in candidate:
            candidate = candidate.split('#')[-1]
        if '/' in candidate:
            candidate = candidate.split('/')[-1]
        if candidate != token_raw:
            tried.append(('strip_fragments', candidate))
            inv = get_invitation_by_token(db, candidate)
            if inv:
                return _found(inv, 'strip_fragments')
    except Exception:
        pass

    # 4) fallback: substring search by a reasonable prefix (first 8 chars)
    try:
        prefix = token_raw[:8]
        if prefix:
            tried.append(('substring_prefix', prefix))
            q = db.query(InvitationModel).filter(InvitationModel.token.like(f"%{prefix}%"))
            maybe = q.first()
            if maybe:
                return _found(maybe, 'substring_prefix')
    except Exception:
        pass

    # nothing found — return helpful debug info
    return {
        "data": {
            "token_received": token_raw,
            "matched_token": None,
            "match_method": None,
            "tried": tried,
        }
    }


class PasswordResetRequest:
    def __init__(self, identifier: str | None = None, expires_hours: int | None = None):
        self.identifier = identifier
        self.expires_hours = expires_hours


@router.post('/user/password_reset')
def password_reset_request(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Public endpoint to request a password reset email for an existing user.

    Accepts JSON { "identifier": "username_or_email" }.
    """
    identifier = (payload or {}).get('identifier') if isinstance(payload, dict) else None
    if not identifier:
        # Bad request
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing identifier")

    # try to find the user by username or email
    user = db.query(User).filter((User.username == identifier) | (User.email == identifier)).first()

    # If no user found, return success=false to avoid leaking existence (still 200)
    if not user:
        return {"data": {"email_sent": False}}

    # create a short-lived invitation token for password reset
    expires = None
    try:
        expires = int((payload or {}).get('expires_hours')) if (payload or {}).get('expires_hours') else 2
    except Exception:
        expires = 2
    inv = create_invitation(db, user.id, expires_hours=expires)

    # determine frontend link
    frontend_base = get_setting(db, 'frontend_base_url') or os.getenv('FRONTEND_BASE_URL', '')
    frontend_base = (frontend_base or '').strip()
    if not frontend_base:
        origin = request.headers.get('origin') or request.headers.get('referer') or ''
        if origin:
            try:
                from urllib.parse import urlparse
                p = urlparse(origin)
                if p.scheme and p.netloc:
                    frontend_base = f"{p.scheme}://{p.netloc}"
            except Exception:
                frontend_base = origin
    if frontend_base:
        frontend_base = frontend_base.rstrip('/')
        # use hash route for SPA
        link = f"{frontend_base}/#/invite/accept?token={inv.token}"
    else:
        link = f"#/invite/accept?token={inv.token}"

    # resolve templates
    def _get_template_and_key(key_base: str):
        lang = getattr(user, 'language', None)
        if lang:
            key = f"{key_base}_{lang}"
            v = get_setting(db, key)
            if v:
                return v, key
            base = (lang.split('-')[0] if '-' in lang else lang)
            if base and base != lang:
                key2 = f"{key_base}_{base}"
                v2 = get_setting(db, key2)
                if v2:
                    return v2, key2
        v3 = get_setting(db, key_base)
        if v3:
            return v3, key_base
        return None, None

    subject_template, subject_key = _get_template_and_key('password_reset_subject')
    html_template, html_key = _get_template_and_key('password_reset_html')
    text_template, text_key = _get_template_and_key('password_reset_text')

    if not subject_template:
        # use language-appropriate defaults when possible
        if getattr(user, 'language', None) and str(user.language).lower().startswith('sv'):
            subject_template = 'Återställ ditt lösenord'
        else:
            subject_template = 'Reset your password'
    if not html_template:
        if getattr(user, 'language', None) and str(user.language).lower().startswith('sv'):
            html_template = '<p>Hej {display} ({username}),</p><p>Klicka <a href="{link}">här</a> för att återställa ditt lösenord.</p><p>Ditt användarnamn är <strong>{username}</strong>.</p>'
        else:
            html_template = '<p>Hello {display},</p><p>Click <a href="{link}">this link</a> to reset your password.</p>'
    if not text_template:
        if getattr(user, 'language', None) and str(user.language).lower().startswith('sv'):
            text_template = 'Hej {display} ({username}),\n\nÖppna följande länk för att återställa ditt lösenord: {link}\n\nDitt användarnamn: {username}\n'
        else:
            text_template = 'Hello {display},\n\nOpen the following link to reset your password: {link}\n'

    display = user.display_name or user.username
    try:
        subject = subject_template.format(display=display, username=user.username, link=link)
    except Exception:
        subject = subject_template
    try:
        html = html_template.format(display=display, username=user.username, link=link)
    except Exception:
        html = html_template
    try:
        text = text_template.format(display=display, username=user.username, link=link)
    except Exception:
        text = text_template

    sent = False
    try:
        to_addr = user.email or user.username
        sent = send_invite_mail(to_addr, subject, html, text, db=db)
    except Exception:
        sent = False

    return {"data": {"email_sent": bool(sent)}}


@router.post('/user/invite/accept')
def accept_invite(payload: InviteAccept, db: Session = Depends(get_db)):
    token = payload.token
    password = payload.password
    inv = get_invitation_by_token(db, token)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite token")
    if inv.used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token already used")
    if inv.expires_at:
        expires_at = getattr(inv, 'expires_at')
        if getattr(expires_at, 'tzinfo', None) is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token expired")

    user = get_user_by_id(db, inv.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for invite")

    # set provided password
    user = update_user(db, user, None, password, None)
    try:
        mark_invitation_used(db, inv)
    except Exception:
        pass
    return {"data": {"id": user.id}}


@router.post('/user/user/{user_id}/calendar_token/regenerate')
def users_regenerate_calendar_token(user_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    require_superadmin(_user)
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    from app.crud.user import regenerate_calendar_token
    token = regenerate_calendar_token(db, user)
    return {"data": {"id": user.id, "calendar_token": token}}



@router.patch("/user/me")
def users_update_me(
    payload: UserSelfUpdate,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    # allow the current user to update their own profile (username, display_name, password)
    try:
        user = update_user(
            db,
            _user,
            payload.display_name,
            payload.password,
            None,
            payload.username,
            payload.language,
            email=payload.email,
            personal_calendar_activity_ids=payload.personal_calendar_activity_ids,
        )
    except ValueError as e:
        if str(e) == "username_taken":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        raise

    # decode stored personal_calendar_activity_ids for response
    import json
    pca_out = None
    try:
        raw = getattr(user, 'personal_calendar_activity_ids', None)
        if raw:
            pca_out = json.loads(raw)
    except Exception:
        pca_out = None

    return {
        "data": {
            "id": user.id,
            "type": "user",
            "attributes": {
                "username": user.username,
                "display_name": user.display_name,
                "is_active": user.is_active,
                "calendar_token": getattr(user, 'calendar_token', None),
                "personal_calendar_activity_ids": pca_out,
            },
        }
    }



@router.post('/user/me/calendar_token/regenerate')
def regenerate_token(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    token = regenerate_calendar_token(db, _user)
    return {"data": {"token": token}}


@router.delete("/user/user/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def users_delete(
    user_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    require_superadmin(_user)
    delete_user(db, user)
    return None
