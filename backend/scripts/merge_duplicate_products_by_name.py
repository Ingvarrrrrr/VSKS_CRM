#!/usr/bin/env python3
"""
CLI: разовый мерж дублей каталога товаров (`products`) по ТОЧНОМУ совпадению
названия после нормализации.

ПРИЧИНА. Владелец обнаружил в каталоге 41 группу дублей (82 товара): в 20
группах один экземпляр товара — с описанием и остальными заполненными
полями (заведён позже, при подготовке ТЗ), другой — пустая карточка,
оставшаяся от старого импорта. Позиции закупок (19 штук по всей базе, 16 —
в закупке 858) ссылаются на ПУСТОЙ дубль, а не на заполненный. Решение
владельца: оставить запись С ОПИСАНИЕМ, перевести на неё все ссылки и
историю цен, пустой дубль удалить.

КРИТЕРИЙ ДУБЛЯ (владелец прямо запретил fuzzy-сравнение — на этом проекте
оно уже путало разные товары, д600/д500, ZenBook 14/13): ТОЛЬКО точное
совпадение name после normalize_name() — обрезка пробелов по краям,
схлопывание повторяющихся пробелов, регистр игнорируется. Никакой
похожести, никакого сравнения по префиксу/токенам.

КОГО ОСТАВЛЯТЬ В ГРУППЕ:
  - запись без непустого description в группе есть хотя бы одна с
    описанием — иначе (описания нет ни у кого) группа НЕ трогается вовсе
    (сливать нечего, риск больше пользы);
  - среди записей с описанием — та, где больше заполненных полей из
    {description, description_44fz, price, category, фото (photo_url или
    photo_data)};
  - при равенстве числа заполненных полей — с МЕНЬШИМ id (пишется в отчёт
    отдельной строкой, чтобы было видно, что выбор неоднозначный).

ЧТО ПЕРЕЕЗЖАЕТ НА ОСТАЮЩУЮСЯ ЗАПИСЬ:
  - ВСЕ внешние ссылки на products.id — таблицы находятся ЧЕРЕЗ
    information_schema (тот же приём, что в cleanup_bad_product_import.py),
    а не по жёстко перечисленному списку, чтобы не пропустить забытую
    таблицу;
  - product_price_history — строки НЕ удаляются, а перевешиваются на
    оставшийся id (владелец отдельно просил: средняя цена должна считаться
    по всей истории обоих дублей);
  - supplier_products — единственная FK-таблица с составным UNIQUE
    (supplier_id, product_id): если после переноса такая пара уже была бы
    у оставшейся записи, лишняя строка дубля удаляется (а не создаёт
    конфликт), в остальных случаях — обычный перенос;
  - пустые поля оставшейся записи донаполняются из удаляемой (только если
    у оставшейся ПУСТО — непустое никогда не перезаписывается): description,
    description_44fz, category, unit, photo_url, photo_link, фото-бинарник
    (photo_data+photo_mime+photo_size одним блоком) и price вместе с его
    метаданными актуализации (price_source, price_source_ref,
    price_source_contractor_id, price_updated_at, price_ttl_days) — чтобы
    у перенесённой цены не остался "осиротевший"/ошибочный source.

РЕЖИМ ПО УМОЛЧАНИЮ — ПРОСМОТР. Ничего не пишется в БД, пока не передан
--yes. Удаление пустых дублей делает ТОЛЬКО --yes.

ФЛАГИ:
    --dry-run              показать план (умолчание, если --yes не передан).
    --yes                  применить слияние по-настоящему.
    --filter-name-substr S  учитывать только группы, чьё нормализованное имя
                           содержит S (регистр не важен) — для точечного
                           прогона на конкретной группе/тестовых данных, не
                           трогая остальной каталог.
    --limit N              ограничить число ОБРАБАТЫВАЕМЫХ групп (отладка).

Запуск (внутри контейнера backend, tests/scripts не примонтированы —
предварительно docker cp):
    docker exec vsks_crm-backend_a-1 python scripts/merge_duplicate_products_by_name.py --dry-run
    docker exec vsks_crm-backend_a-1 python scripts/merge_duplicate_products_by_name.py --yes

ВНИМАНИЕ: реальное удаление на боевой/локальной копии — только после того,
как владелец увидел отчёт --dry-run и подтвердил список.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from app.database import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

# Простые поля, которые донаполняются из удаляемой записи, если у оставшейся
# они пустые. Фото и цена обрабатываются отдельными блоками ниже — фото,
# потому что состоит из нескольких колонок, которые должны переезжать
# согласованно (данные+mime+size), цена — потому что тянет за собой
# метаданные актуализации (см. app/services/price_actualization.py).
SIMPLE_BACKFILL_FIELDS = ["description", "description_44fz", "category", "unit", "photo_url", "photo_link"]
PRICE_FIELDS = ["price", "price_source", "price_source_ref", "price_source_contractor_id",
                "price_updated_at", "price_ttl_days"]
PHOTO_DATA_FIELDS = ["photo_data", "photo_mime", "photo_size"]

# Поля, которые учитываются при выборе "у кого больше заполнено" среди
# кандидатов с непустым description. Фото считается одним булевым признаком
# (photo_url ИЛИ photo_data), как и просил владелец в задаче.
COMPLETENESS_TEXT_FIELDS = ["description", "description_44fz", "category"]


def normalize_name(name: str) -> str:
    """Обрезка пробелов по краям + схлопывание повторяющихся пробелов +
    регистронезависимость. НИКАКОГО fuzzy — только это."""
    return " ".join((name or "").split()).lower()


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def has_photo(row: dict) -> bool:
    return not is_empty(row.get("photo_url")) or row.get("photo_data") is not None


def completeness_score(row: dict) -> int:
    score = 0
    for f in COMPLETENESS_TEXT_FIELDS:
        if not is_empty(row.get(f)):
            score += 1
    if row.get("price") is not None:
        score += 1
    if has_photo(row):
        score += 1
    return score


async def find_fk_tables_on_products(db) -> list[tuple[str, str]]:
    """Возвращает [(table_name, column_name), ...] для ВСЕХ FK, ссылающихся
    на products.id — берётся из information_schema динамически (как в
    cleanup_bad_product_import.py), чтобы не полагаться на память и не
    пропустить забытую таблицу."""
    result = await db.execute(text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND ccu.table_name = 'products'
          AND ccu.column_name = 'id'
        ORDER BY tc.table_name, kcu.column_name
    """))
    return [(row[0], row[1]) for row in result.all()]


