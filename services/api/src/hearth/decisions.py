"""Private decision jobs and independent internal/member assignments."""
import hashlib
import json
import time
from threading import BoundedSemaphore
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import text

from hearth import decision_transport
from hearth.client_keys import bearer, key_current, principal_current
from hearth.contracts import DecisionRequest
from hearth.database import scoped_session
from hearth.identity import authenticate
from hearth.inference import ProviderError
from hearth.policy import require_capability, scoped_permissions
from hearth.providers import administrator, claim_pool, release_pool, target_record

router = APIRouter()
DEFAULTS = {'revision': 1, 'mode': 'legacy', 'source': 'builtin', 'target_id': None, 'fallback_builtin': True,
            'member_builtin': True, 'threshold': .85, 'deadline_ms': 5000, 'shadow_sample': 0}
FEATURES = ['decision.choice', 'decision.score', 'decision.boolean']
_member_slots = BoundedSemaphore(4)


def member_work(*args):
    try:
        execute(*args)
    finally:
        _member_slots.release()


class DecisionSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1)
    mode: Literal['legacy', 'shadow', 'semantic']
    source: Literal['builtin', 'dedicated']
    target_id: UUID | None = None
    fallback_builtin: StrictBool = True
    member_builtin: StrictBool = True
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    deadline_ms: int = Field(strict=True, ge=100, le=10000)
    shadow_sample: int = Field(strict=True, ge=0, le=100)

    @model_validator(mode='after')
    def selected_source(self):
        if self.source == 'dedicated' and self.target_id is None:
            raise ValueError('Select a verified dedicated decision target.')
        return self


class Evaluate(DecisionRequest):
    target_id: UUID | None = None
    use_route: StrictBool = False

    @model_validator(mode='after')
    def one_assignment(self):
        if self.use_route and self.target_id:
            raise ValueError('Choose an assigned route or one explicit target, not both.')
        return self


def configuration(db):
    row = db.execute(text('SELECT * FROM decision_settings LIMIT 1')).mappings().one_or_none()
    return dict(row) if row else dict(DEFAULTS)


def qualified(row):
    return row['protocol'] == 'hearth.decision.v1' and row['state'] == 'ready' and set(FEATURES) <= set(row['features'])


def bound_target(db, target_id, *, lock=False):
    if not db.execute(text("SELECT 1 FROM capability_bindings WHERE capability_id='decision.evaluate' AND target_id=:id"), {'id': target_id}).first():
        raise HTTPException(409, 'This dedicated target is no longer assigned to Decisions.')
    row = target_record(db, target_id, lock=lock)
    if not qualified(row):
        raise HTTPException(409, 'The decision target needs successful typed verification.')
    return row


def builtin_status(settings):
    try:
        return decision_transport.information(settings).model_dump(mode='json')
    except ProviderError as exc:
        return {'ready': False, 'reason': str(exc)}


def reconcile(db):
    """Never replay work abandoned by a process. Unknown dedicated work stays fenced."""
    rows = db.execute(text("SELECT id,target_id FROM decision_runs WHERE state='running' AND created_at<now()-interval '90 seconds' FOR UPDATE")).mappings().all()
    for row in rows:
        if row['target_id']:
            target = target_record(db, row['target_id'])
            release_pool(db, target['resource_pool_id'], row['id'], uncertain=True)
        db.execute(text("UPDATE decision_runs SET state='failed',reason='The decision was interrupted or exceeded its deadline. It was not replayed.',finished_at=now() WHERE id=:id"), {'id': row['id']})


