import hashlib
import json
from uuid import uuid4

from hearth import image_queue, image_transport, workers
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import INFO, MODEL, image_target, receipt
from tests.integration.test_postgres import databases as databases


def adopt(migration, settings, target, *, paused=True):
    node, token = uuid4(), "b" * 64
    with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
        row = (
            db.execute(
                text("SELECT connection_id,resource_pool_id FROM inference_targets WHERE id=:id"),
                {"id": target},
            )
            .mappings()
            .one()
        )
        db.execute(
            text(
                "INSERT INTO managed_workers(id,farm_id,name,pool_id,token_hash,recipe_digest,services,desired_service,paused) VALUES(:id,:farm,'Worker fixture',:pool,:token,:digest,CAST(:services AS jsonb),'fooocus',:paused)"
            ),
            {
                "id": node,
                "farm": settings.farm_id,
                "pool": row["resource_pool_id"],
                "token": hashlib.sha256(token.encode()).hexdigest(),
                "digest": "a" * 64,
                "services": json.dumps(
                    {"fooocus": {"name": "Fooocus", "connection_id": str(row["connection_id"])}}
                ),
                "paused": paused,
            },
        )
    return node, token, row["resource_pool_id"]


def fixture_provider(monkeypatch):
    monkeypatch.setattr(image_transport, "information", lambda *args: INFO)
    monkeypatch.setattr(
        image_transport,
        "render",
        lambda url, key, config, data, observe=lambda value: False: (receipt(data), b"fixture PNG"),
    )


def report(sequence=1, **updates):
    return {
        "boot_id": str(uuid4()),
        "sequence": sequence,
        "recipe_digest": "a" * 64,
        "observed_revision": 1,
        "ready_service": "fooocus",
        "state": "ready",
        "reason": "",
        **updates,
    }


def request(target, seed=1):
    return {
        "target_id": target,
        "request": {"id": str(uuid4()), "model": MODEL, "prompt": "Queue fixture", "seed": seed},
    }


