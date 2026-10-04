"""Resident CPU Laya service. No downloads, tools or model switches at request time."""
import hashlib
import json
import math
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from hearth.contracts import DecisionAnswer, DecisionProviderInfo, DecisionRequest, DecisionResult


class Admission:
    """Bounded FIFO lanes: internal work has priority, members cannot starve it."""
    def __init__(self):
        self.condition = threading.Condition()
        self.waiting = {'internal': [], 'member': []}
        self.active = False
        self.internal_streak = 0

    @contextmanager
    def slot(self, lane, deadline):
        ticket = object()
        with self.condition:
            if len(self.waiting[lane]) >= (8 if lane == 'internal' else 4):
                raise HTTPException(429, 'Decision capacity is busy. Try again after current work finishes.')
            self.waiting[lane].append(ticket)
            try:
                while True:
                    if time.monotonic() >= deadline:
                        raise HTTPException(504, 'Decision admission deadline exceeded.')
                    first = 'internal' if self.waiting['internal'] and (self.internal_streak < 4 or not self.waiting['member']) else 'member'
                    if not self.active and lane == first and self.waiting[lane][0] is ticket:
                        self.waiting[lane].pop(0)
                        self.active = True
                        self.internal_streak = self.internal_streak + 1 if lane == 'internal' else 0
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise HTTPException(504, 'Decision admission deadline exceeded.')
                    self.condition.wait(min(remaining, .1))
            except BaseException:
                self.waiting[lane].remove(ticket)
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            with self.condition:
                self.active = False
                self.condition.notify_all()


def questions_for(data):
    return {q.id: {'type': 'noul' if q.kind == 'boolean' else q.kind, 'instructions': q.instructions,
                   **({'criteria': q.options if q.kind == 'choice' else q.rubric} if q.kind != 'boolean' else {})}
            for q in data.questions}


def create_app():
    gate = Admission()
    manifest_path = Path(os.environ['HEARTH_DECISION_MANIFEST'])
    manifest = json.loads(manifest_path.read_text())
    model_path = manifest_path.parent / 'model'
    token_path = os.environ.get('HEARTH_DECISION_TOKEN_FILE')
    token = Path(token_path).read_text().strip() if token_path else None
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    @asynccontextmanager
    async def lifespan(app):
        import torch
        from laya import Agent
        torch.set_num_threads(int(os.environ.get('HEARTH_DECISION_THREADS', '4')))
        torch.set_num_interop_threads(1)
        # Offline environment plus local files and explicit digests make startup fail closed.
        started = time.monotonic()
        app.state.agent = Agent(str(model_path), device='cpu', expected_sha256=manifest['sha256'])
        app.state.agent.cfg['max_len'] = manifest['maximum_tokens']
        app.state.agent.cfg['head_max_len'] = 512
        app.state.agent.predict('Hello.', {'warm': {'type': 'noul', 'instructions': 'Is this a greeting?'}})
        app.state.cold_ms = (time.monotonic()-started)*1000
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        if token and not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer '+token):
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Authentication required.'}, status_code=401)
        # UDS mode is accessible only through the head's socket volume. TCP requires a token.
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 40000:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail': 'Decision request is too large.'}, status_code=413)
        request._body = bytes(raw)
        return await call_next(request)

    @app.get('/v1/info', response_model=DecisionProviderInfo)
    def info():
        return DecisionProviderInfo(model=manifest['model'], model_revision=manifest['revision'],
            manifest_sha256=manifest_digest, question_kinds=['choice', 'score', 'boolean'],
            maximum_tokens=manifest['maximum_tokens'], maximum_characters=8000,
            languages=manifest['languages'], offline=True, ready=True)

    @app.post('/v1/evaluate', response_model=DecisionResult)
    def evaluate(data: DecisionRequest, request: Request):
        started = time.monotonic()
        try:
            budget = float(request.headers.get('x-hearth-deadline-ms', '30000'))/1000
            if not math.isfinite(budget) or budget <= 0:
                raise ValueError()
            budget = min(30., max(.05, budget))
        except ValueError:
            raise HTTPException(400, 'Invalid deadline.') from None
        lane = 'internal' if request.headers.get('x-hearth-decision-lane') == 'internal' else 'member'
        with gate.slot(lane, started+budget):
            agent = app.state.agent
            questions = questions_for(data)
            # Inspect the exact tokenization before inference: never silently discard state,
            # rubric levels, option text or instructions to fit a context window.
            internal = {key: agent._to_internal(value) for key, value in questions.items()}
            from laya.common import render_options
            for q in internal.values():
                option_sizes = [len(agent.tok.encode(' '+option.replace(agent.tok.mask_token, ' '), add_special_tokens=False)) for option in render_options(q)]
                instruction_size = len(agent.tok.encode(q['t']+' question: '+q['ins'].replace(agent.tok.mask_token, ' '), add_special_tokens=False))
                if any(size > 48 for size in option_sizes) or instruction_size > 512-sum(size+1 for size in option_sizes):
                    raise HTTPException(413, 'The question or option descriptions exceed this checkpoint context. Shorten them; no decision was made.')
            encoded = agent._encode_state(data.state, list(questions), internal)
            if any(item['state_stats']['truncated'] or item['options'].get('truncated', False)
                   or item['options'].get('options_distinct', len(q.options or q.rubric or [0, 1])) < len(q.options or q.rubric or [0, 1])
                   for item, q in zip(encoded, data.questions, strict=True)):
                raise HTTPException(413, 'The state or question exceeds this checkpoint context. Shorten it; no decision was made.')
            if time.monotonic() >= started+budget:
                raise HTTPException(504, 'Decision deadline exceeded before inference.')
            raw = agent.predict(data.state, questions)
            if raw['usage'].get('truncated') or raw['usage'].get('options'):
                raise HTTPException(413, 'The checkpoint could not preserve the whole input.')
            answers = []
            for q in data.questions:
                answer = raw['answers'][q.id]
                answers.append(DecisionAnswer(id=q.id, kind=q.kind, choice=answer.get('choice'),
                    score=answer.get('score'), probability_true=answer.get('noul'),
                    probabilities=answer.get('probabilities'), provider_confidence=answer.get('confidence'),
                    answer_confidence=answer.get('answer_confidence'), abstained=answer.get('abstained', False)))
            return DecisionResult(id=data.id, model=manifest['model'], model_revision=manifest['revision'],
                manifest_sha256=manifest_digest, answers=answers,
                elapsed_ms=(time.monotonic()-started)*1000, input_tokens=raw['usage']['input_tokens'])

    return app
