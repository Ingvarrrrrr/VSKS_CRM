"""Владелец (21.09, раздел W2 плана corrections-21-09.md): у плановой позиции
ФЭО обязано быть поле «Тип» (товар/услуга/работа) с автозаполнением из
каталога товаров; если пользователь ЗАДАЛ тип, а у товара каталога он пуст
или отличается — тип обязан записаться обратно в товар.

Проверяет ЕДИНЫЙ источник (ПРАВИЛО №6) — app/services/item_types.py:
  1. normalize_item_type — та же нормализация, что раньше жила прямо в
     app/routers/feo_planned_items.py (реэкспорт оттуда продолжает работать,
     см. test_reexport_from_router ниже).
  2. apply_item_type_to_product — единственная точка записи Product.item_kind
     из плановой позиции.
  3. PUT /feo-planned-items/{id} с sync_product_kind=true действительно меняет
     Product.item_kind (через реальный роутер, минуя FastAPI DI, тот же приём,
     что и в остальных тестах этого модуля — см. test_planned_item_link_rules.py).
  4. GET /feo-planned-items/product-hint отдаёт item_kind товара.

Гонять по одному узлу за вызов pytest в контейнере (флейк pytest-asyncio
«different loop» при параллельном запуске async-тестов — project_pytest_asyncio_loop_flake).
"""
import uuid
from decimal import Decimal

import pytest

from app.services.item_types import ITEM_TYPES, apply_item_type_to_product, normalize_item_type


# ---------------------------------------------------------------------------
# 1) normalize_item_type — чистая функция, без БД
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Товар", "товар"),
    ("товар", "товар"),
    ("  Товар  ", "товар"),
    ("Услуга", "услуга"),
    ("Услуги", "услуга"),
    ("услуг", "услуга"),
    ("Работа", "работа"),
    ("раб.", "работа"),
    ("работы", "работа"),
    (None, None),
    ("", None),
    ("   ", None),
    ("мусор", None),
    ("непонятное значение", None),
])
def test_normalize_item_type(raw, expected):
    assert normalize_item_type(raw) == expected


def test_item_types_constant_matches_normalizer_outputs():
    """ITEM_TYPES — единственный источник допустимых значений; каждое
    значение, которое отдаёт normalize_item_type, обязано быть в нём (иначе
    apply_item_type_to_product молча откажется его применить)."""
    for raw in ("товар", "услуга", "работа"):
        assert normalize_item_type(raw) in ITEM_TYPES


def test_reexport_from_router_is_identical_function():
    """app.routers.feo_planned_items.normalize_item_type — тот же объект, что
    и app.services.item_types.normalize_item_type (реэкспорт, не копия) —
    app/services/feo_import_apply.py и app/services/item_type_split.py
    импортируют его из роутера и не должны были заметить перенос."""
    from app.routers.feo_planned_items import normalize_item_type as reexported
    assert reexported is normalize_item_type


# ---------------------------------------------------------------------------
# 2) apply_item_type_to_product — единственная точка записи Product.item_kind
# ---------------------------------------------------------------------------

async def _make_product(db_session, item_kind="товар"):
    """item_kind=None — колонка Product.item_kind объявлена с Python-side
    default="товар" (app/models/product.py): явный None в конструкторе всё
    равно уходит в БД как "товар" (SQLAlchemy подставляет default, а не NULL) —
    поэтому для по-настоящему пустого item_kind обнуляем сырым UPDATE ПОСЛЕ
    вставки, а не через конструктор."""
    from app.models.product import Product
    p = Product(name=f"Товар-{uuid.uuid4().hex[:8]}", category="Прочее", item_kind=item_kind or "товар")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    if item_kind is None:
        from sqlalchemy import text as sql_text
        await db_session.execute(sql_text("UPDATE products SET item_kind = NULL WHERE id = :id"), {"id": p.id})
        await db_session.commit()
        await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_apply_updates_empty_item_kind(db_session):
    product = await _make_product(db_session, item_kind=None)
    assert product.item_kind is None
    changed = await apply_item_type_to_product(db_session, product.id, "работа")
    assert changed is True
    # apply_item_type_to_product НЕ коммитит (см. докстринг) — коммит здесь
    # имитирует то, что в реальном роутере делает create/update_planned_item
    # ОДНИМ общим commit() на позицию и товар вместе.
    await db_session.commit()
    await db_session.refresh(product)
    assert product.item_kind == "работа"


