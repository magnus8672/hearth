"""Explicit CPU Whisper provider with durable job receipts and bounded WAV input."""
import argparse
import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import io
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
from fastapi.responses import JSONResponse
from hearth.contracts import TranscriptionRequest
from hearth.transcription_audio import normalize
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

MODEL = 'faster-whisper-small.en'


class Upload(TranscriptionRequest):
    audio_b64: str = Field(min_length=60, max_length=5120060)


class Cancelled(Exception):
    pass


class WhisperCPU:
    def __init__(self, model):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        from faster_whisper import WhisperModel
        self.model = WhisperModel(str(model), device='cpu', compute_type='int8', cpu_threads=4, num_workers=1, local_files_only=True)

    def transcribe(self, audio, cancelled):
        import numpy as np
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(np.float32)/32768
        segments, _ = self.model.transcribe(samples, language='en', beam_size=3, temperature=0, condition_on_previous_text=False, vad_filter=True)
        parts = []
        for segment in segments:
            if cancelled():
                raise Cancelled()
            parts.append(segment.text.strip())
            if len(' '.join(parts)) > 6000:
                raise ValueError('Transcript too long.')
        if cancelled():
            raise Cancelled()
        result = ' '.join(parts).strip()
        if not result:
            raise ValueError('No speech recognized.')
        return result


def verify_files(model):
    raw = Path(__file__).with_name('model-manifest.json').read_bytes()
    manifest = json.loads(raw)
    for name, expected in manifest['files'].items():
        path = model/name
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != expected['sha256'] or path.stat().st_size != expected['bytes']:
            raise RuntimeError('The transcription model does not match its pinned manifest.')
    return hashlib.sha256(raw).hexdigest()


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
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL, cancel INTEGER NOT NULL DEFAULT 0, reason TEXT, transcript TEXT NOT NULL DEFAULT \'\')')
            db.execute("UPDATE jobs SET state='interrupted',reason='The process restarted. This job was not replayed.' WHERE state IN ('queued','running')")
        for path in root.glob('*.wav'):
            path.unlink()

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.root/'jobs.sqlite', timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (str(job_id),)).fetchone()
        if not row:
            raise HTTPException(404, 'This transcription job is not available.')
        data = json.loads(row['request'])
        return data | {'schema_version': 1, 'state': row['state'], 'reason': row['reason'], 'text': row['transcript'], 'language': 'en',
                       'execution_released': row['state'] not in {'queued', 'running'}, 'manifest_sha256': self.digest, 'cancel_requested': bool(row['cancel'])}

    def submit(self, data):
        if data.model != MODEL:
            raise HTTPException(400, 'Select the resident transcription model.')
        try:
            audio = base64.b64decode(data.audio_b64, validate=True)
            if hashlib.sha256(audio).hexdigest() != data.audio_sha256 or normalize(audio) != audio:
                raise ValueError('Mismatch')
        except (ValueError, binascii.Error):
            raise HTTPException(400, 'Audio must be normalized PCM WAV matching its digest.') from None
        payload = json.dumps(data.model_dump(mode='json', exclude={'audio_b64'}), sort_keys=True)
        with self.mutex, self.db() as db:
            prior = db.execute('SELECT request FROM jobs WHERE id=?', (str(data.id),)).fetchone()
            if prior:
                if prior['request'] != payload:
                    raise HTTPException(409, 'This job identifier was already used.')
            else:
                if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running')").fetchone():
                    raise HTTPException(409, 'This transcription provider is occupied.')
                if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 1000:
                    raise HTTPException(409, 'This development provider has reached its saved job limit.')
                (self.root/(str(data.id)+'.wav')).write_bytes(audio)
                db.execute("INSERT INTO jobs(id,request,state) VALUES(?,?,'queued')", (str(data.id), payload))
                db.commit()
                self.pool.submit(self.execute, data.id)
        return self.get(data.id)

    def execute(self, job_id):
        job_id = str(job_id)
        source = self.root/(job_id+'.wav')
        def cancelled():
            with self.db() as db:
                return bool(db.execute('SELECT cancel FROM jobs WHERE id=?', (job_id,)).fetchone()[0])
        with self.db() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
        state, reason, transcript = 'completed', None, ''
        try:
            if cancelled():
                raise Cancelled()
            transcript = self.engine.transcribe(source.read_bytes(), cancelled)
            if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 6000:
                raise ValueError('Invalid transcript.')
        except Cancelled:
            state, reason = 'cancelled', 'Transcription stopped.'
        except Exception:
            state, reason = 'failed', 'No transcript could be produced. Check the recording and provider.'
        finally:
            source.unlink(missing_ok=True)
        with self.mutex, self.db() as db:
            if cancelled():
                state, reason = 'cancelled', 'Transcription stopped.'
            db.execute('UPDATE jobs SET state=?,reason=?,transcript=? WHERE id=?', (state, reason, transcript if state == 'completed' else '', job_id))

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
    app = FastAPI(title='hearth transcription provider', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts or ['127.0.0.1', 'localhost', '10.0.2.2', 'testserver'])
    @app.middleware('http')
    async def boundary(request: Request, call_next):
        if request.headers.get('origin') or not hmac.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer '+token).encode()):
            return JSONResponse({'detail': 'A trusted controller credential is required.'}, status_code=401)
        body = bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body) > 5_121_024:
                return JSONResponse({'detail': 'The recording is too large.'}, status_code=413)
        request._body = bytes(body)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response
    @app.get('/v1/transcription-provider')
    def information():
        return {'schema_version': 1, 'protocol': 'hearth.transcription.v1', 'model': MODEL, 'model_revision': 'small.en', 'manifest_sha256': digest,
                'languages': ['en'], 'maximum_seconds': 120, 'sample_rate': 16000, 'job_cancellation': True, 'offline': True}
    @app.post('/v1/transcription-jobs', status_code=202)
    def submit(data: Upload):
        return jobs.submit(data)
    @app.get('/v1/transcription-jobs/{job_id}')
    def status(job_id: UUID):
        return jobs.get(job_id)
    @app.post('/v1/transcription-jobs/{job_id}/cancel')
    def cancel(job_id: UUID):
        with jobs.mutex, jobs.db() as db:
            db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND state IN ('queued','running')", (str(job_id),))
        return jobs.get(job_id)
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    config = json.loads(parser.parse_args().config.read_text(encoding='utf-8'))
    model = Path(config['model'])
    digest = verify_files(model)
    def offline(*args, **kwargs):
        raise RuntimeError('Outbound connections are disabled in this transcription process.')
    async def serve():
        socket.socket.connect = offline
        socket.socket.connect_ex = offline
        socket.create_connection = offline
        app = create_app(Path(config['jobs']), Path(config['token_file']).read_text(encoding='utf-8').strip(), engine=WhisperCPU(model), digest=digest, hosts=config.get('hosts'))
        await uvicorn.Server(uvicorn.Config(app, host=config.get('bind', '127.0.0.1'), port=config.get('port', 1237), access_log=False,
                                           ssl_keyfile=config.get('tls_key'), ssl_certfile=config.get('tls_cert'))).serve()
    asyncio.run(serve())


if __name__ == '__main__':
    main()
