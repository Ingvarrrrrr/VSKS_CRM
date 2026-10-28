"""Тесты миграции f5a7c9e1b3d5 (subsidy_calc_versions/account_contour_version)
и кросс-запросного кэша compute_feo_plan_tree/compute_account_contour_org_ids
(владелец, 28.10.2026 — замер прода, см. докстринги feo_plan_tree_cache.py,
account_contour_cache.py, миграции f5a7c9e1b3d5).

a) для КАЖДОЙ из 11 таблиц с триггером — изменение строки увеличивает версию
   нужной субсидии (TestTriggersBumpVersion);
b) защитный тест — набор таблиц, которые РЕАЛЬНО читает compute_feo_plan_tree
   (перехват SQL, before_cursor_execute, та же методика, которой построен
   набор триггеров) ⊆ набор таблиц с триггером (test_probe_subset_of_triggers)
   — новое чтение новой таблицы роняет этот тест;
c) результат с кэшем == без кэша на одних данных (test_cache_matches_uncached);
d) правка позиции → следующий вызов видит новое число; без правок — второй
   вызов не шлёт SQL дерева (test_cache_invalidates_on_write /
   test_cache_hit_no_sql);
e) то же для compute_account_contour_org_ids (TestContourCache).
"""
import re
import uuid
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import event, text

from app.database import engine
from app.services.feo_plan_tree_cache import clear_global_cache as _clear_tree_lru
from app.auth.account_contour_cache import clear_global_cache as _clear_contour_lru

# Набор таблиц с триггером (f5a7c9e1b3d5) — источник истины для теста (b) —
# ИМЕННО этот список создаёт сама миграция; тест (b) сверяет его с тем, что
# реально читает SQL compute_feo_plan_tree.
TABLES_WITH_SUBSIDY_TRIGGER = {
    "subsidies", "feo_categories", "feo_planned_items",
    "plan_excess_approvals", "plan_excess_approval_steps",
    "purchases", "purchase_items", "purchase_approvals",
    "purchase_files", "contract_items", "users",
}


def _tables_from_sql(sql: str) -> set[str]:
    out = set()
    for m in re.finditer(r'(?:FROM|JOIN|UPDATE|INTO)\s+"?([a-zA-Z_][a-zA-Z0-9_]*)"?', sql, re.IGNORECASE):
        out.add(m.group(1).lower())
    return out


class _SqlCapture:
    """Контекст-менеджер — перехватывает все таблицы, затронутые SQL внутри
    `with`, через before_cursor_execute (как и зонд, которым построен набор
    триггеров — см. докстринг миграции)."""

    def __init__(self):
        self.tables: set[str] = set()
        self.count = 0

    def _listener(self, conn, cursor, statement, parameters, context, executemany):
        self.tables.update(_tables_from_sql(statement))
        self.count += 1

    def __enter__(self):
        event.listen(engine.sync_engine, "before_cursor_execute", self._listener)
        return self

    def __exit__(self, *exc):
        event.remove(engine.sync_engine, "before_cursor_execute", self._listener)


@pytest.fixture(autouse=True)
def _reset_global_lru():
    """Каждый тест видит пустой межзапросный LRU — иначе порядок тестов внутри
    одного процесса pytest мог бы дать ложный HIT/MISS."""
    _clear_tree_lru()
    _clear_contour_lru()
    yield
    _clear_tree_lru()
    _clear_contour_lru()


async def _get_version(db_session, subsidy_id: int) -> int:
    """Версия = MAX(id) в append-only subsidy_calc_changes (см. докстринг
    миграции f5a7c9e1b3d5 и subsidy_calc_versions.py — переделка с UPDATE-
    строки на append-only журнал, чтобы INSERT в журнал не держал row lock)."""
    row = (await db_session.execute(
        text("SELECT max(id) FROM subsidy_calc_changes WHERE subsidy_id = :sid"),
        {"sid": subsidy_id},
    )).first()
    assert row is not None and row[0] is not None, (
        f"subsidy_calc_changes не содержит ни одной строки для subsidy_id={subsidy_id}"
    )
    return int(row[0])


