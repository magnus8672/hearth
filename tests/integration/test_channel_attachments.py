import time
from uuid import uuid4

from hearth import channels, identity, vision
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import configure, csrf, promote, setup
from tests.integration.test_identity import approve_fixture_member, signin
from tests.integration.test_identity import bff as bff
from tests.integration.test_postgres import databases as databases
from tests.integration.test_vision import picture


def test_channel_drafts_publish_atomically_and_membership_protects_pixels(bff, monkeypatch):
    factory, settings, app, migration, first_subject = setup(bff, monkeypatch)
    with factory() as first, factory() as second:
        signin(first)
        h1 = csrf(first, settings.user_origin)
        channel = first.post('/api/v1/channels', headers=h1, json={'name': 'Pictures'}).json()['id']
        path = '/api/v1/channels/' + channel
        other_room = first.post('/api/v1/channels', headers=h1, json={'name': 'Elsewhere'}).json()['id']
        assert first.post(path + '/attachments', content=picture()).status_code == 403
        assert first.post(path + '/attachments', headers=h1, content=b'not an image').status_code == 400
        assert first.post(path + '/attachments', headers=h1, content=b'x' * (vision.UPLOAD_LIMIT + 1)).status_code == 413
        upload = first.post(path + '/attachments', headers=h1, content=picture())
        assert upload.status_code == 201, upload.text
        attachment = upload.json()
        image_url = path + '/attachments/' + attachment['id']
        assert first.get(path).json()['unused_attachments'] == [attachment]
        response = first.get(image_url)
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['content-type'] == 'image/jpeg'
        assert response.content[:2] == b'\xff\xd8'
        assert first.get('/api/v1/channels/' + other_room + '/attachments/' + attachment['id']).status_code == 404
        subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *a: {'sub': subject, 'name': 'Second'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
            {'active': True, 'sub': first_subject if data.get('token') == 'EXPLICIT PROVIDER FIXTURE' else subject, 'iss': config.issuer}
            if endpoint == 'token/introspect' else {'id_token': 'SECOND', 'access_token': 'SECOND', 'refresh_token': 'SECOND', 'expires_in': 300})
        signin(second)
        approve_fixture_member(second, migration, settings)
        h2 = csrf(second, settings.user_origin)
        second_id = second.get('/api/v1/session').json()['id']
        assert second.get(image_url).status_code == 404
        assert second.post(path + '/attachments', headers=h2, content=picture()).status_code == 404
        assert second.post(path + '/join', headers=h2).status_code == 200
        assert second.get(image_url).status_code == 404  # Unsent drafts stay private even to joined members.
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM channel_attachments')).scalar_one() == 0
        body = {'request_id': str(uuid4()), 'content': '', 'attachment_ids': [attachment['id']]}
        assert second.post(path + '/messages', headers=h2, json=body).status_code == 404
        assert first.post(path + '/messages', headers=h1, json=body | {'attachment_ids': [attachment['id'], str(uuid4())]}).status_code == 404
        assert first.get(path).json()['messages'] == []
        assert first.get(path).json()['unused_attachments'] == [attachment]
        assert first.post(path + '/messages', headers=h1, json=body | {'attachment_ids': [attachment['id']] * 2}).status_code == 422
        assert first.post(path + '/messages', headers=h1, json=body | {'attachment_ids': []}).status_code == 422
        assert first.post(path + '/messages', headers=h1, json=body).status_code == 201
        assert first.post(path + '/messages', headers=h1, json=body).status_code == 201
        assert first.post(path + '/messages', headers=h1, json=body | {'content': 'changed'}).status_code == 409
        assert first.post(path + '/messages', headers=h1, json=body | {'request_id': str(uuid4())}).status_code == 404
        assert second.get(image_url).content == response.content
        assert second.get(path).json()['messages'][0]['attachments'] == [attachment]
        assert first.delete(image_url, headers=h1).status_code == 404
        assert second.delete(image_url, headers=h2).status_code == 404
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM channel_attachments')).scalar_one() == 1
            assert db.execute(text("UPDATE channel_attachments SET width=1 WHERE id=:id"), {'id': attachment['id']}).rowcount == 0
        with scoped_session(app, second_id, uuid4()) as db:
            assert db.execute(text('SELECT count(*) FROM channel_attachments')).scalar_one() == 0
        assert second.post(path + '/leave', headers=h2).status_code == 200
        assert second.get(image_url).status_code == 404
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM channel_attachments')).scalar_one() == 0
        assert second.post(path + '/join', headers=h2).status_code == 200
        assert second.get(image_url).status_code == 200


