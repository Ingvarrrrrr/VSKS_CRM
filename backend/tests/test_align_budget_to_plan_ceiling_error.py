# -*- coding: utf-8 -*-
"""Волна 2, п.14 (владелец): «Приравнять ФЭО к плану» на субсидии ДНР_2026
выдавала INTERNAL_ERROR (correlation_id e188c17c-1656-471a-bc82-48621242b005)
вместо понятного отказа.

Настоящая причина — НЕ бизнес-логика, а sqlalchemy.exc.MissingGreenlet в
app.routers.feo_tree_ops.align_budget_to_plan: когда суммарный план по
субсидии после выравнивания превышает потолок финансирования (ветка
PLAN_OVER_SUBSIDY_CEILING), код делал `await db.rollback()` (это expire'ит
ВСЕ объекты сессии, включая уже загруженный `cat`), а СРАЗУ следом читал
`cat.subsidy_id` внутри тела HTTPException — синхронное обращение к
expired-атрибуту пытается лениво подгрузить её из БД ВНЕ greenlet-контекста
(тот уже закрылся вместе с rollback) и валит MissingGreenlet, который
unhandled_exception_handler (app/errors.py) заворачивает в honest-looking, но
INTERNAL_ERROR/500 вместо запланированного 409 с понятным текстом.

Фикс — читать `cat.subsidy_id` в локальную переменную ДО db.rollback().
Воспроизведено локально на боевых данных (ДНР_2026, subsidy_id=57, ЛЮБАЯ
категория — план по субсидии уже превышал потолок ФЭО) через прямой вызов
эндпоинта на локальном стенде; здесь — минимальный офлайн-репродюсер той же
формы (две корневые категории, суммарный план выше суммарного бюджета),
воспроизводящий именно ветку, где раньше падал MissingGreenlet.

ВТОРОЙ боевой случай (та же субсидия ДНР_2026, 22.09): у субсидии УЖЕ было
накопленное превышение (план дороже потолка ФЭО) ДО нажатия кнопки — «Прочие
расходы» с ручным ФЭО ниже своего плана, «ФОТ» вовсе без ФЭО. «Приравнять» на
«ФОТ» СНИЖАЛО общее превышение (действие подтягивает недостающее
финансирование), но старая проверка сравнивала план-после с потолком-после
БЕЗ учёта того, что было ДО, и отказывала 409 на любом действии, пока
превышение не обнулится целиком — тупик: ни одну категорию без ФЭО было не
приравнять. Фикс (feo_tree_ops.align_budget_to_plan) считает превышение ДО и
ПОСЛЕ и отказывает 409 ТОЛЬКО когда действие УВЕЛИЧИВАЕТ превышение — тесты
test_align_over_ceiling_returns_409_not_500 (увеличивает — 409, как раньше,
но данные фикстуры теперь именно такие, где align УВЕЛИЧИВАЕТ превышение —
см. её докстринг) и test_align_reduces_subsidy_ceiling_excess_succeeds
(уменьшает — 200, воспроизводит боевой тупик ДНР_2026 напрямую).

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять
ПООДИНОЧКЕ: pytest tests/test_align_budget_to_plan_ceiling_error.py::<name>.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.feo_tree_ops import align_budget_to_plan


async def _make_subsidy(db_session, org_id, budget=1_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"AlignCeiling-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    """Категория-корень (level=1, без родителя) — так её budget напрямую
    попадает в calculate_budget_from_categories (потолок субсидии)."""
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, amount, quantity=1, name="Позиция плана"):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal(str(quantity)),
        unit="шт",
        amount=Decimal(str(amount)),
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


def _mk_admin_user(org_id):
    return SimpleNamespace(role="org_admin", id=1, org_id=org_id, _active_org_id=org_id, _uoa_org_ids=[])


@pytest.mark.asyncio
async def test_align_over_ceiling_returns_409_not_500(db_session, test_org):
    """Ветка A: budget=100 000, план 150 000 (свой перекос, не согласован,
    display=150 000 независимо от align — эта ветка не трогается).
    Ветка Б: budget=200 000 (ЗАПАС сверх своего плана), план РОВНО 100 000.

    «Приравнять ФЭО к плану» на Ветке Б снижает её budget с 200 000 до
    100 000 (= её плану) — план субсидии (250 000 = 150 000 + 100 000) НЕ
    меняется (display Ветки Б и так был 100 000, budget=200 000 просто был
    запасом сверху), а вот потолок субсидии ПАДАЕТ с 300 000 (100k+200k) до
    200 000 (100k+100k): превышение растёт с 0 (план 250k ≤ потолок 300k) до
    50 000 (план 250k > потолок 200k) — действие УХУДШАЕТ субсидию (срезает
    запас, который покрывал перекос Ветки A), поэтому обязано вернуть
    HTTPException(409, PLAN_OVER_SUBSIDY_CEILING), а НЕ уронить
    MissingGreenlet/500. Раньше (до фикса MissingGreenlet) здесь падал
    sqlalchemy.exc.MissingGreenlet — тест ловит именно регресс к этому
    падению; после добавления сравнения «до/после» (боевой случай ДНР_2026)
    ловит ещё и то, что рост превышения по-прежнему блокируется."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    subsidy_id = subsidy.id  # снят ДО align — db.rollback() внутри align expire'ит
    # ВСЕ объекты этой сессии (в т.ч. subsidy теста, не только cat из самого
    # роутера), обращение к атрибуту ПОСЛЕ него — та же ловушка, что чинит этот
    # тест на стороне приложения.
    cat_a = await _make_category(db_session, subsidy.id, name="Ветка A (перебор)", budget=Decimal("100000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Ветка Б (запас снимается)", budget=Decimal("200000"))
    cat_b_id = cat_b.id
    await _make_planned_item(db_session, cat_a.id, amount=150_000)
    await _make_planned_item(db_session, cat_b.id, amount=100_000)

    user = _mk_admin_user(test_org.id)

    with pytest.raises(HTTPException) as exc_info:
        await align_budget_to_plan(cat_b_id, db=db_session, current_user=user)

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert isinstance(detail, dict), f"ожидался структурированный 409, получено: {detail!r}"
    assert detail.get("code") == "PLAN_OVER_SUBSIDY_CEILING", detail
    assert detail.get("subsidy_id") == subsidy_id, "subsidy_id обязан попасть в тело ошибки (сам баг был именно тут)"
    # Превышение ДО (0 — план 250к ≤ потолок 300к) должно быть строго меньше
    # превышения ПОСЛЕ (50 000 — план 250к > потолок 200к после снижения
    # budget Ветки Б) — именно это и есть критерий блокировки теперь.
    assert detail.get("over_before") == pytest.approx(0.0), detail
    assert detail.get("over_after") == pytest.approx(50_000.0), detail
    assert detail["over_after"] > detail["over_before"], "align обязан быть заблокирован именно потому, что УВЕЛИЧИВАЕТ превышение"

    # Сессия обязана остаться рабочей ПОСЛЕ отказа — если фикс регрессировал
    # обратно к MissingGreenlet где-то ещё, следующий запрос к БД в этом же
    # тесте тоже упадёт. db_session.refresh() — явный await, не бьётся о ту же
    # ловушку (в отличие от голого обращения к атрибуту expired-объекта выше).
    cat_b_after = await db_session.get(type(cat_a), cat_b_id)
    await db_session.refresh(cat_b_after)
    assert cat_b_after.budget == Decimal("200000"), "budget обязан остаться прежним — align откатился (db.rollback)"


@pytest.mark.asyncio
async def test_align_over_ceiling_error_lists_offending_root_category(db_session, test_org):
    """Тот же сценарий, что и test_align_over_ceiling_returns_409_not_500 —
    409-текст обязан явно назвать корневую категорию, у которой план выше
    её ФЭО (Ветка A: план 150 000 / ФЭО 100 000), а не только общие цифры по
    субсидии — владелец должен видеть, КУДА именно смотреть."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_a = await _make_category(db_session, subsidy.id, name="Ветка A (перебор)", budget=Decimal("100000"))
    cat_b = await _make_category(db_session, subsidy.id, name="Ветка Б (запас снимается)", budget=Decimal("200000"))
    cat_b_id = cat_b.id
    await _make_planned_item(db_session, cat_a.id, amount=150_000)
    await _make_planned_item(db_session, cat_b.id, amount=100_000)

    user = _mk_admin_user(test_org.id)

    with pytest.raises(HTTPException) as exc_info:
        await align_budget_to_plan(cat_b_id, db=db_session, current_user=user)

    detail = exc_info.value.detail
    assert detail.get("code") == "PLAN_OVER_SUBSIDY_CEILING", detail
    over_lines = detail.get("over_root_categories") or []
    assert any("Ветка A (перебор)" in line for line in over_lines), over_lines
    assert any("150,000.00" in line and "100,000.00" in line for line in over_lines), over_lines
    assert "Ветка A (перебор)" in detail.get("message", ""), detail.get("message")


@pytest.mark.asyncio
async def test_align_reduces_subsidy_ceiling_excess_succeeds(db_session, test_org):
    """Прямой репродюсер боевого тупика ДНР_2026 (22.09): у субсидии УЖЕ
    накоплено превышение (Ветка X: ФЭО 280 000 < план 300 000, не
    согласовано, не трогается этим align) ДО нажатия кнопки. Ветка Y — БЕЗ
    ФЭО вовсе (budget=None), план 330 000. «Приравнять ФЭО к плану» на
    Ветке Y ДОБАВЛЯЕТ недостающее финансирование (budget становится = 330 000)
    — суммарный план субсидии не меняется (630к до/после: 300к+330к), а
    потолок РАСТЁТ с 280к до 610к (280к+330к): превышение ПАДАЕТ с 350 000
    (630к−280к) до 20 000 (630к−610к). Действие УЛУЧШАЕТ субсидию — обязано
    пройти 200, а не быть заблокированным (это и есть боевой тупик: на
    субсидии с накопленным превышением ни одну категорию без ФЭО было не
    приравнять, хотя это единственный способ превышение снизить)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_x = await _make_category(db_session, subsidy.id, name="Ветка X (свой перекос)", budget=Decimal("280000"))
    cat_y = await _make_category(db_session, subsidy.id, name="Ветка Y (без ФЭО)", budget=None)
    cat_y_id = cat_y.id
    await _make_planned_item(db_session, cat_x.id, amount=300_000)
    await _make_planned_item(db_session, cat_y.id, amount=330_000)

    user = _mk_admin_user(test_org.id)

    result = await align_budget_to_plan(cat_y_id, db=db_session, current_user=user)

    assert result["id"] == cat_y_id
    assert result["subsidy_id"] == subsidy.id
    assert result["old_budget"] is None
    assert result["new_budget"] == pytest.approx(330_000.0)
    assert result["subsidy_over_before"] == pytest.approx(350_000.0), result
    assert result["subsidy_over_after"] == pytest.approx(20_000.0), result
    assert result["subsidy_over_after"] < result["subsidy_over_before"], "превышение обязано СНИЗИТЬСЯ — иначе это тот же тупик ДНР_2026"

    cat_y_after = await db_session.get(type(cat_x), cat_y_id)
    await db_session.refresh(cat_y_after)
    assert cat_y_after.budget == Decimal("330000")


@pytest.mark.asyncio
async def test_align_within_ceiling_succeeds(db_session, test_org):
    """Контроль: когда потолок НЕ превышен, «Приравнять ФЭО к плану» проходит
    и возвращает новый budget — фикс не должен был сломать штатный путь."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, name="Ветка без превышения", budget=None)
    await _make_planned_item(db_session, cat.id, amount=42_000)

    user = _mk_admin_user(test_org.id)
    result = await align_budget_to_plan(cat.id, db=db_session, current_user=user)

    assert result["id"] == cat.id
    assert result["subsidy_id"] == subsidy.id
    assert result["old_budget"] is None
    assert result["new_budget"] == pytest.approx(42_000.0)
