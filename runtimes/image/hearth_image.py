"""Experimental loopback SDXL provider. No model downloads occur at runtime.

This is a development provider, not a signed/enrolled native worker package.
The control plane owns user authorization; this process accepts one trusted
controller credential and one pinned local model closure.
"""
import argparse
import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from hearth.contracts import ImageGeneration as Generate
from starlette.middleware.trustedhost import TrustedHostMiddleware

MODEL = 'stabilityai/stable-diffusion-xl-base-1.0'
REVISION = '462165984030d82259a11f4367a4eed129e94a7b'
SIZES = {'square': (1024, 1024), 'landscape': (1024, 768), 'portrait': (768, 1024)}


class Cancelled(Exception):
    pass


class GenerationError(Exception):
    pass


class SDXL:
    def __init__(self, model_path):
        self.model_path, self.pipe = model_path, None

    def generate(self, data, cancelled, progress, output):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        import torch
        from diffusers import StableDiffusionXLPipeline
        if not torch.cuda.is_available():
            raise GenerationError('This provider profile requires a CUDA GPU.')
        if cancelled():
            raise Cancelled()
        if self.pipe is None:
            self.pipe = StableDiffusionXLPipeline.from_pretrained(str(self.model_path), torch_dtype=torch.float16,
                variant='fp16', use_safetensors=True, local_files_only=True, add_watermarker=False)
            self.pipe.enable_model_cpu_offload()
            self.pipe.enable_vae_tiling()
            self.pipe.set_progress_bar_config(disable=True)
        for tokenizer in (self.pipe.tokenizer, self.pipe.tokenizer_2):
            for value in (data.prompt, data.negative_prompt):
                if len(tokenizer(value)['input_ids']) > tokenizer.model_max_length:
                    raise GenerationError('This SDXL profile supports short prompts. Shorten your description or negative prompt to about 60 words.')

        def step(pipe, index, timestep, kwargs):
            if cancelled():
                raise Cancelled()
            progress(index + 1)
            return kwargs

        width, height = SIZES[data.shape]
        result = self.pipe(prompt=data.prompt, negative_prompt=data.negative_prompt, width=width, height=height,
            num_inference_steps=data.steps, guidance_scale=7.0, generator=torch.Generator('cpu').manual_seed(data.seed),
            callback_on_step_end=step)
        if cancelled():
            raise Cancelled()
        result.images[0].save(output, format='PNG')

    def release(self):
        import torch
        if self.pipe is not None:
            self.pipe.maybe_free_model_hooks()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()


def verify_model(path):
    manifest_bytes = (path / 'hearth-manifest.json').read_bytes()
    expected = Path(__file__).with_name('model-manifest.json').read_bytes()
    if hashlib.sha256(manifest_bytes).digest() != hashlib.sha256(expected).digest():
        raise RuntimeError('The model closure does not match this provider recipe.')
    manifest = json.loads(manifest_bytes)
    if manifest['model'] != MODEL or manifest['revision'] != REVISION:
        raise RuntimeError('The configured model is not the qualified SDXL profile.')
    for item in manifest['files']:
        target = (path / item['path']).resolve()
        if not target.is_relative_to(path.resolve()) or target.stat().st_size != item['bytes']:
            raise RuntimeError('The model closure failed verification.')
        with target.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != item['sha256']:
                raise RuntimeError('A model file failed verification.')
    return hashlib.sha256(manifest_bytes).hexdigest()


