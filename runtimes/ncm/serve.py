"""Fixed local XSum service; expose LAN access only through hearth's TLS connector."""
import argparse
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

MODEL = 'hazyresearch/ncm-xsum'
REVISION = 'c70274273f489abc73832b2b98584a8483b6b203'


def handler(engine, key, device):
    slot = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log private source text or credentials.

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def reply(self, status, body):
            encoded = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(encoded)

        def authenticated(self):
            if self.headers.get('Origin') or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+key):
                self.reply(401, {'error': 'authentication_required'})
                return False
            return True

        def do_GET(self):
            if not self.authenticated():
                return
            if self.path == '/v1/models':
                self.reply(200, {'object': 'list', 'data': [{'id': MODEL, 'object': 'model', 'owned_by': 'hazyresearch'}]})
            elif self.path == '/v1/ncm-provider':
                self.reply(200, {'protocol': 'hearth.summary.v1', 'model': MODEL, 'revision': REVISION,
                                 'task': 'xsum', 'input_tokens': 512, 'output_tokens': 48,
                                 'device': device, 'chat': False, 'tools': False, 'streaming': False})
            else:
                self.reply(404, {'error': 'unsupported_operation'})

        def do_POST(self):
            if not self.authenticated():
                return
            if self.path != '/v1/summaries':
                self.reply(404, {'error': 'XSum is a summarization specialist, not a chat model.'})
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if self.headers.get('Transfer-Encoding') or not 0 < length <= 65536:
                    self.reply(413, {'error': 'bounded_content_length_required'})
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {'id', 'model', 'text'} or body['model'] != MODEL:
                    raise ValueError('Use id, model and text only.')
                UUID(body['id'])
                if not isinstance(body['text'], str) or not body['text'].strip():
                    raise ValueError('Supply the article text.')
            except (ValueError, TypeError, KeyError):
                self.reply(400, {'error': 'invalid_summary_request'})
                return
            if not slot.acquire(blocking=False):
                self.reply(503, {'error': 'NCM is busy. No second generation was started.'})
                return
            started = time.monotonic()
            try:
                result = engine.summarize(body['text'])
                result.update(id=body['id'], model=MODEL, revision=REVISION, elapsed_seconds=round(time.monotonic()-started, 3))
                self.reply(200, result)
            except ValueError as exc:
                self.reply(422, {'error': str(exc)})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass  # Generation has completed before freeing the slot.
            except Exception:
                self.reply(500, {'error': 'NCM inference failed.'})
            finally:
                slot.release()
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--port', type=int, default=1242)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    key = args.key_file.read_text().strip()
    if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise SystemExit('Invalid provider key file.')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from model import XSum
    engine = XSum(args.root, args.device, args.threads)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(engine, key, args.device)).serve_forever()


if __name__ == '__main__':
    main()
