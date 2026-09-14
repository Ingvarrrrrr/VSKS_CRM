"""Раздельные числа по ФЭО и по внутреннему плану у плановой позиции
(FeoPlannedItem.feo_quantity/feo_unit_price/feo_amount, владелец, 2026-09-14).

КОНТЕКСТ: жалоба владельца — «здесь явно не хватает полей для ввода, надо
отдельно если я включил по ФЭО, и отдельно для Внутреннего плана, это нужно
если ФЭО и внутренний план разнятся». Решение по опросу: quantity/unit_price/
amount (существующие поля) ОСТАЮТСЯ «планом» — единственным источником для
compute_feo_plan_tree/assert_no_unapproved_excess/assert_tz_not_over_plan
(ПРАВИЛО №6 — вторая формула дерева/контроля здесь НЕ заводится).
feo_quantity/feo_unit_price/feo_amount — второй, независимый комплект ТОЛЬКО
для отображения рядом «для сверки», ни в одной формуле не участвует.

Эти тесты подтверждают именно это разделение — см. миграцию
c2d4e6f8a0b2_feo_planned_item_feo_split.py и докстринг модели
(backend/app/models/feo_planned_item.py).

Гонять ПО ОДНОМУ УЗЛУ за вызов pytest в контейнере (флейк pytest-asyncio
«different loop» при параллельном запуске нескольких async-тестов, см.
project_pytest_asyncio_loop_flake — известная особенность этого проекта).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text as sql_text

from app.services.feo_plan import compute_feo_plan_tree, assert_no_unapproved_excess


async def _make_subsidy(db_session, org_id, budget=8_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, parent_id=None, **kwargs):
    from app.models.feo_category import FeoCategory
    level = 1 if parent_id is None else 2
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=parent_id,
        level=level,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, **kwargs):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=kwargs.pop("name", "Позиция плана"),
        unit="шт",
        is_active=True,
        **kwargs,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


@pytest.mark.asyncio
async def test_both_flags_different_numbers_tree_uses_internal(db_session, test_org):
    """Обе галочки стоят, числа расходятся — владелец: «Суммой плана в дереве, в
    остатках и в контроле превышения считается ВНУТРЕННИЙ ПЛАН». quantity/
    unit_price/amount (внутренний план) = 2 × 100 000 = 200 000. feo_quantity/
    feo_unit_price/feo_amount (по ФЭО, для сверки) = 2 × 150 000 = 300 000 —
    ЗАВЕДОМО другое число. Дерево обязано посчитать план по 200 000, а не по
    300 000 — иначе feo_amount начал бы незаметно участвовать в формуле,
    которую владелец просил не трогать."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(
        db_session, subsidy.id,
        name="Лист — обе галочки, числа расходятся",
        budget=Decimal("1000000"),
    )
    await _make_planned_item(
        db_session, leaf.id,
        is_feo_breakdown=True, is_internal_plan=True,
        quantity=Decimal("2"), unit_price=Decimal("100000"), amount=Decimal("200000"),
        feo_quantity=Decimal("2"), feo_unit_price=Decimal("150000"), feo_amount=Decimal("300000"),
    )

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 200_000.0, (
        "план дерева обязан считаться по внутреннему плану (amount=200000), "
        "а не по числу ФЭО (feo_amount=300000)"
    )
    assert node["display"] == 200_000.0
    assert node["excess_amount"] == 0.0, "200000 < budget 1000000 — превышения быть не должно"


@pytest.mark.asyncio
async def test_only_internal_flag_as_before(db_session, test_org):
    """Только «Внутренний план» — поведение НЕ изменилось: план = amount, как и
    до появления feo_quantity/feo_unit_price/feo_amount (они остаются NULL —
    диалоги не показывают второй набор полей для единственной галочки)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(
        db_session, subsidy.id,
        name="Лист — только внутренний план",
        budget=Decimal("1000000"),
    )
    fpi = await _make_planned_item(
        db_session, leaf.id,
        is_feo_breakdown=False, is_internal_plan=True,
        quantity=Decimal("3"), unit_price=Decimal("50000"), amount=Decimal("150000"),
    )
    assert fpi.feo_quantity is None and fpi.feo_unit_price is None and fpi.feo_amount is None

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 150_000.0
    assert node["display"] == 150_000.0


@pytest.mark.asyncio
async def test_only_feo_flag_value_is_plan(db_session, test_org):
    """Только «По ФЭО» (is_internal_plan=False), второй комплект не заполнен —
    задача, тестовый узел: «только фэошная → фэошное значение и есть план».
    Единственный набор полей, введённый в диалоге (см. п.3 задачи: «Когда
    отмечена только одна галочка — один комплект полей, как сейчас»), уходит в
    quantity/unit_price/amount — то же самое число, что дерево читает как
    план. feo_amount остаётся NULL — нет отдельного «числа по ФЭО», отличного
    от плана, и это ожидаемо (не второй ввод, а один и тот же)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(
        db_session, subsidy.id,
        name="Лист — только по ФЭО",
        budget=Decimal("1000000"),
    )
    fpi = await _make_planned_item(
        db_session, leaf.id,
        is_feo_breakdown=True, is_internal_plan=False,
        quantity=Decimal("4"), unit_price=Decimal("25000"), amount=Decimal("100000"),
    )
    assert fpi.feo_amount is None, "второй комплект не введён — единственное число и есть план"

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 100_000.0, "фэошное (единственное введённое) значение и есть план"
    assert node["display"] == 100_000.0


