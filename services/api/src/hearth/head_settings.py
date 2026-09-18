"""Authenticated admin facade for the narrowly scoped local head supervisor."""
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from hearth.database import scoped_session
from hearth.identity import authenticate

router = APIRouter(prefix='/api/v1/head', tags=['administration'])


class AddressPreview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    base_url: str = Field(min_length=8, max_length=300)


class AddressApply(AddressPreview):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    operation_id: UUID


def administrator(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    if request.app.state.settings.audience != 'admin':
        raise HTTPException(403, 'Open Administration to configure the head address.')
    principal.require('farm.configure')
    return principal


def control(request, method, path, body=None):
    socket = request.app.state.settings.head_control_socket
    if not socket:
        raise HTTPException(503, 'The head address service is not installed. Run scripts/head.py install-control on the head VM.')
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=socket), timeout=20, trust_env=False) as client:
            result = client.request(method, 'http://head-control'+path, json=body)
            if result.status_code != 200:
                raise HTTPException(result.status_code, result.json().get('message', 'The address operation could not complete.'))
            return result
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'The head address service is unavailable. Check hearth-head-control on the VM.') from None


@router.get('/settings')
def settings(request: Request):
    administrator(request)
    return control(request, 'GET', '/status').json()


@router.post('/preview')
def preview(request: Request, data: AddressPreview):
    administrator(request, mutation=True)
    return control(request, 'POST', '/preview', data.model_dump()).json()


@router.post('/apply', status_code=202)
def apply(request: Request, data: AddressApply):
    principal = administrator(request, mutation=True)
    # Commit the authenticated intent before host maintenance can restart this BFF.
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'head.address_requested',CAST(:metadata AS jsonb))"),
                   {'farm': principal.farm_id, 'actor': principal.id,
                    'metadata': data.model_dump_json()})
    return control(request, 'POST', '/apply', data.model_dump(mode='json') | {'actor_id': str(principal.id)}).json()


@router.get('/certificates')
def certificates(request: Request):
    administrator(request)
    content = control(request, 'GET', '/certificates').content
    return Response(content, media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="hearth-client-certificates.zip"'})
