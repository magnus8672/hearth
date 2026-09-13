from fastapi.testclient import TestClient
from hearth.config import Settings
from hearth.main import create_app


def test_liveness_does_not_claim_readiness_and_headers_cannot_authenticate():
    with TestClient(create_app(Settings(mode="test")), base_url="http://localhost") as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_unconfigured"
        response = client.get("/api/v1/session", headers={"X-User-ID": "owner", "X-Client-Cert": "trusted"})
        assert response.status_code == 401
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/health/live", headers={"Host": "rebinding.invalid"}).status_code == 400
