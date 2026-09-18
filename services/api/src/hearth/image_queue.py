"""Durable gallery admission, fair between owners and independent across GPUs.

Only undispatched jobs are resumed after a restart. An expired execution lease
remains fenced in provider_pools until the backend's release is confirmed.
"""
import logging
import time
from datetime import UTC, datetime
from threading import Event, Thread

from sqlalchemy import text

from hearth import workers
from hearth.chat import session_current
from hearth.contracts import ImageGeneration
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.policy import Principal
from hearth.providers import claim_pool, release_pool, target_record

logger = logging.getLogger('hearth')


def enqueue(db, principal, target, job_id):
    # The caller holds the resource pool and owner's workspace locks.
    if db.execute(text("SELECT count(*) FROM image_queue WHERE owner_id=:owner AND state IN ('queued','starting','dispatched')"), {'owner': principal.id}).scalar_one() >= 8:
        from fastapi import HTTPException
        raise HTTPException(429, 'You already have eight images waiting or running. Let one finish or cancel it first.')
    if db.execute(text("SELECT count(*) FROM image_queue WHERE pool_id=:pool AND state IN ('queued','starting','dispatched')"), {'pool': target['resource_pool_id']}).scalar_one() >= 64:
        from fastapi import HTTPException
        raise HTTPException(429, 'This GPU queue is full. Please try again after some work finishes.')
    worker = workers.for_pool(db, target['resource_pool_id'])
    if worker and (worker['revoked'] or not workers.service_for(worker, target['connection_id'])):
        from fastapi import HTTPException
        raise HTTPException(409, 'This provider is not an approved service for its worker.')
    db.execute(text('INSERT INTO image_queue(id,farm_id,owner_id,pool_id,target_id,target_revision) VALUES(:id,:farm,:owner,:pool,:target,:revision)'),
               {'id': job_id, 'farm': principal.farm_id, 'owner': principal.id, 'pool': target['resource_pool_id'], 'target': target['id'], 'revision': target['revision']})


def finish_waiting(db, job_id, state, reason):
    db.execute(text("UPDATE image_jobs SET status=:state,reason=:reason,finished_at=now() WHERE id=:id AND status='queued'"), {'id': job_id, 'state': state, 'reason': reason})
    db.execute(text("UPDATE image_queue SET state='finished' WHERE id=:id"), {'id': job_id})


def claim(engine, settings, pool_id):
    with scoped_session(engine, workers.SYSTEM, settings.farm_id) as db:
        pool = db.execute(text('SELECT * FROM provider_pools WHERE id=:id FOR UPDATE SKIP LOCKED'), {'id': pool_id}).mappings().one_or_none()
        if not pool:
            return
        # Queue rows carry no content. Select fairly under a single pool lock,
        # then adopt the stored owner scope before reading their private payload.
        entry = db.execute(text("SELECT * FROM image_queue WHERE pool_id=:pool AND state='queued' ORDER BY (owner_id IS NOT DISTINCT FROM :last),created_at,id LIMIT 1 FOR UPDATE"), {'pool': pool_id, 'last': pool['last_queue_owner']}).mappings().one_or_none()
        if not entry:
            return
        db.execute(text("SELECT set_config('hearth.principal_id',:owner,true)"), {'owner': str(entry['owner_id'])})
        job = db.execute(text('SELECT * FROM image_jobs WHERE id=:id FOR UPDATE'), {'id': entry['id']}).mappings().one()
        principal = Principal(entry['owner_id'], settings.farm_id, frozenset({'conversation.own'}), job['authorization_version'])
        target = target_record(db, entry['target_id'])
        if job['status'] != 'queued' or job['cancel_requested']:
            finish_waiting(db, entry['id'], 'cancelled', 'Removed from the queue.')
            return
        if entry['expires_at'] <= datetime.now(UTC) or not session_current(db, principal, job['session_hash']):
            finish_waiting(db, entry['id'], 'cancelled', 'The queued request expired or its sending session ended. Submit it again when ready.')
            return
        if target['revision'] != entry['target_revision'] or target['state'] != 'ready' or target['resource_pool_id'] != pool_id:
            finish_waiting(db, entry['id'], 'failed', 'The provider changed while this image was waiting. Check its settings and try again.')
            return
        if pool['active_run_id']:
            return
        worker = workers.for_pool(db, pool_id)
        if worker:
            service = workers.service_for(worker, target['connection_id'])
            if worker['revoked'] or not service:
                finish_waiting(db, entry['id'], 'failed', 'The worker no longer authorizes this service.')
                return
            if worker['paused'] or not workers.fresh(worker):
                return
            if worker['policy'] == 'resident' and worker['desired_service'] != service:
                finish_waiting(db, entry['id'], 'failed', 'Another service is selected to stay resident on this GPU. Select this image service in Workers, or enable shared GPU mode, before retrying.')
                return
            if worker['desired_service'] != service:
                db.execute(text('UPDATE managed_workers SET desired_service=:service,revision=revision+1 WHERE id=:id'), {'service': service, 'id': worker['id']})
        claim_pool(db, target, entry['id'], principal.id, preparing=True)
        db.execute(text("UPDATE image_queue SET state='starting',claimed_at=now() WHERE id=:id"), {'id': entry['id']})
        db.execute(text('UPDATE provider_pools SET last_queue_owner=:owner WHERE id=:pool'), {'pool': pool_id, 'owner': principal.id})
        return principal, target, ImageGeneration.model_validate(job['request'])


