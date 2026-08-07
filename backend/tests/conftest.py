import os

# app.config.Settings requires SECRET_KEY (no hardcoded default — see
# backend/app/config.py). Give the test suite a throwaway key so pytest
# works out of the box without a real .env; never used outside tests.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")

import pytest
import pytest_asyncio
from decimal import Decimal
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


# ---------------------------------------------------------------------------
# Phase 17: permission system fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def superadmin_user(db_session, test_org):
    import uuid
    from app.models.user import User
    from app.auth.jwt import hash_password
    username = f"test_super_{uuid.uuid4().hex[:8]}"
    user = User(
        username=username,
        password_hash=hash_password("testpass123"),
        role="superadmin",
        org_id=test_org.id,
        full_name=f"Super {username}",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
def superadmin_headers(superadmin_user):
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": superadmin_user.username, "org_id": superadmin_user.org_id})
    return {"Authorization": f"Bearer {token}"}

@pytest_asyncio.fixture
async def user_org_access(db_session, test_user, test_org):
    """Ensure UserOrgAccess row exists for test_user in test_org."""
    from app.models.user_org_access import UserOrgAccess
    from sqlalchemy import select
    res = await db_session.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == test_user.id,
            UserOrgAccess.org_id == test_org.id,
        )
    )
    uoa = res.scalar_one_or_none()
    if uoa is None:
        uoa = UserOrgAccess(user_id=test_user.id, org_id=test_org.id, role=test_user.role)
        db_session.add(uoa)
        await db_session.commit()
        await db_session.refresh(uoa)
    return uoa

@pytest_asyncio.fixture
async def make_user(db_session, test_org):
    """Parameterized user factory: make_user(role='manager', org_id=None, can_publish=False).

    Mirrors superadmin_user pattern but caller chooses role/org.
    Returns a persisted User row with a unique username.
    """
    import uuid
    from app.models.user import User
    from app.auth.jwt import hash_password

    async def _factory(role: str = "employee", org_id: int = None, can_publish: bool = False, **extra):
        username = f"test_{role}_{uuid.uuid4().hex[:8]}"
        kwargs = dict(
            username=username,
            password_hash=hash_password("testpass123"),
            role=role,
            org_id=org_id if org_id is not None else test_org.id,
            full_name=f"Test {role} {username}",
        )
        # can_publish may or may not exist on User model depending on Phase 17-01 migration state
        try:
            kwargs["can_publish"] = can_publish
        except Exception:
            pass
        kwargs.update(extra)
        u = User(**{k: v for k, v in kwargs.items() if hasattr(User, k)})
        db_session.add(u)
        await db_session.commit()
        await db_session.refresh(u)
        return u

    return _factory

@pytest_asyncio.fixture
async def make_role_permission(db_session):
    """Factory: make_role_permission(role='admin', key='staff', granted=True)"""
    from app.models.permission import RolePermission
    created = []
    async def _factory(role: str, key: str, granted: bool = True):
        rp = RolePermission(role_name=role, key=key, granted=granted)
        db_session.add(rp)
        await db_session.commit()
        await db_session.refresh(rp)
        created.append(rp)
        return rp
    yield _factory
    # no rollback — cross-test isolation via unique org/user fixtures

@pytest_asyncio.fixture
async def make_override(db_session):
    """Factory: make_override(user_org_access_id, key, granted)"""
    from app.models.permission import UserOrgPermissionOverride
    async def _factory(user_org_access_id: int, key: str, granted: bool):
        ov = UserOrgPermissionOverride(
            user_org_access_id=user_org_access_id,
            key=key,
            granted=granted,
        )
        db_session.add(ov)
        await db_session.commit()
        await db_session.refresh(ov)
        return ov
    return _factory


# ---------------------------------------------------------------------------
# Phase 27.1: contract_items fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def make_purchase(db_session, test_org):
    """Phase 27.1: Factory for creating a minimal Purchase in tests."""
    from app.models.purchase import Purchase

    async def _make(status="planned", org_id=None, **kwargs):
        p = Purchase(
            org_id=org_id if org_id is not None else test_org.id,
            status=status,
            item_type="goods",
            item_name="Test purchase",
            **kwargs,
        )
        db_session.add(p)
        await db_session.commit()
        await db_session.refresh(p)
        return p

    return _make


@pytest_asyncio.fixture
async def make_purchase_with_items(db_session, test_org):
    """Phase 27.1: Factory for creating a Purchase with PurchaseItems."""
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    async def _make(status="planned", items_count=2, item_total=Decimal("500"), org_id=None):
        p = Purchase(
            org_id=org_id if org_id is not None else test_org.id,
            status=status,
            item_type="goods",
            item_name="Test purchase with items",
        )
        db_session.add(p)
        await db_session.flush()  # get p.id without committing
        for i in range(items_count):
            item = PurchaseItem(
                purchase_id=p.id,
                item_name=f"Item {i + 1}",
                quantity=Decimal("1"),
                unit="шт",
                unit_price=item_total,
                total_price=item_total,
            )
            db_session.add(item)
        await db_session.commit()
        await db_session.refresh(p)
        return p

    return _make


@pytest_asyncio.fixture
async def make_contract_item(db_session):
    """Phase 27.1: Helper for creating ContractItem in tests."""
    from app.models.contract_item import ContractItem

    async def _make(
        purchase_id,
        name="Test item",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        total=Decimal("100"),
        source_item_id=None,
        product_id=None,
        contract_id=None,
        match_confirmed=True,
        unit="шт",
    ):
        ci = ContractItem(
            purchase_id=purchase_id,
            name=name,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            total=total,
            source_item_id=source_item_id,
            product_id=product_id,
            contract_id=contract_id,
            match_confirmed=match_confirmed,
        )
        db_session.add(ci)
        await db_session.commit()
        await db_session.refresh(ci)
        return ci

    return _make


@pytest_asyncio.fixture
async def make_legacy_contracted_purchase(db_session, make_purchase_with_items):
    """Phase 27.1: closure for backfill testing — purchase in `contracted` status WITHOUT contract_items."""

    async def _make(status="contracted", items_count=2, item_total=Decimal("500")):
        p = await make_purchase_with_items(items_count=items_count, item_total=item_total)
        p.status = status
        await db_session.commit()
        return p

    return _make
