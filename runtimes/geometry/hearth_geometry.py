"""Private image-to-GLB jobs around a pinned TRELLIS CLI. Linux only."""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import hmac
import io
import json
import os
import signal
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from hearth.contracts import GeometryGeneration
from hearth.geometry_validation import validate_glb


class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request: GeometryGeneration
    image: str = Field(max_length=12_000_000)


class Jobs:
    def __init__(self, root, installation):
        self.root, self.installation = root, installation
        root.mkdir(parents=True, exist_ok=True)
        self.lock = (root / 'process.lock').open('a+b')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw = (installation / 'inventory.json').read_bytes()
        self.inventory, self.digest = json.loads(raw), hashlib.sha256(raw).hexdigest()
        for entry in json.loads((installation / 'engine-inventory.json').read_text()):
            path = (installation / 'engine' / entry['path']).resolve()
            if not path.is_relative_to((installation / 'engine').resolve()):
                raise RuntimeError('Invalid engine closure path.')
            with path.open('rb') as source:
                if path.stat().st_size != entry['bytes'] or hashlib.file_digest(source, 'sha256').hexdigest() != entry['sha256']:
                    raise RuntimeError('The approved engine inventory changed.')
        for entry in self.inventory['files']:
            path = installation / 'models' / entry['path']
            with path.open('rb') as source:
                if path.stat().st_size != entry['bytes'] or hashlib.file_digest(source, 'sha256').hexdigest() != entry['sha256']:
                    raise RuntimeError('The approved model inventory changed.')
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.mutex = threading.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL, cancel INTEGER NOT NULL DEFAULT 0, digest TEXT, reason TEXT, released INTEGER NOT NULL DEFAULT 0)')
            # systemd KillMode=control-group and ExitType=cgroup are required.
            # The next service starts only after the previous child scope is gone.
            db.execute("UPDATE jobs SET state='interrupted',reason='The geometry service restarted.',released=1 WHERE state IN ('queued','running')")

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.root / 'jobs.sqlite', timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, identifier):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (str(identifier),)).fetchone()
        if not row:
            raise HTTPException(404, 'This geometry job is unavailable.')
        return json.loads(row['request']) | {'state': row['state'], 'progress': 100 if row['state'] == 'completed' else 0,
            'sha256': row['digest'], 'reason': row['reason'], 'execution_released': bool(row['released']),
            'cancel_requested': bool(row['cancel']), 'manifest_sha256': self.digest}

    def submit(self, submission):
        data = submission.request
        if data.model != self.inventory['model']:
            raise HTTPException(404, 'This model is not installed.')
        try:
            raw = base64.b64decode(submission.image, validate=True)
            if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != data.image_sha256:
                raise ValueError()
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'PNG', 'JPEG'} or max(image.size) > 1600 or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError()
                image.verify()
        except Exception:
            raise HTTPException(422, 'Supply one normalized image with a matching digest.') from None
        with self.mutex, self.db() as db:
            previous = db.execute('SELECT request FROM jobs WHERE id=?', (str(data.id),)).fetchone()
            if previous:
                if previous['request'] != data.model_dump_json():
                    raise HTTPException(409, 'This job identifier was already used.')
            else:
                if db.execute("SELECT 1 FROM jobs WHERE released=0").fetchone():
                    raise HTTPException(409, 'This GPU is occupied.')
                if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 1000:
                    raise HTTPException(409, 'The geometry job storage limit was reached.')
                (self.root / f'{data.id}.jpg').write_bytes(raw)
                db.execute("INSERT INTO jobs(id,request,state) VALUES(?,?,'queued')", (str(data.id), data.model_dump_json()))
                db.commit()
                self.executor.submit(self.execute, data)
        return self.get(data.id)

    def execute(self, data):
        output = self.root / f'{data.id}.glb'
        image = self.root / f'{data.id}.jpg'
        state, reason, digest = 'failed', 'Geometry generation failed. Check GPU memory and the worker log.', None
        process = None
        try:
            with self.db() as db:
                db.execute("UPDATE jobs SET state='running' WHERE id=?", (str(data.id),))
            args = [str(self.installation / 'engine/trellis-cli'), str(image), str(output),
                    '--models', str(self.installation / 'models'), '--res', str(data.resolution),
                    '--seed', str(data.seed), '--require-gpu', '--webp', 'off', '--threads', '4']
            # Fixed executable and typed numeric options; no shell or user paths.
            with (self.root / f'{data.id}.log').open('wb') as log:
                process = subprocess.Popen(args, stdout=log, stderr=log, start_new_session=True,
                                           cwd=self.installation, env=os.environ | {'HF_HUB_OFFLINE': '1'})
                deadline = time.monotonic() + 1200
                while process.poll() is None:
                    if self.get(data.id)['cancel_requested'] or time.monotonic() >= deadline:
                        state, reason = ('cancelled', 'Geometry generation stopped.') if self.get(data.id)['cancel_requested'] else ('failed', 'Geometry generation exceeded twenty minutes.')
                        break
                    time.sleep(.3)
                else:
                    if process.returncode == 0:
                        validate_glb(output.read_bytes())
                        digest = hashlib.sha256(output.read_bytes()).hexdigest()
                        state, reason = 'completed', None
        except Exception:
            pass
        finally:
            if process:
                # Kill the whole isolated CLI group, then reap before issuing a
                # release receipt. A timed-out caller never implies GPU release.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            image.unlink(missing_ok=True)
            with self.mutex, self.db() as db:
                if self.get(data.id)['cancel_requested']:
                    state, reason, digest = 'cancelled', 'Geometry generation stopped.', None
                if state != 'completed':
                    output.unlink(missing_ok=True)
                db.execute('UPDATE jobs SET state=?,reason=?,digest=?,released=1 WHERE id=?', (state, reason, digest, str(data.id)))


