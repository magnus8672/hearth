"""Isolated trusted Linux browser for reference identity acceptance testing."""
import argparse
import hashlib
import json
import subprocess

import httpx
from appliance import ROOT, ssh_args
from configure_identity import admin_client
from development_stack import configuration

QA = '/opt/hearth/.hearth/browser-qa'
NODE = '/opt/hearth/.hearth/toolchains/node-linux/bin/node'
BROWSER_HOME = '/opt/hearth/.hearth/browser-home'


def ssh(command, **kwargs):
    return subprocess.run([str(arg) for arg in ssh_args()] + [command], check=True, **kwargs)


def install():
    lock = json.loads((ROOT / 'deploy/bootstrap/browser-test.lock.json').read_text())
    name = 'node-v24.14.0-linux-x64.tar.xz'
    target = ROOT / '.hearth/downloads' / name
    with httpx.Client(timeout=120, follow_redirects=True, trust_env=False) as client:
        checksums = client.get('https://nodejs.org/dist/v24.14.0/SHASUMS256.txt')
        checksums.raise_for_status()
        expected = next(line.split()[0] for line in checksums.text.splitlines() if line.endswith('  ' + name))
        if not target.exists():
            response = client.get('https://nodejs.org/dist/v24.14.0/' + name)
            response.raise_for_status()
            target.write_bytes(response.content)
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError('Node archive does not match the official checksum')
    if expected != lock['node']['sha256']:
        raise ValueError('Official Node checksum differs from the reviewed test lock')
    with target.open('rb') as stream:
        ssh('mkdir -p /opt/hearth/.hearth/toolchains/node-linux && tar -xJf - --strip-components=1 -C /opt/hearth/.hearth/toolchains/node-linux', stdin=stream)
    ssh(f'sudo apt-get update -qq && sudo apt-get install -y -qq npm libnss3-tools && mkdir -p {QA} && cd {QA} && {NODE} /usr/share/nodejs/npm/bin/npm-cli.js install --no-audit --no-fund @playwright/test@1.63.0')
    ssh(f'cd {QA} && {NODE} node_modules/playwright/cli.js install-deps chromium')
    # The guest's CDN download timed out. Transfer the hash-pinned browser from
    # the host over the authenticated maintenance channel instead.
    browser = ROOT / '.hearth/downloads' / lock['chromium']['filename']
    if not browser.exists():
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(lock['chromium']['url'])
            response.raise_for_status()
            browser.write_bytes(response.content)
    if hashlib.sha256(browser.read_bytes()).hexdigest() != lock['chromium']['sha256']:
        raise ValueError('Browser archive checksum differs from the reviewed test lock')
    with browser.open('rb') as stream:
        ssh(f'cat > {QA}/chrome.zip', stdin=stream)
    cache = BROWSER_HOME + '/.cache/ms-playwright/chromium_headless_shell-1243'
    ssh(f'python3 -m zipfile -e {QA}/chrome.zip {cache} && chmod +x {cache}/chrome-headless-shell-linux64/chrome-headless-shell')
    ssh(f'mkdir -p {BROWSER_HOME}/.pki/nssdb && if [ ! -f {BROWSER_HOME}/.pki/nssdb/cert9.db ]; then certutil -N --empty-password -d sql:{BROWSER_HOME}/.pki/nssdb; fi && docker exec hearth-development-edge-1 cat /data/caddy/pki/authorities/local/root.crt > {QA}/root.crt && certutil -A -d sql:{BROWSER_HOME}/.pki/nssdb -n hearth-local-test -t "C,," -i {QA}/root.crt')
    print('Browser installed with an isolated NSS trust store. Windows trust is unchanged.')


def run():
    for source, target in [(ROOT / 'tests/browser/identity-live.mjs', QA + '/identity-live.mjs'),
                           (ROOT / '.hearth/identity-qa.json', QA + '/identity-qa.json')]:
        with source.open('rb') as stream:
            ssh(f'umask 077; cat > {target}', stdin=stream)
    try:
        ssh(f'cd {QA} && HOME={BROWSER_HOME} {NODE} identity-live.mjs')
    finally:
        result = ssh(f'cat {QA}/identity-qa.json', capture_output=True)
        data = json.loads(result.stdout)
        with admin_client(configuration()) as client:
            for account in client.get('/admin/realms/hearth/users', params={'username': data['signup']['username'], 'exact': True}).json():
                if account['id'] not in data['users']:
                    data['users'].append(account['id'])
        (ROOT / '.hearth/identity-qa.json').write_text(json.dumps(data))
    evidence = ROOT / 'evidence/identity/2026-09-12'
    evidence.mkdir(parents=True, exist_ok=True)
    for filename in ['admin-overview.png', 'admin-firelight.png', 'capabilities.png', 'user-drafts.png', 'user-mobile.png', 'identity-browser.json']:
        result = ssh(f'cat {QA}/{filename}', capture_output=True)
        (evidence / filename).write_bytes(result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'run'])
    args = parser.parse_args()
    {'install': install, 'run': run}[args.action]()
