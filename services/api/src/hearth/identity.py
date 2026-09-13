"""Confidential OIDC BFF: tokens never enter the browser or application URLs."""
import hashlib
import json
import secrets
import time
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import httpx
from authlib.oidc.core import CodeIDToken
from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request
from joserfc import jwt
from joserfc.jwk import KeySet
from sqlalchemy import text
from starlette.responses import RedirectResponse

from hearth.policy import ROLES, Principal

router = APIRouter()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cipher(settings):
    value = settings.session_encryption_key.get_secret_value()
    return Fernet((value + '=' * (-len(value) % 4)).encode())


def cookie_name(settings, login=False):
    return f"__Host-hearth_{settings.audience}_{'login' if login else 'session'}"


def check_origin(request, mutation=False):
    settings = request.app.state.settings
    # The two processes have fixed audiences. No forwarded identity header selects one.
    if str(request.base_url).rstrip('/') != settings.origin:
        raise HTTPException(403, "This application origin is not authorized.")
    if mutation and request.headers.get('origin') != settings.origin:
        raise HTTPException(403, "The request origin does not match this application.")


def configured(request):
    settings = request.app.state.settings
    if not settings.farm_id or not settings.client_secret:
        raise HTTPException(503, "Complete local Owner setup to enable sign-in.")
    return settings


def token_request(settings, endpoint, data):
    with httpx.Client(timeout=12, trust_env=False) as client:
        response = client.post(f"{settings.oidc_internal}/{endpoint}", data=data,
                               auth=(settings.client_id, settings.client_secret))
        response.raise_for_status()
        return response.json() if response.content else {}


def verify_id_token(settings, tokens, nonce):
    with httpx.Client(timeout=12, trust_env=False) as client:
        response = client.get(f"{settings.oidc_internal}/certs")
        response.raise_for_status()
    decoded = jwt.decode(tokens['id_token'], KeySet.import_key_set(response.json()), algorithms=['RS256'])
    claims = CodeIDToken(decoded.claims, decoded.header,
        options={'iss': {'essential': True, 'value': settings.issuer},
                 'aud': {'essential': True, 'value': settings.client_id}},
        params={'nonce': nonce, 'client_id': settings.client_id, 'access_token': tokens['access_token']})
    claims.validate(leeway=15)
    return claims


@router.get('/auth/login', include_in_schema=False)
def login(request: Request):
    settings = configured(request)
    check_origin(request)
    # GET navigation starts login but cannot bind an attacker's callback to another browser.
    state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    payload = cipher(settings).encrypt(json.dumps({'nonce': nonce, 'verifier': verifier}).encode()).decode()
    with request.app.state.engine.begin() as connection:
        connection.execute(text('DELETE FROM login_attempts WHERE expires_at < now()'))
        connection.execute(text('INSERT INTO login_attempts(state_hash,audience,browser_hash,payload) VALUES(:state,:audience,:browser,:payload)'),
                           {'state': digest(state), 'audience': settings.audience, 'browser': digest(browser), 'payload': payload})
    query = urlencode({'client_id': settings.client_id, 'redirect_uri': settings.origin + '/auth/callback',
        'response_type': 'code', 'scope': 'openid profile', 'state': state, 'nonce': nonce, 'prompt': 'login',
        'code_challenge': urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),
        'code_challenge_method': 'S256'})
    response = RedirectResponse(settings.issuer + '/protocol/openid-connect/auth?' + query, status_code=303)
    response.set_cookie(cookie_name(settings, True), browser, max_age=300, secure=True, httponly=True, samesite='lax', path='/')
    return response


@router.get('/auth/callback', include_in_schema=False)
def callback(request: Request):
    settings = configured(request)
    check_origin(request)
    state = request.query_params.get('state', '')
    browser = request.cookies.get(cookie_name(settings, True), '')
    if not state or not browser or len(state) > 200:
        raise HTTPException(400, 'The sign-in attempt is missing or expired. Start again.')
    with request.app.state.engine.begin() as connection:
        attempt = connection.execute(text('DELETE FROM login_attempts WHERE state_hash=:state AND browser_hash=:browser AND audience=:audience AND expires_at>now() RETURNING payload'),
            {'state': digest(state), 'browser': digest(browser), 'audience': settings.audience}).scalar_one_or_none()
    if not attempt:
        raise HTTPException(400, 'This sign-in attempt has expired or was already used.')
    try:
        payload = json.loads(cipher(settings).decrypt(attempt.encode()))
        tokens = token_request(settings, 'token', {'grant_type': 'authorization_code',
            'code': request.query_params.get('code', ''), 'redirect_uri': settings.origin + '/auth/callback',
            'code_verifier': payload['verifier']})
        claims = verify_id_token(settings, tokens, payload['nonce'])
    except Exception:
        # Provider responses may contain secrets. Never reflect or log them.
        raise HTTPException(400, 'Sign-in could not be verified. Please start again.') from None
    secret, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    tokens['expires_at'] = int(time.time()) + int(tokens['expires_in'])
    tokens['subject'] = claims['sub']
    with request.app.state.engine.begin() as connection:
        user_id = connection.execute(text('SELECT provision_member(:farm,:issuer,:subject,:name)'),
            {'farm': settings.farm_id, 'issuer': settings.issuer, 'subject': claims['sub'],
             'name': claims.get('name') or claims.get('preferred_username') or 'Member'}).scalar_one()
        version = connection.execute(text('SELECT authorization_version FROM users WHERE id=:id'), {'id': user_id}).scalar_one()
        # Rotate any prior session in this browser. User and admin sessions are independent.
        connection.execute(text('DELETE FROM browser_sessions WHERE token_hash=:old AND audience=:audience'),
            {'old': digest(request.cookies.get(cookie_name(settings), '')), 'audience': settings.audience})
        connection.execute(text('INSERT INTO browser_sessions(token_hash,audience,user_id,farm_id,csrf_token,credentials,authorization_version) VALUES(:hash,:audience,:user,:farm,:csrf,:credentials,:version)'),
            {'hash': digest(secret), 'audience': settings.audience, 'user': user_id, 'farm': settings.farm_id,
             'csrf': csrf, 'credentials': cipher(settings).encrypt(json.dumps(tokens).encode()).decode(), 'version': version})
        connection.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'identity.sign_in',jsonb_build_object('audience',CAST(:audience AS text)))"),
            {'farm': settings.farm_id, 'actor': user_id, 'audience': settings.audience})
    response = RedirectResponse(settings.origin + '/', status_code=303)
    response.delete_cookie(cookie_name(settings, True), secure=True, httponly=True, samesite='lax')
    response.set_cookie(cookie_name(settings), secret, max_age=28800, secure=True, httponly=True, samesite='lax', path='/')
    return response


