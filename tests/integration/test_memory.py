import io
import json
import os
import socket
import threading
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from hearth import chat, memory, memory_vault
from hearth.database import scoped_session
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def seed_history(db, workspace, owner, farm, content='The observatory telescope is named Juniper.', count=1):
    conversation, first = uuid4(), uuid4()
    db.execute(text("INSERT INTO conversations(id,farm_id,owner_id,workspace_id,title,kind) VALUES(:id,:farm,:owner,:workspace,'Observatory project','chat')"), {'id': conversation, 'farm': farm, 'owner': owner, 'workspace': workspace})
    for index in range(count):
        db.execute(text("INSERT INTO messages(id,conversation_id,farm_id,owner_id,sequence,role,content,status) VALUES(:id,:conversation,:farm,:owner,:sequence,'user',:content,'completed')"), {'id': first if index == 0 else uuid4(), 'conversation': conversation, 'farm': farm, 'owner': owner, 'sequence': index+1, 'content': content})
    return conversation, first


def test_private_notes_revisions_import_tombstones_and_role_boundaries(bff):
    factory, settings, app, migration, subject = bff
    with factory() as user, factory('admin') as admin:
        signin(user)
        signin(admin)
        headers = csrf(user, settings.user_origin)
        data = {'title': 'My telescope', 'body': 'Juniper lives in the observatory.', 'kind': 'preference'}
        assert user.post('/api/v1/memory/notes', json=data).status_code == 403
        assert admin.get('/api/v1/memory').status_code == 403
        saved = user.post('/api/v1/memory/notes', json=data, headers=headers)
        assert saved.status_code == 201, saved.text
        note = saved.json()
        path = '/api/v1/memory/notes/' + note['id']
        assert user.put(path, json=data | {'body': 'Juniper has a 150mm mirror.', 'revision': 1}, headers=headers).status_code == 200
        assert user.put(path, json=data | {'revision': 1}, headers=headers).status_code == 409
        assert [item['revision'] for item in user.get(path).json()['revisions']] == [2, 1]
        download = user.get('/api/v1/memory/vault.zip')
        assert download.status_code == 200, download.text if download.status_code != 200 else ''
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            markdown = archive.read(f"notes/{note['id']}.md").decode('utf-8')
        changed = markdown.replace('Juniper has a 150mm mirror.', 'Juniper has a 200mm mirror. 🔭')
        imported = user.post('/api/v1/memory/import', json={'markdown': changed}, headers=headers)
        assert imported.status_code == 200, imported.text
        assert imported.json()['source']['revision'] == 3
        assert user.post('/api/v1/memory/import', json={'markdown': changed}, headers=headers).status_code == 409
        malicious = changed.replace(f'scope: "{note["owner_id"]}"', f'scope: "{uuid4()}"')
        assert user.post('/api/v1/memory/import', json={'markdown': malicious}, headers=headers).status_code == 403
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM memory_notes')).scalar_one() == 0
            assert memory.search(db, 'Juniper') == []
            assert db.execute(text('SELECT count(*) FROM memory_note_revisions')).scalar_one() == 0
        with pytest.raises(DBAPIError), scoped_session(app, other, settings.farm_id) as db:
            db.execute(text("INSERT INTO memory_note_revisions(note_id,farm_id,owner_id,revision,title,body,kind,enabled,origin) VALUES(:id,:farm,:owner,999,'bad','bad','note',true,'forged')"), {'id': note['id'], 'farm': settings.farm_id, 'owner': other})
        assert user.post(path + '/remove', json={'revision': 3}, headers=headers).status_code == 200
        assert user.get(path).status_code == 404
        assert not user.get('/api/v1/memory/search?q=Juniper').json()['items']
        assert user.post('/api/v1/memory/import', json={'markdown': changed}, headers=headers).status_code == 404
        with zipfile.ZipFile(io.BytesIO(user.get('/api/v1/memory/vault.zip').content)) as archive:
            assert f"notes/{note['id']}.md" not in archive.namelist()
            assert 'Juniper has a 150mm mirror.' in archive.read('revisions.jsonl').decode()


