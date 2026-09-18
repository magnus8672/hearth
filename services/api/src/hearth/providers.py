"""Administrator-owned external services, feature evidence and shared admission."""
import ipaddress
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, model_validator
from sqlalchemy import text

from hearth import geometry_transport, image_transport, speech_transport, transcription_probe, transcription_transport, vision
from hearth.contracts import GeometryGeneration, ImageGeneration, SpeechGeneration, TranscriptionRequest
from hearth.database import scoped_session
from hearth.identity import authenticate, cipher
from hearth.inference import ProviderError, chat_stream, list_models, normalize_url

router = APIRouter()


class ConnectProvider(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=2048)
    model_id: str = Field(min_length=1, max_length=200)
    api_key: SecretStr = SecretStr('')
    resource_pool: str | None = Field(default=None, min_length=1, max_length=120)
    local_only: StrictBool
    protocol: Literal['openai.chat.v1', 'hearth.image.v1', 'hearth.speech.v1', 'hearth.transcription.v1', 'hearth.geometry.v1'] = 'openai.chat.v1'
    tls_ca_pem: str = Field(default='', max_length=16384)
    residency_policy: Literal['unknown', 'lmstudio_loaded'] = 'unknown'
    allow_insecure_http: StrictBool = False

    @model_validator(mode='after')
    def residency_protocol(self):
        if self.residency_policy == 'lmstudio_loaded' and self.protocol != 'openai.chat.v1':
            raise ValueError('LM Studio residency checks require an OpenAI-compatible chat target.')
        if self.allow_insecure_http and urlsplit(self.base_url).scheme != 'http':
            raise ValueError('The HTTP risk override applies only to an HTTP server address.')
        return self


class RetargetProvider(ConnectProvider):
    revision: int = Field(strict=True, ge=1)
    clear_api_key: StrictBool = False


class ProviderRevision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1)


class ProviderProbe(ProviderRevision):
    vision: StrictBool = False
    tools: StrictBool = False


class HttpConsent(ProviderRevision):
    allow_insecure_http: StrictBool


class ClearPool(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_run_id: UUID
    confirm_backend_idle: StrictBool


def administrator(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    if request.app.state.settings.audience != 'admin':
        raise HTTPException(403, 'Open Administration to manage model servers.')
    principal.require('provider.configure')
    return principal


def target_record(db, target_id, *, lock=False, idle_only=False):
    row = db.execute(text('SELECT t.*,c.base_url,c.credential,c.tls_ca_pem,c.allow_insecure_http,c.name,p.execution_state,p.active_run_id,p.lease_until '
        'FROM inference_targets t JOIN provider_connections c ON c.id=t.connection_id '
        'JOIN provider_pools p ON p.id=t.resource_pool_id WHERE t.id=:id' + (' AND p.active_run_id IS NULL' if idle_only else '') + (' FOR UPDATE OF t,p' if lock else '') + (' SKIP LOCKED' if lock and idle_only else '')),
        {'id': target_id}).mappings().one_or_none()
    if not row:
        if idle_only:
            return None
        raise HTTPException(404, 'This model target is not available in this farm.')
    return dict(row)


def credential_for(row, settings):
    return cipher(settings).decrypt(row['credential'].encode()).decode() if row['credential'] else ''


def transport_settings(row, settings):
    return settings.model_copy(update={'provider_ca_pem': row.get('tls_ca_pem', ''),
                                      'provider_http_approved_url': normalize_url(row['base_url']) if row.get('allow_insecure_http', False) else '',
                                      'provider_residency_policy': row.get('residency_policy', 'unknown')})


def audit_http_consent(db, principal, connection_id, allowed):
    db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,:action,jsonb_build_object('connection_id',CAST(:id AS text),'allow_insecure_http',CAST(:allowed AS boolean)))"),
               {'farm': principal.farm_id, 'actor': principal.id, 'id': str(connection_id), 'allowed': allowed,
                'action': 'provider.http_risk_accepted' if allowed else 'provider.http_risk_revoked'})


