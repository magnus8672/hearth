from hearth import farm_map
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def test_admin_scope_safe_projection_and_residency_updates(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    calls = []
    monkeypatch.setattr(farm_map, 'loaded_instances', lambda *args: calls.append(1) or {'fixture'})
    with factory('admin') as admin, factory() as user:
        assert admin.get('/api/v1/farm-map').status_code == 401
        signin(admin)
        assert admin.get('/api/v1/farm-map').status_code == 403
        promote(admin, migration, settings)
        signin(user)
        assert user.get('/api/v1/farm-map').status_code == 403
        target = configure(admin, csrf(admin, settings.admin_origin))
        result = admin.get('/api/v1/farm-map')
        assert result.status_code == 200, result.text
        assert not calls
        assert result.json()['machines'][1]['nodes'][0]['residency'] == 'unknown'
        with scoped_session(migration, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text("UPDATE inference_targets SET residency_policy='lmstudio_loaded' WHERE id=:id"), {'id': target})
        result = admin.get('/api/v1/farm-map')
        assert result.json()['machines'][1]['nodes'][0]['residency'] == 'loaded'
        assert len(calls) == 1
        assert not any(key in result.text for key in ('credential', 'tls_ca_pem', 'token_hash', 'recipe_digest', 'active_owner_id'))
        monkeypatch.setattr(farm_map, 'loaded_instances', lambda *args: set())
        admin.app.state.farm_map_observations.entries.clear()
        result = admin.get('/api/v1/farm-map').json()
        assert result['machines'][1]['nodes'][0]['residency'] == 'unloaded'
        with scoped_session(migration, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text('DELETE FROM capability_bindings WHERE target_id=:id'), {'id': target})
        result = admin.get('/api/v1/farm-map').json()
        assert result['binding_count'] == 0
        assert len(result['unbound_targets']) == 1
        assert 'chat.general' in {n['id'] for n in result['unassigned']}
