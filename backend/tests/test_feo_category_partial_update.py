"""Дефект 2026-10-02 (прод, найден при разрезании записи дерева категорий ФЭО
в app/services/feo_category_write.py): инлайн-правка одного поля категории с
фронта (useFeoTreeDnd.ts::saveInlineBudget/saveInlineQty/saveInlineAmt) шлёт
PUT БЕЗ description/feo_quantity/feo_unit/feo_amount/plan_source/
manual_plan_amount — раньше update_category присваивал ВСЕ поля
FeoCategoryCreate безусловно, молча стирая эти поля и сбрасывая plan_source
в дефолт 'planned_items'.

Фикс: feo_category_write.update_category правит ТОЛЬКО поля, реально
присутствующие в теле запроса (`category_data.model_fields_set` через
`model_dump(exclude_unset=True)`). Тест бьёт по сервису напрямую (как
test_feo_history.py), не по HTTP-ручке — поведение гейтов прав здесь не
проверяется (это test_feo_category_write_gate.py), только сама запись.

Фикстуры — по образцу test_feo_history.py/test_feo_collapse_category_to_item.py
(реальная БД через db_session/test_org/test_user, откатывается тестовой
транзакцией)."""
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.schemas.schemas import FeoCategoryCreate
from app.services import feo_category_write


async def _make_subsidy(db_session, org_id):
    import uuid
    s = Subsidy(name=f"TestSubsidy-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_full_category(db_session, subsidy_id):
    """Категория со ВСЕМИ интересующими полями заполненными — именно те поля,
    которые дефект стирал."""
    cat = FeoCategory(
        subsidy_id=subsidy_id, level=1, name="Направление теста",
        description="Описание направления",
        budget=Decimal("1000"),
        feo_quantity=Decimal("10"), feo_unit="шт", feo_amount=Decimal("100"),
        planned_quantity=Decimal("10"), planned_amount=Decimal("100"),
        unit="шт",
        plan_source="manual_sum", manual_plan_amount=Decimal("999"),
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


@pytest.mark.asyncio
async def test_partial_put_preserves_untouched_fields(db_session, test_org, test_user):
    """PUT только с {name, subsidy_id, budget} — ВСЕ остальные поля (описание,
    ФЭО-количество/сумма, ручной план, режим расчёта) обязаны остаться как
    были в БД — это и есть защита от дефекта."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_full_category(db_session, subsidy.id)

    partial = FeoCategoryCreate.model_validate({
        "name": cat.name, "subsidy_id": cat.subsidy_id, "budget": 500,
    })
    assert partial.model_fields_set == {"name", "subsidy_id", "budget"}

    result = await feo_category_write.update_category(db_session, test_user, cat, partial)
    await db_session.commit()
    await db_session.refresh(cat)

    assert result["warning"] is None
    assert float(cat.budget) == 500.0
    # Поля, которых не было в теле запроса — не тронуты.
    assert cat.description == "Описание направления"
    assert float(cat.feo_quantity) == 10.0
    assert cat.feo_unit == "шт"
    assert float(cat.feo_amount) == 100.0
    assert float(cat.planned_quantity) == 10.0
    assert float(cat.planned_amount) == 100.0
    assert cat.plan_source == "manual_sum"
    assert float(cat.manual_plan_amount) == 999.0


@pytest.mark.asyncio
async def test_full_put_with_explicit_null_still_clears_field(db_session, test_org, test_user):
    """Диалог FeoCategoryDialog.vue шлёт ВСЕ поля явно (buildCategoryFullPayload)
    — в т.ч. description: null для очищенного описания. exclude_unset НЕ
    должен мешать этому: поле, присланное явно со значением null, обязано
    примениться (очистить), а не остаться как «не тронутое»."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_full_category(db_session, subsidy.id)

    full_payload = {
        "parent_id": None,
        "subsidy_id": cat.subsidy_id,
        "name": cat.name,
        "code": None,
        "appendix": None,
        "is_active": True,
        "description": None,  # явная очистка
        "budget": float(cat.budget),
        "feo_quantity": float(cat.feo_quantity),
        "feo_unit": cat.feo_unit,
        "feo_amount": float(cat.feo_amount),
        "planned_quantity": float(cat.planned_quantity),
        "planned_amount": float(cat.planned_amount),
        "unit": cat.unit,
        "plan_source": cat.plan_source,
        "manual_plan_amount": float(cat.manual_plan_amount),
    }
    full = FeoCategoryCreate.model_validate(full_payload)
    assert "description" in full.model_fields_set

    await feo_category_write.update_category(db_session, test_user, cat, full)
    await db_session.commit()
    await db_session.refresh(cat)

    assert cat.description is None
    # Остальные поля, присланные с теми же значениями, что и были — не
    # изменились по сути (полный payload — не регрессия обычного пути).
    assert cat.plan_source == "manual_sum"
    assert float(cat.manual_plan_amount) == 999.0


@pytest.mark.asyncio
async def test_partial_put_plan_pair_validated_against_merged_values(db_session, test_org, test_user):
    """Инлайн-правка ТОЛЬКО planned_amount не должна ложно валиться 409 —
    проверка «пара обязана биться» обязана сравнивать с УЖЕ СУЩЕСТВУЮЩИМ
    planned_quantity из БД (слитым значением), а не с отсутствующим в теле
    запроса (иначе любая инлайн-правка суммы при наличии валидной пары упала
    бы 409, т.к. сырое category_data.planned_quantity было бы None)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_full_category(db_session, subsidy.id)  # planned_quantity=10, planned_amount=100 — валидная пара

    partial = FeoCategoryCreate.model_validate({
        "name": cat.name, "subsidy_id": cat.subsidy_id, "planned_amount": 200,
    })
    result = await feo_category_write.update_category(db_session, test_user, cat, partial)
    await db_session.commit()
    await db_session.refresh(cat)

    assert result["warning"] is None
    assert float(cat.planned_amount) == 200.0
    assert float(cat.planned_quantity) == 10.0  # не тронуто
