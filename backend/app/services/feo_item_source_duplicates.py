"""Признак «дубль строки листа» для плановых позиций ФЭО (владелец,
22.10.2026) — ПРАВИЛО №6: ОДНО правило совпадения для ДВУХ потребителей:
  1) `feo_import_duplicates.py::_upsert_one` (повторный импорт той же строки
     листа в ДРУГУЮ статью переносит существующую позицию, а не заводит вторую
     — см. её докстринг);
  2) этот модуль — тот же признак для экрана (GET /api/feo-categories/
     plan-positions, FeoLevel5Panel.vue — значок «дубль строки N»).

Повод (прод, субсидия ДНР_2026 id 105): строки 253 «Чайник электрический» и
254 «Термопот» первая загрузка файла положила на статью «Расходы на
приобретение основных средств», повторная загрузка ТОГО ЖЕ файла (через 10
минут, тот же source_row/имя) создала их ЕЩЁ РАЗ в подстатье «Бытовая
техника» — план задвоился на 16 500, обе копии видны в дереве как будто это
две разные покупки.

Правило совпадения: активная FeoPlannedItem считается «той же строкой листа»,
что и другая активная FeoPlannedItem ТОЙ ЖЕ СУБСИДИИ, если у них совпадают
`source_row` (номер строки файла, NULL — позиция заведена в GALA вручную и
никогда не участвует) И нормализованное имя (`normalize_feo_name` — тот же
нормализатор, что и в `feo_import_duplicates.group_key`/`_matching_items`,
Правило проекта «дедуп только точным совпадением», без fuzzy). «Дубль» — ТОЛЬКО
когда совпадающие позиции лежат в РАЗНЫХ категориях ФЭО; совпадение внутри
ОДНОЙ категории — это обычная группа дублей импорта (`feo_import_duplicates.py`,
волна 4, п.23), к этому признаку не относится.
"""
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.utils.text import normalize_feo_name
from sqlalchemy import select


async def build_source_row_index(db, subsidy_id: int) -> dict[tuple, list[dict]]:
    """Сырой индекс совпадения (Правило №6 — ЕДИНСТВЕННОЕ место, где строится
    группировка «активные позиции субсидии по (source_row, нормализованное
    имя)»; `find_source_row_duplicates` ниже (экран) и
    `feo_import_duplicates.py` (перенос позиции при повторном импорте того же
    файла, см. её вызов `build_source_row_index`) читают ОДИН И ТОТ ЖЕ индекс,
    а не считают совпадение по отдельности.

    Возвращает {(source_row, нормализованное имя): [{"item_id", "category_id",
    "category_name"}, ...]} — ВСЕ активные позиции субсидии с заполненным
    `source_row`, сгруппированные по ключу совпадения (группа из ОДНОЙ записи
    — обычная, не дубль; вызывающий код сам решает, что делать с группой).

    Один SELECT на субсидию (без N+1)."""
    rows = (await db.execute(
        select(FeoPlannedItem.id, FeoPlannedItem.source_row, FeoPlannedItem.name,
               FeoPlannedItem.feo_category_id, FeoCategory.name)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
        .where(FeoPlannedItem.is_active == True)
        .where(FeoPlannedItem.source_row.isnot(None))
    )).all()

    groups: dict[tuple, list[dict]] = {}
    for item_id, source_row, name, cat_id, cat_name in rows:
        key = (source_row, normalize_feo_name(name or ""))
        groups.setdefault(key, []).append(
            {"item_id": item_id, "category_id": cat_id, "category_name": cat_name}
        )
    return groups


async def find_source_row_duplicates(db, subsidy_id: int) -> dict[int, list[dict]]:
    """Признак для экрана (GET /api/feo-categories/plan-positions,
    FeoLevel5Panel.vue — значок «дубль строки N») — строится из того же
    `build_source_row_index` (Правило №6).

    Возвращает {item_id: [{"item_id", "category_id", "category_name"}, ...]}
    — для КАЖДОЙ активной плановой позиции субсидии со своим `source_row`,
    у которой есть другая(ие) активная(ые) позиция(и) с тем же `source_row` и
    тем же нормализованным именем в ДРУГОЙ категории, список этих «других»
    позиций (НЕ включая саму себя, НЕ включая совпадения в её же категории).
    Позиция без дублей — ключ отсутствует вовсе (экран читает `.get(id, [])`)."""
    groups = await build_source_row_index(db, subsidy_id)

    result: dict[int, list[dict]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        distinct_cats = {m["category_id"] for m in members}
        if len(distinct_cats) < 2:
            continue  # все совпадения внутри одной категории — не этот случай
        for m in members:
            others = [o for o in members if o["category_id"] != m["category_id"]]
            if others:
                result[m["item_id"]] = others
    return result
