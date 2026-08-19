import os

# app.config.Settings requires SECRET_KEY (no hardcoded default — see
# backend/app/config.py). Give the test suite a throwaway key so pytest
# works out of the box without a real .env; never used outside tests.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")

import pytest
import pytest_asyncio
from decimal import Decimal
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Test isolation (2026-08-18): db_session used to commit straight into
# app.database.async_session — the SAME database the local backend container
# uses. Every `.commit()` in a factory fixture (test_org/test_user/...) was a
# REAL commit, so a pytest run left rows behind forever (no teardown ever ran
# to undo them). This bit us for real: three "Great Wall POER" purchase_items
# (8 380 000 each) from test_feo_plan_tree_scenarios.py were mistaken for
# production data corruption during an unrelated FK audit.
#
# Fix: wrap each test in ONE outer transaction on a dedicated connection and
# roll it back at teardown, no matter how many times test code calls
# `.commit()`. `join_transaction_mode="create_savepoint"` (SQLAlchemy 2.0)
# makes the session's `.commit()` release a SAVEPOINT instead of ending the
# real transaction — so existing fixtures/tests that call `.commit()` keep
# working unmodified, but nothing survives past `outer_tx.rollback()`.
#
# Why not a separate test database/schema instead: the backend only reaches
# Postgres at `db:5432` inside the compose network (no host port is
# published, by design — see security baseline), so tests already run
# in-container against the one real dev DB. Standing up a second schema would
# need its own migration bootstrap/teardown per run and would stop tests from
# exercising the actual FK/constraint behaviour of the live schema (exactly
# what the FK-integrity migrations in this session are about). Transaction
# rollback gets the same "leaves nothing behind" guarantee for free, on the
# schema that's actually representative.
#
# `client` now depends on `db_session` and overrides `get_db` to hand out the
# SAME session/connection: request handlers (which normally open their own
# session via get_db()) and directly-created fixtures (test_user, test_org,
# ...) need to see each other's uncommitted rows within the one test
# transaction — otherwise HTTP requests made through `client` would look at a
# separate real connection and simply not see data created via `db_session`
# in the same test (auth_headers/test_user would 401 against a real login).
#
# Known limitation (not fixed here, out of scope): a handful of modules
# (app/routers/chat.py, app/routers/publications.py,
# app/routers/telegram_webhook.py) import `async_session` directly at module
# level instead of going through `get_db()`, so they bypass this override and
# would still hit the real engine. No current test exercises those paths.
#
# Known unrelated flake (do not "fix" by touching this): async tests fail
# with "attached to a different loop" when run together in bulk; pytest.ini
# uses asyncio_mode=auto with the pytest-asyncio default (a fresh event loop
# per test function) against one process-wide `engine`/connection pool. Not a
# regression from this change — run suspect files individually.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Real AsyncSession bound to a per-test connection + outer transaction.

    Everything the test (or any fixture/request sharing this session, see
    `client`) commits lives inside a SAVEPOINT within that one transaction.
    Teardown always rolls the outer transaction back — no row ever survives
    the test, regardless of how many `.commit()` calls happened.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from app.database import engine

    connection = await engine.connect()
    outer_tx = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        await outer_tx.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    """HTTPX AsyncClient wired to the FastAPI app via ASGITransport.

    Overrides get_db() to hand out db_session's own connection-bound session,
    so HTTP requests made through this client participate in the same outer
    transaction/rollback as db_session (see module docstring above) — needed
    for auth_headers/test_user (created via db_session) to be visible to
    request handlers, and for anything a request writes to be rolled back too.
    """
    from app import app  # noqa: WPS433 — deferred to avoid import-time side effects
    from app.database import get_db

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


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
    # No manual cleanup needed here — db_session's outer transaction rollback
    # (see module docstring) discards everything created via this factory.

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
    """Phase 27.1: Factory for creating a minimal Purchase in tests.

    Purchase has no org_id column (that's a data-issue bug — see
    purchase_approvals.py::_resolve_purchase_org_id, org comes from the
    purchase's subsidy, not its own column) — don't pass org_id to the
    model. test_org is kept as a dependency so callers get an org to attach
    via subsidy_id if the test needs one.
    """
    from app.models.purchase import Purchase

    async def _make(status="planned", **kwargs):
        p = Purchase(
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
    """Phase 27.1: Factory for creating a Purchase with PurchaseItems.

    See make_purchase above — Purchase has no org_id column.
    """
    from app.models.purchase import Purchase
    from app.models.purchase_item import PurchaseItem

    async def _make(status="planned", items_count=2, item_total=Decimal("500")):
        p = Purchase(
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
