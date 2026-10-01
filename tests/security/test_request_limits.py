import httpx
import pytest
from hearth.config import Settings
from hearth.main import create_app


async def test_chunked_body_limit_cannot_be_bypassed_without_length_header():
    async def chunks():
        for _ in range(17):
            yield b"x" * 65536

    transport = httpx.ASGITransport(app=create_app(Settings(mode="test")))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post("/api/v1/session", content=chunks())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "body_too_large"
    assert "x" * 100 not in response.text


@pytest.mark.parametrize('method,path,megabytes,status', [
    ('POST', '/api/v1/images', 11, 200),
    ('POST', '/api/v1/images', 12, 413),
    ('PUT', '/api/v1/images', 2, 413),
    ('POST', '/api/v1/chats/12345678-1234-1234-1234-123456789abc/attachments', 2, 200),
    ('POST', '/api/v1/chats/12345678-1234-1234-1234-123456789abc/attachments', 9, 413),
    ('POST', '/api/v1/session', 2, 413),
    ('PUT', '/api/v1/chats/12345678-1234-1234-1234-123456789abc/attachments', 2, 413),
    ('POST', '/api/v1/chats/invalid/attachments', 2, 413),
    ('POST', '/api/v1/channels/12345678-1234-1234-1234-123456789abc/attachments', 2, 200),
    ('POST', '/api/v1/channels/12345678-1234-1234-1234-123456789abc/attachments', 9, 413),
    ('PUT', '/api/v1/channels/12345678-1234-1234-1234-123456789abc/attachments', 2, 413),
    ('POST', '/api/v1/channels/invalid/attachments', 2, 413),
    ('POST', '/api/v1/channels/12345678-1234-1234-1234-123456789abc/messages', 2, 413),
])
async def test_only_picture_uploads_receive_the_larger_chunked_body_budget(method, path, megabytes, status):
    from hearth.middleware import BodyLimitMiddleware
    from starlette.responses import Response

    async def app(scope, receive, send):
        request = await receive()
        assert len(request['body']) == megabytes * 1_048_576
        await Response('accepted')(scope, receive, send)

    async def chunks():
        for _ in range(megabytes * 16):
            yield b'x' * 65536

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=BodyLimitMiddleware(app)), base_url='http://localhost') as client:
        result = await client.request(method, path, content=chunks())
    assert result.status_code == status
