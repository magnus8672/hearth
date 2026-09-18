"""Durable media admission, fair between owners and independent across GPUs.

Only undispatched jobs are resumed after a restart. An expired execution lease
remains fenced in provider_pools until the backend's release is confirmed.
"""
import logging
import time
from datetime import UTC, datetime
from threading import Event, Thread

from sqlalchemy import text

from hearth import conversation_media, workers
from hearth.chat import session_current
from hearth.contracts import GeometryGeneration, ImageGeneration
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.policy import Principal, permissions_for
from hearth.providers import claim_pool, release_pool, target_record

logger = logging.getLogger('hearth')


def enqueue(db, principal, target, job_id, kind="image"):
    # The caller holds the resource pool and owner's workspace locks.
    if db.execute(text("SELECT count(*) FROM capability_queue WHERE owner_id=:owner AND state IN ('queued','starting','dispatched')"), {'owner': principal.id}).scalar_one() >= 8:
        from fastapi import HTTPException
        raise HTTPException(429, 'You already have eight jobs waiting or running. Let one finish or cancel it first.')
    if db.execute(text("SELECT count(*) FROM capability_queue WHERE pool_id=:pool AND state IN ('queued','starting','dispatched')"), {'pool': target['resource_pool_id']}).scalar_one() >= 64:
        from fastapi import HTTPException
        raise HTTPException(429, 'This GPU queue is full. Please try again after some work finishes.')
    worker = workers.for_pool(db, target['resource_pool_id'])
    if worker and (worker['revoked'] or not workers.service_for(worker, target['connection_id'])):
        from fastapi import HTTPException
        raise HTTPException(409, 'This provider is not an approved service for its worker.')
    db.execute(text('INSERT INTO capability_queue(id,kind,farm_id,owner_id,pool_id,target_id,target_revision) VALUES(:id,:kind,:farm,:owner,:pool,:target,:revision)'),
               {'id': job_id, 'kind': kind, 'farm': principal.farm_id, 'owner': principal.id, 'pool': target['resource_pool_id'], 'target': target['id'], 'revision': target['revision']})


def finish_waiting(db, job_id, state, reason):
    kind = db.execute(text("SELECT kind FROM capability_queue WHERE id=:id"), {"id": job_id}).scalar_one()
    table = "geometry_jobs" if kind == "geometry" else "image_jobs"
    db.execute(text(f"UPDATE {table} SET status=:state,reason=:reason,finished_at=now() WHERE id=:id AND status='queued'"), {'id': job_id, 'state': state, 'reason': reason})
    if kind == 'image':
        settle_conversation(db, job_id, state, reason)
    db.execute(text("UPDATE capability_queue SET state='finished' WHERE id=:id"), {'id': job_id})


def settle_conversation(db, job_id, state, reason):
    parent = db.execute(text('SELECT batch_run_id FROM image_jobs WHERE id=:id'), {'id': job_id}).scalar_one_or_none()
    if parent:
        from hearth.image_batches import finish
        plan = db.execute(text('SELECT * FROM image_plans WHERE id=:id'), {'id': parent}).mappings().one()
        finish(db, plan, state, reason)
    else:
        conversation_media.finish(db, job_id, state, reason, None, None)


def waiting_reason(db, entry, reason):
    table = 'geometry_jobs' if entry['kind'] == 'geometry' else 'image_jobs'
    db.execute(text(f"UPDATE {table} SET reason=:reason WHERE id=:id AND status='queued'"), {'id': entry['id'], 'reason': reason})
    if entry['kind'] == 'image':
        db.execute(text("UPDATE conversation_images SET reason=:reason WHERE (id=:id OR batch_run_id=:id) AND status='queued'"), {'id': entry['id'], 'reason': reason})


def authorized(db, principal, job, kind):
    if not session_current(db, principal, job['session_hash']):
        return False
    if kind == 'geometry':
        return 'capability.geometry.generate' in principal.permissions
    if 'capability.image.generate' not in principal.permissions or not conversation_media.active(db, job['id']):
        return False
    if job['channel_id']:
        return 'channel.use' in principal.permissions
    linked = db.execute(text('SELECT id FROM chat_runs WHERE id=:id'), {'id': job['batch_run_id'] or job['id']}).first()
    return not linked or 'conversation.own' in principal.permissions


