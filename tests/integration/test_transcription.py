import hashlib
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, identity, providers, transcription_probe, transcription_transport
from hearth.contracts import TranscriptionProviderInfo, TranscriptionReceipt
from hearth.database import scoped_session
from hearth.inference import ProviderError
from sqlalchemy import text

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases
from tests.security.test_transcription import wav_fixture

MODEL = "faster-whisper-small.en"


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_provider_probe_allows_reasoning_then_requires_a_complete_answer(bff, monkeypatch, finish):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    def reasoning_stream(*args, maximum_tokens, **kwargs):
        if maximum_tokens < 768:
            raise ProviderError('The model returned no answer. Check the model and output limit.')
        yield 'heartbeat', ''
        yield 'text', 'hearth is ready.'
        yield 'done', finish
    monkeypatch.setattr(providers, 'chat_stream', reasoning_stream)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Reasoning specialist', 'model_id': 'fixture', 'base_url': 'http://127.0.0.1:1234', 'local_only': True}).json()
        result = admin.post('/api/v1/providers/'+target['id']+'/probe', headers=ah, json={'revision': 1}).json()
        assert result['state'] == ('ready' if finish == 'stop' else 'failed')


def fixture_provider(monkeypatch, bad=False):
    info = TranscriptionProviderInfo(
        protocol="hearth.transcription.v1",
        model=MODEL,
        model_revision="fixture",
        manifest_sha256="a" * 64,
        languages=["en"],
        job_cancellation=True,
        offline=True,
    )
    monkeypatch.setattr(transcription_transport, "information", lambda *a: info)

    def transcribe(url, key, settings, data, audio, observe=lambda value: False):
        assert hashlib.sha256(audio).hexdigest() == data.audio_sha256
        result = receipt(data, text="Wrong words entirely." if bad else transcription_probe.REFERENCE)
        observe(result)
        return result

    monkeypatch.setattr(transcription_transport, "transcribe", transcribe)


def receipt(data, text="Take the red road home."):
    return TranscriptionReceipt(
        **data.model_dump(),
        state="completed",
        text=text,
        execution_released=True,
        manifest_sha256="a" * 64,
        cancel_requested=False,
    )


def configure_transcription(admin, headers, key=""):
    response = admin.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "name": "Transcription CPU",
            "base_url": "http://127.0.0.1:1237",
            "model_id": MODEL,
            "protocol": "hearth.transcription.v1",
            "resource_pool": "Transcription CPU fixture",
            "local_only": True,
            "api_key": key,
        },
    )
    assert response.status_code == 201, response.text
    target = response.json()["id"]
    result = admin.post("/api/v1/providers/" + target + "/probe", headers=headers, json={"revision": 1})
    assert result.json()["state"] == "ready", result.text
    assert result.json()["features"] == ["audio.transcribe", "audio.jobs"]
    assert assign(admin, headers, "audio.transcribe", [target]).status_code == 200
    return target


def new_chat(user, headers):
    response = user.post("/api/v1/chats", json={}, headers=headers)
    assert response.status_code == 201
    return "/api/v1/chats/" + response.json()["id"]


def wait_transcript(user, path, timeout=10):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        rows = user.get(path + "/transcriptions").json()["items"]
        if rows and rows[0]["status"] != "running":
            return rows[0]
        time.sleep(0.03)
    pytest.fail("Transcription did not settle.")


