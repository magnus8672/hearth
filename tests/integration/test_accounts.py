"""Default-deny registration, scoped approval and execution revocation on real RLS."""
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from hearth import identity, routing
from hearth.chat import session_current
from hearth.client_keys import NewKey, issue_key, key_current
from hearth.database import scoped_session
from hearth.policy import PolicyDenied, Principal, permissions_for
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.fixture
def accounts(bff, monkeypatch):
    from hearth import image_queue
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    factory, settings, engine, migration, subject = bff
    current = {'subject': subject}
    def token(config, endpoint, data):
        if endpoint == 'token/introspect':
            return {'active': True, 'sub': data['token'], 'iss': config.issuer}
        return {'id_token': 'fixture', 'access_token': current['subject'], 'refresh_token': 'fixture', 'expires_in': 300}
    monkeypatch.setattr(identity, 'token_request', token)
    monkeypatch.setattr(identity, 'verify_id_token', lambda config, tokens, nonce: {'sub': tokens['access_token'], 'name': 'Approval fixture'})
    with factory('admin') as admin, factory(approved=False) as pending:
        signin(admin)
        promote(admin, migration, settings)
        current['subject'] = str(uuid4())
        signin(pending)
        account = pending.get('/api/v1/session').json()
        yield admin, pending, account, settings, engine, migration


def update(admin, settings, account, **changes):
    return admin.put(f"/api/v1/accounts/{account['id']}/access", headers=csrf(admin, settings.admin_origin), json={
        'revision': account.get('revision', account.get('authorization_version', 1)), 'state': 'active', 'role': 'Member',
        'permissions': ['conversation.own', 'capability.chat.general'], **changes})


def test_registration_uses_bound_pkce_and_default_deny_workspace(accounts):
    admin, user, account, settings, engine, migration = accounts
    assert account['state'] == 'pending' and account['roles'] == [] and account['permissions'] == []
    assert user.get('/api/v1/workspace').status_code == 200
    assert user.get('/api/v1/capabilities').json()['items'] == []
    for path in ['/api/v1/chats','/api/v1/images','/api/v1/image-targets','/api/v1/geometry',
                 '/api/v1/channels','/api/v1/memory','/api/v1/my-tools','/api/v1/client-keys','/api/v1/accounts','/api/v1/farm']:
        response = user.get(path)
        assert response.status_code == 403, (path, response.text)
    assert user.post('/api/v1/chats', json={}, headers=csrf(user, settings.user_origin)).status_code == 403
    response = user.get('/auth/register')
    url = urlsplit(response.headers['location'])
    assert url.scheme == 'https' and url.path.endswith('/protocol/openid-connect/registrations')
    query = parse_qs(url.query)
    assert query['code_challenge_method'] == ['S256'] and query['redirect_uri'] == [settings.user_origin+'/auth/callback']
    assert admin.get('/auth/register').status_code == 403
    # Logging in again cannot manufacture Member grants.
    signin(user)
    assert user.get('/api/v1/session').json()['permissions'] == []


def test_approval_chat_only_and_direct_capability_bypasses(accounts):
    admin, user, account, settings, engine, migration = accounts
    assert update(admin, settings, account).status_code == 200
    assert user.get('/api/v1/session').status_code == 401
    signin(user)
    session = user.get('/api/v1/session').json()
    assert session['state'] == 'active' and session['roles'] == ['Member']
    assert user.get('/api/v1/chats').status_code == 200
    chat = user.post('/api/v1/chats', headers=csrf(user, settings.user_origin), json={}).json()
    for path in ['/api/v1/images','/api/v1/geometry','/api/v1/channels','/api/v1/memory','/api/v1/client-keys','/api/v1/my-tools',
                 f"/api/v1/chats/{chat['id']}/transcriptions"]:
        assert user.get(path).status_code == 403
    for prompt, capability in [('make an image of a fox', 'auto'), ('write a python script', 'code.implement')]:
        response = user.post(f"/api/v1/chats/{chat['id']}/turns", headers=csrf(user, settings.user_origin),
            json={'request_id': str(uuid4()), 'revision': 1, 'content': prompt, 'capability': capability})
        assert response.status_code == 403, response.text
    with scoped_session(engine, UUID(account['id']), settings.farm_id) as db:
        for capability in ['image.generate', 'geometry.generate', 'code.implement', 'audio.speak', 'vision.describe']:
            with pytest.raises(PolicyDenied):
                routing.select(db, capability)
    assert update(admin, settings, account).status_code == 409