async def find_unique_sibling_columns(db, table: str, column: str) -> list[str]:
    """Для (table, column) возвращает остальные колонки любого UNIQUE-
    ограничения, в которое входит column — нужно, чтобы при переносе ссылок
    не словить нарушение составного уникального индекса (в текущей схеме
    это supplier_products: UNIQUE(supplier_id, product_id))."""
    result = await db.execute(text("""
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'UNIQUE'
          AND tc.table_schema = 'public'
          AND tc.table_name = :table
          AND tc.constraint_name IN (
              SELECT constraint_name FROM information_schema.key_column_usage
              WHERE table_schema = 'public' AND table_name = :table AND column_name = :column
          )
          AND kcu.column_name <> :column
    """), {"table": table, "column": column})
    return [row[0] for row in result.all()]


async def find_duplicate_groups(db, name_substr: str | None) -> list[dict]:
    """Группы дублей по точному совпадению normalize_name(name). Возвращает
    [{"norm": str, "ids": [id,...]}], id по возрастанию внутри группы."""
    result = await db.execute(text("""
        SELECT lower(regexp_replace(btrim(name), '\\s+', ' ', 'g')) AS norm,
               array_agg(id ORDER BY id) AS ids
        FROM products
        GROUP BY norm
        HAVING count(*) > 1
        ORDER BY norm
    """))
    groups = [{"norm": row[0], "ids": list(row[1])} for row in result.all()]
    if name_substr:
        needle = name_substr.lower()
        groups = [g for g in groups if needle in g["norm"]]
    return groups