def test_private_review_does_not_send_raw_audio_or_transcript_to_chat_and_restores(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    with factory("admin") as admin, factory() as user, factory() as other:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure_transcription(admin, ah)
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = new_chat(user, uh)
        data, ident = wav_fixture(), str(uuid4())
        url = path + "/transcriptions?request_id=" + ident
        assert user.post(url, content=data).status_code == 403
        assert user.post(url, content=b"https://untrusted/audio.wav", headers=uh).status_code == 422
        assert user.post(url, content=data, headers=uh).status_code == 202
        result = wait_transcript(user, path)
        assert result["status"] == "completed" and result["transcript"] == transcription_probe.REFERENCE
        assert user.get(path).json()["messages"] == []
        assert user.post(url, content=data, headers=uh).json()["id"] == ident
        assert user.post(url, content=wav_fixture(seconds=2), headers=uh).status_code == 409
        with scoped_session(app, user.get("/api/v1/session").json()["id"], settings.farm_id) as db:
            row = (
                db.execute(
                    text("SELECT audio,route_receipt FROM transcription_jobs WHERE id=:id"), {"id": ident}
                )
                .mappings()
                .one()
            )
            assert row["audio"] is None and row["route_receipt"]["target_id"] == target
            db.execute(text("UPDATE inference_targets SET model_id='renamed' WHERE id=:id"), {"id": target})
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path + "/transcriptions").json()["items"] == [result]
        another = new_chat(user, uh)
        assert (
            user.post(another + "/transcriptions?request_id=" + ident, content=data, headers=uh).status_code
            == 409
        )
        assert user.delete(another + "/transcriptions/" + ident, headers=uh).status_code == 404
        subject = str(uuid4())
        old_verify, old_token = identity.verify_id_token, identity.token_request
        monkeypatch.setattr(identity, "verify_id_token", lambda *a: {"sub": subject, "name": "Other member"})
        monkeypatch.setattr(
            identity,
            "token_request",
            lambda config, endpoint, data: (
                {"active": True, "sub": subject, "iss": config.issuer}
                if endpoint == "token/introspect"
                else {
                    "id_token": "OTHER FIXTURE",
                    "access_token": "OTHER FIXTURE",
                    "refresh_token": "OTHER FIXTURE",
                    "expires_in": 300,
                }
            ),
        )
        signin(other)
        from tests.integration.test_identity import approve_fixture_member
        approve_fixture_member(other, migration, settings)
        oh = csrf(other, settings.user_origin)
        assert other.get(path + "/transcriptions").status_code == 404
        assert other.post(url, content=data, headers=oh).status_code == 404
        with scoped_session(app, other.get("/api/v1/session").json()["id"], settings.farm_id) as db:
            assert db.execute(text("SELECT count(*) FROM transcription_jobs")).scalar_one() == 0
        # Existing user's live token fixture must be restored before another mutation.
        monkeypatch.setattr(identity, "verify_id_token", old_verify)
        monkeypatch.setattr(identity, "token_request", old_token)
        # The session remains sufficient for this CSRF-protected local draft removal.
        assert user.delete(path + "/transcriptions/" + ident, headers=uh).status_code == 200
        assert user.get(path + "/transcriptions").json()["items"] == []


