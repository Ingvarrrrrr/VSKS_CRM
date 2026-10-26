"""ЕДИНСТВЕННОЕ место чтения/записи фото товара (ПРАВИЛО №6, владелец
26.10.2026). Байты лежат в отдельной таблице product_photos (не в products —
чтобы ежедневный бэкап БД не раздувался фото, см. scripts/ops/pg_backup.sh),
`products.photo_mime`/`photo_size` остаются дёшевым кэшем на Product для
has_photo()/списков без похода во вторую таблицу.

Все места записи (upload, скачивание по ссылке, импорт из каталога,
слияние дублей) и чтения (отдача по HTTP, вставка в docx/Excel) переведены
на эти четыре функции — не читать/писать ProductPhoto напрямую где-то ещё.
"""
import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_photo import ProductPhoto
from app.services.product_photo_compress import compress_product_photo


def has_photo(product) -> bool:
    """Есть ли у товара закэшированное фото — по дёшевому `photo_size`
    (всегда доступен, даже если products.photo_data был бы deferred в
    старой схеме; сейчас это просто единственный признак на Product)."""
    return getattr(product, "photo_size", None) is not None


async def save_product_photo(db: AsyncSession, product, raw: bytes) -> tuple[bytes, str]:
    """Сжать `raw` и сохранить как фото `product` (upsert в product_photos +
    обновление product.photo_mime/photo_size). Возвращает (сжатые байты, mime)
    — вызывающему они обычно не нужны, но удобны для тестов/логов.

    Не коммитит сам product (вызывающий решает, когда коммитить — некоторые
    места меняют и другие поля в той же транзакции), но сам upsert
    в product_photos выполняется и коммитится отдельным commit здесь, так как
    product_id должен существовать (product уже должен быть persisted)."""
    compressed, mime = compress_product_photo(raw)
    product_id = product.id
    stmt = pg_insert(ProductPhoto).values(
        product_id=product_id,
        data=compressed,
        mime=mime,
        size=len(compressed),
        updated_at=datetime.datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[ProductPhoto.product_id],
        set_={
            "data": stmt.excluded.data,
            "mime": stmt.excluded.mime,
            "size": stmt.excluded.size,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await db.execute(stmt)
    product.photo_mime = mime
    product.photo_size = len(compressed)
    return compressed, mime


async def load_product_photo(db: AsyncSession, product_id: int) -> Optional[tuple[bytes, str]]:
    """Прочитать байты фото товара. None если фото нет."""
    row = await db.get(ProductPhoto, product_id)
    if row is None:
        return None
    return bytes(row.data), (row.mime or "image/webp")


async def load_photos_bulk(db: AsyncSession, product_ids) -> dict:
    """Один запрос для N товаров — {product_id: (bytes, mime)}. Используют
    генераторы документов (docx/Excel), которые резолвят фото синхронно для
    многих товаров сразу (см. app/services/documents/product_photos.py —
    photo_map): без этого пришлось бы делать по одному await на каждую
    позицию закупки/заявки."""
    ids = [i for i in set(product_ids) if i is not None]
    if not ids:
        return {}
    result = await db.execute(select(ProductPhoto).where(ProductPhoto.product_id.in_(ids)))
    rows = result.scalars().all()
    return {row.product_id: (bytes(row.data), row.mime or "image/webp") for row in rows}


async def delete_product_photo(db: AsyncSession, product) -> None:
    """Удалить фото товара: строку в product_photos + метаданные на product.
    Не коммитит — как и save_product_photo, решение о commit у вызывающего."""
    await db.execute(sa_delete(ProductPhoto).where(ProductPhoto.product_id == product.id))
    product.photo_mime = None
    product.photo_size = None