async def load_products(db, ids: list[int]) -> dict[int, dict]:
    result = await db.execute(text("""
        SELECT id, name, description, description_44fz, category, unit,
               photo_url, photo_link, photo_data, photo_mime, photo_size,
               price, price_source, price_source_ref, price_source_contractor_id,
               price_updated_at, price_ttl_days
        FROM products WHERE id = ANY(:ids)
    """), {"ids": ids})
    rows = {}
    for row in result.mappings().all():
        rows[row["id"]] = dict(row)
    return rows


def choose_keep(ids: list[int], rows: dict[int, dict]) -> tuple[int, list[int], bool] | None:
    """Возвращает (keep_id, remove_ids, tie) или None, если ни у одной
    записи группы нет описания (группу трогать нельзя)."""
    with_desc = [i for i in ids if not is_empty(rows[i].get("description"))]
    if not with_desc:
        return None
    scored = sorted(with_desc, key=lambda i: (-completeness_score(rows[i]), i))
    keep_id = scored[0]
    top_score = completeness_score(rows[keep_id])
    tie = len([i for i in with_desc if completeness_score(rows[i]) == top_score]) > 1
    remove_ids = sorted(i for i in ids if i != keep_id)
    return keep_id, remove_ids, tie


def plan_backfill(keep_row: dict, remove_rows: list[dict]) -> dict:
    """Какие поля оставшейся записи донаполнить (только пустые), в порядке
    возрастания id удаляемых — первое непустое значение выигрывает."""
    plan: dict = {}
    for field in SIMPLE_BACKFILL_FIELDS:
        if not is_empty(keep_row.get(field)):
            continue
        for rrow in remove_rows:
            if not is_empty(rrow.get(field)):
                plan[field] = rrow[field]
                break
    if keep_row.get("photo_data") is None:
        for rrow in remove_rows:
            if rrow.get("photo_data") is not None:
                for f in PHOTO_DATA_FIELDS:
                    plan[f] = rrow[f]
                break
    if keep_row.get("price") is None:
        for rrow in remove_rows:
            if rrow.get("price") is not None:
                for f in PRICE_FIELDS:
                    plan[f] = rrow[f]
                break
    return plan


async def count_refs(db, fk_tables: list[tuple[str, str]], ids: list[int]) -> dict[str, int]:
    """{"table.column": count} ссылок из fk_tables на набор ids."""
    counts: dict[str, int] = {}
    if not ids:
        return counts
    for table, column in fk_tables:
        try:
            result = await db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {column} = ANY(:ids)"),
                {"ids": ids},
            )
            n = result.scalar() or 0
        except Exception:
            print(f"  [!] не удалось проверить {table}.{column} — таблица пропущена в проверке ссылок")
            continue
        if n:
            counts[f"{table}.{column}"] = n
    return counts


async def apply_merge(
    db, keep_id: int, remove_ids: list[int], backfill: dict, fk_tables: list[tuple[str, str]],
) -> dict[str, int]:
    """Переносит поля+ссылки+историю цен на keep_id и удаляет remove_ids
    одной транзакцией. Возвращает {"table.column": перенесено} — фактически
    перемещённые ссылки (после разрешения конфликтов уникальности)."""
    moved: dict[str, int] = {}

    if backfill:
        set_clause = ", ".join(f"{f} = :{f}" for f in backfill)
        params = dict(backfill)
        params["keep_id"] = keep_id
        await db.execute(text(f"UPDATE products SET {set_clause} WHERE id = :keep_id"), params)

    for table, column in fk_tables:
        if table == "products":
            continue
        siblings = await find_unique_sibling_columns(db, table, column)
        if siblings:
            # Составной UNIQUE (сейчас — только supplier_products
            # (supplier_id, product_id)): если у keep_id уже есть строка с
            # теми же значениями сиблинг-колонок, перенос создал бы
            # дубль-конфликт — такую строку дубля удаляем вместо переноса.
            match_clause = " AND ".join(f"k.{c} IS NOT DISTINCT FROM t.{c}" for c in siblings)
            await db.execute(text(f"""
                DELETE FROM {table} t
                WHERE t.{column} = ANY(:remove_ids)
                  AND EXISTS (
                      SELECT 1 FROM {table} k
                      WHERE k.{column} = :keep_id
                        AND {match_clause}
                  )
            """), {"remove_ids": remove_ids, "keep_id": keep_id})
        result = await db.execute(
            text(f"UPDATE {table} SET {column} = :keep_id WHERE {column} = ANY(:remove_ids)"),
            {"keep_id": keep_id, "remove_ids": remove_ids},
        )
        if result.rowcount:
            moved[f"{table}.{column}"] = result.rowcount

    await db.execute(text("DELETE FROM products WHERE id = ANY(:ids)"), {"ids": remove_ids})
    return moved


