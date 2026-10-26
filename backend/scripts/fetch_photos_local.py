#!/usr/bin/env python3
"""ЗАПУСКАЕТСЯ ЛОКАЛЬНО, вне Docker, обычным `python` (сервер прода/разработки
403-ит некоторых поставщиков по IP — фото качаем с машины разработчика).

Зависимости: requests, Pillow (НЕ fastapi/sqlalchemy/app.* — этот скрипт не
трогает БД и не должен требовать докер-окружения):
    pip install requests Pillow

Вход: JSON-файл вида [{"id": 123, "url": "https://..."}, ...] — экспортируется
scripts/export_photo_links.py внутри Docker (там есть доступ к БД).

Выход: папка с файлами <id>.webp — сжатыми той же функцией, что
app/services/product_photo_store.py (ПРАВИЛО №6 — переиспользуем
product_photo_compress.compress_product_photo, загружаем файл напрямую по
пути через importlib, НЕ `import app.*`, чтобы не тянуть пакет app/__init__.py
со всем FastAPI/SQLAlchemy приложением).

Продолжает с места остановки: уже скачанные <id>.webp пропускаются.
Параллелизм 8 потоков, таймаут 20с, 1 ретрай, браузерный User-Agent и
Referer = origin исходной ссылки (многие магазины отдают 403 без Referer).

Запуск:
    python scripts/fetch_photos_local.py photo_links.json --out photos/
"""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import sys
import time
from urllib.parse import urlsplit

try:
    import requests
except ImportError:
    print("Нужен пакет requests: pip install requests", file=sys.stderr)
    sys.exit(1)

_HERE = os.path.dirname(os.path.abspath(__file__))
_COMPRESS_PATH = os.path.join(_HERE, "..", "app", "services", "product_photo_compress.py")


def _load_compress_module():
    """Грузит product_photo_compress.py напрямую по пути файла (importlib),
    минуя `app/__init__.py` (который бы потянул FastAPI/SQLAlchemy и всё
    приложение) — тот же единственный модуль сжатия, что и в контейнере."""
    spec = importlib.util.spec_from_file_location("product_photo_compress", _COMPRESS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_compress_mod = _load_compress_module()
compress_product_photo = _compress_mod.compress_product_photo

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 20
RETRIES = 1
PARALLELISM = 8


def _referer(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def _fetch_one(item: dict, out_dir: str) -> tuple:
    pid = item["id"]
    url = item["url"]
    dest = os.path.join(out_dir, f"{pid}.webp")
    domain = urlsplit(url).netloc
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return pid, domain, "skipped_exists", None

    headers = {"User-Agent": UA, "Referer": _referer(url)}
    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            raw = resp.content
            if not raw:
                raise ValueError("empty body")
            compressed, _mime = compress_product_photo(raw)
            tmp = dest + ".tmp"
            with open(tmp, "wb") as f:
                f.write(compressed)
            os.replace(tmp, dest)
            return pid, domain, "ok", len(compressed)
        except Exception as e:
            last_err = str(e)
            time.sleep(0.5)
    return pid, domain, "error", last_err


def run(items: list, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLELISM) as pool:
        futures = [pool.submit(_fetch_one, item, out_dir) for item in items]
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            pid, domain, status, info = fut.result()
            done += 1
            results.append((pid, domain, status, info))
            print(f"[{done}/{len(items)}] id={pid} domain={domain} status={status}"
                  + (f" ({info})" if status in ("error",) else ""))

    ok = [r for r in results if r[2] == "ok"]
    skipped = [r for r in results if r[2] == "skipped_exists"]
    errors = [r for r in results if r[2] == "error"]
    by_domain_errors: dict = {}
    for _pid, domain, status, _info in results:
        if status == "error":
            by_domain_errors[domain] = by_domain_errors.get(domain, 0) + 1

    print("\n" + "=" * 60)
    print(f"Всего: {len(items)}  ок: {len(ok)}  уже было: {len(skipped)}  ошибок: {len(errors)}")
    if ok:
        avg_kb = sum(r[3] for r in ok) / len(ok) / 1024
        print(f"Средний размер после сжатия: {avg_kb:.1f} КБ")
    if by_domain_errors:
        print("Ошибки по доменам:")
        for domain, cnt in sorted(by_domain_errors.items(), key=lambda kv: -kv[1]):
            print(f"  {domain}: {cnt}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", help="JSON [{id,url},...] от export_photo_links.py")
    parser.add_argument("--out", default="photos", help="папка для <id>.webp (по умолчанию ./photos)")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число ссылок (отладка)")
    args = parser.parse_args()

    with open(args.json_file, "r", encoding="utf-8") as f:
        items = json.load(f)
    if args.limit:
        items = items[: args.limit]
    run(items, args.out)


if __name__ == "__main__":
    main()
