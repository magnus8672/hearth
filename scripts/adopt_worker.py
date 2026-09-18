"""Console-only adoption of operator-reviewed, already installed Linux services.

Run as root on the head. Input is a local reviewed inventory, never model output
or an HTTP request. Output is a private bundle to copy over authenticated SSH.
No packages are downloaded and no remote command is executed by this tool.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]


def sql(statement):
    result = subprocess.run(['docker', 'exec', '-i', 'hearth-head-postgres-1', 'psql', '-U', 'postgres', '-d', 'hearth', '-At', '-v', 'ON_ERROR_STOP=1'], input=statement, text=True, check=True, capture_output=True)
    return result.stdout.strip()


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def encode(data):
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(content if isinstance(content, bytes) else content.encode())


def prepare(inventory, output, state, existing_bundle=None):
    values = json.loads((state / 'config.json').read_text())
    farm, pool = UUID(values['HEARTH_FARM_ID']), UUID(inventory['pool_id'])
    name = inventory['name']
    if not isinstance(name, str) or not 1 <= len(name) <= 120:
        raise ValueError('Use a short worker name.')
    public, approved = {}, {}
    if not 1 <= len(inventory['services']) <= 16:
        raise ValueError('Approve from one to sixteen services per GPU group.')
    for key, entry in inventory['services'].items():
        if not re.fullmatch('[a-z][a-z0-9_-]{0,39}', key):
            raise ValueError('Invalid service identifier.')
        service = {k: entry[k] for k in ('unit', 'files', 'health_url', 'health_key_file', 'health_field', 'health_value')}
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}\.service', service['unit']):
            raise ValueError('Use an exact systemd service unit without templates.')
        if '/etc/systemd/system/' + service['unit'] not in service['files'] or len(service['files']) < 2:
            raise ValueError('Inventory must bind the unit and its entrypoint.')
        for path, digest in service['files'].items():
            if not path.startswith('/') or '..' in Path(path).parts or not re.fullmatch('[a-f0-9]{64}', digest):
                raise ValueError('Invalid approved file digest.')
        endpoint = urlsplit(service['health_url'])
        if endpoint.scheme != 'http' or endpoint.hostname != '127.0.0.1' or not endpoint.port or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError('Health checks must use a fixed loopback URL.')
        connection = UUID(entry['connection_id'])
        if sql(f'SELECT count(*) FROM inference_targets WHERE connection_id={quote(connection)} AND resource_pool_id={quote(pool)} AND farm_id={quote(farm)};') == '0':
            raise ValueError('Register the provider in the selected resource group first.')
        if any(value['connection_id'] == str(connection) for value in public.values()):
            raise ValueError('Each service needs its own provider connection.')
        public[key] = {'name': entry['name'], 'connection_id': str(connection)}
        approved[key] = service
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    node, token = uuid4(), secrets.token_hex(32)
    if existing_bundle:
        previous = json.loads((existing_bundle / 'config.json').read_text())
        node = UUID(previous['worker_id'])
        token = (existing_bundle / 'worker.key').read_text().strip()
        if not re.fullmatch('[a-f0-9]{64}', token):
            raise ValueError('Invalid existing worker credential.')
    signing = state / 'worker-recipe-signing.pem'
    if not signing.exists():
        result = subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519'], capture_output=True, check=True)
        write(signing, result.stdout)
    key_der = subprocess.run(['openssl', 'pkey', '-in', str(signing), '-pubout', '-outform', 'DER'], capture_output=True, check=True).stdout
    if len(key_der) != 44:
        raise ValueError('Unexpected Ed25519 public key format.')
    kid = 'operator-' + hashlib.sha256(key_der).hexdigest()[:16]
    payload = json.dumps({'schema_version': 1, 'worker_id': str(node), 'services': approved}, sort_keys=True, separators=(',', ':')).encode()
    header = json.dumps({'alg': 'Ed25519', 'kid': kid, 'typ': 'application/hearth.recipe+json'}, separators=(',', ':')).encode()
    message = (encode(header) + '.' + encode(payload)).encode()
    temporary = output / 'signing-input'
    write(temporary, message)
    signature = subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(signing), '-in', str(temporary)], capture_output=True, check=True).stdout
    temporary.unlink()
    write(output / 'recipe.jws', message.decode() + '.' + encode(signature))
    write(output / 'trust.json', json.dumps({kid: encode(key_der[-32:])}))
    write(output / 'worker.key', token)
    shutil.copyfile(state / 'hearth-root.crt', output / 'head-ca.pem')
    destination = '/etc/hearth-worker'
    config = {'head_url': values['HEARTH_ADMIN_ORIGIN'], 'worker_id': str(node), 'state_directory': '/var/lib/hearth-worker',
              **{key: destination + '/' + filename for key, filename in [('token_file', 'worker.key'), ('ca_file', 'head-ca.pem'), ('recipe_file', 'recipe.jws'), ('trust_file', 'trust.json')]}}
    write(output / 'config.json', json.dumps(config, indent=2))
    # Locked, fail-closed adoption. An already managed or occupied group must
    # be reviewed manually, never silently replaced by another worker identity.
    if existing_bundle:
        sql(f"""BEGIN;
          SELECT id FROM provider_pools WHERE id={quote(pool)} AND farm_id={quote(farm)} FOR UPDATE;
          DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM managed_workers w JOIN provider_pools p ON p.id=w.pool_id
            WHERE w.id={quote(node)} AND w.farm_id={quote(farm)} AND w.pool_id={quote(pool)} AND w.paused
            AND w.desired_service IS NULL AND w.state='stopped' AND w.observed_revision=w.revision
            AND w.seen_at<now()-interval '30 seconds' AND p.active_run_id IS NULL
            AND w.token_hash={quote(hashlib.sha256(token.encode()).hexdigest())})
          THEN RAISE EXCEPTION 'Pause and unload the idle worker, then stop its supervisor for thirty seconds before updating its approved recipe'; END IF; END $$;
          UPDATE managed_workers SET name={quote(name)},recipe_digest={quote(hashlib.sha256(payload).hexdigest())},
            services={quote(json.dumps(public))}::jsonb,revision=revision+1,boot_id=NULL,sequence=0,seen_at=NULL,
            state='offline',ready_service=NULL,reason='' WHERE id={quote(node)};
          INSERT INTO audit_events(id,farm_id,action,safe_metadata) VALUES(gen_random_uuid(),{quote(farm)},'worker.console_recipe_updated',jsonb_build_object('worker_id',{quote(node)}));
          COMMIT;""")
    else:
        sql(f"""BEGIN;
      SELECT id FROM provider_pools WHERE id={quote(pool)} AND farm_id={quote(farm)} FOR UPDATE;
      DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM provider_pools WHERE id={quote(pool)} AND farm_id={quote(farm)} AND active_run_id IS NULL)
      OR EXISTS(SELECT 1 FROM managed_workers WHERE pool_id={quote(pool)}) THEN RAISE EXCEPTION 'GPU group occupied or already managed'; END IF; END $$;
      INSERT INTO managed_workers(id,farm_id,name,pool_id,token_hash,recipe_digest,services)
      VALUES({quote(node)},{quote(farm)},{quote(name)},{quote(pool)},{quote(hashlib.sha256(token.encode()).hexdigest())},{quote(hashlib.sha256(payload).hexdigest())},{quote(json.dumps(public))}::jsonb);
      INSERT INTO audit_events(id,farm_id,action,safe_metadata) VALUES(gen_random_uuid(),{quote(farm)},'worker.console_adopt',jsonb_build_object('worker_id',{quote(node)}));
      COMMIT;""")
    print(f'Worker {node} registered paused. Private setup bundle: {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--state', type=Path, default=ROOT / '.hearth/head')
    parser.add_argument('--existing-bundle', type=Path, help='Update a stopped, paused worker using its private original bundle.')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run this operator setup tool as root on the head.')
    prepare(json.loads(args.inventory.read_text()), args.output, args.state, args.existing_bundle)


if __name__ == '__main__':
    main()