async def run(apply_changes: bool, name_substr: str | None, limit: int | None) -> int:
    async with async_session() as db:
        fk_tables = await find_fk_tables_on_products(db)
        print(f"Таблицы с FK на products.id (information_schema): {fk_tables}")

        groups = await find_duplicate_groups(db, name_substr)
        print(f"\nГрупп с точным совпадением имени после нормализации: {len(groups)}")
        if limit:
            groups = groups[:limit]

        total_merge_groups = 0
        total_remove = 0
        total_moved: dict[str, int] = {}
        skipped_no_desc = 0

        for g in groups:
            ids = g["ids"]
            rows = await load_products(db, ids)
            decision = choose_keep(ids, rows)
            label = g["norm"][:80]
            if decision is None:
                skipped_no_desc += 1
                print(f"\n[ПРОПУСК — нет описания ни у кого] {label!r} ids={ids}")
                continue

            keep_id, remove_ids, tie = decision
            total_merge_groups += 1
            total_remove += len(remove_ids)
            tie_note = "  [РАВЕНСТВО баллов — выбран меньший id]" if tie else ""
            print(f"\n[СЛИТЬ]{tie_note} {label!r}")
            print(f"    оставить id={keep_id}  удалить ids={remove_ids}")

            keep_row = rows[keep_id]
            remove_rows = [rows[i] for i in remove_ids]
            backfill = plan_backfill(keep_row, remove_rows)
            if backfill:
                shown = {k: (v if not isinstance(v, (bytes, bytearray)) else f"<{len(v)} bytes>")
                         for k, v in backfill.items()}
                print(f"    донаполнить у оставшейся записи: {shown}")

            refs = await count_refs(db, fk_tables, remove_ids)
            if refs:
                print(f"    ссылки на удаляемые id переедут: {refs}")
                for k, v in refs.items():
                    total_moved[k] = total_moved.get(k, 0) + v
            else:
                print("    ссылок на удаляемые id нет")

            if apply_changes:
                try:
                    moved = await apply_merge(db, keep_id, remove_ids, backfill, fk_tables)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
                print(f"    ПРИМЕНЕНО: удалено {len(remove_ids)} товаров, перенесено ссылок: {moved}")

        print("\n" + "=" * 70)
        print(f"Групп к слиянию: {total_merge_groups} (записей на удаление: {total_remove})")
        print(f"Групп пропущено (нет описания ни у кого): {skipped_no_desc}")
        print(f"Ссылок к переносу по таблицам: {total_moved}")
        if not apply_changes:
            print("\nDRY-RUN — изменения НЕ применены (передайте --yes для реального слияния).")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="показать план, ничего не писать (поведение по умолчанию)")
    parser.add_argument("--yes", action="store_true", help="применить слияние по-настоящему")
    parser.add_argument("--filter-name-substr", default=None,
                         help="учитывать только группы, чьё нормализованное имя содержит эту подстроку")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число обрабатываемых групп (отладка)")
    args = parser.parse_args()

    apply_changes = args.yes and not args.dry_run
    return await run(apply_changes, args.filter_name_substr, args.limit)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
