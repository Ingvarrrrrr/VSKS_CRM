import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """HTTPX AsyncClient wired to the FastAPI app via ASGITransport."""
    from app import app  # noqa: WPS433 — deferred to avoid import-time side effects
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
