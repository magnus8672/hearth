"""Linux-only local address supervisor. No TCP listener or arbitrary command API."""
import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import socketserver
import ssl
import struct
import subprocess
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

try:
    from scripts import head
except ModuleNotFoundError:
    import head

AUDIENCES = ('ADMIN', 'USER', 'IDENTITY')


def public(values):
    return {'base_url': values['HEARTH_USER_ORIGIN'], 'admin_url': values['HEARTH_ADMIN_ORIGIN'],
            'identity_url': values['HEARTH_IDENTITY_ORIGIN'], 'welcome_url': head.setup_url(values)}


def revision(values):
    return hashlib.sha256(json.dumps(public(values), sort_keys=True).encode()).hexdigest()


def changed(values, base_url):
    parsed = urlsplit(base_url.strip())
    ports = (int(values['HEARTH_ADMIN_PORT']), parsed.port or 443, int(values['HEARTH_IDENTITY_PORT']))
    replacement = head.base_url_endpoints(base_url, ports)
    previous = json.loads(values.get('HEARTH_PREVIOUS_ENDPOINTS', '[]'))
    origins = [values[f'HEARTH_{audience}_ORIGIN'] for audience in AUDIENCES]
    if origins != [replacement[f'HEARTH_{audience}_ORIGIN'] for audience in AUDIENCES]:
        previous = [item for item in previous if item != origins] + [origins]
    return values | replacement | {'HEARTH_PREVIOUS_ENDPOINTS': json.dumps(previous[-4:])}


def check_dns(host):
    try:
        resolved = {item[4][0] for item in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)}
    except socket.gaierror:
        raise ValueError('The head cannot resolve this name. Add its DNS record before applying.') from None
    interfaces = json.loads(subprocess.run(['ip', '-j', '-4', 'address', 'show'], check=True, capture_output=True, text=True, timeout=10).stdout)
    local = {item['local'] for interface in interfaces for item in interface.get('addr_info', [])
             if not ipaddress.ip_address(item['local']).is_loopback}
    if not resolved or not resolved <= local:
        raise ValueError('Every IPv4 address for this name must point to this head. Check DNS on the VM before applying.')
    return sorted(resolved)


def console(state, action, data):
    return head.compose(state, 'run', '--rm', '--no-deps', '-T', 'head-console', action,
                        input=json.dumps(data).encode(), capture_output=True, timeout=240)


def refresh_services(state, previous, actor, operation):
    head.compose(state, 'config', '--quiet', capture_output=True, timeout=30)
    head.compose(state, 'up', '-d', '--no-deps', 'keycloak', capture_output=True, timeout=180)
    console(state, 'address-apply', {'old_issuer': previous['HEARTH_IDENTITY_ORIGIN']+'/realms/hearth',
                                  'actor_id': actor, 'operation_id': operation})
    head.compose(state, 'up', '-d', '--no-deps', 'api', 'user-api', capture_output=True, timeout=180)
    head.compose(state, 'up', '-d', '--no-deps', '--force-recreate', 'edge', capture_output=True, timeout=180)


