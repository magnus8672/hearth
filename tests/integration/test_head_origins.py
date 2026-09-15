"""Remote browser/API origins with real RLS, explicit OIDC and inference fixtures."""

from urllib.parse import parse_qs, urlsplit

import pytest

from tests.integration.test_client_api import key, prepared
from tests.integration.test_identity import bff as bff
from tests.integration.test_postgres import databases as databases


@pytest.mark.parametrize('workspace', ['https://hearth.home.arpa:18444', 'https://hearth.home.arpa'])
def test_lan_identity_links_client_urls_and_host_rejection(bff, monkeypatch, workspace):
    factory, settings, _, _, _ = bff
    settings.admin_origin = 'https://hearth.home.arpa:18443'
    settings.user_origin = workspace
    settings.identity_origin = 'https://hearth.home.arpa:18445'
    settings.trusted_hosts = ['hearth.home.arpa']
    with factory('admin') as admin, factory() as user:
        config, _, _, _ = prepared(bff, monkeypatch, admin, user)
        start = user.get('/auth/login')
        target = urlsplit(start.headers['location'])
        assert target.netloc == 'hearth.home.arpa:18445'
        assert parse_qs(target.query)['redirect_uri'] == [settings.user_origin + '/auth/callback']
        identity = user.get('/api/v1/session').json()
        assert identity['admin_origin'] == settings.admin_origin
        assert identity['user_origin'] == settings.user_origin
        connections = user.get('/api/v1/client-keys').json()
        assert connections['base_url'] == settings.user_origin + '/v1'
        assert connections['mcp_url'] == settings.user_origin + '/mcp'
        saved = key(user, config)
        auth = {'Authorization': 'Bearer ' + saved['key']}
        assert user.get('/v1/models', headers=auth).status_code == 200
        assert user.get('/v1/models', headers=auth | {'Host': 'localhost:18444'}).status_code == 400
        assert user.get('/v1/models', headers=auth | {'Origin': 'https://localhost:8444'}).status_code == 403
        response = user.post('/mcp', headers=auth | {'Accept': 'application/json, text/event-stream'}, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
        assert response.status_code == 200
        assert [tool['name'] for tool in response.json()['result']['tools']] == ['list_tools', 'describe_tool', 'run_tool']
