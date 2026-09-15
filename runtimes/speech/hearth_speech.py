"""Development CPU speech provider. The model is loaded at startup, never per request."""
import argparse
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import socket
import sqlite3
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from hearth.audio_codec import validate_wav
from hearth.contracts import SpeechGeneration
from starlette.middleware.trustedhost import TrustedHostMiddleware

MODEL = 'kokoro-82m-v1.0-onnx'
VOICE = 'af_heart'


class Cancelled(Exception):
    pass


class KokoroCPU:
    def __init__(self, model, voices):
        os.environ['ONNX_PROVIDER'] = 'CPUExecutionProvider'
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        from kokoro_onnx import Kokoro
        self.runtime = Kokoro(str(model), str(voices))
        if self.runtime.sess.get_providers() != ['CPUExecutionProvider']:
            raise RuntimeError('This recipe requires CPU execution.')

    def generate(self, data, cancelled, output):
        import numpy as np
        # Short segments bound stop latency; cancellation never releases an active segment.
        segments, remaining = [], data.input
        while remaining:
            size = min(320, len(remaining))
            if size < len(remaining):
                split = remaining.rfind('. ', 0, size) + 1 or remaining.rfind(' ', 0, size)
                size = split if split > 0 else size
            segments.append(remaining[:size])
            remaining = remaining[size:].lstrip()
        total = 0
        with wave.open(str(output), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            for segment in segments:
                if cancelled():
                    raise Cancelled()
                samples, rate = self.runtime.create(segment, voice=data.voice, speed=1, lang='en-us')
                total += len(samples)
                if rate != 24000 or samples.ndim != 1 or not np.isfinite(samples).all() or total > 14400000:
                    raise ValueError('Unsupported audio result.')
                wav.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
        if cancelled():
            raise Cancelled()


def verify_files(model, voices):
    manifest_bytes = Path(__file__).with_name('model-manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    for name, path in [('model', model), ('voices', voices)]:
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != manifest['files'][name]['sha256'] or path.stat().st_size != manifest['files'][name]['bytes']:
            raise RuntimeError('The speech files do not match this pinned development recipe.')
    return hashlib.sha256(manifest_bytes).hexdigest()


@contextlib.contextmanager
def transaction(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


class Jobs:
    def __init__(self, root, engine, digest):
        self.root, self.engine, self.digest = root, engine, digest
        root.mkdir(parents=True, exist_ok=True)
        self.lock_file = (root/'process.lock').open('a+b')
        self.lock_file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.mutex, self.pool = threading.Lock(), ThreadPoolExecutor(max_workers=1)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL, cancel INTEGER NOT NULL DEFAULT 0, reason TEXT, digest TEXT, frames INTEGER NOT NULL DEFAULT 0)')
            db.execute("UPDATE jobs SET state='interrupted',reason='The speech process restarted. This job was not replayed.' WHERE state IN ('queued','running')")

    def db(self):
        return transaction(self.root/'jobs.sqlite')

    def get(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (str(job_id),)).fetchone()
        if not row:
            raise HTTPException(404, 'This speech job is not available.')
        data = json.loads(row['request'])
        return {'schema_version': 1, 'id': row['id'], 'model': MODEL, 'voice': data['voice'],
                'input_sha256': hashlib.sha256(data['input'].encode()).hexdigest(),
                'state': row['state'], 'reason': row['reason'], 'sha256': row['digest'], 'frames': row['frames'],
                'sample_rate': 24000, 'execution_released': row['state'] not in {'queued', 'running'},
                'manifest_sha256': self.digest, 'cancel_requested': bool(row['cancel'])}

    def submit(self, data):
        if data.model != MODEL or data.voice != VOICE or not data.input.strip():
            raise HTTPException(400, 'Choose this provider model and its verified stock voice, with nonempty text.')
        payload = data.model_dump_json()
        with self.mutex, self.db() as db:
            previous = db.execute('SELECT request FROM jobs WHERE id=?', (str(data.id),)).fetchone()
            if previous:
                if previous['request'] != payload:
                    raise HTTPException(409, 'This job identifier was already used.')
            else:
                if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running')").fetchone():
                    raise HTTPException(409, 'This speech provider is occupied.')
                if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 1000:
                    raise HTTPException(409, 'This development provider has reached its saved job limit.')
                if sum(file.stat().st_size for file in self.root.glob('*.wav')) + 33554432 > 1073741824:
                    raise HTTPException(409, 'This speech provider has reached its audio storage budget.')
                db.execute("INSERT INTO jobs(id,request,state) VALUES(?,?,'queued')", (str(data.id), payload))
                db.commit()
                self.pool.submit(self.execute, data)
        return self.get(data.id)

    def execute(self, data):
        job_id, output = str(data.id), self.root/(str(data.id)+'.wav')
        def cancelled():
            with self.db() as db:
                return bool(db.execute('SELECT cancel FROM jobs WHERE id=?', (job_id,)).fetchone()[0])
        with self.db() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
        state, reason, digest, frames = 'completed', None, None, 0
        try:
            if cancelled():
                raise Cancelled()
            self.engine.generate(data, cancelled, output)
            raw = output.read_bytes()
            frames = validate_wav(raw)
            digest = hashlib.sha256(raw).hexdigest()
        except Cancelled:
            state, reason = 'cancelled', 'Speech generation stopped.'
        except Exception:
            state, reason = 'failed', 'Speech generation failed. Check the provider environment.'
        with self.mutex, self.db() as db:
            if cancelled() and state == 'completed':
                state, reason = 'cancelled', 'Speech generation stopped.'
            if state != 'completed':
                output.unlink(missing_ok=True)
                digest, frames = None, 0
            db.execute('UPDATE jobs SET state=?,reason=?,digest=?,frames=? WHERE id=?', (state, reason, digest, frames, job_id))

    def close(self):
        self.pool.shutdown(wait=True)
        self.lock_file.close()


def create_app(root, token, *, engine, digest, hosts=None):
    if len(token) < 32:
        raise RuntimeError('A controller credential of at least 32 characters is required.')
    jobs = Jobs(root, engine, digest)
    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()
    app = FastAPI(title='hearth speech provider', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts or ['127.0.0.1', 'localhost', '10.0.2.2', 'testserver'])
    @app.middleware('http')
    async def boundary(request: Request, call_next):
        if request.headers.get('origin') or not hmac.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer '+token).encode()):
            return JSONResponse({'detail': 'A trusted controller credential is required.'}, status_code=401)
        body = bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body) > 65536:
                return JSONResponse({'detail': 'The speech request is too large.'}, status_code=413)
        request._body = bytes(body)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    @app.get('/v1/speech-provider')
    def information():
        return {'schema_version': 1, 'protocol': 'hearth.speech.v1', 'model': MODEL, 'model_revision': '1.0', 'manifest_sha256': digest,
                'voices': [VOICE], 'default_voice': VOICE, 'maximum_characters': 6000, 'sample_rate': 24000, 'job_cancellation': True, 'offline': True}
    @app.post('/v1/speech-jobs', status_code=202)
    def submit(data: SpeechGeneration):
        return jobs.submit(data)
    @app.get('/v1/speech-jobs/{job_id}')
    def status(job_id: UUID):
        return jobs.get(job_id)
    @app.post('/v1/speech-jobs/{job_id}/cancel')
    def cancel(job_id: UUID):
        with jobs.mutex, jobs.db() as db:
            db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND state IN ('queued','running')", (str(job_id),))
        return jobs.get(job_id)
    @app.get('/v1/speech-jobs/{job_id}/audio')
    def audio(job_id: UUID):
        if jobs.get(job_id)['state'] != 'completed':
            raise HTTPException(409, 'This speech job has not completed.')
        return FileResponse(root/(str(job_id)+'.wav'), media_type='audio/wav', filename=f'hearth-{job_id}.wav')
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    model, voices = Path(config['model']), Path(config['voices'])
    digest = verify_files(model, voices)
    def offline(*args, **kwargs):
        raise RuntimeError('Outbound connections are disabled in this local speech process.')
    async def serve():
        # Windows constructs an internal socketpair while creating its event loop.
        # Block outbound connections after that internal setup, before loading the model.
        socket.socket.connect = offline
        socket.socket.connect_ex = offline
        socket.create_connection = offline
        app = create_app(Path(config['jobs']), Path(config['token_file']).read_text(encoding='utf-8').strip(),
                         engine=KokoroCPU(model, voices), digest=digest, hosts=config.get('hosts'))
        await uvicorn.Server(uvicorn.Config(app, host=config.get('bind', '127.0.0.1'), port=config.get('port', 1236), access_log=False,
                                           ssl_keyfile=config.get('tls_key'), ssl_certfile=config.get('tls_cert'))).serve()
    asyncio.run(serve())


if __name__ == '__main__':
    main()