def test_channel_attachment_limit_removal_and_leave_cleanup(bff, monkeypatch):
    factory, settings, _, _, _ = setup(bff, monkeypatch)
    with factory() as user:
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Drafts'}).json()['id']
        uploads = [user.post(path + '/attachments', headers=headers, content=picture()).json() for _ in range(4)]
        assert user.post(path + '/attachments', headers=headers, content=picture()).status_code == 409
        assert user.delete(path + '/attachments/' + uploads[0]['id'], headers=headers).status_code == 200
        assert user.get(path + '/attachments/' + uploads[0]['id']).status_code == 404
        assert len(user.get(path).json()['unused_attachments']) == 3
        assert user.post(path + '/leave', headers=headers).status_code == 200
        assert user.post(path + '/join', headers=headers).status_code == 200
        assert user.get(path).json()['unused_attachments'] == []


def test_channel_mentions_use_verified_vision_and_recent_shared_pixels(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    calls = []
    def stream(*args, **kwargs):
        calls.append(args[3])
        yield 'text', 'A red rectangle and a blue circle.'
        yield 'done', 'stop'
    monkeypatch.setattr(channels, 'chat_stream', stream)
    monkeypatch.setattr(vision, 'probe', lambda *a: {'vision_probe': 'explicit-fixture'})
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert assign(admin, ah, 'vision.describe', [target]).status_code == 200
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Vision'}).json()['id']
        attachment = user.post(path + '/attachments', headers=headers, content=picture()).json()
        body = {'request_id': str(uuid4()), 'content': '@hearth what do you see?', 'attachment_ids': [attachment['id']]}
        assert user.post(path + '/messages', headers=headers, json=body).status_code == 201
        failed = user.get(path).json()['messages'][-1]
        assert failed['status'] == 'failed' and 'vision' in failed['reason']
        assert calls == []  # Never silently fall back to the text-only target.
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 2, 'vision': True}).status_code == 200
        follow = {'request_id': str(uuid4()), 'content': '@hearth which shape is blue?'}
        assert user.post(path + '/messages', headers=headers, json=follow).status_code == 201
        for _ in range(150):
            result = user.get(path).json()
            if result['messages'][-1]['status'] != 'running':
                break
            time.sleep(.02)
        assert result['messages'][-1]['content'] == 'A red rectangle and a blue circle.'
        assert len(calls) == 1
        pixels = [part for message in calls[0] if isinstance(message['content'], list) for part in message['content'] if part['type'] == 'image_url']
        assert len(pixels) == 1 and pixels[0]['image_url']['url'].startswith('data:image/jpeg;base64,')
        assert user.post(path + '/messages', headers=headers, json=follow).status_code == 201
        assert len(calls) == 1
        with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            assert db.execute(text('SELECT capability_id FROM channel_runs WHERE id=:id'), {'id': follow['request_id']}).scalar_one() == 'vision.describe'
        for count in (4, 2):
            images = [user.post(path + '/attachments', headers=headers, content=picture()).json()['id'] for _ in range(count)]
            assert user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': '', 'attachment_ids': images}).status_code == 201
        private_draft = user.post(path + '/attachments', headers=headers, content=picture()).json()
        assert user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': '@hearth compare the recent pictures'}).status_code == 201
        for _ in range(150):
            if user.get(path).json()['messages'][-1]['status'] != 'running':
                break
            time.sleep(.02)
        pixels = [part for message in calls[-1] if isinstance(message['content'], list) for part in message['content'] if part['type'] == 'image_url']
        assert len(pixels) == 4
        assert user.get(path).json()['unused_attachments'] == [private_draft]