@router.get('/api/v1/decision-settings', tags=['decisions'])
def get_settings(request: Request):
    principal = administrator(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        reconcile(db)
        config = configuration(db)
        ids = db.execute(text("SELECT target_id FROM capability_bindings WHERE capability_id='decision.evaluate' ORDER BY priority DESC,target_id")).scalars().all()
        targets = [target_record(db, item) for item in ids]
    return {'settings': {key: config[key] for key in DEFAULTS}, 'builtin': builtin_status(request.app.state.settings),
            'targets': [{'id': str(t['id']), 'name': t['name'], 'model': t['model_id'], 'ready': qualified(t)} for t in targets]}


@router.put('/api/v1/decision-settings', tags=['decisions'])
def put_settings(request: Request, data: DecisionSettings):
    principal = administrator(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,0))'), {'farm': str(principal.farm_id)})
        current = configuration(db)
        if current['revision'] != data.revision:
            raise HTTPException(409, 'Decision settings changed. Reload before saving.')
        if data.source == 'dedicated':
            bound_target(db, data.target_id)
        values = data.model_dump() | {'farm': principal.farm_id, 'revision': data.revision+1}
        db.execute(text('INSERT INTO decision_settings(farm_id,revision,mode,source,target_id,fallback_builtin,member_builtin,threshold,deadline_ms,shadow_sample) VALUES(:farm,:revision,:mode,:source,:target_id,:fallback_builtin,:member_builtin,:threshold,:deadline_ms,:shadow_sample) ON CONFLICT(farm_id) DO UPDATE SET revision=:revision,mode=:mode,source=:source,target_id=:target_id,fallback_builtin=:fallback_builtin,member_builtin=:member_builtin,threshold=:threshold,deadline_ms=:deadline_ms,shadow_sample=:shadow_sample'), values)
        db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:owner,'decision.settings.changed',CAST(:metadata AS jsonb))"),
                   {'farm': principal.farm_id, 'owner': principal.id, 'metadata': json.dumps(data.model_dump(mode='json') | {'revision': data.revision+1})})
    return data.model_dump(mode='json') | {'revision': data.revision+1}