def test_cross_session_recall_full_history_correction_and_context_window(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    contexts = []
    def stream(*args, **kwargs):
        contexts.append(args[3])
        yield 'text', 'Juniper is your telescope.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        owner = UUID(user.get('/api/v1/session').json()['id'])
        with scoped_session(app, owner, settings.farm_id) as db:
            workspace = db.execute(text('SELECT id FROM workspaces')).scalar_one()
            old_chat, first = seed_history(db, workspace, owner, settings.farm_id, count=45)
        created = user.post('/api/v1/chats', json={}, headers=headers).json()
        path = '/api/v1/chats/' + created['id']
        assert user.post(path + '/turns', json={'request_id': str(uuid4()), 'revision': 1, 'content': 'What is my telescope named?'}, headers=headers).status_code == 202
        result = wait_finished(user, path)
        receipt = result['runs'][-1]['memory_receipt']
        assert receipt['sources'] and all(item['type'] == 'message' for item in receipt['sources'])
        assert 'Juniper' in contexts[-1][0]['content']
        correction_path = f'/api/v1/memory/messages/{first}'
        corrected = user.put(correction_path, json={'revision': 1, 'content': 'My telescope is now named Maple.'}, headers=headers)
        assert corrected.status_code == 200, corrected.text
        assert user.put(correction_path, json={'revision': 1, 'content': 'Stale edit'}, headers=headers).status_code == 409
        revisions = user.get(correction_path).json()['revisions']
        assert revisions[-1]['origin'] == 'original' and 'Juniper' in revisions[-1]['content']
        assert not memory_receipt_valid(app, owner, settings.farm_id, receipt) if str(first) in [x['id'] for x in receipt['sources']] else True
        archive_page = user.get(f'/api/v1/memory/history/{old_chat}/messages?offset=40')
        assert archive_page.status_code == 200 and len(archive_page.json()['items']) == 5
        assert archive_page.json()['items'][0]['sequence'] == 41
        assert user.get(f'/api/v1/memory/history/{uuid4()}/messages').status_code == 404
        history = user.get('/api/v1/memory/history').json()['items']
        old = next(item for item in history if item['id'] == str(old_chat))
        assert user.put(f'/api/v1/memory/history/{old_chat}', json={'revision': old['revision'], 'enabled': False}, headers=headers).status_code == 200
        with scoped_session(app, owner, settings.farm_id) as db:
            assert memory.search(db, 'telescope', recall=True, exclude_chat=created['id']) == []
        # The old hard 31-message limit no longer blocks a conversation.
        old_path = '/api/v1/chats/' + str(old_chat)
        current = user.get(old_path).json()
        assert user.post(old_path + '/turns', json={'request_id': str(uuid4()), 'revision': current['revision'], 'content': 'Carry on please'}, headers=headers).status_code == 202
        long_result = wait_finished(user, old_path)
        assert len(long_result['messages']) == 47
        assert long_result['runs'][-1]['memory_receipt']['older_messages'] >= 16
        with zipfile.ZipFile(io.BytesIO(user.get('/api/v1/memory/vault.zip').content)) as archive:
            rows = archive.read(f'conversations/{old_chat}.jsonl').decode('utf-8').splitlines()
            assert len(rows) == 47
            assert json.loads(rows[0])['content'] == 'My telescope is now named Maple.'
            graph = json.loads(archive.read('graph.json'))
            assert str(old_chat) not in [item['id'] for item in graph['nodes']]


def memory_receipt_valid(app, owner, farm, receipt):
    with scoped_session(app, owner, farm) as db:
        return memory.receipt_current(db, receipt)


def test_edit_during_generation_fences_memory_without_failing_provider(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    entered, finish = threading.Event(), threading.Event()
    def stream(*args, **kwargs):
        yield 'text', 'Before the correction.'
        entered.set()
        assert finish.wait(10)
        yield 'text', ' This stale memory must not be published.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        note = user.post('/api/v1/memory/notes', json={'title': 'Style', 'body': 'Use metric measurements.', 'kind': 'preference'}, headers=headers).json()
        created = user.post('/api/v1/chats', json={}, headers=headers).json()
        path = '/api/v1/chats/' + created['id']
        try:
            assert user.post(path+'/turns', json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Help me plan my observatory'}, headers=headers).status_code == 202
            assert entered.wait(5)
            updated = user.put('/api/v1/memory/notes/' + note['id'], json={'title': 'Style', 'body': 'Use inches.', 'kind': 'preference', 'revision': 1}, headers=headers)
            assert updated.status_code == 200
        finally:
            finish.set()
        result = wait_finished(user, path)
        assert result['runs'][-1]['status'] == 'cancelled'
        assert 'stale memory' not in result['messages'][-1]['content']
        assert admin.get('/api/v1/providers').json()['items'][0]['state'] == 'ready'


def test_removed_memory_cannot_return_through_a_derived_reply_or_graph(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(chat, 'chat_stream', lambda *args, **kwargs: iter([('text', 'Your telescope has the secret name QuartzCanary.'), ('done', 'stop')]))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        owner = UUID(user.get('/api/v1/session').json()['id'])
        note = user.post('/api/v1/memory/notes', json={'title': 'Telescope', 'body': 'The telescope is QuartzCanary.', 'kind': 'preference'}, headers=headers).json()
        created = user.post('/api/v1/chats', json={}, headers=headers).json()
        path = '/api/v1/chats/'+created['id']
        assert user.post(path+'/turns', json={'request_id': str(uuid4()), 'revision': 1, 'content': 'What is my telescope called?'}, headers=headers).status_code == 202
        result = wait_finished(user, path)
        reply_id = result['messages'][-1]['id']
        assert result['runs'][-1]['memory_receipt']['sources'][0]['id'] == note['id']
        assert user.post('/api/v1/memory/notes/'+note['id']+'/remove', json={'revision': 1}, headers=headers).status_code == 200
        with scoped_session(app, owner, settings.farm_id) as db:
            context, receipt = memory.recall_context(db, 'telescope', uuid4(), [{'role': 'user', 'content': 'telescope'}], 0)
            assert 'QuartzCanary' not in json.dumps(context)
            assert reply_id not in [item['id'] for item in receipt['sources']]
        with zipfile.ZipFile(io.BytesIO(user.get('/api/v1/memory/vault.zip').content)) as archive:
            graph = json.loads(archive.read('graph.json'))
            assert reply_id not in [item['id'] for item in graph['nodes']]
            assert 'QuartzCanary' in archive.read(f'messages/{reply_id}.md').decode()


def test_message_correction_invalidates_its_saved_audio(bff, monkeypatch):
    from tests.integration.test_speech import configure_speech, fixture_provider, reply, wait_speech
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(chat, 'chat_stream', lambda *args, **kwargs: iter([('text', 'Original spoken reply.'), ('done', 'stop')]))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        configure(admin, headers)
        configure_speech(admin, headers)
        signin(user)
        headers = csrf(user, settings.user_origin)
        path, message = reply(user, headers)
        endpoint = path+'/messages/'+message['id']+'/speech'
        assert user.post(endpoint, json={'request_id': str(uuid4())}, headers=headers).status_code == 202
        spoken = wait_speech(user, path)
        audio = path+'/speech/'+spoken['id']+'/audio'
        assert user.get(audio).status_code == 200
        edited = user.put('/api/v1/memory/messages/'+message['id'], json={'revision': 1, 'content': 'Corrected spoken reply.'}, headers=headers)
        assert edited.status_code == 200, edited.text
        assert user.get(audio).status_code == 404
        assert user.post(endpoint, json={'request_id': str(uuid4())}, headers=headers).status_code == 202
        updated = wait_speech(user, path)
        assert updated['id'] != spoken['id'] and updated['status'] == 'completed'


def test_outbox_rebuild_failure_recovery_conflicts_and_offline_graphify(bff, tmp_path, monkeypatch):
    from scripts.graphify_vault import render
    factory, settings, app, _, _ = bff
    with factory() as user:
        signin(user)
        headers = csrf(user, settings.user_origin)
        owner = UUID(user.get('/api/v1/session').json()['id'])
        note = user.post('/api/v1/memory/notes', json={'title': '../../unsafe\nlabel', 'body': 'Observatory notes'}, headers=headers).json()
        root = tmp_path/'vaults'
        root.write_text('not a directory')
        with pytest.raises(OSError):
            memory_vault.project(app, settings.farm_id, owner, root)
        with scoped_session(app, owner, settings.farm_id) as db:
            assert memory.state(db)['projected_generation'] == 0
            assert db.execute(text("SELECT count(*) FROM outbox WHERE event_type='memory.vault.changed' AND delivered_at IS NULL")).scalar_one() > 0
        root.unlink()
        assert memory_vault.project(app, settings.farm_id, owner, root)
        assert not memory_vault.project(app, settings.farm_id, owner, root)
        base = root/str(settings.farm_id)/str(owner)
        note_path = base/'notes'/f"{note['id']}.md"
        note_path.write_text('My unexpected desktop edit', encoding='utf-8')
        second = user.post('/api/v1/memory/notes', json={'title': 'Linked note', 'body': f"See [[{note['id']}]]"}, headers=headers).json()
        assert memory_vault.project(app, settings.farm_id, owner, root)
        assert any(path.read_text(encoding='utf-8') == 'My unexpected desktop edit' for path in (base/'conflicts').glob('*.md'))
        graph = json.loads((base/'graph.json').read_text(encoding='utf-8'))
        def blocked(*args, **kwargs):
            raise AssertionError('The explicit graph adapter must never use a network or model.')
        monkeypatch.setattr(socket.socket, 'connect', blocked)
        result = render(graph, tmp_path/'graph')
        assert result == {'nodes': 2, 'edges': 1, 'notes_written': 2, 'network_calls': 0}
        assert f"[[{second['id']}]]" in (tmp_path/'graph'/f"{note['id']}.md").read_text(encoding='utf-8')
        with pytest.raises(ValueError):
            render(graph | {'edges': [{'source': note['id'], 'target': str(uuid4()), 'evidence': note['id'], 'relation': 'links_to'}]}, tmp_path/'badgraph')


def test_unicode_window_and_hostile_import_parser():
    newest = {'role': 'user', 'content': '🔥'*4000, 'attachment_ids': []}
    context, omitted = memory.recent_window([{'role': 'assistant', 'content': 'older'}, newest])
    assert context == [newest] and omitted == 1
    long_answer = {'role': 'assistant', 'content': 'a'*30000+'THE END', 'attachment_ids': []}
    continued, _ = memory.recent_window([long_answer, {'role': 'user', 'content': 'Continue', 'attachment_ids': []}])
    assert continued[0]['context_truncated'] and continued[0]['content'].endswith('THE END')
    assert sum(len(item['content'].encode()) for item in continued) <= 12000
    meta, body = memory_vault.parse_markdown('---\nschema: hearth.memory.v1\nenabled: false\nrevision: 3\n---\nObsidian properties can use plain scalars.')
    assert meta['enabled'] is False and meta['revision'] == 3 and body.startswith('Obsidian')
    for value in ('---\nschema: !!python/object:exec\n---\nno', '---\nschema: "hearth.memory.v1"\nschema: "hearth.memory.v1"\n---\nno'):
        with pytest.raises(HTTPException):
            memory_vault.parse_markdown(value)


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_MEMORY') != '1', reason='Explicit resident LAN model recall qualification required.')
def test_live_resident_qwen_recall_and_corrected_note(bff):
    import httpx
    factory, settings, _, migration, _ = bff
    url, model = 'http://10.20.30.40:1234', 'qwen/qwen3.8-27b'
    def loaded():
        return sorted(item['id'] for row in httpx.get(url+'/api/v1/models', timeout=10, trust_env=False).raise_for_status().json()['models'] for item in row['loaded_instances'])
    before = loaded()
    assert model in before
    nonce = str(uuid4())[:8]
    names = ['Juniper-'+nonce, 'Maple-'+nonce]
    replies = []
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Private memory LAN qualification', 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'})
        assert target.status_code == 201, target.text
        verified = admin.post(f"/api/v1/providers/{target.json()['id']}/probe", headers=ah, json={'revision': 1})
        assert verified.status_code == 200 and verified.json()['state'] == 'ready', verified.text
        signin(user)
        uh = csrf(user, settings.user_origin)
        note = user.post('/api/v1/memory/notes', json={'title': 'My telescope', 'body': f'My telescope is named {names[0]}.', 'kind': 'preference'}, headers=uh).json()
        for index, name in enumerate(names):
            if index:
                updated = user.put('/api/v1/memory/notes/'+note['id'], json={'title': 'My telescope', 'body': f'My telescope is now named {name}. The earlier name has been replaced.', 'kind': 'preference', 'revision': 1}, headers=uh)
                assert updated.status_code == 200, updated.text
            created = user.post('/api/v1/chats', json={}, headers=uh).json()
            path = '/api/v1/chats/'+created['id']
            accepted = user.post(path+'/turns', json={'request_id': str(uuid4()), 'revision': 1, 'content': 'What is my telescope currently named? Answer with just the name.', 'capability': 'chat.general'}, headers=uh)
            assert accepted.status_code == 202, accepted.text
            result = wait_finished(user, path, timeout=600)
            assert result['runs'][-1]['status'] == 'completed', result['runs'][-1]
            assert name.lower() in result['messages'][-1]['content'].lower()
            assert any(item['id'] == note['id'] and item['revision'] == index+1 for item in result['runs'][-1]['memory_receipt']['sources'])
            replies.append({'note_revision': index+1, 'reply': result['messages'][-1]['content'], 'finish_reason': result['runs'][-1]['finish_reason'], 'memory_sources': result['runs'][-1]['memory_receipt']['sources']})
        assert loaded() == before
        output = Path('evidence/memory/2026-09-13')
        output.mkdir(parents=True, exist_ok=True)
        (output/'live-recall.json').write_text(json.dumps({'scope': 'Real resident Qwen over the LAN and real restricted-role PostgreSQL/BFF in a disposable farm. OIDC is an explicit fixture.', 'model': model, 'new_chat_each_time': True, 'replies': replies, 'loaded_models_unchanged': True, 'cloud_calls': 0}, indent=2), encoding='utf-8')