def change_http_consent(db, principal, connection_id, allowed, *, excluding=None):
    """Caller holds the farm mutation lock. Consent is bound to one exact URL.

    All models share a connection's transport; fence their evidence together.
    An in-flight or uncertain execution must finish before changing policy.
    """
    connection = db.execute(text('SELECT base_url,allow_insecure_http FROM provider_connections WHERE id=:id FOR UPDATE'), {'id': connection_id}).mappings().one()
    if urlsplit(connection['base_url']).scheme != 'http':
        raise HTTPException(400, 'This connection uses HTTPS. Its certificate verification stays enabled.')
    if connection['allow_insecure_http'] == allowed:
        return False
    rows = db.execute(text('SELECT t.id,p.active_run_id FROM inference_targets t JOIN provider_pools p ON p.id=t.resource_pool_id WHERE t.connection_id=:id ORDER BY t.id FOR UPDATE OF t,p'), {'id': connection_id}).mappings().all()
    if any(row['active_run_id'] for row in rows):
        raise HTTPException(409, 'Wait for all models on this server to finish, including uncertain jobs, before changing its HTTP approval.')
    db.execute(text('UPDATE provider_connections SET allow_insecure_http=:allowed WHERE id=:id'), {'id': connection_id, 'allowed': allowed})
    condition = ' AND id<>:excluding' if excluding else ''
    db.execute(text("UPDATE inference_targets SET revision=revision+1,state=CASE WHEN state='disabled' THEN 'disabled' ELSE 'configured' END,features='[]',profile='{}',verified_until=NULL,probed_at=NULL,reason='HTTP approval changed. Verify before dispatch.' WHERE connection_id=:connection" + condition), {'connection': connection_id, 'excluding': excluding})
    audit_http_consent(db, principal, connection_id, allowed)
    return True


def pool_name(data, base_url):
    # Ports on one host may share a GPU. Defaults are conservative per host,
    # never one global pool, and explicit groups support multiple GPUs/aliases.
    host = urlsplit(base_url).hostname
    try:
        if ipaddress.ip_address(host).is_loopback:
            host = 'localhost'
    except ValueError:
        pass
    return data.resource_pool or ('Host ' + host if len(host) <= 115 else 'Host ' + sha256(host.encode()).hexdigest())


def validate_ca(pem):
    if not pem:
        return ''
    try:
        if len(pem) > 16384 or 'PRIVATE KEY' in pem or pem.count('-----BEGIN CERTIFICATE-----') != 1:
            raise ValueError()
        cert = x509.load_pem_x509_certificate(pem.encode())
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError()
        if not cert.not_valid_before_utc <= datetime.now(UTC) < cert.not_valid_after_utc:
            raise ValueError()
        return cert.fingerprint(hashes.SHA256()).hex()
    except (ValueError, x509.ExtensionNotFound):
        raise HTTPException(400, 'Supply one currently valid public CA certificate in PEM format, without a private key.') from None


def ca_fingerprint(pem):
    return x509.load_pem_x509_certificate(pem.encode()).fingerprint(hashes.SHA256()).hex() if pem else None


