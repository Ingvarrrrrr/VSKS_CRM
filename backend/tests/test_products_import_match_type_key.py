"""Критерий (0.75) сопоставления строки импорта — ключ вида товара (пожарная
безопасность: огнетушитель/знак/рукав/шкаф, решение владельца, 27.10.2026,
app.services.product_type_keys). См. докстринг app/services/products_import_
match.py и app/services/products_import_match_type_key.py. Тот же стиль
проверки, что у test_products_import_match_barcode.py (brand_article/
barcode)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.contractor_resolve import find_or_create_contractor
from app.services.products_import_apply import apply_products_import


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


async def _count_by_name(db_session, name: str) -> int:
    rows = (await db_session.execute(select(Product).where(Product.name == name))).scalars().all()
    return len(rows)


@pytest.mark.asyncio
async def test_two_stores_same_full_key_merge_into_one_card(db_session, test_user):
    """«Огнетушитель углекислотный ОУ-5 ВСЕ РИФ» (магазин 1) и «Огнетушитель
    углекислотный ОУ-5-ВСЕ (55В, С, Е) РИФ» (магазин 2, другое написание,
    та же модель/класс/бренд) — один и тот же ключ вида товара, РОВНО одна
    карточка у каждого магазина → сводятся в одну карточку."""
    suf = _suffix()
    old_name = f"Огнетушитель углекислотный ОУ-5 ВСЕ РИФ {suf}"
    new_name = f"Огнетушитель углекислотный ОУ-5-ВСЕ (55В, С, Е) РИФ {suf}"

    inn1 = "7701000201"
    contractor1_id = await find_or_create_contractor(
        db_session, "ТипКлюч-Магазин1", inn1, match_by_name=False,
    )
    product = Product(name=old_name, category="Прочее", price=Decimal("1000"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("1000"), source="import",
        contractor_id=contractor1_id, store_article="TK-ART1",
    ))
    await db_session.commit()

    inn2 = "7701000202"
    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3}
    data_rows = [(new_name, "1100", inn2, "TK-ART2")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="type_key_merge.xlsx", current_user=test_user,
    )
    assert result["created"] == 0, result
    assert result["updated"] == 1, result
    assert await _count_by_name(db_session, new_name) == 0, "второй магазин не создаёт отдельную карточку"
    assert "по ключу вида товара" in result["rows"][0]["reason"]

    hist = (await db_session.execute(
        select(ProductPriceHistory).where(ProductPriceHistory.product_id == product.id)
    )).scalars().all()
    assert len(hist) == 2, "вторая строка истории (магазин 2) должна появиться у ТОЙ ЖЕ карточки"


@pytest.mark.asyncio
async def test_three_variants_one_store_ambiguous_not_merged(db_session, test_user):
    """Три карточки с ОДНИМ И ТЕМ ЖЕ ключом вида товара у ОДНОГО магазина
    (разные store_article — реально разные позиции, случайно давшие
    одинаковый ключ) + одна строка у ДРУГОГО магазина с тем же ключом —
    неоднозначно (count в каталоге >1, правило однозначности
    keys_match_unique), сведения НЕТ, строка создаёт новую карточку."""
    suf = _suffix()
    names_store_a = [
        f"Огнетушитель порошковый ОП-4 АВСЕ ИНГА {suf}",
        f"Огнетушитель порошковый ОП-4-АВСЕ ИНГА {suf}X",
        f"Огнетушитель порошковый ОП-4 (АВСЕ) ИНГА {suf}Y",
    ]
    new_name = f"Огнетушитель порошковый ОП-4 АВСЕ ИНГА {suf}Z"

    inn_a = "7701000203"
    contractor_a_id = await find_or_create_contractor(
        db_session, "ТипКлюч-МагазинA", inn_a, match_by_name=False,
    )
    for i, name in enumerate(names_store_a):
        p = Product(name=name, category="Прочее", price=Decimal("500"))
        db_session.add(p)
        await db_session.commit()
        await db_session.refresh(p)
        db_session.add(ProductPriceHistory(
            product_id=p.id, price=Decimal("500"), source="import",
            contractor_id=contractor_a_id, store_article=f"TK-AMBIG-{i}",
        ))
        await db_session.commit()

    inn_b = "7701000204"
    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3}
    data_rows = [(new_name, "520", inn_b, "TK-B-ART")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="type_key_ambiguous.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert await _count_by_name(db_session, new_name) == 1
    for name in names_store_a:
        assert await _count_by_name(db_session, name) == 1, "существующие карточки магазина A не затронуты"


@pytest.mark.asyncio
async def test_rukav_with_stvol_vs_without_not_merged(db_session, test_user):
    """Пожарный рукав «с головкой ГР-51 и стволом РС-50.01» и тот же рукав
    БЕЗ ствола — РАЗНЫЕ ключи вида товара (ствол — часть key у рукава),
    сведения нет, строка создаёт новую карточку."""
    suf = _suffix()
    with_stvol = f"Рукав пожарный напорный РПМ(Д)-51-1,6МПа, с головками ГР-51, (20±1м), с головкой ГР-51 и стволом РС-50.01, Берег {suf}"
    without_stvol = f"Рукав пожарный напорный РПМ(Д)-51-1,6МПа, с головками ГР-51, (20±1м), Берег {suf}"

    inn1 = "7701000205"
    contractor1_id = await find_or_create_contractor(
        db_session, "ТипКлюч-РукавМагазин1", inn1, match_by_name=False,
    )
    product = Product(name=with_stvol, category="Прочее", price=Decimal("300"))
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("300"), source="import",
        contractor_id=contractor1_id, store_article="TK-RUKAV-1",
    ))
    await db_session.commit()

    inn2 = "7701000206"
    col_idx = {"name": 0, "price": 1, "seller_inn": 2, "store_article": 3}
    data_rows = [(without_stvol, "310", inn2, "TK-RUKAV-2")]
    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="type_key_rukav.xlsx", current_user=test_user,
    )
    assert result["created"] == 1, result
    assert await _count_by_name(db_session, without_stvol) == 1
    assert await _count_by_name(db_session, with_stvol) == 1