async def _get_contour_version(db_session) -> int:
    row = (await db_session.execute(
        text("SELECT max(id) FROM account_contour_changes")
    )).first()
    return int(row[0]) if row and row[0] is not None else 0


# ---------------------------------------------------------------------------
# Фикстуры данных — минимальный граф subsidy → feo_category → feo_planned_item
#                    + purchase → purchase_item/purchase_approval/
#                    purchase_file/contract_item + plan_excess_approval → step
# ---------------------------------------------------------------------------

async def _make_subsidy(db_session, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(name=f"T-{uuid.uuid4().hex[:8]}", year=2026, budget=budget, require_planned_dates=False)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(subsidy_id=subsidy_id, parent_id=None, level=1,
                       name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"), **kwargs)
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, amount=500_000, quantity=2):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(feo_category_id=feo_category_id, name=f"Item-{uuid.uuid4().hex[:8]}",
                          quantity=Decimal(str(quantity)), unit="шт", amount=Decimal(str(amount)), is_active=True)
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_contractor(db_session):
    from app.models.contractor import Contractor
    c = Contractor(name=f"C-{uuid.uuid4().hex[:8]}", inn="1234567890")
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _make_purchase(db_session, subsidy_id, feo_category_id, contractor_id, status="contracted"):
    from app.models.purchase import Purchase
    p = Purchase(subsidy_id=subsidy_id, feo_category_id=feo_category_id,
                 contractor_id=contractor_id, status=status)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _make_item(db_session, purchase_id, feo_category_id=None, feo_planned_item_id=None,
                      quantity=2, unit_price=250_000):
    from app.models.purchase_item import PurchaseItem
    it = PurchaseItem(purchase_id=purchase_id, item_name="Item", quantity=Decimal(str(quantity)),
                       unit_price=Decimal(str(unit_price)), total_price=Decimal(str(quantity * unit_price)),
                       feo_category_id=feo_category_id, feo_planned_item_id=feo_planned_item_id)
    db_session.add(it)
    await db_session.commit()
    await db_session.refresh(it)
    return it


async def _full_graph(db_session):
    """Один полный граф, используемый несколькими тестами."""
    # Без budget на категории: с заданным budget формула «гасит» display на
    # сумме заказа независимо от правки плановой позиции (другая, корректная
    # ветка формулы, НЕ связанная с кэшем — проверено отдельным прогоном
    # _compute_feo_plan_tree_uncached без кэша на тех же данных). Без budget
    # display остаётся Σ plan_manual поддерева, что и нужно тесту ниже.
    s = await _make_subsidy(db_session)
    cat = await _make_category(db_session, s.id)
    fpi = await _make_planned_item(db_session, cat.id)
    contractor = await _make_contractor(db_session)
    purchase = await _make_purchase(db_session, s.id, cat.id, contractor.id)
    item = await _make_item(db_session, purchase.id, feo_category_id=cat.id, feo_planned_item_id=fpi.id)
    return s, cat, fpi, contractor, purchase, item


# ---------------------------------------------------------------------------
# (a) каждая таблица с триггером бампает нужную субсидию
# ---------------------------------------------------------------------------

class TestTriggersBumpVersion:

    @pytest.mark.asyncio
    async def test_subsidies_insert_sets_version(self, db_session):
        # Версия — MAX(id) в общем append-only журнале (не счётчик "с нуля"
        # на эту субсидию), поэтому для НОВОЙ субсидии проверяем только, что
        # строка появилась (version существует), не конкретное число.
        s = await _make_subsidy(db_session)
        assert await _get_version(db_session, s.id) > 0

    @pytest.mark.asyncio
    async def test_subsidies_update_bumps(self, db_session):
        s = await _make_subsidy(db_session)
        v0 = await _get_version(db_session, s.id)
        s.budget = Decimal("2000000")
        await db_session.commit()
        assert await _get_version(db_session, s.id) == v0 + 1

    @pytest.mark.asyncio
    async def test_feo_categories_insert_bumps_subsidy(self, db_session):
        s = await _make_subsidy(db_session)
        v0 = await _get_version(db_session, s.id)
        cat = await _make_category(db_session, s.id)
        assert await _get_version(db_session, s.id) > v0
        v1 = await _get_version(db_session, s.id)
        cat.budget = Decimal("123")
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v1

    @pytest.mark.asyncio
    async def test_feo_planned_items_bumps_owning_subsidy(self, db_session):
        s = await _make_subsidy(db_session)
        cat = await _make_category(db_session, s.id)
        v0 = await _get_version(db_session, s.id)
        fpi = await _make_planned_item(db_session, cat.id)
        assert await _get_version(db_session, s.id) > v0
        v1 = await _get_version(db_session, s.id)
        fpi.amount = Decimal("999")
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v1
        v2 = await _get_version(db_session, s.id)
        await db_session.delete(fpi)
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v2

    @pytest.mark.asyncio
    async def test_purchases_bumps_subsidy(self, db_session):
        s = await _make_subsidy(db_session)
        cat = await _make_category(db_session, s.id)
        contractor = await _make_contractor(db_session)
        v0 = await _get_version(db_session, s.id)
        p = await _make_purchase(db_session, s.id, cat.id, contractor.id)
        assert await _get_version(db_session, s.id) > v0
        v1 = await _get_version(db_session, s.id)
        p.status = "paid"
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v1

    @pytest.mark.asyncio
    async def test_purchase_items_bumps_owning_subsidy(self, db_session):
        s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)
        v0 = await _get_version(db_session, s.id)
        item.quantity = Decimal("5")
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v0

    @pytest.mark.asyncio
    async def test_purchase_approvals_bumps_owning_subsidy(self, db_session):
        from app.models.purchase_approval import PurchaseApproval
        s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)
        v0 = await _get_version(db_session, s.id)
        pa = PurchaseApproval(purchase_id=purchase.id, order_num=0, role_name="Руководитель",
                               approver_full_name="Тест Тестович", status="pending")
        db_session.add(pa)
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v0

    @pytest.mark.asyncio
    async def test_purchase_files_bumps_owning_subsidy(self, db_session):
        from app.models.purchase_file import PurchaseFile
        s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)
        v0 = await _get_version(db_session, s.id)
        pf = PurchaseFile(purchase_id=purchase.id, filename="a.pdf", original_name="a.pdf",
                           filepath="/tmp/a.pdf")
        db_session.add(pf)
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v0

    @pytest.mark.asyncio
    async def test_contract_items_bumps_owning_subsidy(self, db_session):
        from app.models.contract_item import ContractItem
        s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)
        v0 = await _get_version(db_session, s.id)
        ci = ContractItem(purchase_id=purchase.id, name="Товар", quantity=Decimal("1"), unit_price=Decimal("1"))
        db_session.add(ci)
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v0

    @pytest.mark.asyncio
    async def test_plan_excess_approvals_bumps_subsidy(self, db_session):
        from app.models.plan_excess_approval import PlanExcessApproval
        s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)
        v0 = await _get_version(db_session, s.id)
        appr = PlanExcessApproval(feo_category_id=cat.id, subsidy_id=s.id, kind="plan_over_feo_goods",
                                   excess_amount=Decimal("100"), status="pending", mode="sequential")
        db_session.add(appr)
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v0
        return appr

    @pytest.mark.asyncio
    async def test_plan_excess_approval_steps_bumps_owning_subsidy(self, db_session):
        from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
        s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)
        appr = PlanExcessApproval(feo_category_id=cat.id, subsidy_id=s.id, kind="plan_over_feo_goods",
                                   excess_amount=Decimal("100"), status="pending", mode="sequential")
        db_session.add(appr)
        await db_session.commit()
        await db_session.refresh(appr)
        v0 = await _get_version(db_session, s.id)
        step = PlanExcessApprovalStep(approval_id=appr.id, order_num=0, status="pending")
        db_session.add(step)
        await db_session.commit()
        assert await _get_version(db_session, s.id) > v0

    @pytest.mark.asyncio
    async def test_users_full_name_bumps_global_row_only(self, db_session):
        from app.models.user import User
        u = User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x", role="employee", full_name="A B")
        db_session.add(u)
        await db_session.commit()
        await db_session.refresh(u)
        v0 = await _get_version(db_session, 0)
        u.full_name = "Другое Имя"
        await db_session.commit()
        assert await _get_version(db_session, 0) > v0

    @pytest.mark.asyncio
    async def test_truncate_contract_items_bumps_global_row(self, db_session):
        """TRUNCATE не вызывает ROW/STATEMENT-триггеры с transition tables
        (REFERENCING NEW/OLD TABLE) — отдельная пара AFTER TRUNCATE триггеров
        (см. миграцию f5a7c9e1b3d5) обязана бампнуть хотя бы глобальную строку
        subsidy_id=0 (входит в ключ версии любой субсидии в get_subsidy_versions),
        иначе кэш дерева ФЭО остаётся устаревшим после TRUNCATE. contract_items —
        лист без зависимых FK, безопасно чистить внутри db_session (откатывается
        outer_tx фикстуры)."""
        v0 = await _get_version(db_session, 0)
        await db_session.execute(text("TRUNCATE TABLE contract_items"))
        await db_session.commit()
        assert await _get_version(db_session, 0) > v0

    @pytest.mark.asyncio
    async def test_users_unrelated_column_does_not_bump(self, db_session):
        from app.models.user import User
        u = User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x", role="employee", full_name="A B")
        db_session.add(u)
        await db_session.commit()
        await db_session.refresh(u)
        v0 = await _get_version(db_session, 0)
        u.failed_login_count = 3
        await db_session.commit()
        assert await _get_version(db_session, 0) == v0


