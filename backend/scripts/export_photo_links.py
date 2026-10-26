#!/usr/bin/env python3
"""Выгружает [{"id": product_id, "url": ...}] для товаров БЕЗ фото, у
которых есть внешняя http(s)-ссылка (photo_url приоритетнее photo_link —
тот же выбор источника, что и app.services.product_photo_download.pick_external_url,
ПРАВИЛО №6, вторая копия формулы не заводится).

Сервер прода/разработки не пускают запросы к сайтам некоторых поставщиков
(403 по IP) — фото приходится качать с машины разработчика. Эта выгрузка
(запускается внутри Docker — доступ к БД есть) — первый шаг: JSON передаётся
на машину разработчика, где scripts/fetch_photos_local.py (ВНЕ Docker,
обычным python) скачивает файлы, затем scripts/import_photos_dir.py (снова
внутри Docker) загружает их обратно в product_photos.

Запуск (внутри контейнера backend):
    docker exec vsks_crm-backend_a-1 python -m scripts.export_photo_links > /tmp/photo_links.json
    docker cp vsks_crm-backend_a-1:/tmp/photo_links.json .
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.product_photo_download import pick_external_url  # noqa: E402
from app.services.product_photo_store import has_photo  # noqa: E402


async def run() -> list:
    async with async_session() as db:
        rows = (await db.execute(select(Product).where(Product.is_active == True))).scalars().all()
    out = []
    for p in rows:
        if has_photo(p):
            continue
        url = pick_external_url(p)
        if url:
            out.append({"id": p.id, "url": url})
    return out


def main():
    data = asyncio.run(run())
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n# Товаров без фото с внешней ссылкой: {len(data)}", file=sys.stderr)


if __name__ == "__main__":
    main()