def maintain(engine, settings):
    """Settle cancelled/expired waiting jobs even behind a busy or paused GPU.

    A lost claimed execution is terminal and remains fenced; it is never replayed.
    Queue metadata is farm scoped, but all payload and conversation writes use its owner.
    """
    followups = []
    with scoped_session(engine, workers.SYSTEM, settings.farm_id) as db:
        ids = db.execute(text("SELECT id,owner_id FROM capability_queue WHERE state IN ('queued','starting','dispatched')")).mappings().all()
    for item in ids:
        with scoped_session(engine, item['owner_id'], settings.farm_id) as db:
            entry = db.execute(text('SELECT * FROM capability_queue WHERE id=:id FOR UPDATE SKIP LOCKED'), {'id': item['id']}).mappings().one_or_none()
            if not entry or entry['state'] == 'finished':
                continue
            table = 'geometry_jobs' if entry['kind'] == 'geometry' else 'image_jobs'
            job = db.execute(text(f'SELECT * FROM {table} WHERE id=:id FOR UPDATE'), {'id': entry['id']}).mappings().one()
            principal = Principal(item['owner_id'], settings.farm_id, permissions_for(db, item['owner_id'], settings.farm_id), job['authorization_version'])
            if entry['state'] == 'queued':
                if job['status'] != 'queued' or job['cancel_requested'] or not authorized(db, principal, job, entry['kind']):
                    finish_waiting(db, entry['id'], 'cancelled', 'The queued request was stopped or its sending session or access ended.')
                elif entry['expires_at'] <= datetime.now(UTC):
                    finish_waiting(db, entry['id'], 'cancelled', 'This request expired after waiting 30 minutes. Submit it again when ready.')
            else:
                pool = db.execute(text('SELECT active_run_id,lease_until FROM provider_pools WHERE id=:id'), {'id': entry['pool_id']}).mappings().one()
                if pool['active_run_id'] != entry['id'] or pool['lease_until'] < datetime.now(UTC):
                    batch_active = entry['kind'] == 'image' and job['batch_run_id'] and db.execute(text("SELECT id FROM image_plans WHERE id=:id AND status='rendering'"), {'id': job['batch_run_id']}).first()
                    if job['status'] in {'queued', 'running'} or batch_active:
                        reason = 'Generation was interrupted. Check the worker before retrying; this request will not be replayed.'
                        db.execute(text(f"UPDATE {table} SET status='interrupted',reason=:reason,finished_at=now() WHERE id=:id AND status IN ('queued','running')"), {'id': entry['id'], 'reason': reason})
                        if entry['kind'] == 'image':
                            settle_conversation(db, entry['id'], 'interrupted', reason)
                        release_pool(db, entry['pool_id'], entry['id'], uncertain=True)
                    db.execute(text("UPDATE capability_queue SET state='finished' WHERE id=:id"), {'id': entry['id']})
            if entry['kind'] == 'image' and db.execute(text('SELECT state FROM capability_queue WHERE id=:id'), {'id': entry['id']}).scalar_one() == 'finished':
                chat_id = db.execute(text('SELECT conversation_id FROM chat_runs WHERE id=:id'), {'id': entry['id']}).scalar_one_or_none()
                if chat_id:
                    followups.append((principal, chat_id))
    return followups