def member(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    if request.app.state.settings.audience != 'user':
        raise HTTPException(403, 'Open Decisions in your workspace.')
    principal.require('capability.decision.evaluate')
    return principal


@router.get('/api/v1/decisions', tags=['decisions'])
def listing(request: Request):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        reconcile(db)
        config = configuration(db)
        ids = db.execute(text("SELECT target_id FROM capability_bindings WHERE capability_id='decision.evaluate' ORDER BY priority DESC,target_id")).scalars().all()
        targets = [target_record(db, item) for item in ids]
        jobs = [dict(row) for row in db.execute(text('SELECT * FROM decision_runs ORDER BY created_at DESC LIMIT 50')).mappings()]
        observations = [dict(row) for row in db.execute(text('SELECT metadata,created_at FROM decision_observations ORDER BY created_at DESC LIMIT 30')).mappings()]
    builtin = builtin_status(request.app.state.settings) if config['member_builtin'] else None
    return {'builtin': builtin, 'targets': [{'id': str(t['id']), 'name': t['name'], 'model': t['model_id'], 'ready': qualified(t)} for t in targets], 'items': jobs, 'comparisons': observations}


def admit(engine, settings, principal, data, key=None):
    body = DecisionRequest.model_validate(data.model_dump(exclude={'target_id', 'use_route'}))
    fingerprint = hashlib.sha256(json.dumps(data.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    prepared = None
    if data.use_route:
        from hearth.route_decisions import select_target
        prepared = select_target(engine, settings, principal, 'decision.evaluate')
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,29))'), {'owner': str(principal.id)})
        reconcile(db)
        require_capability(db, 'decision.evaluate')
        if not principal_current(db, principal) or (key and not key_current(db, principal, key)):
            raise HTTPException(401, 'This account or client key changed.')
        old = db.execute(text('SELECT * FROM decision_runs WHERE id=:id'), {'id': data.id}).mappings().one_or_none()
        if old:
            if old['request_hash'] != fingerprint:
                raise HTTPException(409, 'This request ID was already used for different decision input.')
            return dict(old), None, None
        if db.execute(text("SELECT count(*) FROM decision_runs WHERE state='running' AND created_at>now()-interval '2 minutes'")).scalar_one() >= 1:
            raise HTTPException(429, 'Wait for your current decision to finish or cancel it.')
        config = configuration(db)
        target = None
        if data.target_id or data.use_route:
            if data.use_route:
                from hearth.routing import select
                target = select(db, 'decision.evaluate', prepared=prepared)
                if target is None:
                    raise HTTPException(409, 'No assigned decision target is idle and verified.')
            else:
                target = bound_target(db, data.target_id, lock=True)
            if target['active_run_id']:
                raise HTTPException(409, 'This decision target is busy.')
            claim_pool(db, target, data.id, principal.id)
        elif not config['member_builtin'] or not settings.decision_socket:
            raise HTTPException(409, 'Built-in Decisions are not available for member requests.')
        receipt = {'schema_version': 1, 'source': 'dedicated' if target else 'builtin', 'target_id': str(target['id']) if target else None,
                   'target_revision': target['revision'] if target else None, 'settings_revision': config['revision'],
                   'authorization_version': principal.authorization_version, 'key_id': str(key) if key else None}
        if prepared:
            receipt['selection'] = target['_selection']
        db.execute(text('INSERT INTO decision_runs(id,farm_id,owner_id,target_id,request,request_hash,receipt) VALUES(:id,:farm,:owner,:target,CAST(:request AS jsonb),:hash,CAST(:receipt AS jsonb))'),
                   {'id': data.id, 'farm': principal.farm_id, 'owner': principal.id, 'target': target['id'] if target else None,
                    'request': json.dumps(body.model_dump(mode='json')), 'hash': fingerprint, 'receipt': json.dumps(receipt)})
    return {'id': data.id, 'state': 'running', 'receipt': receipt}, target, body


def execute(engine, settings, principal, target, data, key=None):
    result, problem = None, None
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            if not principal_current(db, principal) or (key and not key_current(db, principal, key)):
                raise ProviderError('Access changed before the decision started.', provider_fault=False)
            row = db.execute(text('SELECT cancel_requested FROM decision_runs WHERE id=:id'), {'id': data.id}).one()
            if row.cancel_requested:
                raise ProviderError('Decision cancelled before it started.', provider_fault=False)
            if target:
                current = bound_target(db, target['id'])
                if current['revision'] != target['revision'] or current['active_run_id'] != data.id:
                    raise ProviderError('The selected decision target changed.', provider_fault=False)
        result = decision_transport.evaluate(settings, data, target)
    except (ProviderError, HTTPException) as exc:
        problem = exc if isinstance(exc, ProviderError) else ProviderError('The selected decision target changed.', provider_fault=False)
    except Exception:
        problem = ProviderError('Decision execution could not be confirmed.', uncertain=True)
    finally:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            row = db.execute(text('SELECT * FROM decision_runs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
            if row['state'] == 'running':
                permitted = principal_current(db, principal) and (not key or key_current(db, principal, key))
                permitted = permitted and 'capability.decision.evaluate' in scoped_permissions(db)
                if target:
                    from hearth.provider_health import record_failure
                    current = target_record(db, target['id'])
                    permitted = permitted and current['revision'] == target['revision'] and current['active_run_id'] == data.id and qualified(current)
                    release_pool(db, target['resource_pool_id'], data.id, uncertain=bool(problem and problem.uncertain))
                    record_failure(db, target, problem)
                cancelled = row['cancel_requested'] or not permitted
                db.execute(text('UPDATE decision_runs SET state=:state,result=CAST(:result AS jsonb),reason=:reason,finished_at=now() WHERE id=:id'),
                           {'id': data.id, 'state': 'cancelled' if cancelled else 'failed' if problem else 'completed',
                            'result': json.dumps(result.model_dump(mode='json')) if result and not cancelled and not problem else None,
                            'reason': 'Decision cancelled or access changed.' if cancelled else str(problem) if problem else None})


@router.post('/api/v1/decisions', tags=['decisions'], status_code=202)
def create(request: Request, data: Evaluate):
    principal = member(request, True)
    if not _member_slots.acquire(blocking=False):
        raise HTTPException(429, 'Member decision capacity is busy. Please try again shortly.')
    try:
        row, target, body = admit(request.app.state.engine, request.app.state.settings, principal, data)
        if body:
            request.app.state.decision_executor.submit(member_work, request.app.state.engine, request.app.state.settings, principal, target, body)
        else:
            _member_slots.release()
    except BaseException:
        _member_slots.release()
        raise
    return row


@router.get('/api/v1/decisions/{decision_id}', tags=['decisions'])
def get(request: Request, decision_id: UUID):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        reconcile(db)
        row = db.execute(text('SELECT * FROM decision_runs WHERE id=:id'), {'id': decision_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(404, 'This decision is not in your workspace.')
        return dict(row)


@router.delete('/api/v1/decisions/{decision_id}', tags=['decisions'])
def remove(request: Request, decision_id: UUID):
    principal = member(request, True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT * FROM decision_runs WHERE id=:id FOR UPDATE'), {'id': decision_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(404, 'This decision is not in your workspace.')
        if row['state'] == 'running':
            db.execute(text('UPDATE decision_runs SET cancel_requested=true WHERE id=:id'), {'id': decision_id})
            return {'stopping': True}
        db.execute(text('DELETE FROM decision_runs WHERE id=:id'), {'id': decision_id})
    return {'deleted': True}


@router.post('/v1/decisions', tags=['clients'])
def client_decision(request: Request, data: Evaluate):
    client = bearer(request)
    if 'decision.evaluate' not in client.capabilities:
        raise HTTPException(403, 'This key does not allow decisions.')
    engine, settings = request.app.state.engine, request.app.state.settings
    if not _member_slots.acquire(blocking=False):
        raise HTTPException(429, 'Member decision capacity is busy. Please try again shortly.')
    try:
        row, target, body = admit(engine, settings, client.principal, data, client.key_id)
        if body:
            execute(engine, settings, client.principal, target, body, client.key_id)
    finally:
        _member_slots.release()
    with scoped_session(engine, client.principal.id, client.principal.farm_id) as db:
        row = dict(db.execute(text('SELECT * FROM decision_runs WHERE id=:id'), {'id': data.id}).mappings().one())
    if row['state'] in {'failed', 'cancelled'}:
        raise HTTPException(503, row['reason'])
    return row


def internal(engine, settings, principal, data, config, *, shadow=False):
    """Ancillary routing service; output is only a proposal checked against caller grants."""
    started = time.monotonic()
    attempts = []
    sources = [config['source']]
    if config['source'] == 'dedicated' and config['fallback_builtin']:
        sources.append('builtin')
    for source in sources:
        target, claimed, problem = None, False, None
        budget = config['deadline_ms']/1000 - (time.monotonic()-started)
        if budget <= .02:
            break
        try:
            if source == 'dedicated':
                if config['fallback_builtin']:
                    budget *= .6
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    if not principal_current(db, principal):
                        raise HTTPException(401, 'Access changed.')
                    target = bound_target(db, config['target_id'], lock=True)
                    if target['active_run_id']:
                        raise HTTPException(409, 'Decision pool busy.')
                    claim_pool(db, target, data.id, principal.id)
                    claimed = True
            result = decision_transport.evaluate(settings, data, target, budget=budget, lane='member' if shadow else 'internal')
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                if not principal_current(db, principal):
                    raise HTTPException(401, 'Access changed during the decision.')
                if target:
                    current = bound_target(db, target['id'])
                    if current['revision'] != target['revision'] or current['active_run_id'] != data.id:
                        raise HTTPException(409, 'The decision target changed during evaluation.')
            return result, {'source': source, 'target_id': str(target['id']) if target else None,
                            'model': result.model, 'model_revision': result.model_revision, 'manifest_sha256': result.manifest_sha256,
                            'settings_revision': config['revision'], 'attempts': attempts, 'elapsed_ms': (time.monotonic()-started)*1000}
        except (ProviderError, HTTPException) as exc:
            problem = exc
            reason = ('busy_or_changed' if exc.status_code == 409 else 'authorization_changed') if isinstance(exc, HTTPException) else ('execution_unconfirmed' if exc.uncertain else 'unavailable_or_invalid')
            attempts.append({'source': source, 'reason': reason})
            if isinstance(exc, HTTPException) and exc.status_code in {401, 403}:
                break
        finally:
            if claimed:
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    from hearth.provider_health import record_failure
                    release_pool(db, target['resource_pool_id'], data.id, uncertain=isinstance(problem, ProviderError) and problem.uncertain)
                    if isinstance(problem, ProviderError):
                        record_failure(db, target, problem)
    raise ProviderError('No qualified routing decision arrived before the deadline.', provider_fault=False)
