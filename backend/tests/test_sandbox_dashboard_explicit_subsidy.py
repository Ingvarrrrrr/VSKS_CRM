"""routers/dashboard.py::_apply_purchase_org_filter — правило владельца
(план breezy-mixing-lovelace.md, Часть Б, правка после риска): «в самой
субсидии-копии все цифры считаются как обычно». Песочницу исключать ТОЛЬКО
когда запрос НЕ ограничен явно конкретными субсидиями — агрегат «дашборд без
фильтра» копию не подмешивает, но тот же виджет, вызванный с явным
subsidy_id копии (карточка самой копии), обязан вернуть её настоящие числа,
не ноль.

Тест через db_session (реальная БД, транзакция с откатом, см. conftest.py).
"""
import uuid
from decimal import Decimal

from sqlalchemy import select, func

from app.models.subsidy import Subsidy
from app.models.purchase import Purchase
from app.routers.dashboard import _apply_purchase_org_filter
from app.services.subsidy_copy import create_sandbox_copy


async def _make_subsidy(db_session) -> Subsidy:
    subsidy = Subsidy(name=f"Тест-субсидия-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def _sum_contract_price(db_session, apply_filter) -> Decimal:
    q = select(func.coalesce(func.sum(Purchase.contract_price), 0))
    q = apply_filter(q)
    return (await db_session.execute(q)).scalar() or Decimal("0")


async def test_sandbox_excluded_without_explicit_filter_but_counted_with_it(db_session):
    source = await _make_subsidy(db_session)
    purchase = Purchase(
        subsidy_id=source.id, item_name="Закупка оригинала",
        status="paid", contract_price=Decimal("777.00"),
    )
    db_session.add(purchase)
    await db_session.commit()

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    copy_purchase = (await db_session.execute(
        select(Purchase).where(Purchase.subsidy_id == copy.id)
    )).scalars().first()
    assert copy_purchase is not None
    assert copy_purchase.contract_price == Decimal("777.00")

    # 1. «Дашборд без фильтра» (нет org-ограничения, нет явного subsidy_id) —
    # копия НЕ входит в сумму: должна остаться ровно сумма оригинала. Доп.
    # .where(subsidy_id IN {source, copy}) — только чтобы не считать всю
    # общую БД проекта (там реальных contract_price хватает), саму ветку
    # org_ids=None это не меняет (_apply_purchase_org_filter видит её как
    # обычный .where(), не как explicit_subsidy_ids).
    total_no_filter = await _sum_contract_price(
        db_session,
        lambda q: _apply_purchase_org_filter(
            q.where(Purchase.subsidy_id.in_({source.id, copy.id})), None, org_ids=None,
        ),
    )
    assert total_no_filter == Decimal("777.00")

    # 2. Тот же виджет, но запрос явно ограничен субсидией-КОПИЕЙ (карточка
    # самой копии: ?subsidy_id=<копия>) — её закупки ДОЛЖНЫ учитываться.
    total_copy_explicit = await _sum_contract_price(
        db_session,
        lambda q: _apply_purchase_org_filter(
            q, None, org_ids=None, explicit_subsidy_ids={copy.id},
        ).where(Purchase.subsidy_id == copy.id),
    )
    # 3. Для сравнения — тот же виджет на оригинале с явным subsidy_id=оригинал.
    total_source_explicit = await _sum_contract_price(
        db_session,
        lambda q: _apply_purchase_org_filter(
            q, None, org_ids=None, explicit_subsidy_ids={source.id},
        ).where(Purchase.subsidy_id == source.id),
    )

    assert total_copy_explicit == Decimal("777.00")
    assert total_copy_explicit == total_source_explicit


async def test_sandbox_excluded_from_broad_visibility_subsidy_ids_set(db_session):
    """Та же правка, но через ветку subsidy_ids= (видимость, не org_ids) —
    напр. scope=dashboard: широкий видимый набор, включающий копию, всё
    равно не должен подмешивать её БЕЗ явного запроса именно этой субсидии."""
    source = await _make_subsidy(db_session)
    purchase = Purchase(
        subsidy_id=source.id, item_name="Закупка оригинала 2",
        status="paid", contract_price=Decimal("500.00"),
    )
    db_session.add(purchase)
    await db_session.commit()

    copy = await create_sandbox_copy(db_session, source)
    await db_session.commit()

    visible_ids = {source.id, copy.id}  # копия ВИДИМА, но не запрошена явно

    total_visible_no_explicit = await _sum_contract_price(
        db_session,
        lambda q: _apply_purchase_org_filter(q, None, subsidy_ids=visible_ids),
    )
    assert total_visible_no_explicit == Decimal("500.00")  # только оригинал

    total_visible_with_explicit = await _sum_contract_price(
        db_session,
        lambda q: _apply_purchase_org_filter(
            q, None, subsidy_ids=visible_ids, explicit_subsidy_ids={copy.id},
        ).where(Purchase.subsidy_id == copy.id),
    )
    assert total_visible_with_explicit == Decimal("500.00")  # теперь копия учтена
