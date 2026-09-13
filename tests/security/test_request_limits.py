import httpx
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
