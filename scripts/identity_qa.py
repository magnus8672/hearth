"""Create and remove ONLY recorded synthetic identities in the empty reference test farm."""
import json
import secrets
import sys
from uuid import UUID

from appliance import ROOT
from configure_identity import ISSUER, admin_client, create_owner, owner_created
from development_stack import configuration
from hearth.database import make_engine, scoped_session
from sqlalchemy import text

RECORD = ROOT / '.hearth/identity-qa.json'


def prepare():
    values = configuration()
    if RECORD.exists() or owner_created(values):
        raise SystemExit('QA refuses to overwrite an existing record or Owner. Use an isolated empty farm.')
    data = {'username': 'qa-owner-' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24),
            'name': 'Morgan', 'farm_name': 'Test Hearth'}
    record = {'owner': data, 'farm_id': values['HEARTH_FARM_ID'], 'users': [],
              'signup': {'username': 'qa-signup-' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24), 'name': 'Casey'}}
    # Persist the narrow cleanup scope before touching either service.
    RECORD.write_text(json.dumps(record))
    create_owner(data)
    with admin_client(values) as client:
        users = client.get('/admin/realms/hearth/users', params={'username': data['username'], 'exact': True}).json()
        record['users'].append(users[0]['id'])
        for name in ['Rowan', 'Alex']:
            member = {'username': 'qa-member-' + secrets.token_hex(4), 'password': secrets.token_urlsafe(24), 'name': name}
            response = client.post('/admin/realms/hearth/users', json={'username': member['username'], 'firstName': name,
                'enabled': True, 'requiredActions': ['CONFIGURE_TOTP', 'CONFIGURE_RECOVERY_AUTHN_CODES'],
                'credentials': [{'type': 'password', 'value': member['password'], 'temporary': False}]})
            response.raise_for_status()
            record['users'].append(response.headers['Location'].split('/')[-1])
            record[name.lower()] = member
        RECORD.write_text(json.dumps(record))
    print('Synthetic Owner and two Members prepared. Credentials are in ignored local state only.')


def clean():
    record, values = json.loads(RECORD.read_text()), configuration()
    with admin_client(values) as client:
        if record.get('signup'):
            for account in client.get('/admin/realms/hearth/users', params={'username': record['signup']['username'], 'exact': True}).json():
                if account['id'] not in record['users']:
                    record['users'].append(account['id'])
    farm = UUID(record['farm_id'])
    app = make_engine(f"postgresql+psycopg://hearth_app:{values['HEARTH_APP_PASSWORD']}@127.0.0.1:55432/hearth")
    migration = make_engine(f"postgresql+psycopg://hearth_migrator:{values['HEARTH_MIGRATION_PASSWORD']}@127.0.0.1:55432/hearth")
    with migration.connect() as db:
        users = db.execute(text('SELECT id,subject,issuer FROM users WHERE farm_id=:farm'), {'farm': farm}).mappings().all()
        if any(str(user['subject']) not in record['users'] or user['issuer'] != ISSUER for user in users):
            raise SystemExit('Unrecorded real identity found. QA cleanup stopped without deleting anything.')
    for user in users:
        with scoped_session(app, user['id'], farm) as db:
            for table in ['outbox', 'messages', 'conversations', 'workspaces']:
                db.execute(text(f'DELETE FROM {table} WHERE farm_id=:farm'), {'farm': farm})
    with migration.begin() as db:
        for table in ['browser_sessions', 'audit_events', 'role_grants', 'users']:
            db.execute(text(f'DELETE FROM {table} WHERE farm_id=:farm'), {'farm': farm})
        db.execute(text('DELETE FROM farms WHERE id=:farm'), {'farm': farm})
    with admin_client(values) as client:
        for subject in record['users']:
            client.delete('/admin/realms/hearth/users/' + subject).raise_for_status()
        client.put('/admin/realms/hearth', json={'registrationAllowed': False}).raise_for_status()
    app.dispose()
    migration.dispose()
    RECORD.unlink()
    print('Recorded synthetic farm data removed. The real Owner setup is unclaimed.')


if __name__ == '__main__':
    {'prepare': prepare, 'clean': clean}[sys.argv[1]]()
