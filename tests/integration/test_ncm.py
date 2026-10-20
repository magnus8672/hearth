from uuid import uuid4

from hearth import summary_transport

from tests.integration.test_chat import csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases
from tests.security.test_ncm import INFO


def test_ncm_probe_single_article_route_and_history_rejection(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []
    monkeypatch.setattr(summary_transport, 'information', lambda *args: summary_transport.SummaryInfo(**INFO))
    def summarize(url, key, model, source, transport):
        calls.append(source)
        return summary_transport.SummaryResult(id=str(uuid4()), model=model, revision=INFO['revision'],
            text='A library reopened.', input_tokens=20, output_tokens=4, truncated=False, elapsed_seconds=1.)
    monkeypatch.setattr(summary_transport, 'summarize', summarize)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        response = admin.post('/api/v1/providers', headers=ah, json=dict(name='NCM fixture',
            base_url='http://127.0.0.1:1242', model_id=INFO['model'], protocol='hearth.summary.v1', local_only=True))
        assert response.status_code == 201, response.text
        target = response.json()
        verified = admin.post(f"/api/v1/providers/{target['id']}/probe", headers=ah, json={'revision': target['revision']})
        assert verified.status_code == 200 and verified.json()['state'] == 'ready', verified.text
        assert verified.json()['features'] == ['text.summarize', 'summary.single_document']
        signin(user)
        uh = csrf(user, settings.user_origin)
        created = user.post('/api/v1/chats', headers=uh, json={})
        path = '/api/v1/chats/'+created.json()['id']
        source = 'The library reopened after a renovation.'
        response = user.post(path+'/turns', headers=uh, json=dict(request_id=str(uuid4()), revision=1, content=source, capability='text.summarize'))
        assert response.status_code == 202, response.text
        result = wait_finished(user, path)
        assert result['messages'][-1]['content'] == 'A library reopened.', result
        assert calls[-1] == source
        before = len(calls)
        response = user.post(path+'/turns', headers=uh, json=dict(request_id=str(uuid4()), revision=result['revision'], content='Summarize our history', capability='text.summarize'))
        assert response.status_code == 409, response.text
        assert len(calls) == before