def create_target(engine, settings, principal, data):
    principal.require('provider.configure')
    if not data.local_only:
        raise HTTPException(400, 'This build connects trusted local inference only. Cloud spending remains disabled.')
    base_url = normalize_url(data.base_url)
    resource_pool = pool_name(data, base_url)
    validate_ca(data.tls_ca_pem)
    if data.tls_ca_pem and not base_url.startswith('https://'):
        raise HTTPException(400, 'A trusted CA requires an HTTPS server address.')
    key = data.api_key.get_secret_value()
    if len(key) > 2048 or any(ord(c) < 32 or ord(c) > 126 for c in key):
        raise HTTPException(400, 'Use an API key with at most 2048 printable characters.')
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,0))'), {'farm': str(principal.farm_id)})
        if db.execute(text('SELECT count(*) FROM inference_targets')).scalar_one() >= 32:
            raise HTTPException(409, 'This build supports up to 32 configured model targets.')
        connection = db.execute(text('SELECT * FROM provider_connections WHERE base_url=:url'), {'url': base_url}).mappings().one_or_none()
        if connection:
            connection_id = connection['id']
            if data.allow_insecure_http != connection['allow_insecure_http']:
                raise HTTPException(409, 'This server already has a saved HTTP policy. Use its saved approval, or change it on the existing server card.')
            if key and key != credential_for(connection, settings):
                raise HTTPException(409, 'This server is already registered with different credentials.')
            if data.tls_ca_pem.strip() != connection['tls_ca_pem'].strip():
                raise HTTPException(409, 'This server is already registered with different certificate trust.')
            if db.execute(text('SELECT id FROM inference_targets WHERE connection_id=:id AND model_id=:model'), {'id': connection_id, 'model': data.model_id}).first():
                raise HTTPException(409, 'That model is already registered. Use its verification control below.')
        else:
            connection_id = uuid4()
            db.execute(text('INSERT INTO provider_connections(id,farm_id,name,base_url,credential,tls_ca_pem,allow_insecure_http) VALUES(:id,:farm,:name,:url,:credential,:ca,:http)'),
                {'id': connection_id, 'farm': principal.farm_id, 'name': data.name, 'url': base_url,
                 'credential': cipher(settings).encrypt(key.encode()).decode() if key else '', 'ca': data.tls_ca_pem, 'http': data.allow_insecure_http})
            if data.allow_insecure_http:
                audit_http_consent(db, principal, connection_id, True)
        pool = db.execute(text('SELECT id FROM provider_pools WHERE name=:name'), {'name': resource_pool}).scalar_one_or_none()
        if not pool:
            pool = uuid4()
            db.execute(text('INSERT INTO provider_pools(id,farm_id,name) VALUES(:id,:farm,:name)'), {'id': pool, 'farm': principal.farm_id, 'name': resource_pool})
        from hearth.workers import require_binding
        require_binding(db, connection_id, pool)
        target = uuid4()
        db.execute(text('INSERT INTO inference_targets(id,farm_id,connection_id,resource_pool_id,model_id,protocol,residency_policy) VALUES(:id,:farm,:connection,:pool,:model,:protocol,:residency)'),
            {'id': target, 'farm': principal.farm_id, 'connection': connection_id, 'pool': pool, 'model': data.model_id, 'protocol': data.protocol, 'residency': data.residency_policy})
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'provider.configured',jsonb_build_object('target_id',CAST(:target AS text)))"),
            {'farm': principal.farm_id, 'actor': principal.id, 'target': str(target)})
    return {'id': target, 'revision': 1, 'state': 'configured'}


def claim_pool(db, row, run_id, owner_id, *, preparing=False):
    if row['active_run_id']:
        raise HTTPException(409, 'This resource group is occupied or awaiting confirmation that its model is idle.')
    if not preparing:
        from hearth.workers import require_available
        require_available(db, row)
    db.execute(text("UPDATE provider_pools SET active_run_id=:run,active_owner_id=:owner,execution_state='running',lease_until=now()+interval '240 seconds' WHERE id=:pool"),
        {'run': run_id, 'owner': owner_id, 'pool': row['resource_pool_id']})


def release_pool(db, pool_id, run_id, *, uncertain=False):
    if uncertain:
        db.execute(text("UPDATE provider_pools SET execution_state='unknown',lease_until=now() WHERE id=:pool AND active_run_id=:run"), {'pool': pool_id, 'run': run_id})
    else:
        db.execute(text("UPDATE provider_pools SET active_run_id=NULL,active_owner_id=NULL,execution_state='idle',lease_until=NULL WHERE id=:pool AND active_run_id=:run"), {'pool': pool_id, 'run': run_id})


