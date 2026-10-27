"""Единственное место отбора товаров, у которых Product.article сейчас
хранит НОМЕР МАГАЗИНА, а не артикул производителя — старая трактовка поля
(до задачи manufacturer_article/store_article, владелец 27.10.2026).
Используется ДВУМЯ местами (ПРАВИЛО №6, не дублировать):
  - backend/scripts/split_store_articles.py — сам перенос article →
    store_article истории цены (--apply) и пробный прогон;
  - app.services.products_import_match.load_candidates_by_brand_article —
    чтобы критерий (0.5) (бренд+артикул производителя) НЕ сводил товар с
    таким "артиклем-номером-магазина" по случайному совпадению номера с
    чужим артикулом производителя, пока перенос для этого товара не
    выполнен.

Отбор (см. также докстринг split_store_articles.py): Product.article
непустой И price_source_contractor_id указывает на контрагента, у которого
article_is_manufacturer_for_inn(inn) == False (включая неизвестный
ИНН/контрагента — безопасный дефолт "не производитель"). "Перенос уже
сделан" для конкретного товара — у него есть хотя бы одна строка
product_price_history с тем же contractor_id, source='import' и ПУСТЫМ
store_article (ждёт переноса) — если таких строк 0, товар либо уже
перенесён (article уже NULL — такой товар сюда не попадёт вовсе, т.к.
Product.article непустой — часть отбора), либо у него никогда не было
истории этого магазина (перенос невозможен, article трогать нельзя, но он
и не является "ждущим переноса" — исключать из сопоставления тоже не
нужно, проверка на деле безопасна по умолчанию)."""
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.catalog_gala.stores import article_is_manufacturer_for_inn
from app.utils.chunking import chunked


async def collect_pending_split_candidates(db: AsyncSession) -> list[tuple]:
    """Возвращает список (product_id, product_name, article, contractor_id,
    inn) — товары с непустым article, чей price_source_contractor_id
    указывает на магазин НЕ-производителя (см. докстринг модуля)."""
    rows = (await db.execute(
        select(
            Product.id, Product.name, Product.article,
            Product.price_source_contractor_id, Contractor.inn,
        )
        .join(Contractor, Contractor.id == Product.price_source_contractor_id)
        .where(Product.article.isnot(None), Product.article != "")
    )).all()
    return [
        (pid, name, article, contractor_id, inn)
        for pid, name, article, contractor_id, inn in rows
        if not article_is_manufacturer_for_inn(inn)
    ]


async def history_row_counts(db: AsyncSession, pairs) -> dict:
    """Для набора (product_id, contractor_id) — число строк
    product_price_history с source='import' и пустым store_article (те, что
    получат store_article при --apply split_store_articles.py). Пара без
    строк не попадает в результат (а не 0) — удобно отличать has_history от
    no_history у вызывающих."""
    valid_pairs = [(pid, cid) for pid, cid in pairs if pid is not None and cid is not None]
    if not valid_pairs:
        return {}
    counts: dict = {}
    for chunk in chunked(valid_pairs):
        rows = (await db.execute(
            select(ProductPriceHistory.product_id, ProductPriceHistory.contractor_id)
            .where(
                tuple_(ProductPriceHistory.product_id, ProductPriceHistory.contractor_id).in_(chunk),
                ProductPriceHistory.source == "import",
                ProductPriceHistory.store_article.is_(None),
            )
        )).all()
        for product_id, contractor_id in rows:
            key = (product_id, contractor_id)
            counts[key] = counts.get(key, 0) + 1
    return counts


async def pending_split_product_ids(db: AsyncSession) -> set[int]:
    """Множество id товаров, у которых Product.article ещё хранит НОМЕР
    МАГАЗИНА (перенос split_store_articles.py --apply для них ещё НЕ
    выполнен) — ровно те товары, что скрипт перенесёт при следующем
    --apply (affected_ids там же). Пустое множество, если переноса не
    требуется ни для одного товара (например, после --apply)."""
    candidates = await collect_pending_split_candidates(db)
    if not candidates:
        return set()
    counts = await history_row_counts(db, [(pid, cid) for pid, _, _, cid, _ in candidates])
    return {pid for pid, _, _, cid, _ in candidates if counts.get((pid, cid), 0) > 0}
