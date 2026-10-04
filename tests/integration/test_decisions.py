"""Decision authority, lifecycle and selection checks against restricted PostgreSQL."""

import threading
import time
from uuid import UUID, uuid4

import pytest
from hearth import decision_transport, decisions, route_decisions
from hearth.contracts import DecisionAnswer, DecisionProviderInfo, DecisionResult
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.policy import Principal, permissions_for
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def answer(data, choice="yes", **changes):
    return DecisionResult(
        id=data.id,
        model="fixture-decision",
        model_revision="fixture-v1",
        manifest_sha256="a" * 64,
        answers=[
            DecisionAnswer(
                id=q.id,
                kind=q.kind,
                choice=choice if q.kind == "choice" else None,
                score=1.2 if q.kind == "score" else None,
                probability_true=0.8 if q.kind == "boolean" else None,
                answer_confidence=0.95,
            )
            for q in data.questions
        ],
        elapsed_ms=12.0,
        input_tokens=24,
        **changes,
    )


def payload():
    return {
        "id": str(uuid4()),
        "state": "The parcel arrived.",
        "questions": [
            {
                "id": "delivered",
                "kind": "choice",
                "instructions": "Was the parcel delivered?",
                "options": {"yes": "Delivered", "no": "Not delivered"},
            }
        ],
    }


def wait(user, path):
    for _ in range(1500):
        response = user.get(path)
        assert response.status_code == 200, response.text
        value = response.json()
        if value["state"] != "running":
            return value
        time.sleep(0.02)
    pytest.fail("Decision did not complete")


def runtime(monkeypatch):
    monkeypatch.setattr(
        decision_transport,
        "information",
        lambda *a: DecisionProviderInfo(
            model="fixture-decision",
            model_revision="fixture-v1",
            manifest_sha256="a" * 64,
            question_kinds=["choice", "score", "boolean"],
            maximum_tokens=1024,
            maximum_characters=8000,
            languages=["en"],
            offline=True,
            ready=True,
        ),
    )
    monkeypatch.setattr(decision_transport, "evaluate", lambda settings, data, *a, **kw: answer(data))


def test_direct_private_idempotency_cancel_recover_and_client_scope(bff, monkeypatch):
    factory, settings, app, migration, subject = bff
    settings.decision_socket = "/fixture-only.sock"
    runtime(monkeypatch)
    calls = []

    def evaluate(settings, data, *a, **kw):
        calls.append(data.id)
        return answer(data)

    monkeypatch.setattr(decision_transport, "evaluate", evaluate)
    with factory() as user:
        signin(user)
        headers = csrf(user, settings.user_origin)
        data = payload()
        assert user.post("/api/v1/decisions", json=data).status_code == 403
        saved = user.post("/api/v1/decisions", headers=headers, json=data)
        assert saved.status_code == 202, saved.text
        path = "/api/v1/decisions/" + data["id"]
        assert wait(user, path)["result"]["answers"][0]["choice"] == "yes"
        assert user.post("/api/v1/decisions", headers=headers, json=data).status_code == 202
        assert len(calls) == 1
        assert (
            user.post("/api/v1/decisions", headers=headers, json=data | {"state": "Different"}).status_code
            == 409
        )
        owner = user.get("/api/v1/session").json()["id"]
        # Even a farm Owner cannot open another user's private results.
        with migration.connect() as db:
            other = db.execute(
                text("SELECT id FROM users WHERE farm_id=:farm AND id<>:owner LIMIT 1"),
                {"farm": settings.farm_id, "owner": owner},
            ).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text("SELECT count(*) FROM decision_runs")).scalar_one() == 0
        grant = user.post(
            "/api/v1/client-keys",
            headers=headers,
            json={"name": "Decision fixture", "capabilities": ["decision.evaluate"]},
        )
        assert grant.status_code == 201, grant.text
        auth = {"Authorization": "Bearer " + grant.json()["key"]}
        result = user.post("/v1/decisions", headers=auth, json=payload())
        assert result.status_code == 200, result.text
        assert (
            user.post(
                "/v1/chat/completions",
                headers=auth,
                json={"model": "chat.general", "messages": [{"role": "user", "content": "hi"}]},
            ).status_code
            == 403
        )
        entered, release = threading.Event(), threading.Event()

        def slow(settings, data, *a, **kw):
            entered.set()
            release.wait(5)
            return answer(data)

        monkeypatch.setattr(decision_transport, "evaluate", slow)
        data = payload()
        path = "/api/v1/decisions/" + data["id"]
        user.post("/api/v1/decisions", headers=headers, json=data)
        assert entered.wait(2)
        assert user.post("/api/v1/decisions", headers=headers, json=payload()).status_code == 429
        assert user.delete(path, headers=headers).json() == {"stopping": True}
        release.set()
        assert wait(user, path)["state"] == "cancelled"
        assert user.get(path).json()["result"] is None
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(
                text(
                    "UPDATE decision_runs SET state='running',created_at=now()-interval '2 minutes' WHERE id=:id"
                ),
                {"id": data["id"]},
            )
        assert user.get(path).json()["state"] == "failed"
        assert user.delete(path, headers=headers).status_code == 200
        assert user.get(path).status_code == 404