def probe_target(engine, settings, principal, target_id, revision, *, check_vision=False, check_tools=False):
    principal.require('provider.configure')
    receipt = uuid4()
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        row = target_record(db, target_id, lock=True)
        if row['revision'] != revision:
            raise HTTPException(409, 'The target changed. Refresh its settings before verifying.')
        if (check_vision or check_tools) and row['protocol'] != 'openai.chat.v1':
            raise HTTPException(400, 'Vision and tools require an OpenAI-compatible model server.')
        claim_pool(db, row, receipt, principal.id)
        db.execute(text("UPDATE inference_targets SET state='configured',verified_until=NULL,features='[]',revision=revision+1 WHERE id=:id"), {'id': target_id})
    problem, warning = None, None
    features = []
    profile = {}
    try:
        transport = transport_settings(row, settings)
        key = credential_for(row, settings)
        if row['protocol'] == 'hearth.transcription.v1':
            info = transcription_transport.information(row['base_url'], key, transport)
            if info.model != row['model_id'] or not info.offline or not info.job_cancellation or 'en' not in info.languages:
                raise ProviderError('The transcription provider does not offer the selected local English model and job controls.')
            def progress(value):
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': row['resource_pool_id'], 'run': receipt})
                return False
            audio = transcription_probe.recording()
            result = transcription_transport.transcribe(row['base_url'], key, transport, TranscriptionRequest(id=receipt, model=row['model_id'], audio_sha256=sha256(audio).hexdigest()), audio, progress)
            wer = transcription_probe.word_error_rate(transcription_probe.REFERENCE, result.text)
            if result.state == 'completed' and result.manifest_sha256 == info.manifest_sha256 and wer <= .25:
                features = ['audio.transcribe', 'audio.jobs']
                profile = info.model_dump(mode='json') | {'probe_word_error_rate': wer}
            else:
                raise ProviderError('The known-recording transcription check did not pass. Check the selected model.')
        elif row['protocol'] == 'hearth.speech.v1':
            info = speech_transport.information(row['base_url'], key, transport)
            if info.model != row['model_id'] or not info.offline or not info.job_cancellation or info.default_voice not in info.voices:
                raise ProviderError('The speech provider does not offer the selected local model, default voice and job controls.')
            def progress(value):
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': row['resource_pool_id'], 'run': receipt})
                return False
            result, artifact = speech_transport.render(row['base_url'], key, transport, SpeechGeneration(id=receipt, model=row['model_id'], voice=info.default_voice, input='Welcome home. Your hearth is ready to speak.'), progress)
            if result.state == 'completed' and artifact and result.manifest_sha256 == info.manifest_sha256:
                features = ['audio.speak', 'audio.jobs']
                profile = info.model_dump(mode='json')
        elif row['protocol'] == 'hearth.geometry.v1':
            from hearth.geometry_probe import reference
            info = geometry_transport.information(row['base_url'], key, transport)
            if info.model != row['model_id'] or not info.offline or not info.job_cancellation:
                raise ProviderError('The geometry provider does not offer the selected local model and job controls.')
            def progress(value):
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': row['resource_pool_id'], 'run': receipt})
                return False
            image = reference()
            result, artifact = geometry_transport.render(row['base_url'], key, transport, GeometryGeneration(id=receipt, model=row['model_id'], image_sha256=sha256(image).hexdigest()), image, progress)
            if result.state == 'completed' and artifact and result.manifest_sha256 == info.manifest_sha256:
                features = ['geometry.image_to_3d', 'geometry.jobs']
                profile = info.model_dump(mode='json')
        elif row['protocol'] == 'hearth.image.v1':
            info = image_transport.information(row['base_url'], key, transport)
            if info.model != row['model_id'] or not info.offline or not info.job_cancellation:
                raise ProviderError('The image provider does not offer the selected local model and job controls.')
            def progress(value):
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': row['resource_pool_id'], 'run': receipt})
                return False
            result, artifact = image_transport.render(row['base_url'], key, transport, ImageGeneration(id=receipt, model=row['model_id'], prompt='A small warm stone cottage in a pine forest, illustration', seed=451), progress)
            if result.state == 'completed' and artifact and result.manifest_sha256 == info.manifest_sha256:
                features = ['image.text_to_image', 'image.jobs']
                profile = info.model_dump(mode='json')
        else:
            if row['model_id'] not in list_models(row['base_url'], key, transport):
                raise ProviderError('The selected model is not listed by this server. Check its exact model identifier.')
            answer = ''
            for kind, value in chat_stream(row['base_url'], key, row['model_id'],
                    [{'role': 'user', 'content': 'Reply briefly with: hearth is ready.'}], transport, maximum_tokens=4096):
                if kind == 'text':
                    answer += value
                if kind == 'done' and value == 'stop' and answer.strip():
                    features = ['chat', 'streaming']
        if not features:
            raise ProviderError('The server did not complete the required capability probe.')
        if check_vision:
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE active_run_id=:run"), {'run': receipt})
            try:
                profile.update(vision.probe(row['base_url'], key, row['model_id'], transport))
                features.append('vision')
            except ProviderError as exc:
                if exc.uncertain:
                    raise
                warning = 'Vision was not verified. Text replies remain available. ' + str(exc)
                profile['vision_probe'] = 'failed'
        if check_tools:
            from hearth import tool_probe
            try:
                profile.update(tool_probe.probe(row['base_url'], key, row['model_id'], transport))
                features.append('tools')
            except ProviderError as exc:
                if exc.uncertain:
                    raise
                warning = 'Tool calling was not verified. Text replies remain available. '+str(exc)
                profile['tool_probe'] = 'failed'
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('The provider check was interrupted. Verify that the model is idle before retrying.', uncertain=True)
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,0))'), {'farm': str(principal.farm_id)})
        current = target_record(db, target_id, lock=True)
        if current['active_run_id'] != receipt:
            raise HTTPException(409, 'The provider changed during verification. Run a fresh check.')
        release_pool(db, row['resource_pool_id'], receipt, uncertain=bool(problem and problem.uncertain))
        authorized = db.execute(text("SELECT EXISTS(SELECT 1 FROM users u JOIN role_grants g ON g.user_id=u.id AND g.farm_id=u.farm_id WHERE u.id=:owner AND u.farm_id=:farm AND u.state='active' AND u.authorization_version=:version AND g.role IN ('Owner','FarmAdmin'))"),
            {'owner': principal.id, 'farm': principal.farm_id, 'version': principal.authorization_version}).scalar_one()
        if current['revision'] != revision + 1 or not authorized:
            return {'id': target_id, 'revision': current['revision'], 'state': current['state'], 'features': [], 'reason': 'Settings or authorization changed. Run a fresh check.', 'admin_agent_ready': False}
        db.execute(text("UPDATE inference_targets SET state=:state,features=CAST(:features AS jsonb),profile=CAST(:profile AS jsonb),probed_at=now(),verified_until=NULL,reason=:reason WHERE id=:id"),
            {'id': target_id, 'state': 'failed' if problem else 'ready', 'features': json.dumps(features), 'profile': json.dumps(profile), 'ready': not problem, 'reason': str(problem) if problem else warning})
        if not problem:
            db.execute(text("INSERT INTO capability_bindings(farm_id,capability_id,target_id) SELECT :farm,CAST(:capability AS varchar(80)),:target WHERE NOT EXISTS(SELECT 1 FROM capability_routes WHERE capability_id=CAST(:capability AS varchar(80))) ON CONFLICT DO NOTHING"), {'farm': principal.farm_id, 'target': target_id, 'capability': {'hearth.geometry.v1': 'geometry.generate', 'hearth.image.v1': 'image.generate', 'hearth.speech.v1': 'audio.speak', 'hearth.transcription.v1': 'audio.transcribe'}.get(row['protocol'], 'chat.general')})
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'provider.probed',jsonb_build_object('target_id',CAST(:target AS text),'ready',CAST(:ready AS boolean)))"),
            {'farm': principal.farm_id, 'actor': principal.id, 'target': str(target_id), 'ready': not problem})
    return {'id': target_id, 'revision': revision + 1, 'state': 'failed' if problem else 'ready', 'features': features,
            'reason': str(problem) if problem else warning, 'admin_agent_ready': False}