def execute_queued(engine, settings, principal, target, data):
    from hearth.images import execute
    from hearth.provider_health import check_connection, record_failure
    dispatched = False
    try:
        deadline = time.monotonic() + 180
        while True:
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                db.execute(text('SELECT id FROM image_queue WHERE id=:id FOR UPDATE'), {'id': data.id})
                job = db.execute(text('SELECT * FROM image_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
                current = target_record(db, target['id'])
                if job['cancel_requested'] or not session_current(db, principal, job['session_hash']):
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
                db.execute(text("UPDATE image_jobs SET reason='Preparing the image service…' WHERE id=:id"), {'id': data.id})
            if time.monotonic() >= deadline:
                raise TimeoutError()
            time.sleep(.5)
        if worker:
            # Process/health readiness is separate from model qualification.
            # Recheck the qualified provider manifest after every activation.
            check_connection(target, settings)
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            db.execute(text('SELECT id FROM image_queue WHERE id=:id FOR UPDATE'), {'id': data.id})
            job = db.execute(text('SELECT * FROM image_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
            if job['cancel_requested'] or not session_current(db, principal, job['session_hash']):
                finish_waiting(db, data.id, 'cancelled', 'Stopped before generation started.')
                return
            db.execute(text("UPDATE image_jobs SET status='running',reason=NULL WHERE id=:id AND status='queued'"), {'id': data.id})
            db.execute(text("UPDATE image_queue SET state='dispatched' WHERE id=:id"), {'id': data.id})
        dispatched = True
        execute(engine, settings, principal, target, data)
    except Exception as problem:
        # Nothing was sent to inference before 'dispatched'. After that fence,
        # an unexpected failure must never release the device optimistically.
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            db.execute(text('SELECT id FROM image_queue WHERE id=:id FOR UPDATE'), {'id': data.id})
            if not dispatched:
                record_failure(db, target, problem if isinstance(problem, ProviderError) else None)
                finish_waiting(db, data.id, 'failed', str(problem) if isinstance(problem, ProviderError) else 'The worker could not prepare its service. Check Workers in Administration.')
            else:
                db.execute(text("UPDATE image_jobs SET status='interrupted',reason='Generation was interrupted. Check the worker before retrying.',finished_at=now() WHERE id=:id AND status='running'"), {'id': data.id})
                release_pool(db, target['resource_pool_id'], data.id, uncertain=True)
    finally:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            if not dispatched:
                release_pool(db, target['resource_pool_id'], data.id)
            db.execute(text("UPDATE image_queue SET state='finished' WHERE id=:id"), {'id': data.id})


class ImageQueue:
    def __init__(self, engine, settings, executor):
        self.engine, self.settings, self.executor = engine, settings, executor
        self.stop = Event()
        self.thread = Thread(target=self.run, name='hearth-image-queue', daemon=True)
        self.thread.start()

    def tick(self):
        with scoped_session(self.engine, workers.SYSTEM, self.settings.farm_id) as db:
            pools = db.execute(text("SELECT DISTINCT pool_id FROM image_queue WHERE state='queued'")).scalars().all()
            # A head crash after reservation is not permission to replay. Keep
            # its pool fenced, and release only the *queue quota* after expiry.
            db.execute(text("UPDATE image_queue q SET state='finished' FROM provider_pools p WHERE p.id=q.pool_id AND q.state IN ('starting','dispatched') AND (p.active_run_id IS DISTINCT FROM q.id OR p.lease_until<now())"))
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
