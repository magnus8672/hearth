"""Real socket regressions for silent model startup, without a model or database."""
import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from hearth import inference
from hearth.config import Settings
from hearth.inference import ProviderError, chat_stream

from tests.security.test_inference import event, transport


@contextmanager
def silent_model(delay):
    stopped = threading.Event()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.flush()
            if stopped.wait(delay):
                return
            try:
                self.wfile.write((event({'content': 'ready'}, 'stop')+'data: [DONE]\n\n').encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', requests
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_silent_start_can_outlast_thirty_seconds():
    # This reproduces the observed Continue -> hearth -> LM Studio failure:
    # headers arrive, but the model has not produced any SSE bytes at 30 seconds.
    with silent_model(31) as (url, requests):
        started = time.monotonic()
        result = list(chat_stream(url, '', 'fixture', [], Settings(mode='test', chat_timeout_seconds=40)))
        assert result == [('text', 'ready'), ('done', 'stop')]
        assert 31 <= time.monotonic()-started < 40
        assert len(requests) == 1


def test_silent_model_still_times_out_without_success_or_retry():
    # Shorten the configured budget only inside this fixture.
    settings = Settings(mode='test').model_copy(update={'chat_timeout_seconds': .2})
    with silent_model(2) as (url, requests):
        started = time.monotonic()
        with pytest.raises(ProviderError, match='did not send response data') as caught:
            list(chat_stream(url, '', 'fixture', [], settings))
        assert caught.value.uncertain
        assert time.monotonic()-started < 1.5
        assert len(requests) == 1


def test_probe_retains_three_minute_elapsed_bound(monkeypatch):
    from types import SimpleNamespace

    transport(monkeypatch, event({'content': 'too late'}, 'stop')+'data: [DONE]\n\n')
    ticks = iter([0, 181])
    monkeypatch.setattr(inference, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(ProviderError, match='time limit') as caught:
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), maximum_tokens=256))
    assert caught.value.uncertain