@router.get('/api/v1/providers', tags=['providers'])
def providers(request: Request):
    principal = administrator(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text('SELECT t.id,t.connection_id,t.model_id,t.protocol,t.residency_policy,t.revision,t.state,t.features,t.probed_at,t.verified_until,t.reason,t.resource_pool_id,c.name,c.base_url,c.tls_ca_pem,c.allow_insecure_http,(c.credential<>\'\') AS credential_configured,p.name AS pool_name,p.execution_state,p.active_run_id,p.lease_until FROM inference_targets t JOIN provider_connections c ON c.id=t.connection_id JOIN provider_pools p ON p.id=t.resource_pool_id ORDER BY c.created_at,t.model_id')).mappings().all()
        return {'items': [dict(row) | {'tls_ca_sha256': ca_fingerprint(row['tls_ca_pem']), 'management': 'external', 'locality_assurance': 'operator_declared_local',
            'admin_agent_ready': False, 'expired': False, 'verified_until': None} for row in rows]}


@router.post('/api/v1/providers', tags=['providers'], status_code=201)
def connect(request: Request, data: ConnectProvider):
    principal = administrator(request, mutation=True)
    return create_target(request.app.state.engine, request.app.state.settings, principal, data)


@router.put('/api/v1/providers/{target_id}', tags=['providers'])
def retarget(request: Request, target_id: UUID, data: RetargetProvider):
    principal = administrator(request, mutation=True)
    settings = request.app.state.settings
    if not data.local_only:
        raise HTTPException(400, 'Approve the local execution boundary before saving.')
    base_url = normalize_url(data.base_url)
    resource_pool = pool_name(data, base_url)
    validate_ca(data.tls_ca_pem)
    if data.tls_ca_pem and not base_url.startswith('https://'):
        raise HTTPException(400, 'A trusted CA requires an HTTPS server address.')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,0))'), {'farm': str(principal.farm_id)})
        current = target_record(db, target_id, lock=True)
        if current['revision'] != data.revision:
            raise HTTPException(409, 'This target changed. Refresh before saving.')
        if current['active_run_id']:
            raise HTTPException(409, 'Wait for this resource group to finish before moving the target.')
        key = '' if data.clear_api_key else (data.api_key.get_secret_value() or credential_for(current, settings))
        if len(key) > 2048 or any(ord(c) < 32 or ord(c) > 126 for c in key):
            raise HTTPException(400, 'Use an API key with at most 2048 printable characters.')
        connection = db.execute(text('SELECT * FROM provider_connections WHERE base_url=:url FOR UPDATE'), {'url': base_url}).mappings().one_or_none()
        if connection:
            connection_id = connection['id']
            siblings = db.execute(text('SELECT id FROM inference_targets WHERE connection_id=:id ORDER BY id'), {'id': connection_id}).scalars().all()
            if data.allow_insecure_http != connection['allow_insecure_http']:
                if connection_id != current['connection_id']:
                    raise HTTPException(409, "Use the existing destination server's saved HTTP approval. Change it separately on that server's card.")
                change_http_consent(db, principal, connection_id, data.allow_insecure_http, excluding=target_id)
            if connection_id != current['connection_id'] and siblings and data.name != connection['name']:
                raise HTTPException(409, 'This address belongs to an existing server. Use its saved connection name to move the model there.')
            changed = key != credential_for(connection, settings) or data.tls_ca_pem.strip() != connection['tls_ca_pem'].strip()
            # A shared connection cannot be silently changed by editing one model.
            if changed and any(item != target_id for item in siblings):
                raise HTTPException(409, 'Other models share this address. Move them to a new connection before changing shared credentials or trust.')
            db.execute(text('UPDATE provider_connections SET name=:name,credential=:key,tls_ca_pem=:ca WHERE id=:id'), {'id': connection_id, 'name': data.name, 'key': cipher(settings).encrypt(key.encode()).decode() if key else '', 'ca': data.tls_ca_pem})
        else:
            connection_id = uuid4()
            db.execute(text('INSERT INTO provider_connections(id,farm_id,name,base_url,credential,tls_ca_pem,allow_insecure_http) VALUES(:id,:farm,:name,:url,:key,:ca,:http)'), {'id': connection_id, 'farm': principal.farm_id, 'name': data.name, 'url': base_url, 'key': cipher(settings).encrypt(key.encode()).decode() if key else '', 'ca': data.tls_ca_pem, 'http': data.allow_insecure_http})
            if data.allow_insecure_http:
                audit_http_consent(db, principal, connection_id, True)
        if db.execute(text('SELECT 1 FROM inference_targets WHERE connection_id=:connection AND model_id=:model AND id<>:id'), {'connection': connection_id, 'model': data.model_id, 'id': target_id}).first():
            raise HTTPException(409, 'That model already has a target at this address. Assign that target instead.')
        pool = db.execute(text('SELECT id,active_run_id FROM provider_pools WHERE name=:name FOR UPDATE'), {'name': resource_pool}).mappings().one_or_none()
        if pool and pool['active_run_id']:
            raise HTTPException(409, 'The destination resource group is occupied.')
        pool_id = pool['id'] if pool else uuid4()
        if not pool:
            db.execute(text('INSERT INTO provider_pools(id,farm_id,name) VALUES(:id,:farm,:name)'), {'id': pool_id, 'farm': principal.farm_id, 'name': resource_pool})
        from hearth.workers import require_binding
        require_binding(db, connection_id, pool_id)
        require_binding(db, current['connection_id'], pool_id)
        db.execute(text("UPDATE inference_targets SET connection_id=:connection,resource_pool_id=:pool,model_id=:model,protocol=:protocol,residency_policy=:residency,revision=revision+1,state='configured',features='[]',profile='{}',verified_until=NULL,probed_at=NULL,reason='Connection changed. Verify before dispatch.' WHERE id=:id"), {'id': target_id, 'connection': connection_id, 'pool': pool_id, 'model': data.model_id, 'protocol': data.protocol, 'residency': data.residency_policy})
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'provider.retargeted',jsonb_build_object('target_id',CAST(:id AS text)))"), {'farm': principal.farm_id, 'actor': principal.id, 'id': str(target_id)})
    return {'id': target_id, 'revision': data.revision+1, 'state': 'configured'}


