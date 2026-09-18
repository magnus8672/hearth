"""Farm account approval without access to another person's private content."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from hearth.catalog import CAPABILITIES
from hearth.identity import authenticate
from hearth.policy import USER_PERMISSIONS

router = APIRouter()


def administrator(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    if request.app.state.settings.audience != 'admin':
        raise HTTPException(403, 'Open Administration to manage accounts.')
    principal.require('role.grant')
    return principal


class AccessUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1, le=9007199254740991)
    state: Literal['pending', 'active', 'suspended']
    role: Literal['Member', 'FarmAdmin', 'Operator', 'Auditor'] = 'Member'
    permissions: list[str] = Field(default_factory=list, max_length=32)

    @field_validator('permissions')
    @classmethod
    def known_permissions(cls, value):
        if len(set(value)) != len(value) or not set(value) <= USER_PERMISSIONS:
            raise ValueError('Choose supported workspace permissions.')
        return sorted(value)


@router.get('/api/v1/accounts', tags=['accounts'])
def accounts(request: Request):
    principal = administrator(request)
    with request.app.state.engine.connect() as db:
        rows = db.execute(text("""SELECT u.id,u.display_name,u.state,u.created_at,
            u.authorization_version AS revision,u.access_permissions AS permissions,
            ARRAY(SELECT role FROM role_grants WHERE user_id=u.id AND farm_id=u.farm_id ORDER BY role) AS roles
            FROM users u WHERE u.farm_id=:farm ORDER BY (u.state='pending') DESC,u.created_at,u.id"""),
            {'farm': principal.farm_id}).mappings().all()
    return {'items': [dict(row) for row in rows], 'capabilities': [
        {'permission': 'capability.'+cap.capability_id, 'name': cap.display_name} for cap in CAPABILITIES]}


@router.put('/api/v1/accounts/{user_id}/access', tags=['accounts'])
def change_access(request: Request, user_id: UUID, data: AccessUpdate):
    principal = administrator(request, True)
    try:
        with request.app.state.engine.begin() as db:
            version = db.execute(text('SELECT change_member_access(:actor,:farm,:actor_version,:user,:version,:state,:role,CAST(:permissions AS text[]))'),
                {'actor': principal.id, 'farm': principal.farm_id, 'actor_version': principal.authorization_version,
                 'user': user_id, 'version': data.revision, 'state': data.state, 'role': data.role, 'permissions': data.permissions}).scalar_one()
    except DBAPIError as exc:
        detail = str(exc.orig)
        if 'revision_conflict' in detail:
            raise HTTPException(409, 'This account changed in another tab. Reload before saving.') from None
        if 'protected_account' in detail:
            raise HTTPException(403, 'Your own account and Owner accounts are protected from this editor.') from None
        if 'account_missing' in detail:
            raise HTTPException(404, 'This account is not in your farm.') from None
        raise HTTPException(403, 'The account change is not authorized. Refresh your session and try again.') from None
    return {'id': user_id, 'revision': version, 'state': data.state}
