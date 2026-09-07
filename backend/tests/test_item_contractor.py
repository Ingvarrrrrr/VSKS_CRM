"""ПРАВИЛО №6, группа D5: контрагент позиции закупки/заявки — один источник истины.

Покрывает:
  1. item_contractor() — чистая функция (SimpleNamespace, без БД): FK с
     переданным объектом контрагента, FK через bulk-карты (name_map/inn_map),
     FK без резолва (source='fk_unloaded'), голый текст, сущность без колонки
     contractor_inn (Wish).
  2. set_item_contractor() — FK (текст обнуляется), текст-только (FK NULL),
     FK + противоречащий текст (текст игнорируется, warning в лог, FK остаётся).
  3. Миграция b4d6f8h0j2l4 идемпотентна: на реальных строках БД первый прогон
     чистит/линкует, второй — rowcount 0.
  4. Сериализатор _item_to_out отдаёт имя контрагента по FK, даже когда
     item.contractor_name пуст (bulk name_map/inn_map, без N+1 SELECT'а).
"""
import importlib.util
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.services.item_contractor import item_contractor, set_item_contractor
from app.services.purchase_serializers import _item_to_out


def _load_migration_module():
    """importlib по пути файла — см. test_purchase_contract_header.py::_load_migration_module
    (та же коллизия имён: локальный alembic/ и pip-пакет alembic делят top-level имя)."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(
        here, "..", "alembic", "versions",
        "b4d6f8h0j2l4_item_contractor_fk_wins_over_text.py",
    ))
    spec = importlib.util.spec_from_file_location("_b4d6f8h0j2l4_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. item_contractor() — offline, no DB
# ---------------------------------------------------------------------------

def _mk_item(contractor_id=None, contractor_inn=None, contractor_name=None):
    return SimpleNamespace(
        contractor_id=contractor_id, contractor_inn=contractor_inn, contractor_name=contractor_name,
    )


def _mk_wish_like(contractor_id=None, contractor_name=None):
    """Wish не имеет колонки contractor_inn — SimpleNamespace без атрибута
    воспроизводит это (hasattr(entity, 'contractor_inn') is False)."""
    return SimpleNamespace(contractor_id=contractor_id, contractor_name=contractor_name)


def test_item_contractor_fk_with_object():
    contractor = SimpleNamespace(id=5, inn="7700000000", name="ООО Ромашка")
    item = _mk_item(contractor_id=5, contractor_inn=None, contractor_name=None)
    out = item_contractor(item, contractor=contractor)
    assert out == {
        "contractor_id": 5, "contractor_name": "ООО Ромашка",
        "contractor_inn": "7700000000", "source": "fk",
    }


def test_item_contractor_fk_via_bulk_maps():
    item = _mk_item(contractor_id=5)
    out = item_contractor(item, name_map={5: "ООО Ромашка"}, inn_map={5: "7700000000"})
    assert out["contractor_id"] == 5
    assert out["contractor_name"] == "ООО Ромашка"
    assert out["contractor_inn"] == "7700000000"
    assert out["source"] == "fk"


def test_item_contractor_fk_unresolved_does_not_leak_stale_text():
    # FK задан, но ни объект, ни карты не переданы, а текст на сущности всё
    # ещё висит (до миграции/до записи через set_item_contractor) — читатель
    # НЕ должен подмешивать этот текст к чужому FK.
    item = _mk_item(contractor_id=5, contractor_inn="OLD-INN", contractor_name="Старый текст")
    out = item_contractor(item)
    assert out["contractor_id"] == 5
    assert out["contractor_name"] is None
    assert out["contractor_inn"] is None
    assert out["source"] == "fk_unloaded"


def test_item_contractor_text_only():
    item = _mk_item(contractor_id=None, contractor_inn="7700000000", contractor_name="ИП Иванов")
    out = item_contractor(item)
    assert out == {
        "contractor_id": None, "contractor_name": "ИП Иванов",
        "contractor_inn": "7700000000", "source": "text",
    }


def test_item_contractor_wish_has_no_inn_key():
    wish = _mk_wish_like(contractor_id=None, contractor_name="Свободный текст")
    out = item_contractor(wish)
    assert "contractor_inn" not in out
    assert out["contractor_name"] == "Свободный текст"
    assert out["source"] == "text"

    contractor = SimpleNamespace(id=9, inn="123", name="ООО Вектор")
    wish2 = _mk_wish_like(contractor_id=9)
    out2 = item_contractor(wish2, contractor=contractor)
    assert "contractor_inn" not in out2
    assert out2["contractor_name"] == "ООО Вектор"


# ---------------------------------------------------------------------------
# 2. set_item_contractor() — offline, no DB
# ---------------------------------------------------------------------------

def test_set_item_contractor_with_object_clears_text():
    contractor = SimpleNamespace(id=5, inn="7700000000", name="ООО Ромашка")
    item = _mk_item(contractor_id=None, contractor_inn="стар", contractor_name="стар")
    set_item_contractor(item, contractor=contractor)
    assert item.contractor_id == 5
    assert item.contractor_inn is None
    assert item.contractor_name is None


def test_set_item_contractor_text_only_clears_fk():
    item = _mk_item(contractor_id=7, contractor_inn=None, contractor_name=None)
    set_item_contractor(item, inn="7700000000", name="ИП Иванов")
    assert item.contractor_id is None
    assert item.contractor_inn == "7700000000"
    assert item.contractor_name == "ИП Иванов"


def test_set_item_contractor_mismatched_text_ignored_with_warning(caplog):
    contractor = SimpleNamespace(id=5, inn="7700000000", name="ООО Ромашка")
    item = _mk_item()
    with caplog.at_level("WARNING"):
        set_item_contractor(item, contractor=contractor, inn="9999999999", name="Совсем другое имя")
    assert item.contractor_id == 5
    assert item.contractor_inn is None
    assert item.contractor_name is None
    assert any("не совпадает" in rec.message for rec in caplog.records)


def test_set_item_contractor_by_id_only_clears_text_no_object_needed():
    item = _mk_item(contractor_inn="стар", contractor_name="стар")
    set_item_contractor(item, contractor_id=42)
    assert item.contractor_id == 42
    assert item.contractor_inn is None
    assert item.contractor_name is None


def test_set_item_contractor_wish_no_inn_column_does_not_crash():
    wish = _mk_wish_like()
    contractor = SimpleNamespace(id=9, inn="123", name="ООО Вектор")
    set_item_contractor(wish, contractor=contractor)
    assert wish.contractor_id == 9
    assert wish.contractor_name is None
    assert not hasattr(wish, "contractor_inn")


# ---------------------------------------------------------------------------
# 3. Сериализатор — offline (SimpleNamespace item), name_map/inn_map bulk
# ---------------------------------------------------------------------------

def test_item_to_out_uses_contractor_name_from_map_when_text_is_empty():
    item = SimpleNamespace(
        id=1, product=None, product_id=None, item_name="Товар", item_type="товар",
        quantity=Decimal("1"), unit="шт", unit_price=Decimal("100"), total_price=Decimal("100"),
        final_unit_price=None, final_total=None, planned_quantity=None, planned_unit_price=None,
        planned_total=None, country_origin=None,
        contractor_id=5, contractor_inn=None, contractor_name=None,  # текст пуст — только FK
        match_confirmed=True, receipt_id=None, vat_rate=None, vat_amount=None, total_with_vat=None,
        feo_planned_item_id=None, feo_category_id=None, over_plan=False, needed_date=None,
        accepted_name=None, accepted_quantity=None, accepted_unit=None,
    )
    out = _item_to_out(item, contractor_names={5: "ООО Ромашка"}, contractor_inns={5: "7700000000"})
    assert out.contractor_id == 5
    assert out.contractor_name == "ООО Ромашка"
    assert out.contractor_inn == "7700000000"


# ---------------------------------------------------------------------------
# 4. Миграция b4d6f8h0j2l4 — идемпотентна на реальных данных
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def _contractor_pair(db_session):
    from app.models.contractor import Contractor

    c_match = Contractor(name="ООО Ромашка", inn="7700000001")
    c_other = Contractor(name="ООО Другое", inn="7700000002")
    db_session.add_all([c_match, c_other])
    await db_session.flush()
    return c_match, c_other


@pytest.mark.asyncio
async def test_migration_clears_matching_text_and_reports_mismatch(db_session, make_purchase, _contractor_pair):
    from app.models.purchase_item import PurchaseItem

    c_match, c_other = _contractor_pair
    p = await make_purchase()

    item_match = PurchaseItem(
        purchase_id=p.id, item_name="Совпадает", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("10"), total_price=Decimal("10"),
        contractor_id=c_match.id, contractor_inn=c_match.inn, contractor_name="Старое имя (неважно)",
    )
    item_mismatch = PurchaseItem(
        purchase_id=p.id, item_name="Расходится", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("10"), total_price=Decimal("10"),
        contractor_id=c_match.id, contractor_inn=c_other.inn, contractor_name="Чужой ИНН",
    )
    item_linkable = PurchaseItem(
        purchase_id=p.id, item_name="Только текст", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("10"), total_price=Decimal("10"),
        contractor_id=None, contractor_inn=c_other.inn, contractor_name="Найдётся по ИНН",
    )
    db_session.add_all([item_match, item_mismatch, item_linkable])
    await db_session.commit()
    for it in (item_match, item_mismatch, item_linkable):
        await db_session.refresh(it)

    mod = _load_migration_module()

    async def _run_once():
        r1 = await db_session.execute(text(mod.CLEAR_ITEM_TEXT_WHEN_MATCHES_FK))
        r3 = await db_session.execute(text(mod.LINK_ITEM_FK_FROM_TEXT_INN))
        await db_session.commit()
        return r1.rowcount, r3.rowcount

    n_cleared, n_linked = await _run_once()
    assert n_cleared >= 1  # как минимум item_match
    assert n_linked >= 1   # как минимум item_linkable

    await db_session.refresh(item_match)
    await db_session.refresh(item_mismatch)
    await db_session.refresh(item_linkable)

    assert item_match.contractor_inn is None and item_match.contractor_name is None

    # Mismatch — НЕ трогаем: FK и текст остаются как были (отчёт, не запись).
    assert item_mismatch.contractor_id == c_match.id
    assert item_mismatch.contractor_inn == c_other.inn

    # Linkable — FK проставлен по тексту, текст очищен.
    assert item_linkable.contractor_id == c_other.id
    assert item_linkable.contractor_inn is None
    assert item_linkable.contractor_name is None

    # Идемпотентность: повторный прогон ничего больше не меняет.
    n_cleared2, n_linked2 = await _run_once()
    assert n_cleared2 == 0
    assert n_linked2 == 0
