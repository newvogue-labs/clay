import httpx
import pytest

from clay.api.main import app


@pytest.mark.anyio
async def test_health_endpoint_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_health_endpoint_allows_local_frontend_origin() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
