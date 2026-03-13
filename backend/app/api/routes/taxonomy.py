from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_superadmin, is_superadmin, user_assigned_to_org
from app.crud import (
    create_term,
    delete_term,
    get_term,
    list_terms,
    update_term,
    list_activities,
    create_activity,
    get_activity,
    update_activity,
    delete_activity,
)
from app.db.session import get_db
from app.schemas.term import TermCreate, TermUpdate
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/terms")
def terms_index(
    organization_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    # If an organization_id filter is provided, ensure the requester may view that org
    if organization_id is not None:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view terms for this organization")
        terms = list_terms(db, organization_id=organization_id)
    else:
        # Return only global terms and terms for organizations the user is assigned to (unless superadmin)
        all_terms = list_terms(db)
        if is_superadmin(_user):
            terms = all_terms
        else:
            # collect user's org ids
            from app.crud.organization import list_organizations_for_user

            assigned = {str(o.id) for o in list_organizations_for_user(db, _user.id)}
            terms = [t for t in all_terms if (t.organization_id is None) or (str(t.organization_id) in assigned)]

    return {
        "data": [
            {
                "id": term.id,
                "type": "term",
                "attributes": {"name": term.name, "organization_id": term.organization_id},
            }
            for term in terms
        ]
    }


@router.get("/terms/{term_id}")
def terms_detail(
    term_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    term = get_term(db, term_id)
    if not term:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    if getattr(term, 'organization_id', None):
        if not (is_superadmin(_user) or user_assigned_to_org(_user, term.organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this term")
    return {
        "data": {
            "id": term.id,
            "type": "term",
            "attributes": {"name": term.name, "organization_id": term.organization_id},
        }
    }


@router.post("/terms", status_code=status.HTTP_201_CREATED)
def terms_create(
    payload: TermCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    require_superadmin(_user)
    org_id = getattr(payload, 'organization_id', None)
    term = create_term(db, payload.name, org_id)
    return {
        "data": {
            "id": term.id,
            "type": "term",
            "attributes": {"name": term.name, "organization_id": term.organization_id},
        }
    }


@router.patch("/terms/{term_id}")
def terms_update(
    term_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    term = get_term(db, term_id)
    if not term:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    require_superadmin(_user)

    # Accept either JSONAPI-style payload { data: { attributes: { ... } } }
    # or plain payload { name: ..., organization_id: ... }
    attrs = None
    if isinstance(payload, dict) and 'data' in payload and isinstance(payload['data'], dict):
        attrs = payload['data'].get('attributes') or {}
    else:
        attrs = payload

    name = attrs.get('name') if isinstance(attrs, dict) else None
    org_id = attrs.get('organization_id') if isinstance(attrs, dict) else None

    term = update_term(db, term, name, org_id)
    return {
        "data": {
            "id": term.id,
            "type": "term",
            "attributes": {"name": term.name, "organization_id": term.organization_id},
        }
    }


@router.delete("/terms/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
def terms_delete(
    term_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    term = get_term(db, term_id)
    if not term:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Term not found")
    require_superadmin(_user)
    delete_term(db, term)
    return None


@router.get("/activities")
def activities_index(
    organization_id: str | None = None,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    # If org filter provided, ensure user may view that org
    if organization_id is not None:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view activities for this organization")
        acts = list_activities(db, organization_id=organization_id)
    else:
        all_acts = list_activities(db)
        if is_superadmin(_user):
            acts = all_acts
        else:
            from app.crud.organization import list_organizations_for_user

            assigned = {str(o.id) for o in list_organizations_for_user(db, _user.id)}
            acts = [a for a in all_acts if (a.organization_id is None) or (str(a.organization_id) in assigned)]

    return {
        "data": [
            {"id": a.id, "type": "activity", "attributes": {"name": a.name, "organization_id": a.organization_id, "default_start_time": a.default_start_time.isoformat() if a.default_start_time else None, "default_end_time": a.default_end_time.isoformat() if a.default_end_time else None}}
            for a in acts
        ]
    }


@router.post("/activities", status_code=status.HTTP_201_CREATED)
def activities_create(payload: dict, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    # Allow users assigned to the organization to create activities for that org;
    # creating a global (no organization) activity requires superadmin.
    org_id = payload.get("organization_id")
    from app.core.rbac import is_superadmin, user_assigned_to_org
    if org_id is None:
        require_superadmin(_user)
    else:
        if not (is_superadmin(_user) or user_assigned_to_org(_user, org_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create activity for this organization")
    name = payload.get("name")
    org_id = payload.get("organization_id")
    # parse optional default times (expecting HH:MM or HH:MM:SS strings)
    def _parse_time(s):
        if not s:
            return None
        try:
            from datetime import time as dtime
            # time.fromisoformat accepts HH:MM[:SS[.ffffff]]
            return dtime.fromisoformat(s)
        except Exception:
            return None

    default_start = _parse_time(payload.get('default_start_time'))
    default_end = _parse_time(payload.get('default_end_time'))
    logger.debug('activities_create payload=%s parsed_start=%s parsed_end=%s', payload, default_start, default_end)
    act = create_activity(db, name, org_id, default_start_time=default_start, default_end_time=default_end)
    logger.debug('created activity id=%s start=%s end=%s', act.id, act.default_start_time, act.default_end_time)
    return {
        "data": {
            "id": act.id,
            "type": "activity",
            "attributes": {"name": act.name, "organization_id": act.organization_id, "default_start_time": act.default_start_time.isoformat() if act.default_start_time else None, "default_end_time": act.default_end_time.isoformat() if act.default_end_time else None},
        }
    }


@router.get("/activities/{activity_id}")
def activities_detail(
    activity_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    act = get_activity(db, activity_id)
    if not act:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    if getattr(act, 'organization_id', None):
        if not (is_superadmin(_user) or user_assigned_to_org(_user, act.organization_id)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this activity")
    return {
        "data": {
            "id": act.id,
            "type": "activity",
            "attributes": {"name": act.name, "organization_id": act.organization_id, "default_start_time": act.default_start_time.isoformat() if act.default_start_time else None, "default_end_time": act.default_end_time.isoformat() if act.default_end_time else None},
        }
    }


@router.patch("/activities/{activity_id}")
def activities_update(
    activity_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    act = get_activity(db, activity_id)
    if not act:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    require_superadmin(_user)

    # Accept either JSONAPI-style payload { data: { attributes: { ... } } },
    # or JSONAPI-lite { data: { ... } }, or plain payload { name: ..., organization_id: ... }
    attrs = None
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict):
        # Prefer attributes if present, otherwise allow fields directly under data
        attrs = payload["data"].get("attributes") or payload["data"] or {}
    else:
        attrs = payload

    name = attrs.get("name") if isinstance(attrs, dict) else None
    org_id = attrs.get("organization_id") if isinstance(attrs, dict) else None
    default_start = attrs.get('default_start_time') if isinstance(attrs, dict) else None
    default_end = attrs.get('default_end_time') if isinstance(attrs, dict) else None
    def _parse_time(s):
        if not s:
            return None
        try:
            from datetime import time as dtime
            return dtime.fromisoformat(s)
        except Exception:
            return None

    parsed_start = _parse_time(default_start)
    parsed_end = _parse_time(default_end)
    logger.debug('activities_update attrs=%s parsed_start=%s parsed_end=%s', attrs, parsed_start, parsed_end)
    act = update_activity(db, act, name, org_id, default_start_time=parsed_start, default_end_time=parsed_end)
    logger.debug('updated activity id=%s start=%s end=%s', act.id, act.default_start_time, act.default_end_time)
    return {
        "data": {
            "id": act.id,
            "type": "activity",
            "attributes": {"name": act.name, "organization_id": act.organization_id, "default_start_time": act.default_start_time.isoformat() if act.default_start_time else None, "default_end_time": act.default_end_time.isoformat() if act.default_end_time else None},
        }
    }


@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def activities_delete(
    activity_id: str, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    act = get_activity(db, activity_id)
    if not act:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    require_superadmin(_user)
    delete_activity(db, act)
    return None


