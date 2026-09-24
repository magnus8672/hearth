from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from hearth import farm_map
from hearth.config import Settings


def target(**changes):
    return dict(id='target', connection_id='connection', resource_pool_id='pool', pool_name='GPU',
                execution_state='idle', queued=0, name='Server', base_url='http://10.1.1.2:1234/v1',
                model_id='model', state='ready', protocol='openai.chat.v1', features=['chat', 'streaming'],
                probed_at=None, credential='SECRET', tls_ca_pem='', allow_insecure_http=True, **changes)


def worker(**changes):
    result = dict(name='Worker', services={'image': {'connection_id': 'connection'}}, desired_service='image',
                  ready_service='image', seen_at=datetime.now(UTC), revoked=False, paused=False, state='ready',
                  revision=4, observed_revision=4, policy='shared')
    return result | changes


@pytest.mark.parametrize(('changes', 'expected'), [({}, 'service_ready'), ({'paused': True}, 'paused'),
    ({'revoked': True}, 'offline'), ({'seen_at': datetime.now(UTC)-timedelta(seconds=30)}, 'offline'),
    ({'observed_revision': 3}, 'unknown'), ({'state': 'starting'}, 'starting'),
    ({'state': 'failed'}, 'failed'), ({'desired_service': 'other', 'ready_service': 'other'}, 'on_demand')])
def test_managed_residency_requires_fresh_matching_observation(changes, expected):
    assert farm_map.residency(target(), worker(**changes), None)[0] == expected


def test_topology_preserves_many_to_many_bindings_and_unknown_residency():
    rows = [target(), target() | {'id': 'second', 'base_url': 'https://10.1.1.2:9999/v1', 'model_id': 'second'}]
    bindings = [dict(capability_id=cap, target_id=t, priority=priority) for cap, t, priority in
                [('chat.general', 'target', 0), ('code.implement', 'target', 1), ('chat.general', 'second', 1)]]
    result = farm_map.topology(Settings(mode='test'), rows, bindings, [], {})
    assert len(result['machines']) == 2
    nodes = result['machines'][1]['nodes']
    assert len(nodes) == 3 and len({n['id'] for n in nodes}) == 3
    assert all(n['residency'] == 'unknown' and n['verified'] for n in nodes)
    assert 'SECRET' not in str(result) and 'credential' not in str(result)
    assert len(result['machines'][0]['nodes']) == 2
    assert 'vision.describe' in {n['id'] for n in result['unassigned']}
    observed = {'connection': ({'model'}, datetime.now(UTC))}
    result = farm_map.topology(Settings(mode='test'), rows, bindings, [], observed)
    assert {n['residency'] for n in result['machines'][1]['nodes']} == {'loaded', 'unloaded'}


def test_inventory_is_bounded_read_only_and_matches_instance_ids(monkeypatch):
    calls = []

    def transport(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={'models': [{'type': 'llm', 'key': 'downloaded-but-not-loaded',
                                                    'loaded_instances': [{'id': 'resident-instance'}]}]})

    @contextmanager
    def client(*args):
        with httpx.Client(base_url='http://localhost/v1/', transport=httpx.MockTransport(transport)) as instance:
            yield instance, {}

    monkeypatch.setattr(farm_map, 'client_for', client)
    monkeypatch.setattr(farm_map, 'credential_for', lambda *args: '')
    monkeypatch.setattr(farm_map, 'transport_settings', lambda row, settings: settings)
    assert farm_map.loaded_instances(target(), None) == {'resident-instance'}
    assert calls == [('GET', '/api/v1/models')]


def test_cached_inventory_invalidates_on_connection_change(monkeypatch):
    calls = []
    monkeypatch.setattr(farm_map, 'loaded_instances', lambda *args: calls.append(1) or None)
    cache = farm_map.Observations()
    settings = SimpleNamespace(farm_id='farm')
    assert cache.get(target(), settings)[0] is None
    cache.get(target(), settings)
    assert len(calls) == 1
    cache.get(target() | {'credential': 'changed'}, settings)
    assert len(calls) == 2


def test_shared_pool_does_not_merge_distinct_hosts():
    result = farm_map.topology(Settings(mode='test'), [target(), target() | {'id': 'other', 'base_url': 'http://10.1.1.3:1234/v1'}], [], [], {})
    assert len(result['machines']) == 3
    assert len(result['unbound_targets']) == 2