class LocalTLS(http.client.HTTPSConnection):
    """Connect to this host while verifying the advertised DNS/IP certificate."""
    def connect(self):
        raw = socket.create_connection(('127.0.0.1', self.port), timeout=self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def verify(state):
    values = head.load(state)
    context = ssl.create_default_context(cadata=head.export_ca(state))
    for audience in AUDIENCES:
        origin = urlsplit(values[f'HEARTH_{audience}_ORIGIN'])
        path = '/realms/hearth/.well-known/openid-configuration' if audience == 'IDENTITY' else '/health/ready'
        for attempt in range(45):
            connection = LocalTLS(origin.hostname, origin.port or 443, context=context, timeout=4)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                data = json.loads(response.read(65536))
                if response.status != 200 or (audience == 'IDENTITY' and data.get('issuer') != values['HEARTH_IDENTITY_ORIGIN']+'/realms/hearth'):
                    raise ValueError('The updated head is not ready.')
                break
            except (OSError, ValueError, http.client.HTTPException):
                if attempt == 44:
                    raise ValueError('The updated HTTPS, API or identity health check failed.') from None
                time.sleep(2)
            finally:
                connection.close()
    head.export_certificates(state)


class Controller:
    def __init__(self, state):
        self.state = state.resolve()
        self.lock = threading.Lock()
        self.journal = self.state / 'address-operation.json'

    def read_job(self):
        return json.loads(self.journal.read_text()) if self.journal.exists() else None

    def write_job(self, job):
        job['updated_at'] = datetime.now(UTC).isoformat()
        head.private_write(self.journal, json.dumps(job, indent=2)+'\n')

    def status(self):
        values = head.load(self.state)
        job = self.read_job()
        visible = {key: job[key] for key in ('operation_id', 'state', 'message', 'target', 'updated_at')} if job else None
        fingerprint = None
        root = self.state / 'hearth-root.crt'
        if root.exists():
            fingerprint = hashlib.sha256(head.certificate_der(root.read_text())[0]).hexdigest()
        return public(values) | {'revision': revision(values), 'operation': visible, 'root_sha256': fingerprint}

    def preview(self, base_url):
        values = head.load(self.state)
        proposed = changed(values, base_url)
        return public(proposed) | {'revision': revision(values), 'addresses': check_dns(proposed['HEARTH_PUBLIC_HOST']),
                                   'previous': public(values), 'trust_root_preserved': True}

    def submit(self, data):
        actor, operation = str(UUID(data['actor_id'])), str(UUID(data['operation_id']))
        if not self.lock.acquire(blocking=False):
            raise ValueError('An address operation is already running. Wait for it to finish.')
        try:
            job = self.read_job()
            if job and job['operation_id'] == operation:
                if job['target']['base_url'] != data['base_url'].rstrip('/') or job['actor_id'] != actor:
                    raise ValueError('This operation ID belongs to a different request.')
                return self.status()
            if job and job['state'] in {'queued', 'applying', 'rolling_back', 'recovery_required'}:
                raise ValueError('The previous address operation must finish or be recovered before another can start.')
            old = head.load(self.state)
            if data['expected_revision'] != revision(old):
                raise ValueError('The head address changed since this preview. Refresh and preview again.')
            new = changed(old, data['base_url'])
            check_dns(new['HEARTH_PUBLIC_HOST'])
            console(self.state, 'address-check', {'actor_id': actor})
            job = {'operation_id': operation, 'actor_id': actor, 'state': 'queued',
                   'message': 'Preparing the new address. The head will restart and require sign-in.',
                   'target': public(new), 'before': old, 'after': new}
            self.write_job(job)
            # A short delay lets the browser receive and retain the new links.
            threading.Thread(target=self.run, args=(job,), daemon=False).start()
            return self.status()
        finally:
            self.lock.release()

    def rollback(self, job):
        job.update(state='rolling_back', message='Restoring the previous address after an incomplete change.')
        self.write_job(job)
        head.private_write(self.state / 'config.json', json.dumps(job['before'], indent=2)+'\n')
        refresh_services(self.state, job['after'], job['actor_id'], job['operation_id'])
        verify(self.state)
        job.update(state='rolled_back', message='The change did not complete. The previous address has been restored; sign in there and check DNS before retrying.')

    def run(self, job, recovering=False):
        with self.lock:
            started = recovering
            try:
                if recovering:
                    self.rollback(job)
                else:
                    time.sleep(3)
                    check_dns(job['after']['HEARTH_PUBLIC_HOST'])
                    console(self.state, 'address-check', {'actor_id': job['actor_id']})
                    job.update(state='applying', message='Updating certificates and sign-in addresses. Use the new Administration link when ready.')
                    self.write_job(job)
                    started = True
                    head.private_write(self.state / 'config.json', json.dumps(job['after'], indent=2)+'\n')
                    refresh_services(self.state, job['before'], job['actor_id'], job['operation_id'])
                    verify(self.state)
                    job.update(state='succeeded', message='Address and public certificate package updated. Sign in at the new address.')
            except Exception:
                # Never publish exception output: Compose/identity errors can contain credentials.
                if not started:
                    job.update(state='failed', message='DNS or administrator authorization changed before maintenance. No addresses were changed. Preview again before retrying.')
                else:
                    try:
                        self.rollback(job)
                    except Exception:
                        job.update(state='recovery_required', message='Automatic recovery could not finish. On the VM stop hearth-head-control, then run: sudo python3 scripts/head_control.py recover')
            self.write_job(job)

    def recover(self):
        job = self.read_job()
        if job and job['state'] in {'queued', 'applying', 'rolling_back', 'recovery_required'}:
            self.run(job, recovering=True)


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.handle_call()

    def do_POST(self):
        self.handle_call()

    def handle_call(self):
        self.connection.settimeout(15)
        status, content_type = 200, 'application/json'
        try:
            _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in {0, 10001}:
                raise ValueError('This socket is restricted to the local admin service.')
            controller = self.server.controller
            if self.command == 'GET' and self.path == '/status':
                result = controller.status()
            elif self.command == 'GET' and self.path == '/certificates':
                result = (controller.state / 'hearth-client-certificates.zip').read_bytes()
                content_type = 'application/zip'
            elif self.command == 'POST' and self.path in {'/preview', '/apply'}:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 2048 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Invalid address request size.')
                data = json.loads(self.rfile.read(length))
                fields = {'base_url'} if self.path == '/preview' else {'base_url', 'actor_id', 'operation_id', 'expected_revision'}
                if not isinstance(data, dict) or set(data) != fields or not all(isinstance(value, str) and len(value) <= 300 for value in data.values()):
                    raise ValueError('Invalid address request.')
                result = controller.preview(data['base_url']) if self.path == '/preview' else controller.submit(data)
            else:
                status, result = 404, {'message': 'Unknown head operation.'}
        except ValueError as exc:
            status, result = 409, {'message': str(exc)}
        except Exception:
            status, result = 503, {'message': 'The local address operation could not complete. Check the head service on the VM.'}
        body = result if isinstance(result, bytes) else json.dumps(result).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def install(state):
    if os.geteuid() != 0 or not Path('/run/systemd/system').is_dir():
        raise ValueError('Install the head address service as root on a systemd Linux VM.')
    head.compose_context(state)
    unit = '\n'.join(['[Unit]', 'Description=hearth head address and certificate supervisor',
        'After=docker.service network-online.target', 'Requires=docker.service', '[Service]',
        'Type=simple', 'User=root',
        'ExecStart=/usr/bin/python3 '+json.dumps(str(head.ROOT/'scripts/head_control.py'))+' --state '+json.dumps(str(state))+' serve',
        'Restart=on-failure', 'RestartSec=5', 'UMask=0077', 'NoNewPrivileges=yes',
        'ProtectSystem=full', 'ProtectHome=yes', 'PrivateTmp=yes', '[Install]', 'WantedBy=multi-user.target', ''])
    Path('/etc/systemd/system/hearth-head-control.service').write_text(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'hearth-head-control.service'], check=True)
    print('hearth head address service installed. Administration settings can now change the base URL.')


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=head.STATE)
    parser.add_argument('action', choices=['serve', 'recover'])
    args = parser.parse_args()
    # Serialize daemon and explicit recovery across host processes.
    lock_file = (args.state / 'address-control.lock').open('a')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('The address supervisor is already running. Stop it before manual recovery.') from None
    controller = Controller(args.state)
    controller.recover()
    if args.action == 'recover':
        print(json.dumps(controller.status()))
        return
    directory = args.state / 'control'
    directory.mkdir(exist_ok=True, mode=0o755)
    path = directory / 'control.sock'
    path.unlink(missing_ok=True)
    with Server(str(path), Handler) as server:
        os.chown(path, 0, 10001)
        os.chmod(path, 0o660)
        server.controller = controller
        server.serve_forever()


if __name__ == '__main__':
    main()