@pytest.mark.asyncio
async def test_apply_updates_different_item_kind(db_session):
    product = await _make_product(db_session, item_kind="товар")
    changed = await apply_item_type_to_product(db_session, product.id, "услуга")
    assert changed is True
    await db_session.commit()
    await db_session.refresh(product)
    assert product.item_kind == "услуга"


@pytest.mark.asyncio
async def test_apply_noop_when_equal():
    """Уже равно переданному значению — apply_item_type_to_product не трогает
    товар (нечего менять, не гоняем лишний UPDATE)."""
    from types import SimpleNamespace

    class _FakeDB:
        def __init__(self, product):
            self._product = product

        async def execute(self, stmt):
            class _R:
                def __init__(self, obj):
                    self._obj = obj

                def scalar_one_or_none(self):
                    return self._obj
            return _R(self._product)

    product = SimpleNamespace(id=1, item_kind="работа")
    db = _FakeDB(product)
    changed = await apply_item_type_to_product(db, product.id, "работа")
    assert changed is False
    assert product.item_kind == "работа"  # не тронуто


@pytest.mark.asyncio
async def test_apply_product_not_found_returns_false(db_session):
    changed = await apply_item_type_to_product(db_session, 999_999_999, "работа")
    assert changed is False


@pytest.mark.asyncio
async def test_apply_missing_inputs_return_false(db_session):
    product = await _make_product(db_session, item_kind="товар")
    assert await apply_item_type_to_product(db_session, None, "работа") is False
    assert await apply_item_type_to_product(db_session, product.id, None) is False
    assert await apply_item_type_to_product(db_session, product.id, "мусор") is False
    await db_session.refresh(product)
    assert product.item_kind == "товар"  # ничего не изменилось


# ---------------------------------------------------------------------------
# 3) PUT /feo-planned-items/{id} с sync_product_kind=true — реальный роутер,
#    вызванный напрямую (Depends(...) в сигнатуре — просто значения по
#    умолчанию, см. докстринг test_planned_item_link_rules.py).
# ---------------------------------------------------------------------------