def test_dedicated_probe_source_and_fallback_do_not_change_member_routes(bff, monkeypatch):
    factory, settings, app, migration, subject = bff
    settings.decision_socket = "/fixture-only.sock"
    runtime(monkeypatch)
    with factory("admin") as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        created = admin.post(
            "/api/v1/providers",
            headers=headers,
            json={
                "name": "Dedicated decisions",
                "base_url": "http://127.0.0.1:8098/v1",
                "model_id": "fixture-decision",
                "protocol": "hearth.decision.v1",
                "local_only": True,
            },
        )
        assert created.status_code == 201, created.text
        target = created.json()
        probe = admin.post(
            "/api/v1/providers/" + target["id"] + "/probe",
            headers=headers,
            json={"revision": target["revision"]},
        )
        assert probe.status_code == 200, probe.text
        assert probe.json()["state"] == "ready", probe.text
        before = admin.get("/api/v1/capability-routes").json()
        config = admin.get("/api/v1/decision-settings").json()["settings"]
        saved = admin.put(
            "/api/v1/decision-settings",
            headers=headers,
            json=config | {"source": "dedicated", "target_id": target["id"], "mode": "semantic"},
        )
        assert saved.status_code == 200, saved.text
        assert admin.get("/api/v1/capability-routes").json() == before
        assert admin.put("/api/v1/decision-settings", headers=headers, json=config).status_code == 409
        signin(user)
        owner = UUID(user.get("/api/v1/session").json()["id"])
        with scoped_session(app, owner, settings.farm_id) as db:
            principal = Principal(owner, settings.farm_id, permissions_for(db, owner, settings.farm_id), 1)
        requests = []

        def fail_dedicated(settings, data, target=None, **kw):
            requests.append(target is not None)
            if target:
                raise ProviderError("fixture connection refused", provider_fault=False)
            return answer(data, "chat.general")

        monkeypatch.setattr(decision_transport, "evaluate", fail_dedicated)
        data = route_decisions.intent_request("Hello there")
        result, receipt = decisions.internal(app, settings, principal, data, saved.json())
        assert requests == [True, False] and receipt["source"] == "builtin" and receipt["attempts"]
        with pytest.raises(ProviderError):
            decisions.internal(app, settings, principal, data, saved.json() | {"fallback_builtin": False})
        # Explicit member comparisons never silently substitute the built-in service.
        member = user.post(
            "/api/v1/decisions",
            headers=csrf(user, settings.user_origin),
            json=payload() | {"target_id": target["id"]},
        )
        assert member.status_code == 202, member.text
        assert wait(user, "/api/v1/decisions/" + member.json()["id"])["state"] == "failed"