@router.post('/api/v1/providers/{target_id}/probe', tags=['providers'])
def probe(request: Request, target_id: UUID, data: ProviderProbe):
    principal = administrator(request, mutation=True)
    return probe_target(request.app.state.engine, request.app.state.settings, principal, target_id, data.revision, check_vision=data.vision, check_tools=data.tools)


@router.post('/api/v1/providers/{target_id}/http-consent', tags=['providers'])
def http_consent(request: Request, target_id: UUID, data: HttpConsent):
    principal = administrator(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,0))'), {'farm': str(principal.farm_id)})
        current = target_record(db, target_id, lock=True)
        if current['revision'] != data.revision:
            raise HTTPException(409, 'This model changed. Refresh before changing its HTTP approval.')
        changed = change_http_consent(db, principal, current['connection_id'], data.allow_insecure_http)
    return {'id': target_id, 'revision': data.revision + int(changed), 'allow_insecure_http': data.allow_insecure_http}


@router.post('/api/v1/providers/{target_id}/disable', tags=['providers'])
def disable(request: Request, target_id: UUID, data: ProviderRevision):
    principal = administrator(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = target_record(db, target_id, lock=True)
        if row['revision'] != data.revision:
            raise HTTPException(409, 'The target changed. Refresh before changing it.')
        db.execute(text("UPDATE inference_targets SET state='disabled',verified_until=NULL,revision=revision+1 WHERE id=:id"), {'id': target_id})
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'provider.disabled',jsonb_build_object('target_id',CAST(:target AS text)))"),
            {'farm': principal.farm_id, 'actor': principal.id, 'target': str(target_id)})
    return {'state': 'disabled'}


@router.post('/api/v1/provider-pools/{pool_id}/clear', tags=['providers'])
def clear_pool(request: Request, pool_id: UUID, data: ClearPool):
    principal = administrator(request, mutation=True)
    if not data.confirm_backend_idle:
        raise HTTPException(400, 'Confirm that the backend has finished before releasing this resource group.')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT * FROM provider_pools WHERE id=:id FOR UPDATE'), {'id': pool_id}).mappings().one_or_none()
        if not row or row['active_run_id'] != data.expected_run_id:
            raise HTTPException(409, 'The resource group changed. Refresh its status.')
        if row['execution_state'] != 'unknown' and row['lease_until'] and row['lease_until'] > datetime.now(UTC):
            raise HTTPException(409, 'The model still has a current execution lease.')
        release_pool(db, pool_id, data.expected_run_id)
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'provider.pool_cleared',jsonb_build_object('pool_id',CAST(:pool AS text)))"),
            {'farm': principal.farm_id, 'actor': principal.id, 'pool': str(pool_id)})
    return {'state': 'idle'}