def authenticate(request: Request, mutation=False):
    settings = request.app.state.settings
    raw = request.cookies.get(cookie_name(settings), '')
    if not raw or len(raw) > 200:
        raise HTTPException(401, 'Sign in to Hearth to continue.')
    configured(request)
    check_origin(request, mutation)
    with request.app.state.engine.begin() as connection:
        row = connection.execute(text("SELECT s.*,u.display_name,u.state,u.authorization_version AS current_version FROM browser_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=:hash AND s.audience=:audience AND s.farm_id=:farm AND s.expires_at>now() AND s.last_seen_at>now()-interval '30 minutes' FOR UPDATE OF s"),
            {'hash': digest(raw), 'audience': settings.audience, 'farm': settings.farm_id}).mappings().one_or_none()
        if not row or row['state'] != 'active' or row['authorization_version'] != row['current_version']:
            raise HTTPException(401, 'Your session has ended. Sign in again.')
        if mutation and not secrets.compare_digest(request.headers.get('x-hearth-csrf', ''), row['csrf_token']):
            raise HTTPException(403, 'The request verification token is missing or invalid.')
        try:
            tokens = json.loads(cipher(settings).decrypt(row['credentials'].encode()))
            if tokens['expires_at'] < time.time() + 30:
                fresh = token_request(settings, 'token', {'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token']})
                tokens.update(fresh)
                tokens['expires_at'] = int(time.time()) + int(fresh['expires_in'])
            active = token_request(settings, 'token/introspect', {'token': tokens['access_token']})
            if active.get('active') is not True or active.get('sub') != tokens['subject'] or active.get('iss') != settings.issuer:
                raise ValueError('inactive identity')
        except Exception:
            raise HTTPException(401, 'The identity session could not be verified. Sign in again.') from None
        roles = connection.execute(text('SELECT role FROM role_grants WHERE user_id=:user AND farm_id=:farm'),
                                   {'user': row['user_id'], 'farm': row['farm_id']}).scalars().all()
        permissions = frozenset().union(*(ROLES.get(role, frozenset()) for role in roles))
        connection.execute(text('UPDATE browser_sessions SET last_seen_at=now(),credentials=:credentials WHERE token_hash=:hash'),
            {'hash': digest(raw), 'credentials': cipher(settings).encrypt(json.dumps(tokens).encode()).decode()})
        principal = Principal(row['user_id'], row['farm_id'], permissions, row['current_version'])
        request.state.principal = principal
        request.state.identity = dict(row) | {'roles': roles, 'tokens': tokens}
        return principal


@router.get('/api/v1/session', tags=['identity'])
def session(request: Request):
    principal = authenticate(request)
    row = request.state.identity
    settings = request.app.state.settings
    return {'id': str(principal.id), 'display_name': row['display_name'], 'roles': row['roles'],
            'permissions': sorted(principal.permissions), 'audience': settings.audience,
            'csrf_token': row['csrf_token'], 'expires_at': row['expires_at'].isoformat(),
            'admin_origin': settings.admin_origin, 'user_origin': settings.user_origin}


@router.post('/api/v1/logout', tags=['identity'])
def logout(request: Request):
    settings = request.app.state.settings
    check_origin(request, mutation=True)
    raw = request.cookies.get(cookie_name(settings), '')
    with request.app.state.engine.begin() as connection:
        row = connection.execute(text('SELECT csrf_token,credentials FROM browser_sessions WHERE token_hash=:hash AND audience=:audience AND farm_id=:farm FOR UPDATE'),
            {'hash': digest(raw), 'audience': settings.audience, 'farm': settings.farm_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(401, 'Your session has already ended.')
        if not secrets.compare_digest(request.headers.get('x-hearth-csrf', ''), row['csrf_token']):
            raise HTTPException(403, 'The request verification token is missing or invalid.')
        connection.execute(text('DELETE FROM browser_sessions WHERE token_hash=:hash AND audience=:audience'),
            {'hash': digest(raw), 'audience': settings.audience})
    try:
        tokens = json.loads(cipher(settings).decrypt(row['credentials'].encode()))
        token_request(settings, 'revoke', {'token': tokens['refresh_token'], 'token_type_hint': 'refresh_token'})
    except Exception:
        pass  # Local session is already invalidated even during an identity outage.
    response = RedirectResponse(settings.origin, status_code=303)
    response.delete_cookie(cookie_name(settings), secure=True, httponly=True, samesite='lax')
    return response