@pytest.mark.asyncio
async def test_old_item_backfill_makes_both_sets_equal(db_session, test_org):
    """«Старая позиция после миграции имеет оба комплекта равными» — здесь
    воспроизводится сам БЭКФИЛЛ миграции c2d4e6f8a0b2_feo_planned_item_feo_split
    (тот же SQL, что и в её upgrade()) на строке, заведённой ДО правки (feo_*
    NULL, как у любой позиции старше этой миграции), и проверяется результат:
    оба комплекта чисел совпадают до копейки, «цифры никуда не поехали»
    (дословное решение владельца)."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(db_session, subsidy.id, name="Лист — старая позиция")
    fpi = await _make_planned_item(
        db_session, leaf.id,
        is_feo_breakdown=True, is_internal_plan=True,
        quantity=Decimal("7"), unit_price=Decimal("11000"), amount=Decimal("77000"),
    )
    assert fpi.feo_quantity is None and fpi.feo_unit_price is None and fpi.feo_amount is None

    # Тот же UPDATE, что и в migrate upgrade() (backend/alembic/versions/
    # c2d4e6f8a0b2_feo_planned_item_feo_split.py) — не второй расчёт, дословная
    # копия SQL миграции.
    await db_session.execute(sql_text("""
        UPDATE feo_planned_items
        SET feo_quantity = quantity,
            feo_unit_price = unit_price,
            feo_amount = amount
        WHERE feo_amount IS NULL AND feo_quantity IS NULL AND feo_unit_price IS NULL
          AND id = :id
    """), {"id": fpi.id})
    await db_session.commit()
    await db_session.refresh(fpi)

    assert fpi.feo_quantity == fpi.quantity == Decimal("7")
    assert fpi.feo_unit_price == fpi.unit_price == Decimal("11000")
    assert fpi.feo_amount == fpi.amount == Decimal("77000")


@pytest.mark.asyncio
async def test_feo_not_set_does_not_require_excess_check(db_session, test_org):
    """«Фэошное не задано → превышение по позиции не требуется» — задача,
    п.6: сравнение «план над ФЭО» на уровне позиции — ТОЛЬКО отображение
    («число по ФЭО стоит рядом для сверки», дословно владелец), второй
    блокирующий механизм сознательно НЕ заводится (ни compute_feo_plan_tree,
    ни assert_no_unapproved_excess/assert_tz_not_over_plan не читают
    feo_quantity/feo_unit_price/feo_amount вообще). Позиция с is_feo_breakdown
    и feo_amount=NULL, внутренний план (amount) в рамках budget категории —
    assert_no_unapproved_excess обязан пройти без исключения: отсутствие
    числа по ФЭО не порождает никакого превышения, потому что для него просто
    нет соответствующей проверки."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=1_000_000)
    leaf = await _make_category(
        db_session, subsidy.id,
        name="Лист — по ФЭО без числа",
        budget=Decimal("1000000"),
    )
    fpi = await _make_planned_item(
        db_session, leaf.id,
        is_feo_breakdown=True, is_internal_plan=False,
        quantity=Decimal("1"), unit_price=Decimal("500000"), amount=Decimal("500000"),
    )
    assert fpi.feo_amount is None

    # Не должно бросить HTTPException — план (500000) укладывается в budget
    # (1000000), и отсутствие feo_amount не добавляет никакой новой проверки.
    warnings = await assert_no_unapproved_excess(db_session, leaf.id)
    assert warnings == []

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])
    node = tree[leaf.id]
    assert node["plan_manual"] == 500_000.0
    assert node["excess_amount"] == 0.0