# ---------------------------------------------------------------------------
# (b) защитный тест — набор таблиц, реально читаемых compute_feo_plan_tree,
#     ⊆ набор таблиц с триггером.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_probe_subset_of_triggers(db_session):
    from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
    from app.models.user import User
    from app.services.feo_plan_tree import _compute_feo_plan_tree_uncached

    s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)

    approver = User(username=f"appr-{uuid.uuid4().hex[:8]}", password_hash="x", role="employee",
                     full_name="Тест Тестович")
    db_session.add(approver)
    await db_session.commit()
    await db_session.refresh(approver)

    appr = PlanExcessApproval(feo_category_id=cat.id, subsidy_id=s.id, kind="plan_over_feo_goods",
                               excess_amount=Decimal("1000"), status="approved", mode="sequential")
    db_session.add(appr)
    await db_session.commit()
    await db_session.refresh(appr)
    step = PlanExcessApprovalStep(approval_id=appr.id, user_id=approver.id, order_num=0, status="approved",
                                   decided_by_user_id=approver.id, decided_at=dt.datetime.now(dt.timezone.utc))
    db_session.add(step)
    await db_session.commit()

    with _SqlCapture() as cap:
        tree = await _compute_feo_plan_tree_uncached(db_session, [s.id])

    assert tree
    missing = cap.tables - TABLES_WITH_SUBSIDY_TRIGGER
    assert not missing, (
        f"compute_feo_plan_tree читает таблицы без триггера на subsidy_calc_changes: "
        f"{sorted(missing)} — добавь триггер в миграции f5a7c9e1b3d5"
    )


