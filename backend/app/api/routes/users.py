from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.rbac import require_superadmin
from app.crud import create_user, delete_user, get_user_by_id, list_users, update_user
from app.models import User
from app.db.session import get_db
from app.schemas.user import UserCreate, UserUpdate
from app.schemas.user import UserSelfUpdate
from app.crud.user import regenerate_calendar_token

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
                "attributes": {"display_name": user.display_name, "username": user.username},
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
            "attributes": {"display_name": user.display_name, "username": user.username},
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
                "assignments": assignments,
            },
        }
    }


@router.post("/user/user", status_code=status.HTTP_201_CREATED)
def users_create(
    payload: UserCreate, db: Session = Depends(get_db), _user=Depends(get_current_user)
):
    require_superadmin(_user)
    user = create_user(db, payload.username, payload.display_name, payload.password)
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
        )
    except ValueError as e:
        if str(e) == "username_taken":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
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
        user = update_user(db, _user, payload.display_name, payload.password, None, payload.username, payload.language)
    except ValueError as e:
        if str(e) == "username_taken":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")
        raise

    return {
        "data": {
            "id": user.id,
            "type": "user",
            "attributes": {
                "username": user.username,
                "display_name": user.display_name,
                "is_active": user.is_active,
                "calendar_token": getattr(user, 'calendar_token', None),
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