def test_real_switchyard_balancing_affinity_busy_exclusion_and_revisions(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory("admin") as admin:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        first, second = configure(admin, headers), configure(admin, headers, "other")
        # Distinct physical pools. The selection library may choose either, never both.
        saved = admin.put(
            "/api/v1/capability-routes/chat.general",
            headers=headers,
            json={
                "revision": 1,
                "selection_policy": "balanced",
                "targets": [{"target_id": first, "priority": 100}, {"target_id": second, "priority": 90}],
            },
        )
        assert saved.status_code == 200, saved.text
        owner = UUID(admin.get("/api/v1/session").json()["id"])
        with scoped_session(app, owner, settings.farm_id) as db:
            principal = Principal(owner, settings.farm_id, permissions_for(db, owner, settings.farm_id), 1)
        observed = []
        route_decisions.warm_selector()
        assert route_decisions._selector_ready.wait(30)
        real = route_decisions.switchyard_select

        async def selection(ids):
            observed.append(ids)
            return await real(ids)

        monkeypatch.setattr(route_decisions, "switchyard_select", selection)
        picked = route_decisions.select_target(
            app, settings, principal, "chat.general", scope="fixture-conversation"
        )
        assert set(observed[0]) == {UUID(first), UUID(second)}
        assert picked.metadata["reason"] == "switchyard_balanced"
        assert (
            route_decisions.select_target(
                app, settings, principal, "chat.general", scope="fixture-conversation"
            ).target_id
            == picked.target_id
        )
        assert len(observed) == 1
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(
                text("UPDATE inference_targets SET revision=revision+1 WHERE id=:id"),
                {"id": picked.target_id},
            )
        with (
            scoped_session(app, owner, settings.farm_id) as db,
            pytest.raises(Exception, match="changed during selection"),
        ):
            picked.revalidate(db)


def test_semantic_surfaces_context_scope_authority_bypass_and_shadow(bff, monkeypatch):
    import json

    from hearth import channels, chat, client_api

    from tests.integration.test_chat import wait_finished
    from tests.integration.test_client_api import key

    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    runtime(monkeypatch)
    settings.decision_socket = '/fixture-only.sock'
    classified, dispatched = [], []

    def classify(settings, data, *a, **kw):
        classified.append(json.loads(data.state))
        return answer(data, 'code.implement')

    def stream(*args, **kwargs):
        dispatched.append(args[2])
        yield 'text', 'One code response'
        yield 'done', 'stop'

    monkeypatch.setattr(decision_transport, 'evaluate', classify)
    for module in [chat, channels, client_api]:
        monkeypatch.setattr(module, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assigned = admin.put('/api/v1/capability-routes/code.implement', headers=ah, json={
            'revision': 1, 'targets': [{'target_id': target, 'priority': 100}]})
        assert assigned.status_code == 200, assigned.text
        config = admin.get('/api/v1/decision-settings').json()['settings']
        response = admin.put('/api/v1/decision-settings', headers=ah, json=config | {'mode': 'semantic'})
        assert response.status_code == 200, response.text
        config = response.json()
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        first = {'request_id': str(uuid4()), 'revision': 1, 'content': 'PRIVATE_CONTEXT', 'capability': 'chat.general'}
        assert user.post(path+'/turns', headers=uh, json=first).status_code == 202
        result = wait_finished(user, path)
        turn = {'request_id': str(uuid4()), 'revision': result['revision'], 'content': 'Could that routine handle empty input too?'}
        response = user.post(path+'/turns', headers=uh, json=turn)
        assert response.status_code == 202, response.text
        result = wait_finished(user, path)
        assert result['runs'][-1]['route_receipt']['capability_id'] == 'code.implement'
        assert classified[-1]['recent_context_as_data'] == 'PRIVATE_CONTEXT'
        assert user.post(path+'/turns', headers=uh, json=turn).status_code == 202
        assert len(classified) == 1

        channel = '/api/v1/channels/' + user.post('/api/v1/channels', headers=uh, json={'name': 'Routing fixture'}).json()['id']
        assert user.post(channel+'/messages', headers=uh, json={'request_id': str(uuid4()), 'content': 'CHANNEL_CONTEXT'}).status_code == 201
        mention = {'request_id': str(uuid4()), 'content': '@hearth Could that routine handle empty input too?'}
        response = user.post(channel+'/messages', headers=uh, json=mention)
        assert response.status_code == 201, response.text
        for _ in range(500):
            messages = user.get(channel).json()['messages']
            if messages[-1]['status'] == 'completed':
                break
            time.sleep(.01)
        assert messages[-1]['content'] == 'One code response'
        assert classified[-1]['recent_context_as_data'] == 'CHANNEL_CONTEXT'
        assert user.post(channel+'/messages', headers=uh, json=mention).status_code == 201
        assert len(classified) == 2
        saved = key(user, settings, allow_tools=False)
        auth = {'Authorization': 'Bearer '+saved['key']}
        data = {'model': 'auto', 'messages': [{'role': 'user', 'content': 'CLIENT_CONTEXT'}, {'role': 'assistant', 'content': 'Ready'}, {'role': 'user', 'content': turn['content']}]}
        response = user.post('/v1/chat/completions', headers=auth, json=data)
        assert response.status_code == 200, response.text
        assert response.headers['x-hearth-capability'] == 'code.implement'
        assert classified[-1]['recent_context_as_data'] == 'CLIENT_CONTEXT'
        assert len(dispatched) == 4
        restricted = key(user, settings, capabilities=['chat.general'], allow_tools=False)
        assert user.post('/v1/chat/completions', headers={'Authorization': 'Bearer '+restricted['key']}, json=data).status_code == 403
        assert len(dispatched) == 4  # A model suggestion cannot widen a key's grants.
        assert user.post('/v1/chat/completions', headers=auth, json={'model': 'auto', 'messages': [{'role': 'user', 'content': 'x'*6500}]}).status_code == 409

        def unavailable(*a, **kw):
            raise ProviderError('fixture outage', provider_fault=False)
        monkeypatch.setattr(decision_transport, 'evaluate', unavailable)
        assert user.post('/v1/chat/completions', headers=auth, json=data).status_code == 503
        assert user.post('/v1/chat/completions', headers=auth, json=data | {'model': 'code.implement'}).status_code == 200
        # Direct media still takes its deterministic path despite classifier outage.
        owner = UUID(user.get('/api/v1/session').json()['id'])
        with scoped_session(app, owner, settings.farm_id) as db:
            principal = Principal(owner, settings.farm_id, permissions_for(db, owner, settings.farm_id), 1)
        direct = route_decisions.prepare(app, settings, principal, 'Generate an image of a red truck')
        assert direct.capability == 'image.generate'
        response = admin.put('/api/v1/decision-settings', headers=ah, json=config | {'mode': 'shadow'})
        assert response.status_code == 200
        monkeypatch.setattr(decision_transport, 'evaluate', classify)
        response = user.post('/v1/chat/completions', headers=auth, json=data)
        assert response.status_code == 200, response.text
        assert response.headers['x-hearth-capability'] == 'chat.general'
        for _ in range(300):
            with scoped_session(app, owner, settings.farm_id) as db:
                observations = db.execute(text('SELECT metadata FROM decision_observations')).scalars().all()
            if observations:
                break
            time.sleep(.01)
        assert len(dispatched) == 6  # Only primary replies, never shadow inference.
        assert observations[-1]['proposed'] == 'code.implement'
        assert 'CLIENT_CONTEXT' not in json.dumps(observations)
