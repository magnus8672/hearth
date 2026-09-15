"""Network-only MCP adapter. No process spawning, sampling, roots or redirects."""
import asyncio
import json
import ssl
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from hearth.inference import ProviderError, endpoint, normalize_url
from hearth.tool_schemas import NAME, valid_schema


class SchemaChanged(ProviderError):
    def __init__(self):
        super().__init__('This tool schema changed. An administrator must review it before execution.', provider_fault=False)


def normalize_mcp_url(value):
    parsed = urlsplit(value.strip())
    # Reuse the farm's LAN URL validation but preserve this service's MCP path.
    authority = normalize_url(urlunsplit((parsed.scheme, parsed.netloc, '', parsed.query, parsed.fragment)))
    path = parsed.path or '/mcp'
    if any(ord(c) <= 32 for c in value) or '\\' in value or '%' in path or '..' in path or len(path) > 500:
        raise ProviderError('Use the exact MCP endpoint path without escapes, credentials or query parameters.')
    return authority.removesuffix('/v1')+path


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for block in self.stream:
            size += len(block)
            if size > 2_097_152:
                raise ProviderError('The MCP response exceeded 2 MiB.')
            yield block

    async def aclose(self):
        await self.stream.aclose()


class PinnedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, source, settings, ca):
        self.source, self.settings = source, settings
        self.transport = httpx2.AsyncHTTPTransport(verify=ssl.create_default_context(cadata=ca) if ca else True, retries=0)

    async def handle_async_request(self, request):
        canonical = normalize_mcp_url(self.source)
        if str(request.url) != canonical:
            raise ProviderError('The MCP server tried to redirect outside its registered endpoint.')
        parsed = urlsplit(canonical)
        base = urlunsplit((parsed.scheme, parsed.netloc, '/v1', '', ''))
        url, authority, hostname = await asyncio.to_thread(endpoint, base, self.settings)
        request.url = httpx2.URL(str(url)).copy_with(path=parsed.path)
        request.headers['Host'] = authority
        request.extensions['sni_hostname'] = hostname
        response = await self.transport.handle_async_request(request)
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise ProviderError('Use the MCP server’s final endpoint address. Redirects are not followed.')
        response.stream = LimitedStream(response.stream)
        return response

    async def aclose(self):
        await self.transport.aclose()


@asynccontextmanager
async def connect(server, credential, settings):
    base = normalize_mcp_url(server['base_url'])
    if credential and (len(credential) > 2048 or any(ord(c) < 32 or ord(c) > 126 for c in credential)):
        raise ProviderError('The tool credential is not a supported Bearer token.')
    parsed = urlsplit(base)
    approved = normalize_url(urlunsplit((parsed.scheme, parsed.netloc, '/v1', '', ''))) if server['allow_insecure_http'] else ''
    transport_settings = settings.model_copy(update={'provider_http_approved_url': approved})
    async with httpx2.AsyncClient(transport=PinnedTransport(base, transport_settings, server.get('tls_ca_pem', '')),
                                  headers={'Authorization': 'Bearer '+credential} if credential else {},
                                  timeout=httpx2.Timeout(30, connect=5), follow_redirects=False, trust_env=False) as http:
        async with Client(streamable_http_client(base, http_client=http), read_timeout_seconds=60, cache=None) as client:
            yield client


async def catalog(client):
    items, cursor, cursors = [], None, set()
    for _ in range(16):
        result = await client.list_tools(cursor=cursor)
        for item in result.tools:
            definition = item.model_dump(mode='json', by_alias=True, exclude_none=True)
            if not NAME.fullmatch(definition['name']) or len(definition.get('description', '')) > 8000:
                raise ProviderError('The MCP catalog has an unsupported tool name or description.')
            try:
                definition['inputSchema'] = valid_schema(definition['inputSchema'])
                if definition.get('outputSchema'):
                    definition['outputSchema'] = valid_schema(definition['outputSchema'])
            except Exception:
                raise ProviderError('A tool schema is unsupported. Use bounded object schemas without recursive or external references or regular expressions.') from None
            # Only reviewed semantics enter the catalog, never server metadata.
            items.append({key: value for key, value in definition.items() if key in {'name', 'description', 'inputSchema', 'outputSchema', 'annotations', 'title'}})
        if len(items) > 256 or len(json.dumps(items).encode()) > 1_048_576 or len({item['name'] for item in items}) != len(items):
            raise ProviderError('The MCP tool catalog exceeds its limits or contains duplicate names.')
        cursor = result.next_cursor
        if not cursor:
            return items
        if cursor in cursors:
            break
        cursors.add(cursor)
    raise ProviderError('The MCP catalog did not finish within its pagination limit.')


async def discover(server, credential, settings):
    try:
        async with asyncio.timeout(60), connect(server, credential, settings) as client:
            return await catalog(client)
    except ProviderError:
        raise
    except Exception as exc:
        known = provider_error(exc)
        if known:
            raise known from None
        raise ProviderError('The MCP server could not be verified. Check its address, certificate, credential and Streamable HTTP support.') from None


async def execute(server, credential, settings, definition, arguments, before_send=None):
    sent = False
    try:
        async with asyncio.timeout(90), connect(server, credential, settings) as client:
            current = await catalog(client)
            candidate = next((item for item in current if item['name'] == definition['name']), None)
            if candidate != definition:
                raise SchemaChanged()
            if before_send:
                await asyncio.to_thread(before_send)
            sent = True
            result = await client.call_tool(definition['name'], arguments)
            value = result.model_dump(mode='json', by_alias=True, exclude_none=True)
            if len(json.dumps(value).encode()) > 131072:
                raise ProviderError('The tool result exceeded 128 KiB. Its execution may have completed.', uncertain=True)
            return value
    except ProviderError:
        raise
    except Exception as exc:
        known = provider_error(exc)
        if known:
            if sent:
                known.uncertain = True
            raise known from None
        raise ProviderError('The MCP tool did not return a confirmed result.' if sent else 'The MCP server could not be reached. No tool was sent.', uncertain=sent) from None


def provider_error(exc):
    if isinstance(exc, ProviderError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        return next((found for child in exc.exceptions if (found := provider_error(child))), None)
    return None