@pytest.mark.asyncio
async def test_probe_contour_subset_of_trigger(db_session):
    from app.auth.visibility import _compute_account_contour_org_ids_uncached
    from app.models.organization import Organization

    org = Organization(name=f"O-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    with _SqlCapture() as cap:
        await _compute_account_contour_org_ids_uncached(db_session, org.id)

    assert cap.tables <= {"organizations"}, (
        f"compute_account_contour_org_ids читает таблицы без триггера на "
        f"account_contour_changes: {sorted(cap.tables - {'organizations'})}"
    )


# ---------------------------------------------------------------------------
# (c)/(d) кэш == без кэша, инвалидация по правке, HIT не шлёт SQL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_matches_uncached(db_session):
    from app.services.feo_plan_tree import _compute_feo_plan_tree_uncached, compute_feo_plan_tree
    from app.services.feo_plan_tree_cache import feo_plan_tree_request_scope

    s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)

    uncached = await _compute_feo_plan_tree_uncached(db_session, [s.id])
    with feo_plan_tree_request_scope():
        cached = await compute_feo_plan_tree(db_session, [s.id])

    assert set(uncached.keys()) == set(cached.keys())
    for cid in uncached:
        assert uncached[cid].get("display") == cached[cid].get("display")
        assert uncached[cid].get("plan_manual") == cached[cid].get("plan_manual")
        assert uncached[cid].get("excess_amount") == cached[cid].get("excess_amount")


