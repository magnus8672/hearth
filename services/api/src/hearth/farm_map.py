"""Read-only topology and residency observations, separate from route qualification."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import text

from hearth import workers
from hearth.catalog import CAPABILITIES
from hearth.database import scoped_session
from hearth.inference import ProviderError, client_for, response_ok
from hearth.providers import credential_for, transport_settings
from hearth.routing import profile, readiness

router = APIRouter()


def loaded_instances(row, settings):
    """Only native LM Studio inventory proves residency; /v1/models does not."""
    started = time.monotonic()
    try:
        with client_for(row['base_url'], credential_for(row, settings), transport_settings(row, settings)) as (client, extensions):
            with client.stream('GET', client.base_url.copy_with(path='/api/v1/models'),
                               extensions=extensions, timeout=5) as response:
                response_ok(response)
                raw = bytearray()
                for block in response.iter_bytes():
                    raw.extend(block)
                    if len(raw) > 262144 or time.monotonic() - started > 5:
                        raise ValueError()
                entries = json.loads(raw)['models']
                if not isinstance(entries, list) or len(entries) > 1000:
                    raise ValueError()
                loaded = set()
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError()
                    if entry.get('type') != 'llm':
                        continue
                    instances = entry.get('loaded_instances')
                    if not isinstance(instances, list):
                        raise ValueError()
                    for instance in instances:
                        if not isinstance(instance, dict) or not isinstance(instance.get('id'), str):
                            raise ValueError()
                        loaded.add(instance['id'])
                return loaded
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ProviderError):
        # Never return provider bodies, exception text, credentials or TLS material.
        return None


class Observations:
    """Per-app, short-lived cache; concurrent viewers share each metadata GET."""
    def __init__(self):
        self.lock = Lock()
        self.entries = {}
        self.connection_locks = {}

    def get(self, row, settings):
        key = sha256(json.dumps([str(settings.farm_id), str(row['connection_id']), row['base_url'],
                                row['credential'], row['tls_ca_pem'], row['allow_insecure_http']], sort_keys=True).encode()).hexdigest()
        # Metadata checks do not hold a database transaction or GPU reservation.
        with self.lock:
            connection_lock = self.connection_locks.setdefault(key, Lock())
        with connection_lock:
            cached = self.entries.get(key)
            if cached and time.monotonic() - cached[0] < 15:
                return cached[1:]
            result = loaded_instances(row, settings)
            stamp = datetime.now(UTC)
            with self.lock:
                self.entries = {k: v for k, v in self.entries.items() if time.monotonic() - v[0] < 15}
                self.entries[key] = (time.monotonic(), result, stamp)
                self.connection_locks = {k: v for k, v in self.connection_locks.items() if k in self.entries or v.locked()}
            return result, stamp


def residency(row, worker, observed):
    if worker:
        service = workers.service_for(worker, row['connection_id'])
        stamp = worker['seen_at']
        if not workers.fresh(worker):
            return 'offline', stamp
        if worker['paused']:
            return 'paused', stamp
        if worker['state'] == 'failed':
            return 'failed', stamp
        if workers.ready(worker, row['connection_id']):
            return 'service_ready', stamp
        if worker['desired_service'] == service and worker['state'] == 'starting':
            return 'starting', stamp
        if worker['policy'] == 'shared' and worker['desired_service'] != service:
            return 'on_demand', stamp
        return 'unknown', stamp
    if observed:
        loaded, stamp = observed
        return ('unknown' if loaded is None else 'loaded' if row['model_id'] in loaded else 'unloaded'), stamp
    return 'unknown', None


def topology(settings, rows, bindings, worker_rows, observations):
    head_host = urlsplit(settings.admin_origin).hostname
    machines = {'head': {'id': 'head', 'name': 'hearth head', 'address': head_host, 'kind': 'head', 'nodes': [], 'pools': []}}
    targets = {str(row['id']): row for row in rows}
    catalog = {cap.capability_id: cap for cap in CAPABILITIES}
    connected = {binding['capability_id'] for binding in bindings}
    unbound = []
    for row in rows:
        host = urlsplit(row['base_url']).hostname
        machine_id = 'head' if host == head_host else 'host:' + host
        worker = next((w for w in worker_rows if workers.service_for(w, row['connection_id'])), None)
        machine = machines.setdefault(machine_id, {'id': machine_id, 'name': worker['name'] if worker else row['name'],
                                                   'address': host, 'kind': 'managed' if worker else 'external', 'nodes': [], 'pools': []})
        if worker and machine_id != 'head':
            machine['name'], machine['kind'] = worker['name'], 'managed'
        pool = {'id': str(row['resource_pool_id']), 'name': row['pool_name'], 'state': row['execution_state'],
                'queued': row['queued'], 'policy': worker['policy'] if worker else 'external',
                'desired_service': worker['desired_service'] if worker else None,
                'ready_service': worker['ready_service'] if worker and workers.fresh(worker) else None}
        if not any(p['id'] == pool['id'] for p in machine['pools']):
            machine['pools'].append(pool)
        state, stamp = residency(row, worker, observations.get(str(row['connection_id'])))
        common = {'target_id': str(row['id']), 'provider': row['name'], 'model': row['model_id'], 'endpoint': row['base_url'],
                  'pool': row['pool_name'], 'residency': state, 'observed_at': stamp, 'verified_at': row['probed_at'],
                  'target_state': row['state'], 'protocol': row['protocol']}
        assigned = [b for b in bindings if str(b['target_id']) == str(row['id'])]
        if not assigned:
            unbound.append(common | {'machine': machine['address']})
        for binding in assigned:
            cap = catalog[binding['capability_id']]
            machine['nodes'].append(common | {'id': cap.capability_id + ':' + str(row['id']), 'capability': cap.capability_id,
                'name': cap.display_name, 'icon': cap.icon, 'priority': binding['priority'], 'verified': readiness(cap.capability_id, row)[0]})
    for cap in CAPABILITIES:
        if profile(cap.capability_id).get('builtin'):
            machines['head']['nodes'].append({'id': cap.capability_id, 'capability': cap.capability_id, 'name': cap.display_name,
                                             'icon': cap.icon, 'residency': 'builtin', 'verified': True})
    for machine in machines.values():
        machine['nodes'].sort(key=lambda n: (n['capability'], -n.get('priority', 0), n['id']))
    return {'observed_at': datetime.now(UTC), 'machines': list(machines.values()),
            'binding_count': sum(str(b['target_id']) in targets for b in bindings),
            'unassigned': [{'id': c.capability_id, 'name': c.display_name, 'icon': c.icon} for c in CAPABILITIES
                           if c.capability_id not in connected and not profile(c.capability_id).get('builtin')],
            'unbound_targets': unbound}


@router.get('/api/v1/farm-map', tags=['farm'])
def farm_map(request: Request):
    principal = workers.administrator(request)  # admin audience + farm.inspect, not provider.configure
    settings = request.app.state.settings
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = [dict(r) for r in db.execute(text("SELECT t.*,c.name,c.base_url,c.credential,c.tls_ca_pem,c.allow_insecure_http,p.name AS pool_name,p.execution_state,(SELECT count(*) FROM capability_queue q WHERE q.pool_id=p.id AND q.state='queued') AS queued FROM inference_targets t JOIN provider_connections c ON c.id=t.connection_id JOIN provider_pools p ON p.id=t.resource_pool_id ORDER BY c.created_at,t.model_id")).mappings()]
        bindings = [dict(r) for r in db.execute(text('SELECT capability_id,target_id,priority FROM capability_bindings')).mappings()]
        worker_rows = [dict(r) for r in db.execute(text('SELECT * FROM managed_workers')).mappings()]
    eligible = {str(r['connection_id']): r for r in rows if r['residency_policy'] == 'lmstudio_loaded' and r['state'] != 'disabled'
                and not any(workers.service_for(w, r['connection_id']) for w in worker_rows)}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {key: executor.submit(request.app.state.farm_map_observations.get, row, settings) for key, row in eligible.items()}
        observations = {key: future.result() for key, future in futures.items()}
    return topology(settings, rows, bindings, worker_rows, observations)
