#!/usr/bin/env python3
"""CLI: убрать рекламные предложения магазина-поставщика из Product.description
уже загруженных товаров (владелец, 26.10.2026, Задача 4).

Своей логики очистки текста этот скрипт НЕ пишет (ПРАВИЛО №6) — вызывает
ЕДИНСТВЕННЫЙ фильтр app.services.catalog_gala.ad_text_filter.strip_ad_sentences
(второй такой фильтр не заводить). Единственное, что добавляет сам скрипт —
применение этого фильтра к description ПОАБЗАЦНО (абзацы разделены "\\n\\n",
см. _strip_preserving_paragraphs ниже), потому что strip_ad_sentences режет
текст по строкам внутри одной "\\n"-строки и теряет сами разделители "\\n\\n"
между абзацами (пустые строки у него не формируют пустых "абзацев" на
выходе) — для description, где абзацы технических характеристик ("Диаметр:
300 мм") должны остаться читаемыми отдельно от рекламного абзаца, строки
внутри одного абзаца важно не склеивать в одну "\\n"-строку перед вызовом
фильтра, а передавать абзац как есть (возможно, многострочный) и склеивать
результаты обратно через "\\n\\n".

Запуск (внутри контейнера backend):
    docker exec vsks_crm-backend_a-1 python -m scripts.strip_ads_from_descriptions
    docker exec vsks_crm-backend_a-1 python -m scripts.strip_ads_from_descriptions \\
        --apply --batch 2000 --user-email <email>

По умолчанию — dry-run (ничего не пишет). --apply обязательно требует
--user-email (как и load_gala_catalog.py) — через него определяется
user_id для set_product_description(source="import"): это ПРАВКА уже
загруженного описания импортированного товара, тот же смысл source, что у
rebuild_descriptions_from_sources.py (import_note самого товара этот скрипт
не трогает — меняется только description через единственного писателя
истории app.services.product_description_history.set_product_description).

Товары читаются порциями по id (keyset-пагинация, как в
recompress_product_photos.py) — на каждую порцию отдельная сессия/транзакция
с select только колонок id/description/import_note (load_only), чтобы не
грузить в память весь каталог (~215 тыс. товаров) целиком.

Фильтр по источнику (владелец, 27.10.2026) — ОБЯЗАТЕЛЬНЫЙ, не опциональный:
товар трогается только если его import_note даёт имя файла (см.
_import_note_file), совпадающее (fnmatch, маски "*" разрешены) с одним из
--files (по умолчанию — DEFAULT_SOURCE_FILES, выгрузки магазинов-поставщиков).
Товары без import_note или с import_note другого формата (в частности «ТЗ
для АПИ *.xlsx» — тексты, которые вписал владелец вручную, не каталог
магазина) НИКОГДА не трогаются, независимо от --files: это тексты человека,
не реклама поставщика, им в этом скрипте не место ни при каких масках.
"""
import argparse
import asyncio
import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from sqlalchemy import select, func  # noqa: E402
from sqlalchemy.orm import load_only  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.catalog_gala.ad_text_filter import strip_ad_sentences  # noqa: E402
from app.services.product_description_history import set_product_description  # noqa: E402

# Источник записи истории (Source в product_description_history.py) — эта
# правка относится к уже импортированным описаниям поставщика, не к ручной
# правке оператором и не к принятию предложения ИИ, поэтому "import" (тот
# же source, что у rebuild_descriptions_from_sources.py), не "edit".
_HISTORY_SOURCE = "import"

# Извлечение имени файла-источника из import_note вида
# «Импорт каталога из файла «X», ФИО, дата» (см.
# products_import_apply.py::apply_products_import, _import_note) — для
# группировки статистики "сколько изменится по файлу", вторую формулировку
# этого текста здесь не заводим, просто парсим готовую строку.
_IMPORT_NOTE_FILE_RE = re.compile(r"импорт каталога из файла\s*«([^»]*)»", re.IGNORECASE)


def _import_note_file(import_note):
    if not import_note:
        return "(без import_note)"
    m = _IMPORT_NOTE_FILE_RE.search(import_note)
    return m.group(1) if m else "(прочий import_note)"


# Значения _import_note_file, у которых НЕТ реального имени файла-источника
# (товар либо вообще без import_note, либо с import_note нераспознанного
# формата) — такие товары не трогаем вообще, независимо от --files, см.
# докстринг модуля.
_NO_SOURCE_FILE_MARKERS = ("(без import_note)", "(прочий import_note)")

