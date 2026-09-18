"""Persistent qualification and read-only startup checks, scoped to one farm."""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import UUID

from sqlalchemy import text

from hearth import geometry_transport, image_transport, speech_transport, transcription_transport
from hearth.database import scoped_session
from hearth.inference import ProviderError, list_models, require_loaded_model
from hearth.providers import credential_for, target_record, transport_settings

STARTUP = 'Checking the saved provider connection after startup.'
SYSTEM = UUID(int=0)
logger = logging.getLogger('hearth')


def record_failure(db, target, reason):
    """A stale request must never invalidate a newer configuration or probe."""
    if reason is None or isinstance(reason, ProviderError) and not reason.provider_fault:
        return
    db.execute(text("UPDATE inference_targets SET state='failed',verified_until=NULL,reason=:reason "
                    "WHERE id=:id AND revision=:revision AND state='ready'"),
               {'id': target['id'], 'revision': target['revision'], 'reason': str(reason)[:500]})


def check_connection(target, settings):
    """Keep proven features; never generate, load, download or swap a model."""
    transport = transport_settings(target, settings)
    key = credential_for(target, settings)
    if target['protocol'] == 'openai.chat.v1':
        if target['model_id'] not in list_models(target['base_url'], key, transport):
            raise ProviderError('The saved model is not listed on this server. Check the model server and verify again.')
        require_loaded_model(target['base_url'], key, target['model_id'], transport)
    else:
        adapter = {'hearth.geometry.v1': geometry_transport, 'hearth.image.v1': image_transport, 'hearth.speech.v1': speech_transport,
                   'hearth.transcription.v1': transcription_transport}[target['protocol']]
        info = adapter.information(target['base_url'], key, transport).model_dump(mode='json')
        # Match every previously qualified information field, including recipe,
        # model, voices/languages, cancellation and output limits. Probe metrics
        # and our observation timestamp are not provider information fields.
        expected = target['profile']
        if info.get('model') != target['model_id'] or any(expected.get(key) != value for key, value in info.items()):
            raise ProviderError('The provider model or features changed. Run its capability verification again.')


def prepare_startup(engine, settings):
    """Fence idle, qualified targets before serving the admin application."""
    with scoped_session(engine, SYSTEM, settings.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,0))'), {'farm': str(settings.farm_id)})
        pending = db.execute(text("SELECT id,revision FROM inference_targets WHERE NOT EXISTS(SELECT 1 FROM managed_workers w WHERE w.pool_id=inference_targets.resource_pool_id) AND "
                               "(state='ready' OR (state='configured' AND reason=:reason)) AND jsonb_array_length(features)>0"),
                          {'reason': STARTUP}).all()
        for target_id, revision in pending:
            target = target_record(db, target_id, lock=True, idle_only=True)
            if target and target['state'] == 'ready' and target['revision'] == revision:
                db.execute(text("UPDATE inference_targets SET state='configured',verified_until=NULL,reason=:reason WHERE id=:id"),
                           {'id': target_id, 'reason': STARTUP})
        return pending


def check_target(engine, settings, target_id, revision, *, final=True):
    with scoped_session(engine, SYSTEM, settings.farm_id) as db:
        target = target_record(db, target_id, lock=True)
        if target['revision'] != revision or not (target['state'] == 'ready' or target['state'] == 'configured' and target['reason'] == STARTUP):
            return True
        if target['active_run_id']:
            return False  # Busy/unknown capacity is never cleared by a GET.
        db.execute(text("UPDATE inference_targets SET state='configured',reason=:reason,verified_until=NULL WHERE id=:id"), {'id': target_id, 'reason': STARTUP})
    problem = None
    try:
        check_connection(target, settings)
    except ProviderError as exc:
        problem = str(exc)
    except Exception:
        problem = 'The startup connection check failed. Check the provider and verify again.'
    if problem and not final:
        return False  # Give independently booting services time to load.
    with scoped_session(engine, SYSTEM, settings.farm_id) as db:
        # Edits, HTTP revocation, Disable or a concurrent full probe win.
        db.execute(text("UPDATE inference_targets SET state=:state,reason=:reason,verified_until=NULL,"
                        "profile=profile || CAST(:observation AS jsonb) WHERE id=:id AND revision=:revision "
                        "AND state='configured' AND reason=:startup"),
                   {'id': target_id, 'revision': revision, 'state': 'failed' if problem else 'ready', 'reason': problem,
                    'startup': STARTUP, 'observation': json.dumps({'connection_checked_at': datetime.now(UTC).isoformat()})})
    return True


class StartupChecks:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.stop = Event()
        self.pending = prepare_startup(engine, settings)
        self.deadline = time.monotonic() + 120
        self.thread = Thread(target=self.run, name='hearth-provider-startup', daemon=True)
        self.thread.start()

    def run(self):
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix='hearth-provider-check') as executor:
            while self.pending and not self.stop.is_set():
                checks = {executor.submit(self.check, target, revision): (target, revision)
                          for target, revision in self.pending}
                for future in as_completed(checks):
                    try:
                        if future.result():
                            self.pending.remove(checks[future])
                    except Exception:
                        # No credentials or user content in logs. An interrupted
                        # check remains fenced and resumes after DB recovery.
                        logger.warning('Provider startup check could not finish.')
                if self.pending:
                    self.stop.wait(5)

    def check(self, target, revision):
        if self.stop.is_set():
            return True
        return check_target(self.engine, self.settings, target, revision, final=time.monotonic() >= self.deadline)

    def close(self):
        self.stop.set()
        self.thread.join()
