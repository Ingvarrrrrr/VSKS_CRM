"""Дефект на проде 27.10.2026: scripts/split_store_articles.py --apply падал
с NameError (chunked не импортирован — потерялось при выносе отбора в
app/services/catalog_gala/store_article_split.py), ничего не записав.
Покрывает: apply() переносит article → store_article для товара магазина
НЕ-производителя (Сима-ленд, ИНН 6679104850) и очищает Product.article;
товар магазина-производителя (МПО Электромонтаж, ИНН 7719079370) не
трогается. apply() вызывается с product_ids, чтобы не задевать чужие
локальные данные сверх необходимого (параметр добавлен специально для теста,
см. докстринг apply())."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.contractor_resolve import find_or_create_contractor
from scripts.split_store_articles import apply as apply_split

_UNIQ = "ТестРазъездАртикула_20261027"


def _uniq(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_apply_splits_article_for_non_manufacturer_store(db_session, test_user):
    sima_contractor_id = await find_or_create_contractor(
        db_session, "ООО ТД «Сима-ленд» (тест разъезда)", "6679104850", match_by_name=False,
    )
    article = f"X{uuid.uuid4().hex[:10]}"
    product = Product(
        name=_uniq("СимаЛенд"), category="Прочее", price=Decimal("100"),
        article=article, price_source_contractor_id=sima_contractor_id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    history = ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=sima_contractor_id, store_article=None,
    )
    db_session.add(history)
    await db_session.commit()
    await db_session.refresh(history)

    # МПО (производитель) — article не должен быть тронут этим прогоном,
    # даже если обработка затронет что-то ещё в БД (product_ids ограничивает
    # перенос только товаром из этого теста).
    mpo_contractor_id = await find_or_create_contractor(
        db_session, "ЗАО «МПО Электромонтаж» (тест разъезда)", "7719079370", match_by_name=False,
    )
    mpo_article = f"MPO{uuid.uuid4().hex[:10]}"
    mpo_product = Product(
        name=_uniq("МПО"), category="Прочее", price=Decimal("500"),
        article=mpo_article, price_source_contractor_id=mpo_contractor_id,
    )
    db_session.add(mpo_product)
    await db_session.commit()
    await db_session.refresh(mpo_product)

    await apply_split(db_session, product_ids={product.id, mpo_product.id})

    await db_session.refresh(product)
    assert product.article is None, "article Сима-ленда должен очиститься после переноса"

    await db_session.refresh(history)
    assert history.store_article == article, "store_article истории должен получить прежний article"

    await db_session.refresh(mpo_product)
    assert mpo_product.article == mpo_article, "магазин-производитель не разъезжается этим скриптом"


@pytest.mark.asyncio
async def test_apply_without_history_row_does_not_touch_article(db_session, test_user):
    """Нет строки истории этого магазина с source='import' и пустым
    store_article — перенос невозможен, article НЕ очищается (докстрина
    apply(): иначе значение терялось бы безвозвратно)."""
    sima_contractor_id = await find_or_create_contractor(
        db_session, "ООО ТД «Сима-ленд» (тест без истории)", "6679104850", match_by_name=False,
    )
    article = f"X{uuid.uuid4().hex[:10]}"
    product = Product(
        name=_uniq("СимаЛендБезИстории"), category="Прочее", price=Decimal("100"),
        article=article, price_source_contractor_id=sima_contractor_id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    await apply_split(db_session, product_ids={product.id})

    await db_session.refresh(product)
    assert product.article == article, "без строки истории article трогать нельзя"


@pytest.mark.asyncio
async def test_dry_run_candidate_collection_matches_apply_scope(db_session, test_user):
    """Отбор кандидатов (dry-run и apply используют одну и ту же функцию
    collect_pending_split_candidates — ПРАВИЛО №6) находит товар Сима-ленда
    среди affected, не считая его историю уже перенесённой."""
    from app.services.catalog_gala.store_article_split import (
        collect_pending_split_candidates,
        history_row_counts,
    )

    sima_contractor_id = await find_or_create_contractor(
        db_session, "ООО ТД «Сима-ленд» (тест отбора)", "6679104850", match_by_name=False,
    )
    article = f"X{uuid.uuid4().hex[:10]}"
    product = Product(
        name=_uniq("СимаЛендОтбор"), category="Прочее", price=Decimal("100"),
        article=article, price_source_contractor_id=sima_contractor_id,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    db_session.add(ProductPriceHistory(
        product_id=product.id, price=Decimal("100"), source="import",
        contractor_id=sima_contractor_id, store_article=None,
    ))
    await db_session.commit()

    candidates = await collect_pending_split_candidates(db_session)
    match = [c for c in candidates if c[0] == product.id]
    assert len(match) == 1, "товар Сима-ленда должен попасть в кандидаты"

    counts = await history_row_counts(db_session, [(product.id, sima_contractor_id)])
    assert counts.get((product.id, sima_contractor_id), 0) == 1