@pytest.mark.asyncio
async def test_cache_hit_no_sql_until_write(db_session):
    from app.services.feo_plan_tree import compute_feo_plan_tree
    from app.services.feo_plan_tree_cache import feo_plan_tree_request_scope

    s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)

    # Первый вызов — отдельный request-scope (как в проде: один scope на один
    # HTTP-запрос), промах межзапросного LRU, считает и кладёт в кэш.
    with feo_plan_tree_request_scope():
        tree1 = await compute_feo_plan_tree(db_session, [s.id])
    assert tree1[cat.id]["display"] == pytest.approx(500_000.0, rel=1e-6)

    # Второй вызов — НОВЫЙ request-scope (имитируем следующий HTTP-запрос —
    # request-scope кэш пуст), ничего не поменялось → HIT межзапросного LRU,
    # дерево compute_feo_plan_tree НЕ пересчитывается (0 SQL от самой
    # формулы — только 1 легкий запрос версии).
    with _SqlCapture() as cap:
        with feo_plan_tree_request_scope():
            tree2 = await compute_feo_plan_tree(db_session, [s.id])
    assert tree2[cat.id]["display"] == tree1[cat.id]["display"]
    # Единственный ожидаемый SQL — чтение версии (subsidy_calc_changes);
    # дерево НЕ читает feo_planned_items/purchase_items и т.п. повторно.
    assert cap.tables <= {"subsidy_calc_changes"}, (
        f"HIT межзапросного кэша всё равно сходил за данными дерева: {sorted(cap.tables)}"
    )


@pytest.mark.asyncio
async def test_cache_invalidates_on_write(db_session):
    from app.services.feo_plan_tree import compute_feo_plan_tree
    from app.services.feo_plan_tree_cache import feo_plan_tree_request_scope

    s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)

    with feo_plan_tree_request_scope():
        tree1 = await compute_feo_plan_tree(db_session, [s.id])
    assert tree1[cat.id]["display"] == pytest.approx(500_000.0, rel=1e-6)

    # Правка плановой позиции — бампает версию субсидии (test a уже это
    # проверяет отдельно) → следующий вызов обязан увидеть новое число.
    # NB: закупка уже заказала ВСЕ 2 шт плановой позиции — «заказ замещает
    # план» (ФОРМУЛА v2, см. docstring compute_feo_plan_tree), поэтому просто
    # поднять `amount` плановой позиции при полностью выкупленном количестве
    # НЕ двигает display (это умышленное поведение формулы, а не промах
    # кэша — лишнее количество выше заказанного и должно дать новый display).
    fpi.quantity = Decimal("4")
    fpi.amount = Decimal("1000000")
    await db_session.commit()

    with feo_plan_tree_request_scope():
        tree2 = await compute_feo_plan_tree(db_session, [s.id])
    assert tree2[cat.id]["display"] != tree1[cat.id]["display"]
    assert tree2[cat.id]["display"] == pytest.approx(1_000_000.0, rel=1e-6)


