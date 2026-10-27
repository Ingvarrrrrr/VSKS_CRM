"""Критерий (0.25) сопоставления строки импорта каталога с товаром —
штрихкод (EAN-13/EAN-8/UPC-12/GTIN-14), решение владельца 27.10.2026: любой
штрихкод строки, уже записанный за какой-то карточкой (product_barcodes,
app/models/product_barcode.py), — это тот же товар, даже у другого магазина
и с другим названием/брендом/артикулом. Проверяется СРАЗУ после (0)
store_article и ДО (0.5) бренд+артикул производителя в
app/services/products_import_match.py::ProductMatchIndex.find (ПРАВИЛО №6 —
единственный механизм сопоставления, второй не заводить; этот модуль —
только загрузка кандидатов этого ОДНОГО критерия, выделен в отдельный файл
по ПРАВИЛУ №5, чтобы products_import_match.py не разрастался).

«Один магазин не продаёт товар дважды» действует и здесь — через
conflicts_with_row_store из products_import_match.py (ПРАВИЛО №6, та же
единственная реализация правила, что и у критерия (0.5))."""
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_price_history import ProductPriceHistory
from app.services.products_import_match import conflicts_with_row_store
from app.utils.chunking import chunked


@dataclass
class BarcodeCandidate:
    """Товар-кандидат критерия (0.25) + его строки истории цены — та же
    форма данных, что у _BrandArticleCandidate критерия (0.5)
    (products_import_match.py), не объединяем классы — поля идентичны
    случайно, критерии независимы и могут разойтись по составу данных."""
    product: Product
    history_count: int = 0
    store_pairs: set = field(default_factory=set)  # {(contractor_id, store_article), ...}

    def conflicts_with_row_store(self, contractor_id, store_article) -> bool:
        return conflicts_with_row_store(self.store_pairs, contractor_id, store_article)


async def load_candidates_by_barcode(
    db: AsyncSession, barcodes: Iterable[str],
) -> dict[str, list[BarcodeCandidate]]:
    """Для набора УЖЕ НОРМАЛИЗОВАННЫХ штрихкодов (app.services.barcodes.
    normalize_barcode — вызывающий код нормализует ДО вызова, этот модуль
    сам не проверяет контрольную цифру, ПРАВИЛО №6: одна точка нормализации)
    со всех строк файла возвращает {barcode: [BarcodeCandidate, ...]} —
    товары, у которых этот штрихкод уже записан в product_barcodes. Один
    проход на весь файл, порциями через `chunked` (тот же приём, что у
    load_candidates_by_store_article/load_candidates_by_brand_article)."""
    codes = {b for b in barcodes if b}
    if not codes:
        return {}

    barcode_rows: list[tuple] = []
    for chunk in chunked(list(codes)):
        rows = (await db.execute(
            select(ProductBarcode.barcode, ProductBarcode.product_id)
            .where(ProductBarcode.barcode.in_(chunk))
        )).all()
        barcode_rows.extend(rows)
    if not barcode_rows:
        return {}

    product_ids = {pid for _, pid in barcode_rows}
    products_by_id: dict[int, Product] = {}
    for chunk in chunked(list(product_ids)):
        rows = (await db.execute(select(Product).where(Product.id.in_(chunk)))).scalars().all()
        for p in rows:
            products_by_id[p.id] = p

    history_count_by_id: dict[int, int] = {}
    store_pairs_by_id: dict[int, set] = {}
    for chunk in chunked(list(product_ids)):
        rows = (await db.execute(
            select(
                ProductPriceHistory.product_id,
                ProductPriceHistory.contractor_id,
                ProductPriceHistory.store_article,
            ).where(ProductPriceHistory.product_id.in_(chunk))
        )).all()
        for product_id, contractor_id, store_article in rows:
            history_count_by_id[product_id] = history_count_by_id.get(product_id, 0) + 1
            if contractor_id is not None and store_article:
                store_pairs_by_id.setdefault(product_id, set()).add((contractor_id, store_article))

    result: dict[str, list[BarcodeCandidate]] = {}
    for barcode, product_id in barcode_rows:
        product = products_by_id.get(product_id)
        if product is None:
            continue
        result.setdefault(barcode, []).append(BarcodeCandidate(
            product=product,
            history_count=history_count_by_id.get(product_id, 0),
            store_pairs=store_pairs_by_id.get(product_id, set()),
        ))
    return result
