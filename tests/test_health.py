from fastapi.testclient import TestClient

from app.api.health import _clients
from app.main import app


class ReadyClient:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    async def readiness(self) -> bool:
        return self._ready

    async def aclose(self) -> None:
        return None


def test_live() -> None:
    response = TestClient(app).get("/health/live")
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_ready_is_degraded_when_dependency_fails() -> None:
    app.dependency_overrides[_clients] = lambda: (ReadyClient(True), ReadyClient(False))
    response = TestClient(app).get("/health/ready")
    app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
