"""Защита товаров, задействованных в договорах, закупках и заявках, и фильтр битых URL фото.

Единый источник истины (ПРАВИЛО №6): используется скриптами нормализации,
слияния дублей (merge_by_name_model, merge_by_barcode, merge_duplicate_products_by_name),
подготовки дельты и замены фотографий.
"""
from typing import Optional

try:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:  # офлайн-скрипты без установленного sqlalchemy используют только is_bad_photo_url
    text = None
    AsyncSession = object

PROTECTED_PRODUCTS_SQL = """
SELECT DISTINCT product_id FROM (
    SELECT product_id FROM contract_items WHERE product_id IS NOT NULL
    UNION
    SELECT product_id FROM purchase_items WHERE product_id IS NOT NULL
    UNION
    SELECT product_id FROM wish_items WHERE product_id IS NOT NULL
    UNION
    SELECT product_id FROM commercial_request_offers WHERE product_id IS NOT NULL
) t
"""

_BAD_PHOTO_SUBSTRINGS = (
    "avatars.mds.yandex.net",
    "не смог найти",
    "logo.svg",
    "nophoto",
    "no-photo",
    "no_photo",
    "placeholder",
    "shansk-spasatel.ru-500x500.png",
    "/static/img/default",
    "blank.png",
    "blank.jpg",
)


async def load_protected_product_ids(db: AsyncSession) -> set[int]:
    """Возвращает множество product_id, задействованных в действующих
    договорах, активных закупках и не отклонённых заявках."""
    rows = (await db.execute(text(PROTECTED_PRODUCTS_SQL))).scalars().all()
    return {int(pid) for pid in rows if pid is not None}


def is_bad_photo_url(url: Optional[str]) -> bool:
    """True, если URL пустой, не http(s), заглушка магазина, логотип или
    ссылка из поисковой выдачи / старого Маркета Яндекса."""
    if not url or not isinstance(url, str):
        return True
    s = url.strip().strip('"\'').strip()
    if not s:
        return True
    low = s.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return True
    return any(marker in low for marker in _BAD_PHOTO_SUBSTRINGS)