def test_admin_csrf_audience_protected_owner_and_cross_farm(accounts):
    admin, user, account, settings, engine, migration = accounts
    body = {'revision': 1,'state':'active','role':'FarmAdmin','permissions':[]}
    path = f"/api/v1/accounts/{account['id']}/access"
    assert admin.put(path,json=body).status_code == 403
    assert admin.put(path,json=body,headers=csrf(admin, settings.user_origin)).status_code == 403
    assert user.put(path,json=body,headers=csrf(user,settings.user_origin)).status_code == 403
    assert update(admin, settings, admin.get('/api/v1/session').json()).status_code == 403
    assert update(admin, settings, {'id':str(uuid4()), 'revision':1}).status_code == 404
    assert update(admin, settings, account, permissions=['role.grant']).status_code == 422
    assert update(admin, settings, account, role='Owner').status_code == 422
    assert update(admin, settings, account, role='FarmAdmin').status_code == 200
    signin(user)
    assert 'role.grant' in user.get('/api/v1/session').json()['permissions']
    assert user.get('/api/v1/accounts').status_code == 403  # wrong audience even for an administrator


def test_revocation_fences_keys_and_running_work(accounts):
    admin, user, account, settings, engine, migration = accounts
    permissions=['conversation.own','api_key.own','capability.chat.general']
    assert update(admin, settings, account, permissions=permissions).status_code == 200
    signin(user)
    session = user.get('/api/v1/session').json()
    principal = Principal(UUID(account['id']), settings.farm_id, frozenset(permissions), session['authorization_version'])
    key = issue_key(engine, principal, NewKey(name='fixture', capabilities=['chat.general']))
    with pytest.raises(PolicyDenied):
        issue_key(engine, principal, NewKey(name='forbidden', capabilities=['code.implement']))
    with pytest.raises(PolicyDenied):
        issue_key(engine, principal, NewKey(name='forbidden tools', capabilities=['chat.general'], allow_tools=True))
    token_hash=identity.digest(user.cookies.get('__Host-hearth_user_session'))
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        assert key_current(db, principal, key['id']) and session_current(db, principal, token_hash)
    assert update(admin, settings, session, state='suspended', permissions=permissions).status_code == 200
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        assert not key_current(db, principal, key['id']) and not session_current(db, principal, token_hash)
        assert not permissions_for(db, principal.id, principal.farm_id)
    assert user.get('/api/v1/session').status_code == 401
    assert user.get('/v1/models',headers={'Authorization':'Bearer '+key['key']}).status_code == 401
    start=user.get('/auth/login')
    state=parse_qs(urlsplit(start.headers['location']).query)['state'][0]
    assert user.get('/auth/callback?state='+state+'&code=fixture').status_code == 403


def test_geometry_only_grant_and_revocation_before_queue_dispatch(accounts, monkeypatch):
    import base64
    import hashlib

    from hearth import geometry_transport, image_queue
    from hearth.contracts import GeometryReceipt
    from hearth.geometry_probe import reference

    from tests.integration.test_geometry import INFO
    from tests.security.test_geometry import triangle
    admin, user, account, settings, engine, migration = accounts
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: INFO)
    calls = []
    def render(url, key, settings, data, image, observe=lambda value: False):
        calls.append(data.id)
        return GeometryReceipt(**data.model_dump(), state='completed', progress=100, manifest_sha256='a'*64, execution_released=True, cancel_requested=False), triangle()
    monkeypatch.setattr(geometry_transport, 'render', render)
    headers=csrf(admin, settings.admin_origin)
    target=admin.post('/api/v1/providers',headers=headers,json={'name':'Geometry approval fixture','base_url':'http://127.0.0.1:1236','model_id':INFO.model,'protocol':INFO.protocol,'local_only':True}).json()['id']
    assert admin.post(f'/api/v1/providers/{target}/probe',headers=headers,json={'revision':1}).status_code == 200
    image=reference()
    body={'target_id':target,'request':{'id':str(uuid4()),'model':INFO.model,'image_sha256':hashlib.sha256(image).hexdigest()},'image':base64.b64encode(image).decode()}
    assert user.post('/api/v1/geometry',headers=csrf(user,settings.user_origin),json=body).status_code == 403
    assert update(admin,settings,account,permissions=['capability.geometry.generate']).status_code == 200
    signin(user)
    assert user.get('/api/v1/chats').status_code == 403
    assert user.post('/api/v1/geometry',headers=csrf(user,settings.user_origin),json=body).status_code == 202
    session=user.get('/api/v1/session').json()
    assert update(admin,settings,session,permissions=[]).status_code == 200
    with scoped_session(engine,UUID(account['id']),settings.farm_id) as db:
        pool=db.execute(text('SELECT resource_pool_id FROM inference_targets WHERE id=:id'),{'id':target}).scalar_one()
    assert image_queue.claim(engine,settings,pool) is None
    assert len(calls) == 1  # Only the administrator's provider verification ran.
    with scoped_session(engine,UUID(account['id']),settings.farm_id) as db:
        assert db.execute(text('SELECT status FROM geometry_jobs WHERE id=:id'),{'id':body['request']['id']}).scalar_one() == 'cancelled'
