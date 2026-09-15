import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from hearth import providers
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def register(admin, headers, model='fixture', **updates):
    body = {'name': 'LAN server', 'base_url': 'http://10.20.30.40:1234', 'model_id': model, 'local_only': True} | updates
    response = admin.post('/api/v1/providers', headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_admin_approval_is_scoped_audited_revocable_and_fences_siblings(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as member:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        first = register(admin, ah)
        sibling = register(admin, ah, 'other')
        other = register(admin, ah, base_url='http://10.20.30.41:1234', name='Another server')
        path = f'/api/v1/providers/{first}/http-consent'
        payload = {'revision': 1, 'allow_insecure_http': True}
        assert admin.post(path, json=payload).status_code == 403
        signin(member)
        assert member.post(path, json=payload, headers=csrf(member, settings.user_origin)).status_code == 403
        assert admin.post(f'/api/v1/providers/{uuid4()}/http-consent', headers=ah, json=payload).status_code == 404
        assert admin.post(path, headers=ah, json=payload | {'allow_insecure_http': 'true'}).status_code == 422
        owner = admin.get('/api/v1/session').json()['id']
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text("UPDATE inference_targets SET state='disabled' WHERE id=:id"), {'id': sibling})
            db.execute(text("UPDATE provider_pools SET active_run_id=:run,execution_state='unknown' WHERE id=(SELECT resource_pool_id FROM inference_targets WHERE id=:id)"), {'run': uuid4(), 'id': sibling})
        assert admin.post(path, headers=ah, json=payload).status_code == 409
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=NULL,execution_state='idle'"))
        accepted = admin.post(path, headers=ah, json=payload)
        assert accepted.status_code == 200 and accepted.json()['revision'] == 2
        assert admin.post(path, headers=ah, json=payload).status_code == 409
        rows = {r['id']: r for r in admin.get('/api/v1/providers').json()['items']}
        assert rows[first]['allow_insecure_http'] and rows[sibling]['allow_insecure_http']
        assert rows[first]['revision'] == rows[sibling]['revision'] == 2
        assert rows[sibling]['state'] == 'disabled'
        assert rows[other]['revision'] == 1 and not rows[other]['allow_insecure_http']
        with factory('admin') as fresh:
            signin(fresh)
            assert next(r for r in fresh.get('/api/v1/providers').json()['items'] if r['id'] == first)['allow_insecure_http']
        with scoped_session(app, owner, settings.farm_id) as db:
            row = providers.target_record(db, first)
            assert providers.transport_settings(row, settings).provider_http_approved_url == 'http://10.20.30.40:1234/v1'
        # Audit storage is write-only to the application role. Inspect the
        # fixture's audit side effect with the existing migration test role.
        with migration.connect() as db:
            audit = db.execute(text("SELECT actor_id,safe_metadata FROM audit_events WHERE action='provider.http_risk_accepted' AND farm_id=:farm"), {'farm': settings.farm_id}).mappings().one()
            assert str(audit['actor_id']) == owner and audit['safe_metadata']['connection_id'] == str(row['connection_id'])
        assert admin.post(path, headers=ah, json={'revision': 2, 'allow_insecure_http': False}).status_code == 200
        with scoped_session(app, owner, settings.farm_id) as db:
            assert not providers.transport_settings(providers.target_record(db, first), settings).provider_http_approved_url
        with migration.connect() as db:
            assert db.execute(text("SELECT count(*) FROM audit_events WHERE action='provider.http_risk_revoked' AND farm_id=:farm"), {'farm': settings.farm_id}).scalar_one() == 1


def test_registration_and_edit_approval_do_not_leak_to_new_addresses(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        first = register(admin, headers, allow_insecure_http=True)
        sibling = register(admin, headers, 'other', allow_insecure_http=True)
        body = {'revision': 1, 'name': 'Moved model', 'base_url': 'http://10.20.30.42:1234', 'model_id': 'fixture', 'local_only': True}
        assert admin.put(f'/api/v1/providers/{first}', headers=headers, json=body).status_code == 200
        rows = {r['id']: r for r in admin.get('/api/v1/providers').json()['items']}
        assert not rows[first]['allow_insecure_http'] and rows[sibling]['allow_insecure_http']
        assert rows[sibling]['revision'] == 1
        assert admin.put(f'/api/v1/providers/{first}', headers=headers, json=body | {'revision': 2, 'allow_insecure_http': True}).status_code == 200
        https = register(admin, headers, base_url='https://10.20.30.43:1240')
        assert admin.post(f'/api/v1/providers/{https}/http-consent', headers=headers, json={'revision': 1, 'allow_insecure_http': True}).status_code == 400


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_HTTP_URL'), reason='Explicitly approved real LAN server required.')
def test_live_lan_model_failed_probe_admin_override_and_routed_reply(bff):
    factory, settings, _, migration, _ = bff
    url = os.environ['HEARTH_LIVE_HTTP_URL'].rstrip('/')
    model = os.environ['HEARTH_LIVE_HTTP_MODEL']

    def loaded():
        data = httpx.get(url+'/api/v1/models', timeout=10, trust_env=False).raise_for_status().json()
        return sorted(i['id'] for m in data['models'] for i in m['loaded_instances'])

    before = loaded()
    assert model in before
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = register(admin, ah, model=model, base_url=url, residency_policy='lmstudio_loaded')
        path = f'/api/v1/providers/{target}'
        denied = admin.post(path+'/probe', headers=ah, json={'revision': 1})
        assert denied.json()['state'] == 'failed' and 'accept the risks' in denied.json()['reason']
        accepted = admin.post(path+'/http-consent', headers=ah, json={'revision': 2, 'allow_insecure_http': True})
        assert accepted.status_code == 200, accepted.text
        verified = admin.post(path+'/probe', headers=ah, json={'revision': accepted.json()['revision']})
        assert verified.json()['state'] == 'ready', verified.text
        signin(user)
        uh = csrf(user, settings.user_origin)
        chat = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        started = time.monotonic()
        sent = user.post(chat+'/turns', headers=uh, json={'revision': 1, 'request_id': str(uuid4()), 'content': 'Reply with one short greeting for the hearth network connection test.'})
        assert sent.status_code == 202, sent.text
        result = wait_finished(user, chat, timeout=120)
        assert result['runs'][-1]['status'] == 'completed', result['runs']
        assert result['runs'][-1]['route_receipt']['allow_insecure_http'] is True
        after = loaded()
        assert before == after
        out = Path('evidence/http-consent/2026-09-13/live-lan.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'scope': 'Real remote LM Studio over administrator-approved LAN HTTP; real PostgreSQL and BFF APIs with explicit OIDC fixtures in a disposable farm. The user\'s saved connection was not changed.',
            'address': url, 'model': model, 'blocked_without_approval': True, 'admin_approval_then_probe_passed': True,
            'routed_reply_completed': True, 'reply_completion_seconds': round(time.monotonic()-started,3),
            'loaded_instances_before': before, 'loaded_instances_after': after, 'paid_inference': False}, indent=2), encoding='utf-8')
