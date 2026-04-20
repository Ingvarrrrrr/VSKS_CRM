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


# ---------------------------------------------------------------------------
# Phase 13 plan 02: DB / user / auth fixtures for approve-distribution tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Provide a real AsyncSession connected to the app database.

    Uses the same async_session factory as the app, but as a standalone
    session for test setup and assertions. Data is committed so that the
    ASGITransport app (which uses its own get_db() sessions) can see it.
    """
    from app.database import async_session
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_org(db_session):
    """Create a test Organization and return it (committed to DB)."""
    import uuid
    from app.models.organization import Organization
    org = Organization(name=f"TestOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_user(db_session, test_org):
    """Create a regular employee user belonging to test_org (committed to DB)."""
    import uuid
    from app.models.user import User
    from app.auth.jwt import hash_password
    username = f"test_user_{uuid.uuid4().hex[:8]}"
    user = User(
        username=username,
        password_hash=hash_password("testpass123"),
        role="employee",
        org_id=test_org.id,
        full_name=f"Test User {username}",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin_user(db_session, test_org):
    """Create an org_admin user belonging to test_org (committed to DB)."""
    import uuid
    from app.models.user import User
    from app.auth.jwt import hash_password
    username = f"test_admin_{uuid.uuid4().hex[:8]}"
    user = User(
        username=username,
        password_hash=hash_password("testpass123"),
        role="org_admin",
        org_id=test_org.id,
        full_name=f"Test Admin {username}",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Return Authorization headers for a regular employee user."""
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": test_user.username, "org_id": test_user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(test_admin_user):
    """Return Authorization headers for an org_admin user (in ADMIN_ROLES)."""
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": test_admin_user.username, "org_id": test_admin_user.org_id})
    return {"Authorization": f"Bearer {token}"}
