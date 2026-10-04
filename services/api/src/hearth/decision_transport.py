"""Closed local decision transport. Provider text and judgments never grant authority."""
import json
import time
from contextlib import contextmanager

import httpx
from pydantic import ValidationError

from hearth.contracts import DecisionProviderInfo, DecisionRequest, DecisionResult
from hearth.inference import ProviderError, client_for


@contextmanager
def connection(settings, target=None):
    if target is None:
        if not settings.decision_socket:
            raise ProviderError('The built-in decision service is not installed.', provider_fault=False)
        with httpx.Client(transport=httpx.HTTPTransport(uds=settings.decision_socket),
                          base_url='http://decision/v1/', timeout=2, trust_env=False) as client:
            yield client, {}
    else:
        from hearth.providers import credential_for, transport_settings
        with client_for(target['base_url'], credential_for(target, settings), transport_settings(target, settings)) as value:
            yield value


def read(settings, path, *, target=None, payload=None, budget=2., lane='member'):
    started = time.monotonic()
    try:
        with connection(settings, target) as (client, extensions):
            with client.stream('POST' if payload else 'GET', path, json=payload, extensions=extensions,
                    timeout=httpx.Timeout(budget, connect=min(budget, 2)),
                    headers={'X-Hearth-Decision-Lane': lane, 'X-Hearth-Deadline-Ms': str(int(budget*1000))}) as response:
                if response.status_code == 413:
                    raise ProviderError('This checkpoint cannot preserve the entire input. Shorten the state or questions.', provider_fault=False)
                if response.status_code == 429:
                    raise ProviderError('Decision capacity is busy. Try again when current work finishes.', provider_fault=False)
                if response.status_code != 200:
                    raise ProviderError('The decision service is unavailable.', uncertain=bool(payload) and response.status_code >= 500)
                raw = bytearray()
                for block in response.iter_bytes():
                    raw.extend(block)
                    if len(raw) > 65536 or time.monotonic()-started > budget:
                        raise ProviderError('The decision response exceeded its size or time budget.', uncertain=bool(payload))
                return json.loads(raw)
    except ProviderError:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise ProviderError('The decision service did not return a valid response within its deadline.', uncertain=bool(payload)) from None


def information(settings, target=None):
    try:
        info = DecisionProviderInfo.model_validate(read(settings, 'info', target=target))
        if not info.ready or not info.offline or (target and info.model != target['model_id']):
            raise ValueError()
        return info
    except (ValidationError, ValueError):
        raise ProviderError('The decision provider did not confirm a ready, local checkpoint.') from None


def validate_result(data: DecisionRequest, result: DecisionResult):
    if result.id != data.id or len(result.answers) != len(data.questions) or {a.id for a in result.answers} != {q.id for q in data.questions}:
        raise ValueError('Mismatched decision identity or questions.')
    for q in data.questions:
        a = next(a for a in result.answers if a.id == q.id)
        if a.kind != q.kind:
            raise ValueError('Mismatched decision kind.')
        keys = set(q.options) if q.kind == 'choice' else {str(i) for i in range(len(q.rubric))}
        if q.kind == 'choice' and ((a.choice not in q.options and not (a.abstained and a.choice is None)) or a.score is not None or a.probability_true is not None):
            raise ValueError('Out-of-set choice.')
        if q.kind == 'score' and ((a.score is None and not a.abstained) or (a.score is not None and a.score > len(q.rubric)-1) or a.choice is not None or a.probability_true is not None):
            raise ValueError('Out-of-rubric score.')
        if q.kind == 'boolean' and ((a.probability_true is None and not a.abstained) or a.choice is not None or a.score is not None or a.probabilities is not None):
            raise ValueError('Invalid boolean probability.')
        if a.probabilities is not None and (set(a.probabilities) != keys or abs(sum(a.probabilities.values())-1) > .002):
            raise ValueError('Invalid probability distribution.')
    return result


def evaluate(settings, data, target=None, *, budget=30., lane='member'):
    try:
        result = validate_result(data, DecisionResult.model_validate(read(settings, 'evaluate', target=target,
            payload=data.model_dump(mode='json'), budget=budget, lane=lane)))
        if target:
            saved = target.get('profile') or {}
            if (result.model != target['model_id'] or result.model_revision != saved.get('model_revision')
                    or result.manifest_sha256 != saved.get('manifest_sha256')):
                raise ValueError('The verified checkpoint changed.')
        return result
    except (ValidationError, ValueError, KeyError, TypeError):
        raise ProviderError('The decision provider returned an invalid typed answer or changed checkpoint.', uncertain=True) from None