# «ТЗ для АПИ *.xlsx» — тексты владельца, вписанные вручную, не каталог
# магазина (владелец, 27.10.2026). Жёсткий запрет, НЕ зависящий от
# --files: даже если кто-то явно передаст маску "*"/"ТЗ*", эти товары всё
# равно не трогаются — в отличие от DEFAULT_SOURCE_FILES (который можно
# сузить/расширить через --files), этот запрет никаким аргументом не
# обходится.
_HARD_BLOCKED_SOURCE_PATTERN = "тз для апи*"


def _is_hard_blocked_source(file_key: str) -> bool:
    return fnmatch.fnmatch(file_key.lower(), _HARD_BLOCKED_SOURCE_PATTERN)

# Выгрузки магазинов-поставщиков (владелец, 27.10.2026) — ЕДИНСТВЕННЫЙ
# дефолтный список источников, которые можно чистить этим скриптом. «ТЗ для
# АПИ *.xlsx» и любой другой источник сюда НЕ входят намеренно — это тексты
# владельца, не реклама поставщика (см. докстринг модуля). Маски ("*")
# разрешены — electro_mpo_*/vkusvill_grocery_nomenclature* покрывают
# несколько файлов одного поставщика.
DEFAULT_SOURCE_FILES = (
    "fire_equipment_nomenclature.json",
    "k_spasatel_rescue_nomenclature.json",
    "rescue_medical_nomenclature.json",
    "promalp_height_safety_nomenclature.json",
    "sima_land_catalog_all.json",
    "baucenter_construction_all.json",
    "baucenter_electro_lighting.json",
    "baucenter_tools_hardware.json",
    "electro_mpo_*.json",
    "vkusvill_grocery_nomenclature*.json",
)


def source_file_allowed(import_note, file_patterns) -> bool:
    """Товар трогается только если его import_note даёт РЕАЛЬНОЕ имя файла
    (не "(без import_note)"/"(прочий import_note)") и это имя совпадает
    (fnmatch, маски разрешены) с хотя бы одним из `file_patterns`. Без
    import_note или с нераспознанным import_note — всегда False, что бы ни
    было в `file_patterns` (защита «ТЗ для АПИ» и прочих текстов владельца,
    см. докстринг модуля)."""
    file_key = _import_note_file(import_note)
    if file_key in _NO_SOURCE_FILE_MARKERS:
        return False
    if _is_hard_blocked_source(file_key):
        return False
    return any(fnmatch.fnmatch(file_key, pattern) for pattern in file_patterns)


def strip_ads_preserving_paragraphs(description):
    """Применяет strip_ad_sentences к КАЖДОМУ абзацу description отдельно
    (абзацы — части, разделённые пустой строкой "\\n\\n") и склеивает
    оставшиеся непустые абзацы обратно через "\\n\\n". Абзац, после фильтра
    ставший пустым (strip_ad_sentences вернул None — абзац был целиком
    рекламой), выбрасывается целиком, остальные абзацы и порядок между ними
    не меняются. Пустой/None вход, а также вход, где рекламными оказались
    ВСЕ абзацы, дают None (тот же контракт, что у strip_ad_sentences)."""
    if not description:
        return None
    kept_paragraphs = []
    for paragraph in description.split("\n\n"):
        filtered = strip_ad_sentences(paragraph)
        if filtered:
            kept_paragraphs.append(filtered)
    result = "\n\n".join(kept_paragraphs).strip()
    return result or None


async def _count_total(db) -> int:
    return (await db.execute(select(func.count()).select_from(Product))).scalar() or 0


async def _fetch_batch(db, after_id, batch_size):
    stmt = (
        select(Product)
        .options(load_only(Product.id, Product.description, Product.import_note))
        .order_by(Product.id)
        .limit(batch_size)
    )
    if after_id is not None:
        stmt = stmt.where(Product.id > after_id)
    return (await db.execute(stmt)).scalars().all()


async def _get_user_id(email: str) -> int:
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user:
            print(f"Пользователь с email {email!r} не найден.", file=sys.stderr)
            sys.exit(1)
        return user.id


