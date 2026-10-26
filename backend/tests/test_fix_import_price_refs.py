"""Тесты backend/scripts/fix_import_price_refs.py — исправление source_ref/
contractor_id у строк, загруженных ДО того, как apply_products_import начал
писать ссылку вместо имени файла (владелец, 26.10.2026). dry-run (по
умолчанию) ничего не пишет; --apply исправляет; повторный запуск находит
0 строк (идемпотентность, т.к. исправленный source_ref больше не
заканчивается на '.json').

Вызывает fix_import_price_refs(db_session, ...) НАПРЯМУЮ (не CLI `_run`,
которая открывает свою app.database.async_session() — отдельное соединение
не увидело бы SAVEPOINT-данные db_session, см. докстринг фикстуры в
conftest.py и докстринг scripts/fix_import_price_refs.py)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.contractor import Contractor
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from scripts.fix_import_price_refs import fix_import_price_refs

_UNIQ = "ТестFixImportRefs_20261026"


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


async def _make_legacy_product(db_session, *, link_url: str) -> Product:
    name = _uniq_name("Товар")
    product = Product(
        name=name, category="Прочее",
        price=100,
        price_source="import",
        price_source_ref="electro_mpo_cables_all.json",
        clarification_link=link_url,
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=100, source="import",
        source_ref="electro_mpo_cables_all.json",
    ))
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(db_session):
    url = "https://electro-mpo.ru/p/42/"
    product = await _make_legacy_product(db_session, link_url=url)

    await fix_import_price_refs(db_session, apply=False, batch=100)

    await db_session.refresh(product)
    assert product.price_source_ref == "electro_mpo_cables_all.json", "dry-run не должен писать"
    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalar_one()
    assert hist.source_ref == "electro_mpo_cables_all.json"


@pytest.mark.asyncio
async def test_apply_fixes_source_ref_and_contractor(db_session):
    url = "https://electro-mpo.ru/p/42/"
    product = await _make_legacy_product(db_session, link_url=url)

    # >=1, не ==1 (владелец, 26.10): на этом стенде уже лежат настоящие
    # строки каталога GALA с тем же "легаси"-видом source_ref (имя файла) —
    # fix_import_price_refs сканирует ВСЮ таблицу, поэтому чинит и их тоже
    # (это и нужно, см. п.6 задания — реальный прогон на локальной БД). Нас
    # интересует именно наша строка — проверяется ниже отдельным запросом.
    result = await fix_import_price_refs(db_session, apply=True, batch=100)
    assert result["stats"]["history_fixed"] >= 1
    assert result["stats"]["product_fixed"] >= 1

    await db_session.refresh(product)
    assert product.price_source_ref == url
    assert product.price_source_contractor_id is not None
    contractor = await db_session.get(Contractor, product.price_source_contractor_id)
    assert contractor.inn == "7719079370"

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalar_one()
    assert hist.source_ref == url
    assert hist.contractor_id == contractor.id


@pytest.mark.asyncio
async def test_apply_is_idempotent_second_run_changes_nothing(db_session):
    url = "https://electro-mpo.ru/p/42/"
    product = await _make_legacy_product(db_session, link_url=url)

    await fix_import_price_refs(db_session, apply=True, batch=100)
    await db_session.refresh(product)
    fixed_ref = product.price_source_ref
    fixed_contractor = product.price_source_contractor_id

    result2 = await fix_import_price_refs(db_session, apply=True, batch=100)
    assert result2["stats"]["history_fixed"] == 0
    assert result2["stats"]["product_fixed"] == 0

    await db_session.refresh(product)
    assert product.price_source_ref == fixed_ref
    assert product.price_source_contractor_id == fixed_contractor


@pytest.mark.asyncio
async def test_no_link_counted_as_without_link_not_touched(db_session):
    name = _uniq_name("БезСсылки")
    product = Product(
        name=name, category="Прочее", price=100,
        price_source="import", price_source_ref="unknown_supplier.json",
    )
    db_session.add(product)
    await db_session.commit()

    result = await fix_import_price_refs(db_session, apply=True, batch=100)
    assert result["stats"]["product_no_link"] >= 1
    # product_fixed аггрегировано по ВСЕЙ таблице (см. комментарий выше) —
    # не проверяем ==0; важно, что КОНКРЕТНО нашу строку без ссылки не
    # трогает (проверка ниже).
    await db_session.refresh(product)
    assert product.price_source_ref == "unknown_supplier.json", "без ссылки не трогаем старое значение"
