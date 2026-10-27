#!/usr/bin/env python3
"""Дособирает недостающие данные GALA-выгрузок со страниц товаров магазинов
(kuvalda.ru, regard.ru) или из уже имеющихся характеристик файла (promalper —
без сети). См. tools/catalog_enrich/README не заводим — описание в задаче
/ отчёте сессии; структура GALA — ЕДИНСТВЕННО backend/app/services/
catalog_gala/format.py (здесь только читаем её через gala_quality_loader).

Запуск:
    python enrich_from_product_pages.py <путь_к_gala.json> --mode kuvalda [--limit N]
    python enrich_from_product_pages.py <путь_к_gala.json> --mode regard [--limit N]
    python enrich_from_product_pages.py <путь_к_gala.json> --mode promalper

Результат: <имя>.enriched.json рядом с исходным файлом (исходный НЕ трогается).
Кэш ответов: <имя>.enrich_cache.jsonl рядом с исходным — повторный запуск не
ходит за уже успешно полученными URL (неудачные не кэшируются — на следующий
прогон они просто попробуются снова).
Журнал пропущенных (после 3 неудач) и общий прогресс — tools/catalog_enrich/logs/<mode>_<имя>.log
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brand_dictionary import build_kuvalda_brand_dictionary  # noqa: E402
from caps_brand_rule import find_caps_brand  # noqa: E402
from extractors import extract_kuvalda, extract_regard, trailing_code_from_name  # noqa: E402
from gala_quality_loader import load_catalog_gala  # noqa: E402
from http_client import PoliteFetcher  # noqa: E402

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Код-артикул производителя: буквы/цифры/дефисы, минимум 3 знака, не чисто
# номер товара магазина (тот обычно чисто цифровой и совпадает с source_id).
_MFR_CODE_RE = re.compile(r"^[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\-\./ ]{1,30}$")


def log_line(log_path: Path, text: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")
    print(f"[{ts}] {text}")


def load_cache(cache_path: Path) -> dict:
    cache = {}
    if not cache_path.exists():
        return cache
    with cache_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("ok"):
                cache[rec["url"]] = rec
    return cache


def append_cache(cache_path: Path, rec: dict) -> None:
    with cache_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def set_characteristic(characteristics: list, name: str, value: str) -> None:
    """Обновляет (или добавляет) запись характеристики по имени (без учёта
    регистра), не трогая остальные."""
    name_lower = name.lower()
    for c in characteristics:
        if (c.get("name") or "").strip().lower() == name_lower:
            c["value"] = value
            return
    characteristics.append({"name": name, "value": value, "unit": None})


def looks_like_manufacturer_code(code: str, store_article, source_id) -> bool:
    if not code:
        return False
    code = code.strip()
    if not code or len(code) < 3:
        return False
    if code in (str(store_article or ""), str(source_id or "")):
        return False
    if not _MFR_CODE_RE.match(code):
        return False
    return True


# --------------------------------------------------------------------------
# kuvalda — полная пересборка бренда БЕЗ СЕТИ (владелец, 27.10.2026, третье
# решение по Кувалде): исходному manufacturer файла не доверять вовсе — у
# ~2190 строк там второе слово названия, а не бренд (is_bogus_manufacturer
# ловит только совпадение с ПЕРВЫМ словом, такой мусор пропускал). Бренд
# собирается заново для ВСЕХ строк, одно правило в одном месте:
#   1) словарь имени (brand_dictionary.py, целым словом/самое длинное,
#      ГДЕ-ЛИБО в названии — не только в начале);
#   2) иначе — правило ЗАГЛАВНЫХ (caps_brand_rule.py);
#   3) иначе — null (не выдумываем).
# Мусор по is_bogus_manufacturer на любом шаге — null. Сети НЕ требует.
#
# Владелец, 27.10.2026 (вторая правка) — словарь приоритетнее заглавной
# последовательности, даже когда бренд стоит ДАЛЬШЕ в названии, чем слово,
# пойманное правилом 2 ("Зажим для труб CS (хомут) HUSQVARNA" → HUSQVARNA,
# не CS): два прохода по всем строкам.
#   Проход 1 — словарь (как он есть) → иначе правило 2, со счётчиком частоты
#   найденных так брендов.
#   Между проходами — бренды правила 2 с частотой ≥2 в проходе 1 ДОБАВЛЯЮТСЯ
#   в словарь (повтор на разных товарах — подтверждение, что это настоящий
#   бренд, не случайное совпадение).
#   Проход 2 (итоговый) — словарь (уже расширенный) ищет по ВСЕМУ названию
#   и сам выбирает самое длинное совпадение где угодно в строке; поэтому
#   бренд, узнанный из других строк, перебивает более раннее, но более
#   слабое совпадение правила 2 в этой же строке.
_CAPS_BRAND_MIN_FREQ_TO_PROMOTE = 2
# --------------------------------------------------------------------------

def rebuild_kuvalda_brands_offline(items: list, quality, cache_path: Path, log_path: Path,
                                    other_catalogs_dir: Path, limit: int = 0) -> dict:
    stats = {"processed": 0, "matched_by_name": 0, "matched_by_caps": 0, "no_match": 0}
    caps_brand_counts: dict[str, int] = {}

    brand_dict = build_kuvalda_brand_dictionary(quality, cache_path, items, other_catalogs_dir)
    log_line(log_path, f"kuvalda (offline-пересборка): словарь брендов построен, {len(brand_dict)} записей, "
                        f"всего строк = {len(items)}")

    # Проход 1 — только чтобы собрать частоты брендов правила 2 (word->count).
    for item in items:
        name = item.get("name") or ""
        if brand_dict.find_in_name(name):
            continue
        caps_brand = find_caps_brand(name)
        if caps_brand and not quality.is_bogus_manufacturer(caps_brand, name):
            caps_brand_counts[caps_brand] = caps_brand_counts.get(caps_brand, 0) + 1

    promoted = 0
    for brand, count in caps_brand_counts.items():
        if count >= _CAPS_BRAND_MIN_FREQ_TO_PROMOTE:
            brand_dict.add(brand)
            promoted += 1
    brand_dict.finalize()
    log_line(log_path, f"kuvalda (offline-пересборка): в словарь добавлено {promoted} брендов правила 2 "
                        f"(частота ≥{_CAPS_BRAND_MIN_FREQ_TO_PROMOTE}), словарь теперь {len(brand_dict)} записей")

    # Проход 2 — итоговый, с расширенным словарём.
    caps_brand_counts = {}  # пересчитаем по финальному выбору для отчёта
    for item in items:
        if limit and stats["processed"] >= limit:
            break
        name = item.get("name") or ""
        characteristics = item.setdefault("characteristics", []) or []

        brand = brand_dict.find_in_name(name)
        if brand:
            stats["matched_by_name"] += 1
        else:
            caps_brand = find_caps_brand(name)
            if caps_brand and not quality.is_bogus_manufacturer(caps_brand, name):
                brand = caps_brand
                stats["matched_by_caps"] += 1
                caps_brand_counts[caps_brand] = caps_brand_counts.get(caps_brand, 0) + 1
            else:
                stats["no_match"] += 1

        item["manufacturer"] = brand  # исходному значению не доверяем — перезаписываем всегда
        if brand:
            set_characteristic(characteristics, "Бренд", brand)

        stats["processed"] += 1
        if stats["processed"] % 2000 == 0:
            log_line(log_path, f"kuvalda (offline-пересборка): обработано {stats['processed']}/{len(items)}")

    stats["caps_brand_counts"] = caps_brand_counts
    return stats


def process_kuvalda(items: list, quality, fetcher: Optional[PoliteFetcher], cache: dict,
                     cache_path: Path, log_path: Path, limit: int,
                     other_catalogs_dir: Path, no_fetch: bool = False) -> dict:
    """Владелец, 27.10.2026: у 842/843 проверенных страниц бренд со страницы
    и так стоит в названии товара — ДО похода на страницу пробуем найти
    бренд прямо в названии по словарю (brand_dictionary.py); страница
    запрашивается только если словарь не дал совпадения.

    no_fetch=True (владелец, 27.10.2026, второе решение по Кувалде — по
    страницам больше не ходить): страница НЕ запрашивается вовсе — только
    словарь + уже имеющийся кэш страниц; не нашлось ни там, ни там →
    manufacturer остаётся как было (бренд не выдумывается), считается в
    stats["no_match"]. fetcher может быть None в этом режиме."""
    stats = {"processed": 0, "manufacturer_fixed": 0, "articles_added": 0,
              "characteristics_replaced": 0, "errors": 0, "skipped_no_url": 0,
              "matched_by_name": 0, "fetched_pages": 0, "no_match": 0}
    todo = [it for it in items if quality.is_bogus_manufacturer(it.get("manufacturer"), it.get("name"))]
    log_line(log_path, f"kuvalda: строк с неправильным производителем = {len(todo)}")

    brand_dict = build_kuvalda_brand_dictionary(quality, cache_path, items, other_catalogs_dir)
    log_line(log_path, f"kuvalda: словарь брендов построен, {len(brand_dict)} записей")

    done = 0
    for item in todo:
        if limit and done >= limit:
            break
        characteristics = item.setdefault("characteristics", []) or []

        name_brand = brand_dict.find_in_name(item.get("name") or "")
        if name_brand:
            if item.get("manufacturer") != name_brand:
                item["manufacturer"] = name_brand
                stats["manufacturer_fixed"] += 1
            set_characteristic(characteristics, "Бренд", name_brand)
            stats["matched_by_name"] += 1
            stats["processed"] += 1
            done += 1
            if stats["processed"] % 200 == 0:
                log_line(log_path, f"kuvalda: обработано {stats['processed']}/{len(todo)}")
            continue

        url = item.get("source_url")
        if not url:
            stats["skipped_no_url"] += 1
            continue

        rec = cache.get(url)
        if rec is None:
            if no_fetch:
                item["manufacturer"] = None  # бренд не выдумываем — явный null
                stats["no_match"] += 1
                stats["processed"] += 1
                done += 1
                continue
            result = fetcher.fetch(url)
            if not result.ok:
                log_line(log_path, f"ПРОПУСК (ошибка сети): {url} — {result.error}")
                stats["errors"] += 1
                done += 1
                continue
            data = extract_kuvalda(result.html)
            rec = {"url": url, "ok": True, "data": data}
            append_cache(cache_path, rec)
            cache[url] = rec
        stats["fetched_pages"] += 1

        data = rec["data"]
        brand = data.get("brand")
        sku = data.get("sku")

        if brand and not quality.is_bogus_manufacturer(brand, item.get("name")):
            if item.get("manufacturer") != brand:
                item["manufacturer"] = brand
                stats["manufacturer_fixed"] += 1
            set_characteristic(characteristics, "Бренд", brand)

        if sku and looks_like_manufacturer_code(sku, item.get("store_article"), item.get("source_id")):
            if item.get("manufacturer_article") != sku:
                item["manufacturer_article"] = sku
                stats["articles_added"] += 1
                set_characteristic(characteristics, "Модель производителя", sku)

        stats["processed"] += 1
        done += 1
        if stats["processed"] % 200 == 0:
            log_line(log_path, f"kuvalda: обработано {stats['processed']}/{len(todo)}")

    remaining_bogus = sum(
        1 for it in items if quality.is_bogus_manufacturer(it.get("manufacturer"), it.get("name"))
    )
    stats["remaining_bogus"] = remaining_bogus
    stats["total_bogus_before"] = len(todo)
    return stats


# --------------------------------------------------------------------------
# regard
# --------------------------------------------------------------------------

def process_regard(items: list, quality, fetcher: PoliteFetcher, cache: dict,
                    cache_path: Path, log_path: Path, limit: int) -> dict:
    stats = {"processed": 0, "manufacturer_fixed": 0, "articles_added": 0,
              "characteristics_replaced": 0, "errors": 0, "skipped_no_url": 0}
    bogus_before = sum(
        1 for it in items if quality.is_bogus_manufacturer(it.get("manufacturer"), it.get("name"))
    )
    log_line(log_path, f"regard: всего строк = {len(items)}, с неправильным производителем = {bogus_before}")

    done = 0
    for item in items:
        if limit and done >= limit:
            break
        url = item.get("source_url")
        if not url:
            stats["skipped_no_url"] += 1
            continue

        rec = cache.get(url)
        if rec is None:
            result = fetcher.fetch(url)
            if not result.ok:
                log_line(log_path, f"ПРОПУСК (ошибка сети): {url} — {result.error}")
                stats["errors"] += 1
                done += 1
                continue
            data = extract_regard(result.html)
            rec = {"url": url, "ok": True, "data": data}
            append_cache(cache_path, rec)
            cache[url] = rec

        data = rec["data"]
        vendor = data.get("vendor")
        vendorcode = data.get("vendorcode")
        page_characteristics = data.get("characteristics") or []

        if vendor and not quality.is_bogus_manufacturer(vendor, item.get("name")):
            if item.get("manufacturer") != vendor:
                item["manufacturer"] = vendor
                stats["manufacturer_fixed"] += 1

        article = vendorcode
        if not article:
            article = trailing_code_from_name(item.get("name") or "")
        if article and looks_like_manufacturer_code(article, item.get("store_article"), item.get("source_id")):
            if not item.get("manufacturer_article"):
                item["manufacturer_article"] = article
                stats["articles_added"] += 1

        if len(page_characteristics) >= 2:
            item["characteristics"] = page_characteristics
            stats["characteristics_replaced"] += 1

        stats["processed"] += 1
        done += 1
        if stats["processed"] % 200 == 0:
            log_line(log_path, f"regard: обработано {stats['processed']}/{len(items)}")

    remaining_bogus = sum(
        1 for it in items if quality.is_bogus_manufacturer(it.get("manufacturer"), it.get("name"))
    )
    stats["remaining_bogus"] = remaining_bogus
    stats["total_bogus_before"] = bogus_before
    return stats


# --------------------------------------------------------------------------
# magazin01 (строки без бренда; тот же JSON-LD shape, что у kuvalda —
# extract_kuvalda() переиспользуется, ПРАВИЛО №6)
# --------------------------------------------------------------------------

def process_magazin01(items: list, quality, fetcher: PoliteFetcher, cache: dict,
                       cache_path: Path, log_path: Path, limit: int) -> dict:
    stats = {"processed": 0, "manufacturer_fixed": 0, "articles_added": 0,
              "characteristics_replaced": 0, "errors": 0, "skipped_no_url": 0}
    todo = [it for it in items if not (it.get("manufacturer") or "").strip()]
    log_line(log_path, f"magazin01: строк без бренда = {len(todo)}")

    done = 0
    for item in todo:
        if limit and done >= limit:
            break
        url = item.get("source_url") or item.get("link_1")
        if not url:
            stats["skipped_no_url"] += 1
            continue

        rec = cache.get(url)
        if rec is None:
            result = fetcher.fetch(url)
            if not result.ok:
                log_line(log_path, f"ПРОПУСК (ошибка сети): {url} — {result.error}")
                stats["errors"] += 1
                done += 1
                continue
            data = extract_kuvalda(result.html)  # тот же JSON-LD @type=Product shape
            rec = {"url": url, "ok": True, "data": data}
            append_cache(cache_path, rec)
            cache[url] = rec

        data = rec["data"]
        brand = data.get("brand")
        sku = data.get("sku")  # внутренний код магазина, НЕ штрихкод (см. докстринг extractors.py)

        if brand and not quality.is_bogus_manufacturer(brand, item.get("name")):
            item["manufacturer"] = brand
            stats["manufacturer_fixed"] += 1

        if sku and not (item.get("store_article") or "").strip():
            item["store_article"] = sku

        stats["processed"] += 1
        done += 1
        if stats["processed"] % 200 == 0:
            log_line(log_path, f"magazin01: обработано {stats['processed']}/{len(todo)}")

    remaining_no_brand = sum(1 for it in items if not (it.get("manufacturer") or "").strip())
    stats["remaining_bogus"] = remaining_no_brand
    stats["total_bogus_before"] = len(todo)
    return stats


# --------------------------------------------------------------------------
# promalper (без сети — только характеристики файла)
# --------------------------------------------------------------------------

_BRAND_CHAR_KEYS = ("бренд", "производитель")


def process_promalper(items: list, quality, limit: int) -> dict:
    stats = {"processed": 0, "manufacturer_fixed": 0, "articles_added": 0,
              "characteristics_replaced": 0, "errors": 0}
    bogus_before = sum(
        1 for it in items if quality.is_bogus_manufacturer(it.get("manufacturer"), it.get("name"))
    )
    log_line(
        LOG_DIR / "promalper.log",
        f"promalper: всего строк = {len(items)}, с неправильным производителем = {bogus_before}",
    )

    done = 0
    for item in items:
        if limit and done >= limit:
            break
        characteristics = item.get("characteristics") or []
        brand_value = None
        for key in _BRAND_CHAR_KEYS:
            for c in characteristics:
                if (c.get("name") or "").strip().lower() == key:
                    v = (c.get("value") or "").strip()
                    if v:
                        brand_value = v
                        break
            if brand_value:
                break

        stats["processed"] += 1
        done += 1
        if not brand_value:
            continue
        if quality.is_bogus_manufacturer(brand_value, item.get("name")):
            continue

        old_manufacturer = item.get("manufacturer")
        if old_manufacturer == brand_value:
            continue

        if old_manufacturer and quality.is_country_name((old_manufacturer or "").strip().lower()) \
                and not item.get("country_origin"):
            item["country_origin"] = old_manufacturer

        item["manufacturer"] = brand_value
        stats["manufacturer_fixed"] += 1

    remaining_bogus = sum(
        1 for it in items if quality.is_bogus_manufacturer(it.get("manufacturer"), it.get("name"))
    )
    stats["remaining_bogus"] = remaining_bogus
    stats["total_bogus_before"] = bogus_before
    return stats


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="путь к GALA-файлу (.json)")
    parser.add_argument("--mode", required=True, choices=["kuvalda", "regard", "promalper", "magazin01"])
    parser.add_argument("--limit", type=int, default=0, help="обработать не более N подходящих строк (0 = все)")
    parser.add_argument("--min-interval", type=float, default=1.0, help="мин. секунд между запросами")
    parser.add_argument("--no-fetch", action="store_true",
                         help="kuvalda: не ходить на страницы вообще — только словарь имени + уже имеющийся кэш; "
                              "не нашлось ни там, ни там → manufacturer=null")
    args = parser.parse_args()

    quality = load_catalog_gala()

    data = json.loads(args.path.read_text(encoding="utf-8"))
    items = data.get("items") or []

    cache_path = args.path.with_name(args.path.stem + ".enrich_cache.jsonl")
    output_path = args.path.with_name(args.path.stem + ".enriched.json")
    log_path = LOG_DIR / f"{args.mode}_{args.path.stem}.log"

    log_line(log_path, f"старт: mode={args.mode} path={args.path} limit={args.limit or 'без лимита'}")

    if args.mode == "promalper":
        stats = process_promalper(items, quality, args.limit)
    elif args.mode == "kuvalda" and args.no_fetch:
        log_line(log_path, "kuvalda --no-fetch: полная пересборка бренда без сети (исходный manufacturer не используется)")
        stats = rebuild_kuvalda_brands_offline(items, quality, cache_path, log_path, args.path.parent, args.limit)
    else:
        fetcher = PoliteFetcher(min_interval=args.min_interval)
        cache = load_cache(cache_path)
        log_line(log_path, f"кэш: {len(cache)} уже полученных URL")
        if args.mode == "kuvalda":
            stats = process_kuvalda(items, quality, fetcher, cache, cache_path, log_path, args.limit,
                                     args.path.parent)
        elif args.mode == "magazin01":
            stats = process_magazin01(items, quality, fetcher, cache, cache_path, log_path, args.limit)
        else:
            stats = process_regard(items, quality, fetcher, cache, cache_path, log_path, args.limit)

    data["items"] = items
    errors = quality.validate_gala_catalog(data)
    if errors:
        log_line(log_path, f"ВНИМАНИЕ: validate_gala_catalog нашла {len(errors)} ошибок, первые 10:")
        for e in errors[:10]:
            log_line(log_path, f"  {e}")

    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.mode == "kuvalda" and args.no_fetch:
        summary = (
            f"ИТОГ [kuvalda --no-fetch] {args.path.name}: обработано={stats['processed']}, "
            f"словарь={stats['matched_by_name']}, заглавные={stats['matched_by_caps']}, "
            f"null={stats['no_match']}, "
            f"валидация: {'ОК' if not errors else f'{len(errors)} ошибок'} → {output_path}"
        )
    else:
        summary = (
            f"ИТОГ [{args.mode}] {args.path.name}: "
            f"обработано={stats.get('processed', 0)}, "
            f"производителей исправлено={stats.get('manufacturer_fixed', 0)}, "
            f"осталось неправильных={stats.get('remaining_bogus', '?')} (было {stats.get('total_bogus_before', '?')}), "
            f"характеристик заменено={stats.get('characteristics_replaced', 0)}, "
            f"артикулов добавлено={stats.get('articles_added', 0)}, "
            + (f"из них по словарю имени={stats.get('matched_by_name', 0)}, "
               f"со страниц(кэш)={stats.get('fetched_pages', 0)}, "
               f"осталось null={stats.get('no_match', 0)}, " if args.mode == "kuvalda" else "")
            + f"ошибок сети={stats.get('errors', 0)}, "
            f"валидация: {'ОК' if not errors else f'{len(errors)} ошибок'} → {output_path}"
        )
    log_line(log_path, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