async def _make_subsidy_category(db_session):
    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    subsidy = Subsidy(name=f"TestItemTypes-{uuid.uuid4().hex[:8]}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name=f"Cat-{uuid.uuid4().hex[:8]}")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return subsidy, cat


@pytest.mark.asyncio
async def test_put_with_sync_product_kind_updates_product(db_session, test_user):
    from app.models.feo_planned_item import FeoPlannedItem
    from app.routers.feo_planned_items import update_planned_item
    from app.schemas.feo import FeoPlannedItemCreate

    _subsidy, cat = await _make_subsidy_category(db_session)
    product = await _make_product(db_session, item_kind="товар")
    item = FeoPlannedItem(feo_category_id=cat.id, name="Позиция плана", unit="шт", is_active=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    data = FeoPlannedItemCreate(
        feo_category_id=cat.id, name="Позиция плана", is_active=True,
        item_type="Работа", product_id=product.id, sync_product_kind=True,
    )
    await update_planned_item(item_id=item.id, data=data, db=db_session, current_user=test_user)

    await db_session.refresh(item)
    await db_session.refresh(product)
    assert item.item_type == "работа"
    assert product.item_kind == "работа", "sync_product_kind=true обязан перенести тип в товар каталога"


@pytest.mark.asyncio
async def test_put_without_sync_flag_leaves_product_untouched(db_session, test_user):
    """Дефолт sync_product_kind=False — старое поведение (плановая позиция не
    трогает каталог) не должно меняться без явного согласия."""
    from app.models.feo_planned_item import FeoPlannedItem
    from app.routers.feo_planned_items import update_planned_item
    from app.schemas.feo import FeoPlannedItemCreate

    _subsidy, cat = await _make_subsidy_category(db_session)
    product = await _make_product(db_session, item_kind="товар")
    item = FeoPlannedItem(feo_category_id=cat.id, name="Позиция без синка", unit="шт", is_active=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    data = FeoPlannedItemCreate(
        feo_category_id=cat.id, name="Позиция без синка", is_active=True,
        item_type="Работа", product_id=product.id, sync_product_kind=False,
    )
    await update_planned_item(item_id=item.id, data=data, db=db_session, current_user=test_user)

    await db_session.refresh(item)
    await db_session.refresh(product)
    assert item.item_type == "работа"
    assert product.item_kind == "товар", "без sync_product_kind товар каталога трогать нельзя"


@pytest.mark.asyncio
async def test_put_sync_without_product_id_resolves_by_exact_name(db_session, test_user):
    """product_id НЕ прислан в теле запроса (диалог правки/инлайн-селект его
    не знают) — update_planned_item обязан подобрать товар сам через
    resolve_product_for_planned_item по ТОЧНОМУ совпадению нормализованного
    имени и записать в него тип."""
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.product import Product
    from app.routers.feo_planned_items import update_planned_item
    from app.schemas.feo import FeoPlannedItemCreate

    _subsidy, cat = await _make_subsidy_category(db_session)
    pname = f"Перчатки латексные {uuid.uuid4().hex[:8]}"
    product = Product(name=pname, category="Прочее", item_kind="товар")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    item = FeoPlannedItem(feo_category_id=cat.id, name=pname, unit="шт", is_active=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    data = FeoPlannedItemCreate(
        feo_category_id=cat.id, name=pname, is_active=True,
        item_type="Услуга", sync_product_kind=True,  # product_id намеренно не передан
    )
    result = await update_planned_item(item_id=item.id, data=data, db=db_session, current_user=test_user)

    await db_session.refresh(product)
    assert product.item_kind == "услуга", "sync_product_kind=true без product_id обязан подобрать товар по имени"
    assert result.product_kind_synced is True
    assert result.product_name == pname


@pytest.mark.asyncio
async def test_put_sync_without_product_id_ambiguous_name_not_touched(db_session, test_user):
    """Два товара каталога с одинаковым нормализованным именем — неоднозначность,
    resolve_product_for_planned_item обязан вернуть None, а не гадать; ни один
    из двух товаров не трогается."""
    from app.models.feo_planned_item import FeoPlannedItem
    from app.models.product import Product
    from app.routers.feo_planned_items import update_planned_item
    from app.schemas.feo import FeoPlannedItemCreate

    _subsidy, cat = await _make_subsidy_category(db_session)
    pname = f"Дубликат товара {uuid.uuid4().hex[:8]}"
    p1 = Product(name=pname, category="Прочее", item_kind="товар")
    p2 = Product(name=pname, category="Прочее", item_kind="товар")
    db_session.add_all([p1, p2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)

    item = FeoPlannedItem(feo_category_id=cat.id, name=pname, unit="шт", is_active=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    data = FeoPlannedItemCreate(
        feo_category_id=cat.id, name=pname, is_active=True,
        item_type="Работа", sync_product_kind=True,
    )
    result = await update_planned_item(item_id=item.id, data=data, db=db_session, current_user=test_user)

    await db_session.refresh(p1)
    await db_session.refresh(p2)
    assert p1.item_kind == "товар", "неоднозначность по имени — товар не трогаем"
    assert p2.item_kind == "товар"
    assert getattr(result, "product_kind_synced", False) is False


# ---------------------------------------------------------------------------
# 4) GET /feo-planned-items/product-hint отдаёт item_kind
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_product_hint_returns_item_kind(db_session, test_user):
    from app.routers.feo_planned_items_matching import get_product_hint

    product = await _make_product(db_session, item_kind="услуга")
    result = await get_product_hint(product_id=product.id, feo_category_id=None, db=db_session, _=test_user)
    assert result["item_kind"] == "услуга"


@pytest.mark.asyncio
async def test_product_hint_item_kind_none_when_product_missing(db_session, test_user):
    from app.routers.feo_planned_items_matching import get_product_hint

    result = await get_product_hint(product_id=999_999_999, feo_category_id=None, db=db_session, _=test_user)
    assert result["item_kind"] is None