class Jobs:
    def __init__(self, root, engine, manifest_digest):
        self.root, self.engine, self.manifest_digest = root, engine, manifest_digest
        root.mkdir(parents=True, exist_ok=True)
        self.lock_file = (root / 'process.lock').open('a+b')
        self.lock_file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.mutex, self.pool = threading.Lock(), ThreadPoolExecutor(max_workers=1)
        self.poisoned = False
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, cancel INTEGER NOT NULL DEFAULT 0, reason TEXT, digest TEXT, released INTEGER NOT NULL DEFAULT 0)')
            # An exclusive process lock proves the previous process is gone.
            # Its requests remain interrupted; no prompt is automatically replayed.
            db.execute("UPDATE jobs SET state='interrupted',reason='The provider restarted before completing this image.',released=1 WHERE state IN ('queued','running')")

    def db(self):
        db = sqlite3.connect(self.root / 'jobs.sqlite', timeout=5)
        db.row_factory = sqlite3.Row
        return transaction(db)

    def get(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (str(job_id),)).fetchone()
        if not row:
            raise HTTPException(404, 'This image job is not available.')
        data = json.loads(row['request'])
        return {'schema_version': 1, 'id': row['id'], 'model': MODEL, 'state': row['state'], 'progress': row['progress'], 'steps': data['steps'],
                'seed': data['seed'], 'shape': data['shape'], 'width': SIZES[data['shape']][0], 'height': SIZES[data['shape']][1],
                'reason': row['reason'], 'sha256': row['digest'], 'execution_released': bool(row['released']),
                'manifest_sha256': self.manifest_digest, 'cancel_requested': bool(row['cancel'])}

    def submit(self, data):
        if data.model != MODEL:
            raise HTTPException(404, 'This model is not installed on this provider.')
        payload = data.model_dump_json()
        with self.mutex, self.db() as db:
            previous = db.execute('SELECT request FROM jobs WHERE id=?', (str(data.id),)).fetchone()
            if previous:
                if previous['request'] != payload:
                    raise HTTPException(409, 'This job identifier was already used for another request.')
            else:
                if self.poisoned or db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') OR released=0").fetchone():
                    raise HTTPException(409, 'This image provider is occupied or needs a restart after an uncertain execution.')
                if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 2000:
                    raise HTTPException(409, 'This experimental provider reached its saved image limit.')
                db.execute("INSERT INTO jobs(id,request,state) VALUES(?,?,'queued')", (str(data.id), payload))
                db.commit()
                self.pool.submit(self.execute, data)
        return self.get(data.id)

    def execute(self, data):
        job_id = str(data.id)
        def cancelled():
            with self.db() as db:
                return bool(db.execute('SELECT cancel FROM jobs WHERE id=?', (job_id,)).fetchone()[0])

        def progress(value):
            with self.db() as db:
                db.execute('UPDATE jobs SET progress=? WHERE id=?', (value, job_id))

        with self.db() as db:
            db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
        state, reason, digest, released = 'completed', None, None, True
        output = self.root / (job_id + '.png')
        try:
            if cancelled():
                raise Cancelled()
            self.engine.generate(data, cancelled, progress, output)
            if cancelled():
                raise Cancelled()
            with output.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
        except Cancelled:
            state, reason = 'cancelled', 'Image generation stopped.'
        except GenerationError as exc:
            state, reason = 'failed', str(exc)
        except Exception:
            state, reason = 'failed', 'Image generation failed. Check available GPU memory and the provider environment.'
        finally:
            try:
                self.engine.release()
            except Exception:
                state, reason, released, self.poisoned = 'interrupted', 'The provider could not confirm GPU release. Restart it before retrying.', False, True
        with self.mutex, self.db() as db:
            if cancelled() and state == 'completed':
                state, reason = 'cancelled', 'Image generation stopped.'
            if state != 'completed':
                output.unlink(missing_ok=True)
                digest = None
            db.execute('UPDATE jobs SET state=?,reason=?,digest=?,released=? WHERE id=?', (state, reason, digest, int(released), job_id))

    def close(self):
        self.pool.shutdown(wait=True)
        self.lock_file.close()


@contextlib.contextmanager
def transaction(db):
    try:
        with db:
            yield db
    finally:
        db.close()


def create_app(root, model_path, token, *, engine=None, manifest_digest=None):
    if len(token) < 32:
        raise RuntimeError('A controller credential of at least 32 characters is required.')
    digest = manifest_digest or verify_model(model_path)
    jobs = Jobs(root, engine or SDXL(model_path), digest)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title='hearth image provider', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '10.0.2.2', 'testserver'])

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        if request.headers.get('origin') or not hmac.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + token).encode()):
            return JSONResponse({'detail': 'A trusted controller credential is required.'}, status_code=401)
        body = bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body) > 16384:
                return JSONResponse({'detail': 'The image request is too large.'}, status_code=413)
        request._body = bytes(body)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/v1/image-provider')
    def capabilities():
        return {'schema_version': 1, 'protocol': 'hearth.image.v1', 'model': MODEL, 'model_revision': REVISION, 'manifest_sha256': digest,
                'shapes': list(SIZES), 'steps': [20, 30, 40], 'job_cancellation': True, 'offline': True}

    @app.post('/v1/image-jobs', status_code=202)
    def submit(data: Generate):
        return jobs.submit(data)

    @app.get('/v1/image-jobs/{job_id}')
    def status(job_id: UUID):
        return jobs.get(job_id)

    @app.post('/v1/image-jobs/{job_id}/cancel')
    def cancel(job_id: UUID):
        with jobs.mutex, jobs.db() as db:
            db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND state IN ('queued','running')", (str(job_id),))
        return jobs.get(job_id)

    @app.get('/v1/image-jobs/{job_id}/image')
    def artifact(job_id: UUID):
        result = jobs.get(job_id)
        if result['state'] != 'completed' or not result['execution_released']:
            raise HTTPException(409, 'This image has not completed.')
        return FileResponse(root / (str(job_id) + '.png'), media_type='image/png', filename=f'hearth-{job_id}.png')

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    app = create_app(Path(config['jobs']), Path(config['model']), Path(config['token_file']).read_text(encoding='utf-8').strip())
    uvicorn.run(app, host='127.0.0.1', port=1235, access_log=False)


if __name__ == '__main__':
    main()