@pytest.mark.asyncio
async def test_parallel_transactions_same_subsidy_do_not_block(db_session):
    """Ревью координатора (28.10.2026, ДО применения на проде): первая
    редакция миграции держала ОДНУ UPDATE-строку версии на субсидию — row
    lock до конца транзакции, риск сериализации/deadlock у двух параллельных
    транзакций по одной субсидии. Передел на append-only (MAX(id) в журнале)
    должен означать, что INSERT в журнал НЕ ждёт чужую открытую транзакцию.

    Нужны ДВЕ настоящие независимые транзакции (db_session — один connection,
    этого не покажет) — открываем их сами через engine.connect(), поэтому
    чистим за собой явно (обычный rollback db_session здесь не защитит)."""
    from app.database import engine
    import asyncio

    subsidy_id = None
    conn_a = await engine.connect()
    try:
        tx_a = await conn_a.begin()
        row = await conn_a.execute(text(
            "INSERT INTO subsidies (name, year, budget, require_planned_dates) "
            "VALUES (:n, 2026, 1000000, false) RETURNING id"
        ), {"n": f"ParallelTest-{uuid.uuid4().hex[:8]}"})
        subsidy_id = row.scalar_one()
        # commit фиксирует саму субсидию (иначе сессия B её не увидит для FK
        # feo_categories.subsidy_id) — дальше держим ОТКРЫТОЙ новую транзакцию
        # A на запись в feo_categories той же субсидии, не коммитя её.
        await tx_a.commit()
        tx_a = await conn_a.begin()
        await conn_a.execute(text(
            "INSERT INTO feo_categories (subsidy_id, parent_id, level, name) "
            "VALUES (:sid, NULL, 1, 'A-side')"
        ), {"sid": subsidy_id})
        # tx_a НЕ коммитим и НЕ роллбэчим — остаётся открытой, держит то, что
        # держала бы (в старой схеме) строку версии субсидии.

        conn_b = await engine.connect()
        try:
            tx_b = await conn_b.begin()

            async def _write_b():
                await conn_b.execute(text(
                    "INSERT INTO feo_categories (subsidy_id, parent_id, level, name) "
                    "VALUES (:sid, NULL, 1, 'B-side')"
                ), {"sid": subsidy_id})
                await tx_b.commit()

            # Старая (UPDATE-строка) схема держала бы B на ожидании лока
            # строки версии до commit/rollback A — таймаут тут поймал бы
            # зависание. Append-only схема не должна ждать вовсе.
            await asyncio.wait_for(_write_b(), timeout=3.0)
        finally:
            await conn_b.close()

        await tx_a.rollback()  # A можно откатить — проверка была про лок, не про данные
    finally:
        await conn_a.close()
        if subsidy_id is not None:
            async with engine.begin() as cleanup_conn:
                await cleanup_conn.execute(text("DELETE FROM feo_categories WHERE subsidy_id = :sid"), {"sid": subsidy_id})
                await cleanup_conn.execute(text("DELETE FROM subsidy_calc_changes WHERE subsidy_id = :sid"), {"sid": subsidy_id})
                await cleanup_conn.execute(text("DELETE FROM subsidies WHERE id = :sid"), {"sid": subsidy_id})