async def process_rows(db, rows, apply: bool, user, file_patterns, max_samples: int = 15) -> dict:
    """Обрабатывает уже загруженные в сессию `rows` (товары одной порции,
    или произвольный список в тестах) — ядро логики, вынесено из цикла
    пагинации `run()`, чтобы юнит-тест мог вызывать его напрямую с
    `db_session`/вручную созданными Product, без сетевого батчинга по id
    (тот же приём, что у _process_file в rebuild_descriptions_from_sources.py,
    ПРАВИЛО №6 — не вторая копия, вызывается из run() ниже).

    `file_patterns` — ОБЯЗАТЕЛЬНЫЙ фильтр по источнику (владелец,
    27.10.2026, см. докстринг модуля/source_file_allowed): товар, чей
    import_note не распознан как имя файла из `file_patterns`, пропускается
    целиком, даже если его description реально содержит рекламу — счётчики
    не трогает (не считается ни в will_change, ни в became_empty)."""
    will_change = 0
    became_empty = 0  # new пуст (strip_ad_sentences вернул None по абзацам целиком) — не трогаем, считаем отдельно
    by_file = {}  # import_note-файл -> счётчик изменится
    samples = []  # [{"id", "old", "new"}], первые max_samples изменённых

    for row in rows:
        if not source_file_allowed(row.import_note, file_patterns):
            continue

        old = row.description
        new = strip_ads_preserving_paragraphs(old)

        if new == old:
            continue  # либо не изменилось, либо не было рекламы

        if not new:
            became_empty += 1
            continue  # новое пусто — не трогаем (по условию задачи)

        will_change += 1
        file_key = _import_note_file(row.import_note)
        by_file[file_key] = by_file.get(file_key, 0) + 1
        if len(samples) < max_samples:
            samples.append({"id": row.id, "old": (old or "")[:200], "new": new[:200]})

        if apply:
            await set_product_description(db, row, "description", new, user, source=_HISTORY_SOURCE)

    return {
        "processed": len(rows),
        "will_change": will_change,
        "became_empty": became_empty,
        "by_file": by_file,
        "samples": samples,
    }


def _merge_report(total_report: dict, batch_report: dict) -> None:
    total_report["processed"] += batch_report["processed"]
    total_report["will_change"] += batch_report["will_change"]
    total_report["became_empty"] += batch_report["became_empty"]
    for file_key, count in batch_report["by_file"].items():
        total_report["by_file"][file_key] = total_report["by_file"].get(file_key, 0) + count
    remaining = max(0, 15 - len(total_report["samples"]))
    if remaining:
        total_report["samples"].extend(batch_report["samples"][:remaining])


async def run(apply: bool, batch_size: int, user_id, file_patterns) -> dict:
    async with async_session() as db:
        total = await _count_total(db)
    print(f"Всего товаров: {total}")

    report = {"total": total, "processed": 0, "will_change": 0, "became_empty": 0, "by_file": {}, "samples": []}
    after_id = None

    while True:
        async with async_session() as db:
            rows = await _fetch_batch(db, after_id, batch_size)
            if not rows:
                break

            user = await db.get(User, user_id) if (apply and user_id is not None) else None

            batch_report = await process_rows(db, rows, apply, user, file_patterns)
            _merge_report(report, batch_report)
            after_id = rows[-1].id

            if apply:
                await db.commit()

        if len(rows) < batch_size:
            break

    return report


def _print_report(report: dict, apply: bool) -> None:
    mode = "ПРИМЕНЕНО" if apply else "DRY-RUN (ничего не записано)"
    print(f"\n=== {mode} ===")
    print(f"обработано товаров: {report['processed']} из {report['total']}")
    print(f"изменится/изменено описаний: {report['will_change']}")
    print(f"новое описание стало бы пустым (не трогаем): {report['became_empty']}")

    print("\n--- по import_note-файлу ---")
    for file_key, count in sorted(report["by_file"].items(), key=lambda kv: -kv[1]):
        print(f"  {file_key}: {count}")

    print(f"\n--- примеры «было -> станет» (до {len(report['samples'])}) ---")
    for s in report["samples"]:
        print(f"\n  id={s['id']}")
        print(f"    было:   {s['old']!r}")
        print(f"    станет: {s['new']!r}")


async def main_async(apply: bool, batch_size: int, user_email, file_patterns):
    user_id = None
    if apply:
        if not user_email:
            print("--apply требует --user-email", file=sys.stderr)
            sys.exit(2)
        user_id = await _get_user_id(user_email)

    report = await run(apply, batch_size, user_id, file_patterns)
    _print_report(report, apply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="реально записать изменения (по умолчанию — dry-run)")
    parser.add_argument("--batch", type=int, default=2000, help="размер порции по id (по умолчанию 2000)")
    parser.add_argument("--user-email", default=None, help="email пользователя для --apply (source='import')")
    parser.add_argument(
        "--files", nargs="+", default=None,
        help="маски имён файлов-источников (import_note), по умолчанию — DEFAULT_SOURCE_FILES "
             "(выгрузки магазинов; «ТЗ для АПИ *.xlsx» и товары без import_note не трогаются никогда)",
    )
    args = parser.parse_args()

    file_patterns = args.files or DEFAULT_SOURCE_FILES
    asyncio.run(main_async(args.apply, args.batch, args.user_email, file_patterns))


if __name__ == "__main__":
    main()