def claim(engine, settings, pool_id):
    with scoped_session(engine, workers.SYSTEM, settings.farm_id) as db:
        pool = db.execute(text('SELECT * FROM provider_pools WHERE id=:id FOR UPDATE SKIP LOCKED'), {'id': pool_id}).mappings().one_or_none()
        if not pool:
            return
        # Queue rows carry no content. Select fairly under a single pool lock,
        # then adopt the stored owner scope before reading their private payload.
        entry = db.execute(text("SELECT * FROM capability_queue WHERE pool_id=:pool AND state='queued' ORDER BY (owner_id IS NOT DISTINCT FROM :last),created_at,id LIMIT 1 FOR UPDATE"), {'pool': pool_id, 'last': pool['last_queue_owner']}).mappings().one_or_none()
        if not entry:
            return
        db.execute(text("SELECT set_config('hearth.principal_id',:owner,true)"), {'owner': str(entry['owner_id'])})
        table = 'geometry_jobs' if entry['kind'] == 'geometry' else 'image_jobs'
        job = db.execute(text(f'SELECT * FROM {table} WHERE id=:id FOR UPDATE'), {'id': entry['id']}).mappings().one()
        principal = Principal(entry['owner_id'], settings.farm_id, permissions_for(db, entry['owner_id'], settings.farm_id), job['authorization_version'])
        target = target_record(db, entry['target_id'])
        if job['status'] != 'queued' or job['cancel_requested']:
            finish_waiting(db, entry['id'], 'cancelled', 'Removed from the queue.')
            return
        if entry['expires_at'] <= datetime.now(UTC) or not authorized(db, principal, job, entry['kind']):
            finish_waiting(db, entry['id'], 'cancelled', 'The queued request expired or its sending session ended. Submit it again when ready.')
            return
        if target['revision'] != entry['target_revision'] or target['state'] != 'ready' or target['resource_pool_id'] != pool_id:
            finish_waiting(db, entry['id'], 'failed', 'The provider changed while this job was waiting. Check its settings and try again.')
            return
        if pool['active_run_id']:
            waiting_reason(db, entry, 'Waiting for the current GPU job to release the device. Your request is saved.')
            return
        worker = workers.for_pool(db, pool_id)
        if worker:
            service = workers.service_for(worker, target['connection_id'])
            if worker['revoked'] or not service:
                finish_waiting(db, entry['id'], 'failed', 'The worker no longer authorizes this service.')
                return
            if worker['state'] == 'failed':
                finish_waiting(db, entry['id'], 'failed', 'The GPU worker needs attention. Check Workers in Administration before retrying.')
                return
            if worker['paused'] or not workers.fresh(worker):
                waiting_reason(db, entry, 'The GPU queue is paused. Your request is saved.' if worker['paused'] else 'Waiting for the GPU worker to reconnect. Your request is saved.')
                return
            if worker['policy'] == 'resident' and worker['desired_service'] != service:
                finish_waiting(db, entry['id'], 'failed', 'Another service is selected to stay resident on this GPU. Select this service in Workers, or enable shared GPU mode, before retrying.')
                return
            if worker['desired_service'] != service:
                db.execute(text('UPDATE managed_workers SET desired_service=:service,revision=revision+1 WHERE id=:id'), {'service': service, 'id': worker['id']})
        waiting_reason(db, entry, 'Preparing the selected GPU service…')
        claim_pool(db, target, entry['id'], principal.id, preparing=True)
        db.execute(text("UPDATE capability_queue SET state='starting',claimed_at=now() WHERE id=:id"), {'id': entry['id']})
        db.execute(text('UPDATE provider_pools SET last_queue_owner=:owner WHERE id=:pool'), {'pool': pool_id, 'owner': principal.id})
        return principal, target, (GeometryGeneration if entry['kind'] == 'geometry' else ImageGeneration).model_validate(job['request'])


