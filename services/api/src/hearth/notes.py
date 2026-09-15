"""A private scratchpad. Notes enter model context only on explicit send."""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from hearth.chat import member
from hearth.database import scoped_session

router = APIRouter()


class SaveNote(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: UUID
    content: str = Field(min_length=1, max_length=4000)


class NoteRevision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1, le=9007199254740991)


@router.get('/api/v1/side-notes', tags=['notes'])
def notes(request: Request):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        items = db.execute(text('SELECT id,content,revision FROM side_notes WHERE dismissed_at IS NULL ORDER BY created_at,id')).mappings().all()
        return {'items': [dict(item) for item in items]}


@router.post('/api/v1/side-notes', tags=['notes'], status_code=201)
def save(request: Request, data: SaveNote):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        workspace = db.execute(text('SELECT id FROM workspaces FOR UPDATE')).scalar_one()
        existing = db.execute(text('SELECT id,content,revision,dismissed_at FROM side_notes WHERE id=:id'), {'id': data.id}).mappings().one_or_none()
        if existing:
            if existing['content'] != data.content or existing['dismissed_at']:
                raise HTTPException(409, 'This note request was already used. Refresh your side notes.')
            return {key: existing[key] for key in ('id', 'content', 'revision')}
        if db.execute(text('SELECT count(*) FROM side_notes WHERE dismissed_at IS NULL')).scalar_one() >= 100:
            raise HTTPException(409, 'Your scratchpad has 100 notes. Send or dismiss one to make room.')
        db.execute(text('INSERT INTO side_notes(id,farm_id,owner_id,workspace_id,content) VALUES(:id,:farm,:owner,:workspace,:content)'),
            {'id': data.id, 'farm': principal.farm_id, 'owner': principal.id, 'workspace': workspace, 'content': data.content})
        return {'id': data.id, 'content': data.content, 'revision': 1}


@router.post('/api/v1/side-notes/{note_id}/dismiss', tags=['notes'])
def dismiss(request: Request, note_id: UUID, data: NoteRevision):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT revision,dismissed_at FROM side_notes WHERE id=:id FOR UPDATE'), {'id': note_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(404, 'This note is not available in your workspace.')
        if row['dismissed_at']:
            return {'dismissed': True}
        if row['revision'] != data.revision:
            raise HTTPException(409, 'This note changed. Refresh before dismissing it.')
        db.execute(text('UPDATE side_notes SET dismissed_at=now(),revision=revision+1 WHERE id=:id'), {'id': note_id})
    return {'dismissed': True}