def test_worker_authentication_revision_fences_and_admin_scope(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    with factory("admin") as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = image_target(admin, ah)
        node, token, pool = adopt(migration, settings, target)
        escaped = admin.post('/api/v1/providers', headers=ah, json={'name': 'Image fixture', 'base_url': 'http://127.0.0.1:1235', 'model_id': 'another', 'api_key': 'fixture-controller', 'protocol': 'hearth.image.v1', 'local_only': True, 'resource_pool': 'Unrelated GPU'})
        assert escaped.status_code == 409
        path = f"/api/v1/worker-control/{node}/poll"
        data = report()
        assert admin.post(path, json=data).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        assert user.post(path, json=data, headers=headers).status_code == 401
        assert (
            admin.post(path, json=data, headers=headers | {"Origin": settings.admin_origin}).status_code
            == 401
        )
        assert admin.post(path, json=data, headers=headers).status_code == 200
        assert admin.post(path, json=data, headers=headers).status_code == 409
        assert admin.post(path, json=report(2), headers=headers).status_code == 409  # Competing boot.
        assert (
            admin.post(
                path, json=data | {"sequence": 2, "recipe_digest": "c" * 64}, headers=headers
            ).status_code
            == 409
        )
        listing = admin.get("/api/v1/workers")
        assert token not in listing.text and "token_hash" not in listing.text
        assert listing.json()["items"][0]["online"] is True
        signin(user)
        assert user.get("/api/v1/workers").status_code == 403
        assert (
            admin.put(
                f"/api/v1/workers/{node}",
                json={"revision": 1, "paused": False, "policy": "resident", "desired_service": "fooocus"},
            ).status_code
            == 403
        )
        assert (
            admin.put(
                f"/api/v1/workers/{node}",
                headers=ah,
                json={"revision": 1, "paused": False, "policy": "resident", "desired_service": "fooocus"},
            ).status_code
            == 200
        )
        with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
            worker = workers.for_pool(db, pool)
            assert not workers.ready(worker, next(iter(worker["services"].values()))["connection_id"])
        assert (
            admin.post(path, headers=headers, json=data | {"sequence": 2, "observed_revision": 2}).status_code
            == 200
        )
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            db.execute(text("UPDATE managed_workers SET revoked=true WHERE id=:id"), {"id": node})
        assert admin.post(path, headers=headers, json=data | {"sequence": 3}).status_code == 401


def test_durable_queue_cancel_quota_and_restart_resume(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, "run", lambda self: self.stop.wait())
    with factory("admin") as admin:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        with factory() as user:
            signin(user)
            uh = csrf(user, settings.user_origin)
            owner = user.get("/api/v1/session").json()["id"]
            jobs = [request(target, number) for number in range(8)]
            for data in jobs:
                assert user.post("/api/v1/images", json=data, headers=uh).status_code == 202
            assert user.post("/api/v1/images", json=jobs[0], headers=uh).status_code == 202
            assert user.post("/api/v1/images", json=request(target), headers=uh).status_code == 429
            assert {j["status"] for j in user.get("/api/v1/images").json()["items"]} == {"queued"}
            assert (
                user.post("/api/v1/images/" + jobs[1]["request"]["id"] + "/cancel", headers=uh).status_code
                == 200
            )
            assert user.get("/api/v1/images").json()["items"][6]["status"] == "cancelled"
        with factory() as reopened:
            signin(reopened)
            assert len(reopened.get("/api/v1/images").json()["items"]) == 8
            with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
                pool = db.execute(
                    text("SELECT resource_pool_id FROM inference_targets WHERE id=:id"), {"id": target}
                ).scalar_one()
            first = image_queue.claim(app, settings, pool)
            assert first and str(first[2].id) == jobs[0]["request"]["id"]
            assert image_queue.claim(app, settings, pool) is None  # Shared GPU is reserved.
            image_queue.execute_queued(app, settings, *first)
            assert (
                next(
                    j
                    for j in reopened.get("/api/v1/images").json()["items"]
                    if j["id"] == jobs[0]["request"]["id"]
                )["status"]
                == "completed"
            )
            with scoped_session(app, uuid4(), settings.farm_id) as db:
                assert db.execute(text("SELECT count(*) FROM image_jobs")).scalar_one() == 0
            with scoped_session(app, owner, uuid4()) as db:
                assert db.execute(text("SELECT count(*) FROM image_queue")).scalar_one() == 0


def test_queue_waits_for_worker_and_fences_uncertain_execution(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, "run", lambda self: self.stop.wait())
    with factory("admin") as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = image_target(admin, ah)
        node, token, pool = adopt(migration, settings, target)
        signin(user)
        uh = csrf(user, settings.user_origin)
        job = request(target)
        assert user.post("/api/v1/images", json=job, headers=uh).status_code == 202
        assert image_queue.claim(app, settings, pool) is None  # Paused/offline.
        data = report()
        headers = {"Authorization": "Bearer " + token}
        assert (
            admin.post(f"/api/v1/worker-control/{node}/poll", headers=headers, json=data).status_code == 200
        )
        assert image_queue.claim(app, settings, pool) is None  # Still paused.
        assert (
            admin.put(
                f"/api/v1/workers/{node}",
                headers=ah,
                json={"revision": 1, "paused": False, "policy": "shared", "desired_service": "fooocus"},
            ).status_code
            == 200
        )
        admitted = image_queue.claim(app, settings, pool)
        assert admitted
        assert (
            admin.put(
                f"/api/v1/workers/{node}",
                headers=ah,
                json={"revision": 2, "paused": True, "policy": "shared", "desired_service": None},
            ).status_code
            == 409
        )
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            db.execute(
                text(
                    "UPDATE provider_pools SET lease_until=now()-interval '1 second',execution_state='unknown' WHERE id=:id"
                ),
                {"id": pool},
            )
        assert user.get("/api/v1/images").json()["items"][0]["status"] == "interrupted"
        assert image_queue.claim(app, settings, pool) is None
        with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
            assert (
                str(
                    db.execute(
                        text("SELECT active_run_id FROM provider_pools WHERE id=:id"), {"id": pool}
                    ).scalar_one()
                )
                == job["request"]["id"]
            )