def execute_queued(engine, settings, principal, target, data):
    if isinstance(data, GeometryGeneration):
        from hearth.geometry import execute
        table = "geometry_jobs"
    else:
        from hearth.images import execute
        table = "image_jobs"
    from hearth.provider_health import check_connection, record_failure
    dispatched = False
    try:
        deadline = time.monotonic() + 180
        while True:
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                db.execute(text('SELECT id FROM capability_queue WHERE id=:id FOR UPDATE'), {'id': data.id})
                job = db.execute(text(f'SELECT * FROM {table} WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
                current = target_record(db, target['id'])
                if job['cancel_requested'] or not authorized(db, principal, job, 'geometry' if table == 'geometry_jobs' else 'image'):
                    finish_waiting(db, data.id, 'cancelled', 'Stopped before generation started.')
                    return
                if current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready':
                    finish_waiting(db, data.id, 'failed', 'The provider changed before generation started.')
                    return
                worker = workers.for_pool(db, target['resource_pool_id'])
                ready = not worker or workers.ready(worker, target['connection_id'])
                if worker and (worker['revoked'] or worker['state'] == 'failed'):
                    raise RuntimeError('worker unavailable')
                if ready:
                    break
                db.execute(text(f"UPDATE {table} SET reason='Preparing the selected service…' WHERE id=:id"), {'id': data.id})
            if time.monotonic() >= deadline:
                raise TimeoutError()
            time.sleep(.5)
        if worker:
            # Process/health readiness is separate from model qualification.
            # Recheck the qualified provider manifest after every activation.
            check_connection(target, settings)
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            db.execute(text('SELECT id FROM capability_queue WHERE id=:id FOR UPDATE'), {'id': data.id})
            job = db.execute(text(f'SELECT * FROM {table} WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
            if job['cancel_requested'] or not authorized(db, principal, job, 'geometry' if table == 'geometry_jobs' else 'image'):
                finish_waiting(db, data.id, 'cancelled', 'Stopped before generation started.')
                return
            batch = table == 'image_jobs' and job['batch_run_id'] is not None
            if batch:
                plan = dict(db.execute(text('SELECT * FROM image_plans WHERE id=:id'), {'id': data.id}).mappings().one())
                jobs = [ImageGeneration.model_validate(row) for row in db.execute(text('SELECT j.request FROM image_jobs j JOIN conversation_images c ON c.id=j.id WHERE j.batch_run_id=:id ORDER BY c.batch_index'), {'id': data.id}).scalars()]
            else:
                db.execute(text(f"UPDATE {table} SET status='running',reason=NULL WHERE id=:id AND status='queued'"), {'id': data.id})
                if table == 'image_jobs':
                    db.execute(text("UPDATE conversation_images SET status='running',reason=NULL WHERE id=:id AND status='queued'"), {'id': data.id})
            db.execute(text("UPDATE capability_queue SET state='dispatched' WHERE id=:id"), {'id': data.id})
        dispatched = True
        if batch:
            from hearth.image_batches import execute_batch
            execute_batch(engine, settings, principal, plan, target, jobs)
        else:
            execute(engine, settings, principal, target, data)
    except Exception as problem:
        # Nothing was sent to inference before 'dispatched'. After that fence,
        # an unexpected failure must never release the device optimistically.
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            db.execute(text('SELECT id FROM capability_queue WHERE id=:id FOR UPDATE'), {'id': data.id})
            if not dispatched:
                record_failure(db, target, problem if isinstance(problem, ProviderError) else None)
                finish_waiting(db, data.id, 'failed', str(problem) if isinstance(problem, ProviderError) else 'The worker could not prepare its service. Check Workers in Administration.')
            else:
                db.execute(text(f"UPDATE {table} SET status='interrupted',reason='Generation was interrupted. Check the worker before retrying.',finished_at=now() WHERE id=:id AND status='running'"), {'id': data.id})
                if table == 'image_jobs':
                    settle_conversation(db, data.id, 'interrupted', 'Generation was interrupted. Check the worker before retrying.')
                release_pool(db, target['resource_pool_id'], data.id, uncertain=True)
    finally:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            if not dispatched:
                release_pool(db, target['resource_pool_id'], data.id)
            db.execute(text("UPDATE capability_queue SET state='finished' WHERE id=:id"), {'id': data.id})
        if table == 'image_jobs':
            from hearth.chat import dispatch_pending
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                chat_id = db.execute(text('SELECT conversation_id FROM chat_runs WHERE id=:id'), {'id': data.id}).scalar_one_or_none()
            if chat_id:
                dispatch_pending(engine, settings, principal, chat_id)


class ImageQueue:
    def __init__(self, engine, settings, executor):
        self.engine, self.settings, self.executor = engine, settings, executor
        self.stop = Event()
        self.thread = Thread(target=self.run, name='hearth-image-queue', daemon=True)
        self.thread.start()

    def tick(self):
        from hearth.chat import dispatch_pending
        for principal, chat_id in maintain(self.engine, self.settings):
            self.executor.submit(dispatch_pending, self.engine, self.settings, principal, chat_id)
        with scoped_session(self.engine, workers.SYSTEM, self.settings.farm_id) as db:
            pools = db.execute(text("SELECT DISTINCT pool_id FROM capability_queue WHERE state='queued'")).scalars().all()

        for pool in pools:
            if self.stop.is_set():
                break
            admitted = claim(self.engine, self.settings, pool)
            if admitted:
                self.executor.submit(execute_queued, self.engine, self.settings, *admitted)

    def run(self):
        while not self.stop.wait(.3):
            try:
                self.tick()
            except Exception:
                logger.warning('Image queue check interrupted; durable reservations retained.')

    def close(self):
        self.stop.set()
        self.thread.join()
