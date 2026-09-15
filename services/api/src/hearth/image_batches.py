"""Sequential child renders sharing one fenced conversation execution."""
from sqlalchemy import text

from hearth import conversation_media, image_planning, images
from hearth.database import scoped_session
from hearth.providers import release_pool, target_record


def finish(db, plan, state, reason=None):
    unfinished = 'interrupted' if state == 'interrupted' else 'cancelled'
    values = {'id': plan['id'], 'state': unfinished, 'reason': reason or 'The remaining images were stopped.'}
    db.execute(text("UPDATE image_jobs SET status=:state,reason=:reason,finished_at=now() WHERE batch_run_id=:id AND status IN ('queued','running')"), values)
    db.execute(text("UPDATE conversation_images SET status=:state,reason=:reason WHERE batch_run_id=:id AND status IN ('queued','running')"), values)
    rows = db.execute(text("SELECT request->>'prompt' AS prompt FROM conversation_images WHERE batch_run_id=:id AND status='completed' ORDER BY batch_index"), values).scalars().all()
    caption = 'Generated images (descriptions only, without image pixels):\n' + '\n'.join(f'{i}. {prompt}' for i, prompt in enumerate(rows, 1)) if rows else ''
    image_planning.terminal(db, plan, state, reason, caption)


def execute_batch(engine, settings, principal, plan, target, jobs):
    from hearth.chat import identity_current, session_current
    state, reason, uncertain = 'completed', None, False
    try:
        for job in jobs:
            identity_ok = identity_current(engine, settings, principal, plan['session_hash'])
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                status = db.execute(text('SELECT status FROM image_plans WHERE id=:id FOR UPDATE'), {'id': plan['id']}).scalar_one()
                current = target_record(db, target['id'])
                if status != 'rendering' or current['active_run_id'] != plan['id']:
                    return  # Reconciled or superseded. Never release another job.
                child = db.execute(text('SELECT status,cancel_requested FROM image_jobs WHERE id=:id'), {'id': job.id}).mappings().one()
                if (not identity_ok or not session_current(db, principal, plan['session_hash']) or not conversation_media.active(db, plan['id'])
                        or child['cancel_requested'] or current['state'] != 'ready' or current['revision'] != target['revision']):
                    state, reason = 'cancelled', 'The batch stopped. Completed images are saved.'
                    break
                if child['status'] != 'queued':
                    state, reason, uncertain = 'interrupted', 'A batch item was already started. It will not be replayed.', True
                    break
                db.execute(text("UPDATE image_jobs SET status='running' WHERE id=:id"), {'id': job.id})
                db.execute(text("UPDATE conversation_images SET status='running' WHERE id=:id AND status='queued'"), {'id': job.id})
            outcome = images.execute(engine, settings, principal, target, job)
            if outcome is None:
                state, reason, uncertain = 'interrupted', 'An image execution changed. Check the provider before trying again.', True
                break
            state, reason, uncertain = outcome
            if state != 'completed':
                break
    except Exception:
        state, reason, uncertain = 'interrupted', 'The image batch was interrupted. Check the provider before trying again.', True
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        status = db.execute(text('SELECT status FROM image_plans WHERE id=:id FOR UPDATE'), {'id': plan['id']}).scalar_one()
        current = target_record(db, target['id'])
        if status != 'rendering' or current['active_run_id'] != plan['id']:
            return
        finish(db, plan, state, reason)
        release_pool(db, target['resource_pool_id'], plan['id'], uncertain=uncertain)