@pytest.mark.parametrize("ending", ["cancel", "revoke", "archive", "manifest", "disconnect"])
def test_cancel_revoke_archive_and_unknown_execution_preserve_pool_boundaries(bff, monkeypatch, ending):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(
        chat, "chat_stream", lambda *a, **kw: iter([("text", "Independent text model."), ("done", "stop")])
    )
    entered, finish = threading.Event(), threading.Event()

    def transcribe(url, key, settings, data, audio, observe):
        entered.set()
        assert finish.wait(10)
        if ending == "disconnect":
            raise ProviderError("Fixture receipt lost.", uncertain=True)
        result = receipt(data)
        if ending == "manifest":
            result.manifest_sha256 = "b" * 64
        observe(result)
        return result

    with factory("admin") as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        target = configure_transcription(admin, ah)
        monkeypatch.setattr(transcription_transport, "transcribe", transcribe)
        signin(user)
        uh = csrf(user, settings.user_origin)
        uid = user.get("/api/v1/session").json()["id"]
        path, ident = new_chat(user, uh), str(uuid4())
        try:
            assert (
                user.post(
                    path + "/transcriptions?request_id=" + ident, content=wav_fixture(), headers=uh
                ).status_code
                == 202
            )
            assert entered.wait(3)
            assert user.delete(path + "/transcriptions/" + ident, headers=uh).status_code == 409
            other = new_chat(user, uh)
            assert (
                user.post(
                    other + "/transcriptions?request_id=" + str(uuid4()), content=wav_fixture(), headers=uh
                ).status_code
                == 409
            )
            assert (
                user.post(
                    other + "/turns",
                    headers=uh,
                    json={"request_id": str(uuid4()), "revision": 1, "content": "Hello"},
                ).status_code
                == 202
            )
            assert wait_finished(user, other)["messages"][-1]["content"] == "Independent text model."
            if ending == "cancel":
                assert user.post(path + "/transcriptions/" + ident + "/cancel", headers=uh).status_code == 200
            if ending == "archive":
                assert user.delete(path, headers=uh).status_code == 200
            if ending == "revoke":
                with migration.begin() as db:
                    db.execute(
                        text("DELETE FROM browser_sessions WHERE farm_id=:farm AND audience='user'"),
                        {"farm": settings.farm_id},
                    )
        finally:
            finish.set()
        for _ in range(200):
            with scoped_session(app, uid, settings.farm_id) as db:
                result = (
                    db.execute(
                        text("SELECT status,transcript,audio FROM transcription_jobs WHERE id=:id"),
                        {"id": ident},
                    )
                    .mappings()
                    .one()
                )
            if result["status"] != "running":
                break
            time.sleep(0.03)
        assert result["status"] == ("interrupted" if ending == "disconnect" else "cancelled")
        assert result["transcript"] == "" and result["audio"] is None
        item = next(row for row in admin.get("/api/v1/providers").json()["items"] if row["id"] == target)
        assert item["execution_state"] == ("unknown" if ending == "disconnect" else "idle")


def test_known_recording_probe_rejects_wrong_transcription(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch, bad=True)
    with factory("admin") as admin:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        created = admin.post(
            "/api/v1/providers",
            headers=ah,
            json={
                "name": "Wrong recognizer",
                "model_id": MODEL,
                "protocol": "hearth.transcription.v1",
                "base_url": "http://127.0.0.1:1237",
                "local_only": True,
            },
        ).json()
        result = admin.post(
            "/api/v1/providers/" + created["id"] + "/probe", headers=ah, json={"revision": 1}
        ).json()
        assert result["state"] == "failed" and result["features"] == []


@pytest.mark.skipif(
    os.environ.get("HEARTH_LIVE_TRANSCRIPTION") != "1",
    reason="Explicit running local CPU transcription provider required.",
)
def test_live_cpu_transcription_upload_and_restore(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    with factory("admin") as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure_transcription(
            admin,
            ah,
            Path(".hearth/transcription-provider/controller.key").read_text(encoding="utf-8").strip(),
        )
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = new_chat(user, uh)
        source = Path("evidence/voice/2026-09-13/hearth-speech-sample.wav").read_bytes()
        reference = "Welcome home. Your hearth can bring your models together, while your conversations stay on your own machines."
        start = time.monotonic()
        sent = user.post(path + "/transcriptions?request_id=" + str(uuid4()), content=source, headers=uh)
        assert sent.status_code == 202, sent.text
        result = wait_transcript(user, path, timeout=90)
        assert result["status"] == "completed", result
        wer = transcription_probe.word_error_rate(reference, result["transcript"])
        assert wer <= 0.25, result
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path + "/transcriptions").json()["items"] == [result]
            assert fresh.get(path).json()["messages"] == []
        out = Path("evidence/transcription/2026-09-13")
        out.mkdir(parents=True, exist_ok=True)
        (out / "live-transcription.json").write_text(
            json.dumps(
                {
                    "scope": "Real CPU Whisper, authenticated provider job transport and restricted PostgreSQL/BFF; OIDC fixtures in a disposable farm; synthetic English source recording different from the provider probe.",
                    "model": MODEL,
                    "reference": reference,
                    "recognized": result["transcript"],
                    "word_error_rate": wer,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "source_sha256": hashlib.sha256(source).hexdigest(),
                    "restored": True,
                    "chat_messages_created": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
