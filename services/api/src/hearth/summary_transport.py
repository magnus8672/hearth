"""NCM XSum is a bounded single-document specialist, never a general chat model."""
import json
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from hearth.inference import ProviderError, client_for


class SummaryInfo(BaseModel):
    model_config = ConfigDict(extra='forbid')
    protocol: Literal['hearth.summary.v1']
    model: Literal['hazyresearch/ncm-xsum']
    revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    task: Literal['xsum']
    input_tokens: Literal[512]
    output_tokens: Literal[48]
    device: Literal['cpu', 'cuda']
    chat: Literal[False]
    tools: Literal[False]
    streaming: Literal[False]


class SummaryResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    model: Literal['hazyresearch/ncm-xsum']
    revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    text: str = Field(min_length=1, max_length=8192)
    input_tokens: int = Field(strict=True, ge=1, le=512)
    output_tokens: int = Field(strict=True, ge=1, le=48)
    truncated: StrictBool
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)


def read(response, maximum=16384):
    data = bytearray()
    for part in response.iter_bytes():
        data.extend(part)
        if len(data) > maximum:
            raise ProviderError('The summarizer returned an oversized response.', uncertain=True)
    return json.loads(data)


def information(base_url, credential, settings):
    try:
        with client_for(base_url, credential, settings) as (client, extensions):
            with client.stream('GET', 'ncm-provider', extensions=extensions) as response:
                if response.status_code != 200:
                    raise ProviderError('The NCM specialist is not available.')
                return SummaryInfo.model_validate(read(response))
    except (httpx.HTTPError, ValueError):
        raise ProviderError('The NCM specialist returned invalid readiness information.') from None


def summarize(base_url, credential, model, source, settings):
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > 60000:
        raise ProviderError('Supply one bounded source article for NCM XSum.', provider_fault=False)
    info = information(base_url, credential, settings)
    if info.model != model:
        raise ProviderError('The selected summarizer is not resident. No generation was sent.')
    request_id = str(uuid4())
    try:
        with client_for(base_url, credential, settings) as (client, extensions):
            with client.stream('POST', 'summaries', json={'id': request_id, 'model': model, 'text': source},
                               extensions=extensions, timeout=httpx.Timeout(180, connect=5, write=10)) as response:
                if response.status_code in (400, 413, 422):
                    raise ProviderError('NCM XSum requires one article of at most 512 GPT-2 tokens. No text was truncated.', provider_fault=False)
                if response.status_code == 503:
                    raise ProviderError('The NCM summarizer is busy. No new generation was started.', provider_fault=False)
                if response.status_code != 200:
                    raise ProviderError('The NCM summary request failed.', uncertain=response.status_code >= 500)
                result = SummaryResult.model_validate(read(response))
                if result.id != request_id or result.model != model or result.revision != info.revision or result.truncated:
                    raise ValueError('Mismatched receipt')
                return result
    except (httpx.HTTPError, ValueError):
        raise ProviderError('The NCM response was interrupted or invalid. It was not replayed.', uncertain=True) from None


def source_from_messages(messages, *, caller_owned=False):
    # hearth's system context cannot train an XSum checkpoint to follow arbitrary
    # instructions. Do not send private recalled context or silently drop history.
    if caller_owned and any(item.get('role') != 'user' for item in messages):
        raise ProviderError('NCM XSum accepts one user article, without system prompts, history or tools.', provider_fault=False)
    source = [item for item in messages if item.get('role') != 'system']
    if (len(source) != 1 or source[0].get('role') != 'user' or not isinstance(source[0].get('content'), str)
            or source[0].get('attachment_ids')):
        raise ProviderError('NCM XSum needs a fresh conversation containing one source article. It cannot summarize chat history or attachments.', provider_fault=False)
    return source[0]['content']
