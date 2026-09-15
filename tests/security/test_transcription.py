import base64
import hashlib
import io
import math
import struct
import threading
import time
import wave
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from hearth import speech_transport, transcription_transport
from hearth.config import Settings
from hearth.contracts import TranscriptionReceipt, TranscriptionRequest
from hearth.inference import ProviderError
from hearth.middleware import request_body_limit
from hearth.transcription_audio import normalize
from hearth.transcription_probe import word_error_rate

from runtimes.transcription.hearth_transcription import MODEL, Cancelled, create_app


def wav_fixture(rate=16000, channels=1, seconds=1, silent=False):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(
            b"".join(
                struct.pack("<h", 0 if silent else int(10000 * math.sin(2 * math.pi * 220 * n / rate)))
                * channels
                for n in range(int(rate * seconds))
            )
        )
    return output.getvalue()


@pytest.mark.parametrize(
    "rate,channels", [(8000, 1), (16000, 1), (24000, 1), (32000, 2), (44100, 2), (48000, 2)]
)
def test_normalized_input_strips_container_metadata_and_bounds_frames(rate, channels):
    normalized = normalize(wav_fixture(rate, channels))
    assert normalize(normalized) == normalized
    with wave.open(io.BytesIO(normalized)) as wav:
        assert wav.getnchannels() == 1 and wav.getframerate() == 16000
        assert 15998 <= wav.getnframes() <= 16000


def test_audio_rejects_malformed_silent_short_long_and_large_input():
    raw = wav_fixture()
    long = bytearray(wav_fixture(seconds=121))
    for value in [
        raw[:-2],
        raw + b"junk",
        b"https://untrusted/audio.wav",
        wav_fixture(silent=True),
        wav_fixture(seconds=0.2),
        bytes(long),
        b"x" * 8_388_609,
        wav_fixture(rate=11025),
    ]:
        with pytest.raises(ValueError):
            normalize(value)
    assert request_body_limit("/api/v1/chats/" + str(uuid4()) + "/transcriptions", "POST") == 8_388_608
    assert request_body_limit("/api/v1/chats/" + str(uuid4()) + "/transcriptions", "GET") == 1_048_576
    assert word_error_rate("Turn left at the gate.", "Turn LEFT at the gate!") == 0
    assert word_error_rate("one two three four", "one six three four") == 0.25


@pytest.mark.parametrize(
    "fault", ["none", "wrong_id", "wrong_model", "wrong_audio", "empty", "unreleased", "lost", "inconsistent"]
)
def test_receipt_binding_and_unknown_execution(monkeypatch, fault):
    audio = wav_fixture()
    data = TranscriptionRequest(id=uuid4(), model=MODEL, audio_sha256=hashlib.sha256(audio).hexdigest())
    receipt = TranscriptionReceipt(
        **data.model_dump(),
        state="completed",
        text="Recognized text.",
        execution_released=True,
        manifest_sha256="a" * 64,
        cancel_requested=False,
    )
    if fault == "wrong_id":
        receipt.id = uuid4()
    if fault == "wrong_model":
        receipt.model = "replacement"
    if fault == "wrong_audio":
        receipt.audio_sha256 = "b" * 64
    if fault == "empty":
        receipt.text = ""
    if fault == "unreleased":
        receipt.execution_released = False
    if fault == "inconsistent":
        receipt.state = "running"

    def handler(request):
        if fault == "lost":
            if request.method == "POST":
                return httpx.Response(
                    202,
                    json=receipt.model_copy(
                        update={"state": "running", "execution_released": False}
                    ).model_dump(mode="json"),
                )
            raise httpx.ReadError("Fixture lost connection")
        return httpx.Response(202, json=receipt.model_dump(mode="json"))

    @contextmanager
    def client(*args):
        with httpx.Client(base_url="http://fixture/v1/", transport=httpx.MockTransport(handler)) as transport:
            yield transport, {}

    monkeypatch.setattr(speech_transport, "client_for", client)
    if fault == "none":
        assert (
            transcription_transport.transcribe("http://fixture", "", Settings(mode="test"), data, audio).text
            == receipt.text
        )
    else:
        with pytest.raises(ProviderError) as exc:
            transcription_transport.transcribe("http://fixture", "", Settings(mode="test"), data, audio)
        assert exc.value.uncertain is (fault != "empty")


@pytest.mark.parametrize("cancel", [False, True])
def test_runtime_authentication_idempotency_cancellation_raw_audio_cleanup_and_restart(tmp_path, cancel):
    class Engine:
        def __init__(self):
            self.calls = 0
            self.entered, self.finish = threading.Event(), threading.Event()

        def transcribe(self, audio, stopped):
            self.calls += 1
            assert normalize(audio) == audio
            self.entered.set()
            assert self.finish.wait(10)
            if stopped():
                raise Cancelled()
            return "A private transcript."

    engine, token = Engine(), "explicit-runtime-fixture-controller-key"
    raw = wav_fixture()
    body = {
        "id": str(uuid4()),
        "model": MODEL,
        "audio_sha256": hashlib.sha256(raw).hexdigest(),
        "audio_b64": base64.b64encode(raw).decode(),
    }
    with TestClient(create_app(tmp_path, token, engine=engine, digest="a" * 64)) as client:
        assert client.get("/v1/transcription-provider").status_code == 401
        client.headers["Authorization"] = "Bearer " + token
        assert (
            client.get("/v1/transcription-provider", headers={"Origin": "https://untrusted"}).status_code
            == 401
        )
        assert client.get("/v1/transcription-provider", headers={"Host": "untrusted"}).status_code == 400
        assert client.post("/v1/transcription-jobs", content=b"x" * 5_121_025).status_code == 413
        assert client.post("/v1/transcription-jobs", json=body | {"is_admin": True}).status_code == 422
        assert (
            client.post("/v1/transcription-jobs", json=body | {"audio_sha256": "0" * 64}).status_code == 400
        )
        path = "/v1/transcription-jobs/" + body["id"]
        try:
            assert client.post("/v1/transcription-jobs", json=body).status_code == 202
            assert engine.entered.wait(3)
            assert client.post("/v1/transcription-jobs", json=body).status_code == 202
            assert client.post("/v1/transcription-jobs", json=body | {"id": str(uuid4())}).status_code == 409
            if cancel:
                assert client.post(path + "/cancel").json()["cancel_requested"]
                assert not client.get(path).json()["execution_released"]
        finally:
            engine.finish.set()
        for _ in range(200):
            result = client.get(path).json()
            if result["execution_released"]:
                break
            time.sleep(0.01)
        assert result["state"] == ("cancelled" if cancel else "completed")
        assert result["text"] == ("" if cancel else "A private transcript.")
        assert not list(tmp_path.glob("*.wav")) and engine.calls == 1
    replacement = Engine()
    with TestClient(create_app(tmp_path, token, engine=replacement, digest="a" * 64)) as client:
        client.headers["Authorization"] = "Bearer " + token
        assert client.post("/v1/transcription-jobs", json=body).json()["state"] == result["state"]
        assert replacement.calls == 0
