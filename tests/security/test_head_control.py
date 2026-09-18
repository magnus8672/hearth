import json
import socket
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import head, head_control


def test_change_preserves_farm_secrets_and_validates_both_current_and_new_origins(tmp_path):
    before = head.configure(tmp_path, base_url='https://10.20.30.10')
    after = head_control.changed(before, 'https://hearth.home.arpa/')
    assert all(after[key] == before[key] for key in (*head.SECRET_NAMES, 'HEARTH_FARM_ID', 'HEARTH_COMPOSE_PROJECT'))
    assert after['HEARTH_ADMIN_ORIGIN'] == 'https://hearth.home.arpa:8443'
    assert after['HEARTH_IDENTITY_ORIGIN'] == 'https://hearth.home.arpa:8445'
    head.private_write(tmp_path/'config.json', json.dumps(after))
    _, environment = head.compose_context(tmp_path)
    assert environment['HEARTH_DEFAULT_SNI'] == '10.20.30.10'
    aliases = (tmp_path/'public-setup/Caddyfile.aliases').read_text()
    assert 'https://10.20.30.10' in aliases and 'redir https://hearth.home.arpa/ 303' in aliases
    assert '{uri}' not in aliases and 'respond @unsafe 405' in aliases
    for bad in ['http://hearth.home.arpa', 'https://hearth.home.arpa/v1', 'https://user:secret@head', 'https://x\n{evil}', 'https://host:8443']:
        with pytest.raises(ValueError):
            head_control.changed(before, bad)


def test_dns_must_only_resolve_to_this_host(monkeypatch):
    monkeypatch.setattr(head_control.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=json.dumps([{'addr_info': [{'local': '10.20.30.10'}]}])))
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a: [(None, None, None, None, ('10.20.30.10', 0))])
    assert head_control.check_dns('head.home') == ['10.20.30.10']
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a: [(None, None, None, None, ('10.20.30.40', 0))])
    with pytest.raises(ValueError, match='point to this head'):
        head_control.check_dns('head.home')


def job_for(before):
    after = head_control.changed(before, 'https://hearth.home.arpa')
    return {'operation_id': str(uuid4()), 'actor_id': str(uuid4()), 'state': 'queued', 'message': 'queued',
            'target': head_control.public(after), 'before': before, 'after': after}


def test_failure_restores_config_and_does_not_publish_secrets(tmp_path, monkeypatch):
    before = head.configure(tmp_path, base_url='https://10.20.30.10')
    controller = head_control.Controller(tmp_path)
    job = job_for(before)
    calls = []
    monkeypatch.setattr(head_control.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(head_control, 'check_dns', lambda *_: ['10.20.30.10'])
    monkeypatch.setattr(head_control, 'console', lambda *a: None)
    monkeypatch.setattr(head_control, 'verify', lambda *_: None)
    def services(*args):
        calls.append(head.load(tmp_path)['HEARTH_USER_ORIGIN'])
        if len(calls) == 1:
            raise RuntimeError('PRIVATE CREDENTIAL CANARY')
    monkeypatch.setattr(head_control, 'refresh_services', services)
    controller.run(job)
    assert calls == ['https://hearth.home.arpa', 'https://10.20.30.10']
    assert head.load(tmp_path) == before
    status = controller.status()
    assert status['operation']['state'] == 'rolled_back'
    assert 'PRIVATE' not in json.dumps(status)
    assert all(before[key] not in json.dumps(status) for key in head.SECRET_NAMES)


def test_restart_recovers_incomplete_change(tmp_path, monkeypatch):
    before = head.configure(tmp_path, base_url='https://10.20.30.10')
    controller = head_control.Controller(tmp_path)
    job = job_for(before) | {'state': 'applying'}
    controller.write_job(job)
    head.private_write(tmp_path/'config.json', json.dumps(job['after']))
    monkeypatch.setattr(head_control, 'refresh_services', lambda *a: None)
    monkeypatch.setattr(head_control, 'verify', lambda *a: None)
    controller.recover()
    assert head.load(tmp_path) == before
    assert controller.status()['operation']['state'] == 'rolled_back'


def test_pending_operation_blocks_other_requests_and_duplicate_is_idempotent(tmp_path):
    before = head.configure(tmp_path, base_url='https://10.20.30.10')
    controller = head_control.Controller(tmp_path)
    job = job_for(before)
    controller.write_job(job)
    request = {'actor_id': job['actor_id'], 'operation_id': job['operation_id'],
               'base_url': job['target']['base_url'], 'expected_revision': head_control.revision(before)}
    assert controller.submit(request)['operation']['state'] == 'queued'
    with pytest.raises(ValueError, match='previous address'):
        controller.submit(request | {'operation_id': str(uuid4())})
    with pytest.raises(ValueError, match='different request'):
        controller.submit(request | {'base_url': 'https://other.home'})