def create_app(config):
    token = Path(config['token_file']).read_text().strip()
    if len(token) < 32:
        raise RuntimeError('A controller credential is required.')
    jobs = Jobs(Path(config['jobs']), Path(config['installation']))
    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        with jobs.db() as db:
            db.execute("UPDATE jobs SET cancel=1 WHERE released=0")
        jobs.executor.shutdown(wait=True)
        jobs.lock.close()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config['allowed_hosts'])
    @app.middleware('http')
    async def boundary(request, call_next):
        if request.client.host not in config['allowed_controllers']:
            return JSONResponse({'detail': 'Controller address denied.'}, status_code=403)
        if request.headers.get('origin') or not hmac.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + token).encode()):
            return JSONResponse({'detail': 'Controller credential required.'}, status_code=401)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 12_100_000:
                return JSONResponse({'detail': 'Request too large.'}, status_code=413)
        request._body = bytes(raw)
        return await call_next(request)
    @app.get('/v1/geometry-provider')
    def information():
        return {'schema_version': 1, 'protocol': 'hearth.geometry.v1', 'model': jobs.inventory['model'],
                'model_revision': jobs.inventory['model_revision'], 'manifest_sha256': jobs.digest,
                'offline': True, 'job_cancellation': True, 'resolutions': [512, 1024], 'output_format': 'glb'}
    @app.post('/v1/geometry-jobs', status_code=202)
    def submit(data: Submission):
        return jobs.submit(data)
    @app.get('/v1/geometry-jobs/{identifier}')
    def receipt(identifier: UUID):
        return jobs.get(identifier)
    @app.post('/v1/geometry-jobs/{identifier}/cancel')
    def cancel(identifier: UUID):
        jobs.get(identifier)
        with jobs.db() as db:
            db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND released=0", (str(identifier),))
        return jobs.get(identifier)
    @app.get('/v1/geometry-jobs/{identifier}/model')
    def model(identifier: UUID):
        if jobs.get(identifier)['state'] != 'completed':
            raise HTTPException(404, 'This geometry is not completed.')
        return FileResponse(jobs.root / f'{identifier}.glb', media_type='model/gltf-binary', headers={'Cache-Control': 'no-store'})
    return app


def main():
    import uvicorn
    from http.server import BaseHTTPRequestHandler, HTTPServer
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    app = create_app(config)
    token = Path(config['token_file']).read_text().strip()
    class Health(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/v1/geometry-provider' or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send_error(403)
                return
            raw = b'{"protocol":"hearth.geometry.v1"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args):
            pass
    health = HTTPServer(('127.0.0.1', config['health_port']), Health)
    threading.Thread(target=health.serve_forever, daemon=True).start()
    uvicorn.run(app, host=config['listen'], port=config['port'], proxy_headers=False,
                ssl_keyfile=config.get('tls_key'), ssl_certfile=config.get('tls_cert'), access_log=False)
    health.shutdown()


if __name__ == '__main__':
    main()