@pytest.mark.asyncio
async def test_cache_returns_copy_not_shared_mutable(db_session):
    """Требование задачи: вызывающий код не должен испортить кэш для
    остальных — мутация возвращённого узла не должна протечь в LRU."""
    from app.services.feo_plan_tree import compute_feo_plan_tree
    from app.services.feo_plan_tree_cache import feo_plan_tree_request_scope

    s, cat, fpi, contractor, purchase, item = await _full_graph(db_session)

    with feo_plan_tree_request_scope():
        tree1 = await compute_feo_plan_tree(db_session, [s.id])
    tree1[cat.id]["display"] = -999999.0  # имитируем небрежный вызывающий код

    with feo_plan_tree_request_scope():
        tree2 = await compute_feo_plan_tree(db_session, [s.id])
    assert tree2[cat.id]["display"] != -999999.0


# ---------------------------------------------------------------------------
# (e) то же для compute_account_contour_org_ids
# ---------------------------------------------------------------------------

class TestContourCache:

    @pytest.mark.asyncio
    async def test_organizations_change_bumps_global_version(self, db_session):
        from app.models.organization import Organization
        v0 = await _get_contour_version(db_session)
        org = Organization(name=f"O-{uuid.uuid4().hex[:8]}")
        db_session.add(org)
        await db_session.commit()
        assert await _get_contour_version(db_session) > v0
        v1 = await _get_contour_version(db_session)
        # NB: Organization.name — column_property (производное от Contractor,
        # см. app/models/organization.py) и НЕ отражает реальный UPDATE строки
        # organizations; физическая колонка — `_legacy_name` (тот же DB-столбец
        # "name", отдельный Python-атрибут).
        org._legacy_name = "Переименована"
        await db_session.commit()
        assert await _get_contour_version(db_session) > v1

    @pytest.mark.asyncio
    async def test_truncate_organizations_bumps_contour_version(self, db_session):
        """Та же причина, что у test_truncate_contract_items_bumps_global_row —
        TRUNCATE organizations не вызывает transition-table триггер; AFTER
        TRUNCATE должен бампнуть account_contour_changes. CASCADE безопасен —
        откатывается outer_tx фикстуры db_session, ничего не переживает тест."""
        v0 = await _get_contour_version(db_session)
        await db_session.execute(text("TRUNCATE TABLE organizations CASCADE"))
        await db_session.commit()
        assert await _get_contour_version(db_session) > v0

    @pytest.mark.asyncio
    async def test_cache_matches_uncached(self, db_session):
        from app.models.organization import Organization
        from app.auth.visibility import (
            compute_account_contour_org_ids, _compute_account_contour_org_ids_uncached,
        )
        from app.auth.account_contour_cache import account_contour_request_scope

        root = Organization(name=f"Root-{uuid.uuid4().hex[:8]}")
        db_session.add(root)
        await db_session.commit()
        await db_session.refresh(root)
        child = Organization(name=f"Child-{uuid.uuid4().hex[:8]}", root_org_id=root.id)
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        uncached = await _compute_account_contour_org_ids_uncached(db_session, root.id)
        with account_contour_request_scope():
            cached = await compute_account_contour_org_ids(db_session, root.id)
        assert uncached == cached
        assert child.id in cached

    @pytest.mark.asyncio
    async def test_cache_invalidates_on_write(self, db_session):
        from app.models.organization import Organization
        from app.auth.visibility import compute_account_contour_org_ids
        from app.auth.account_contour_cache import account_contour_request_scope

        root = Organization(name=f"Root-{uuid.uuid4().hex[:8]}")
        db_session.add(root)
        await db_session.commit()
        await db_session.refresh(root)

        with account_contour_request_scope():
            contour1 = await compute_account_contour_org_ids(db_session, root.id)
        assert contour1 == {root.id}

        child = Organization(name=f"Child-{uuid.uuid4().hex[:8]}", root_org_id=root.id)
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        with account_contour_request_scope():
            contour2 = await compute_account_contour_org_ids(db_session, root.id)
        assert child.id in contour2
