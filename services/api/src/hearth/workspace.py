"""Personal drafts and the authoritative, currently unassigned capability catalog."""
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from hearth.database import scoped_session
from hearth.identity import authenticate

router = APIRouter()


class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=32000)


class DraftUpdate(DraftInput):
    revision: int = Field(strict=True, ge=1, le=9007199254740991)


@router.get('/api/v1/setup', tags=['identity'])
def setup(request: Request):
    settings = request.app.state.settings
    ready = False
    if request.app.state.engine and settings.farm_id:
        with request.app.state.engine.connect() as connection:
            ready = connection.execute(text("SELECT EXISTS(SELECT 1 FROM role_grants WHERE farm_id=:farm AND role='Owner')"), {'farm': settings.farm_id}).scalar_one()
    return {'owner_created': ready, 'audience': settings.audience, 'provider_ready': False}


@router.get('/api/v1/capabilities', tags=['catalog'])
def capabilities(request: Request):
    authenticate(request)
    with request.app.state.engine.connect() as connection:
        definitions = connection.execute(text('SELECT definition FROM capabilities ORDER BY id')).scalars().all()
    return {'items': [dict(item) | {'state': 'unassigned', 'reason': 'No approved provider has been assigned.'} for item in definitions]}


@router.get('/api/v1/workspace', tags=['workspace'])
def workspace(request: Request):
    principal = authenticate(request)
    principal.require('conversation.own')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT id,name,locality FROM workspaces')).mappings().one()
        drafts = db.execute(text('SELECT id,title,revision FROM conversations WHERE deleted_at IS NULL ORDER BY id DESC')).mappings().all()
        return {'workspace': dict(row), 'drafts': [dict(item) for item in drafts]}


@router.get('/api/v1/drafts/{draft_id}', tags=['workspace'])
def draft(request: Request, draft_id: UUID):
    principal = authenticate(request)
    principal.require('conversation.own')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT c.id,c.title,c.revision,m.content FROM conversations c JOIN messages m ON m.conversation_id=c.id AND m.sequence=1 WHERE c.id=:id AND c.deleted_at IS NULL'), {'id': draft_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(404, 'This draft is not available in your workspace.')
        return dict(row)


@router.post('/api/v1/drafts', tags=['workspace'], status_code=201)
def create_draft(request: Request, data: DraftInput):
    principal = authenticate(request, mutation=True)
    principal.require('conversation.own')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        workspace_id = db.execute(text('SELECT id FROM workspaces FOR UPDATE')).scalar_one()
        count = db.execute(text('SELECT count(*) FROM conversations WHERE deleted_at IS NULL')).scalar_one()
        if count >= 200:
            raise HTTPException(409, 'This test workspace supports 200 saved drafts. Archive a draft to make room.')
        values = {'id': uuid4(), 'farm': principal.farm_id, 'owner': principal.id, 'workspace': workspace_id,
                  'title': data.title, 'content': data.content}
        db.execute(text('INSERT INTO conversations(id,farm_id,owner_id,workspace_id,title) VALUES(:id,:farm,:owner,:workspace,:title)'), values)
        db.execute(text("INSERT INTO messages(id,conversation_id,farm_id,owner_id,sequence,role,content,status) VALUES(gen_random_uuid(),:id,:farm,:owner,1,'user',:content,'draft')"), values)
        return {'id': values['id'], 'title': data.title, 'content': data.content, 'revision': 1}


@router.put('/api/v1/drafts/{draft_id}', tags=['workspace'])
def update_draft(request: Request, draft_id: UUID, data: DraftUpdate):
    principal = authenticate(request, mutation=True)
    principal.require('conversation.own')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT revision FROM conversations WHERE id=:id AND deleted_at IS NULL FOR UPDATE'), {'id': draft_id}).one_or_none()
        if not row:
            raise HTTPException(404, 'This draft is not available in your workspace.')
        if row.revision != data.revision:
            raise HTTPException(409, 'This draft changed in another tab. Reopen it before saving your changes.')
        db.execute(text('UPDATE conversations SET title=:title,revision=revision+1 WHERE id=:id'), {'id': draft_id, 'title': data.title})
        db.execute(text('UPDATE messages SET content=:content WHERE conversation_id=:id AND sequence=1'), {'id': draft_id, 'content': data.content})
        return {'id': draft_id, 'title': data.title, 'content': data.content, 'revision': data.revision + 1}


@router.delete('/api/v1/drafts/{draft_id}', tags=['workspace'])
def archive_draft(request: Request, draft_id: UUID):
    principal = authenticate(request, mutation=True)
    principal.require('conversation.own')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        changed = db.execute(text('UPDATE conversations SET deleted_at=now(),revision=revision+1 WHERE id=:id AND deleted_at IS NULL'), {'id': draft_id}).rowcount
        if not changed:
            raise HTTPException(404, 'This draft is not available in your workspace.')
    return {'archived': True}


@router.get('/api/v1/farm', tags=['administration'])
def farm(request: Request):
    principal = authenticate(request)
    if request.app.state.settings.audience != 'admin':
        raise HTTPException(403, 'Open Administration to inspect the farm.')
    principal.require('farm.inspect')
    with request.app.state.engine.connect() as db:
        farm = db.execute(text('SELECT id,name,created_at FROM farms WHERE id=:id'), {'id': principal.farm_id}).mappings().one()
        members = db.execute(text('SELECT u.id,u.display_name,u.state,array_agg(g.role ORDER BY g.role) AS roles FROM users u LEFT JOIN role_grants g ON g.user_id=u.id WHERE u.farm_id=:farm GROUP BY u.id ORDER BY u.display_name'), {'farm': principal.farm_id}).mappings().all()
    return {'farm': dict(farm), 'members': [dict(item) for item in members],
            'provider': {'state': 'unassigned', 'cloud_budget_minor': 0, 'default_locality': 'local_only'},
            'enrollment_available': False}
