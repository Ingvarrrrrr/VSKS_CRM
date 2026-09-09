#!/usr/bin/env python3
"""
CLI: разовый откат мусорных товаров, созданных импортом `ТЗ для АПИ (4).xlsx`
2026-09-09 (План «импорт ФЭО (уровни) и импорт товаров», Задача C).

ПРИЧИНА. `POST /api/products/import` до фикса (см. Задачу B того же плана)
подбирал колонки фаззи-цепочкой без подтверждения пользователя и на этом
файле взял «Категорию товара» как наименование товара: на проде появилось
1022 товара с именами вроде «Цифровая техника», категорией «Прочее» и
верными описанием/ценой — настоящие наименования (в т.ч. «Коммутатор D-Link
DGS-1024D/J1A», строка 1015 файла) при этом нигде не сохранены. Владелец
распорядился удалить всё, что занеслось в этот день таким импортом.

КРИТЕРИЙ ОТБОРА (проверен на проде, даёт ровно 1022 строки без ложных
попаданий; id мусора и нормальных товаров ЧЕРЕДУЮТСЯ — по диапазону id
отбирать нельзя):
    date(updated_at) = --date  И  category = 'Прочее'  И  name из --names-file

БЕЗОПАСНОСТЬ. Перед удалением КАЖДЫЙ кандидат проверяется на ссылки не
только из известных таблиц (purchase_items, wish_items, contract_items,
commercial_request_offers, supplier_products, product_price_history), но и
из ЛЮБОЙ таблицы, у которой есть FK на products.id — набор таблиц берётся из
information_schema динамически, чтобы не пропустить то, что не перечислено
явно.

Прод-прогон --dry-run (2026-09-09) показал: из 1022 кандидатов 172 имеют
ссылки, и ВСЕ 172 — только из product_price_history (та же ошибочная загрузка
создала мусорную историю цен). Владелец решил удалять такие товары вместе с
их историей цен. Поэтому ссылки делятся на два разряда:
  - product_price_history — снимается флагом --with-price-history: история
    удаляется первой, затем сам товар, одной транзакцией; без флага — как
    раньше, товар не трогается.
  - ЛЮБАЯ другая таблица (purchase_items, wish_items, contract_items,
    commercial_request_offers, supplier_products и всё, что найдётся через
    information_schema) — блокирует удаление ВСЕГДА, никаким флагом не
    снимается.

ФЛАГИ:
    --date YYYY-MM-DD    обязателен, дата updated_at мусорных строк (по
                          умолчанию не подставляется — намеренно, чтобы нельзя
                          было случайно запустить «на сегодня»).
    --names-file PATH     обязателен, файл со списком имён-категорий по одной
                          строке (UTF-8). Путь по умолчанию не задаётся —
                          список обязан прийти явно.
    --dry-run             показать, что было бы сделано, ничего не писать в
                          БД. Поведение ПО УМОЛЧАНИЮ (если не передан --yes).
    --yes                 применить удаление по-настоящему.
    --with-price-history   разрешить удаление товаров, у которых ссылки есть
                          ТОЛЬКО из product_price_history — вместе с этими
                          строками истории. Без флага такие товары остаются
                          нетронутыми, как и товары со ссылками из других таблиц.
    --limit N             ограничить число кандидатов (для отладки на
                          локальной БД).

Запуск (внутри контейнера backend, tests/scripts не примонтированы —
предварительно docker cp):
    docker exec vsks_crm-backend_a-1 python scripts/cleanup_bad_product_import.py \
        --date 2026-09-09 --names-file scripts/bad_product_import_names_20260909.txt --dry-run
    docker exec vsks_crm-backend_a-1 python scripts/cleanup_bad_product_import.py \
        --date 2026-09-09 --names-file scripts/bad_product_import_names_20260909.txt --yes

ВНИМАНИЕ: запуск на проде — только после показа владельцу отчёта --dry-run.
Этот скрипт сам ни к какому проду не подключается — он работает через
app.database.async_session той БД, к которой подключён контейнер, в котором
его запускают.
"""
import argparse
import asyncio
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from app.database import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

# Имя таблицы истории цен — единственная FK-таблица, для которой владелец
# разрешил удаление вместе с товаром (--with-price-history). Любая ДРУГАЯ
# таблица из find_fk_tables_on_products блокирует удаление всегда.
PRICE_HISTORY_TABLE = "product_price_history"


async def find_fk_tables_on_products(db) -> list[tuple[str, str]]:
    """Возвращает список (table_name, column_name) для ВСЕХ FK, ссылающихся на
    products.id — берётся из information_schema, чтобы не полагаться на
    жёстко перечисленный список и не пропустить забытую таблицу."""
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


async def find_candidates(db, date_str: str, names: list[str], limit: int | None) -> list[tuple[int, str]]:
    """Кандидаты на удаление: date(updated_at) = date_str И category = 'Прочее'
    И name в списке names. Возвращает [(id, name), ...] по возрастанию id."""
    if not names:
        return []
    # asyncpg биндит параметр строго типизированно: раз он сравнивается с
    # date(updated_at) (тип date), нужен настоящий datetime.date, а не str —
    # иначе "'str' object has no attribute 'toordinal'".
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    sql = """
        SELECT id, name
        FROM products
        WHERE date(updated_at) = :d
          AND category = 'Прочее'
          AND name = ANY(:names)
        ORDER BY id
    """
    params = {"d": d, "names": names}
    if limit:
        sql += " LIMIT :lim"
        params["lim"] = limit
    result = await db.execute(text(sql), params)
    return [(row[0], row[1]) for row in result.all()]


async def count_references(db, ids: list[int], fk_tables: list[tuple[str, str]]) -> dict[int, dict[str, int]]:
    """Для набора id считает ссылки по каждой FK-таблице одним запросом на
    таблицу (GROUP BY), а не по одному запросу на кандидата — иначе на 1022
    кандидатах и 6+ таблицах это тысячи запросов.

    Возвращает {product_id: {"table.column": count, ...}} только для id, у
    которых есть хотя бы одна ссылка."""
    if not ids:
        return {}
    refs: dict[int, dict[str, int]] = {}
    for table, column in fk_tables:
        try:
            result = await db.execute(
                text(f"SELECT {column}, COUNT(*) FROM {table} WHERE {column} = ANY(:ids) GROUP BY {column}"),
                {"ids": ids},
            )
        except Exception:
            # Таблица/колонка недоступна (гонка схемы, вьюха и т.п.) — не
            # считаем это доказательством отсутствия ссылок, но и не валим
            # весь скрипт: пропускаем эту таблицу с явным предупреждением.
            print(f"  [!] не удалось проверить {table}.{column} — таблица пропущена в проверке ссылок")
            continue
        for pid, cnt in result.all():
            if pid is None or not cnt:
                continue
            refs.setdefault(pid, {})[f"{table}.{column}"] = cnt
    return refs


def read_names_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        names = [line.strip() for line in f]
    return [n for n in names if n]


def validate_date(date_str: str) -> str:
    datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return date_str


def _split_refs_by_kind(
    candidates: list[tuple[int, str]], refs: dict[int, dict[str, int]],
) -> tuple[list[tuple[int, str]], list[tuple[int, str]], list[tuple[int, str]]]:
    """Делит кандидатов на три непересекающихся списка:
      - blocked_other       — есть ссылка хотя бы из ОДНОЙ таблицы, отличной
                               от product_price_history. Блокирует удаление
                               всегда, никаким флагом не снимается.
      - price_history_only  — ссылки есть ТОЛЬКО из product_price_history.
                               Удаляемы вместе с историей при --with-price-history.
      - clean               — ссылок нет вовсе.
    """
    blocked_other, price_history_only, clean = [], [], []
    for pid, name in candidates:
        pid_refs = refs.get(pid)
        if not pid_refs:
            clean.append((pid, name))
            continue
        other_keys = [k for k in pid_refs if not k.startswith(f"{PRICE_HISTORY_TABLE}.")]
        if other_keys:
            blocked_other.append((pid, name))
        else:
            price_history_only.append((pid, name))
    return blocked_other, price_history_only, clean


async def run(
    date_str: str, names: list[str], apply_changes: bool, limit: int | None, with_price_history: bool,
) -> int:
    async with async_session() as db:
        fk_tables = await find_fk_tables_on_products(db)
        print(f"Таблицы с FK на products.id (information_schema): {fk_tables}")

        candidates = await find_candidates(db, date_str, names, limit)
        print(f"\nКандидатов на удаление (date(updated_at)={date_str}, category='Прочее', "
              f"name из {len(names)} значений файла): {len(candidates)}")
        if not candidates:
            print("Нечего удалять.")
            return 0

        ids = [c[0] for c in candidates]
        refs = await count_references(db, ids, fk_tables)
        blocked_other, price_history_only, clean = _split_refs_by_kind(candidates, refs)

        ph_rows_total = sum(
            refs[pid].get(f"{PRICE_HISTORY_TABLE}.product_id", 0) for pid, _name in price_history_only
        )
        print(f"Связаны другими таблицами, кроме истории цен (НЕ удаляются ни при каком флаге): {len(blocked_other)}")
        if blocked_other:
            for pid, name in blocked_other:
                print(f"    id={pid} name={name!r} ссылки={refs[pid]}")

        print(f"Связаны только историей цен (product_price_history) — удаляются вместе с историей "
              f"при --with-price-history: {len(price_history_only)} товаров, {ph_rows_total} записей истории")
        if price_history_only:
            for pid, name in price_history_only:
                print(f"    id={pid} name={name!r} записей истории={refs[pid].get(f'{PRICE_HISTORY_TABLE}.product_id', 0)}")

        deletable = clean + (price_history_only if with_price_history else [])
        still_blocked = blocked_other + ([] if with_price_history else price_history_only)

        print(f"К удалению: {len(deletable)}")

        # Разбивка по именам (топ-20)
        by_name: dict[str, int] = {}
        for _pid, name in deletable:
            by_name[name] = by_name.get(name, 0) + 1
        top_names = sorted(by_name.items(), key=lambda kv: -kv[1])[:20]
        print("\nРазбивка по именам (топ-20):")
        for name, cnt in top_names:
            print(f"    {cnt:>5}  {name!r}")

        print("\nПервые 20 id к удалению:")
        for pid, name in deletable[:20]:
            print(f"    id={pid} name={name!r}")

        if not apply_changes:
            print(f"\nDRY-RUN — изменения НЕ применены (передайте --yes для реального удаления). "
                  f"К удалению было бы: {len(deletable)}.")
            return 0

        if not deletable:
            print("\nПрименять нечего (все кандидаты заблокированы ссылками).")
            return 0

        del_ids = [pid for pid, _name in deletable]
        ph_del_ids = [pid for pid, _name in price_history_only] if with_price_history else []
        try:
            deleted_ph = 0
            if ph_del_ids:
                # Сначала история цен — иначе на некоторых окружениях, где
                # product_price_history.product_id создан без ON DELETE
                # CASCADE, DELETE FROM products упал бы на FK-ограничении.
                ph_result = await db.execute(
                    text(f"DELETE FROM {PRICE_HISTORY_TABLE} WHERE product_id = ANY(:ids)"),
                    {"ids": ph_del_ids},
                )
                deleted_ph = ph_result.rowcount if ph_result.rowcount is not None else 0
            result = await db.execute(text("DELETE FROM products WHERE id = ANY(:ids)"), {"ids": del_ids})
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        deleted_count = result.rowcount if result.rowcount is not None else len(del_ids)
        print(f"\nУДАЛЕНО: {deleted_count} товаров, {deleted_ph} записей истории цен. "
              f"Оставлено заблокированными: {len(still_blocked)}.")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", required=True, type=validate_date,
                         help="дата updated_at мусорных строк, YYYY-MM-DD (обязателен)")
    parser.add_argument("--names-file", required=True,
                         help="путь к файлу со списком имён-категорий, по одному в строке (обязателен)")
    parser.add_argument("--dry-run", action="store_true", help="показать план, ничего не писать (поведение по умолчанию)")
    parser.add_argument("--yes", action="store_true", help="применить удаление по-настоящему")
    parser.add_argument("--with-price-history", action="store_true",
                         help="удалять товары, связанные ТОЛЬКО через product_price_history, вместе с историей")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число кандидатов (отладка)")
    args = parser.parse_args()

    if not os.path.isfile(args.names_file):
        print(f"Файл со списком имён не найден: {args.names_file}")
        return 1

    names = read_names_file(args.names_file)
    if not names:
        print(f"Файл со списком имён пуст: {args.names_file}")
        return 1

    apply_changes = args.yes and not args.dry_run

    return await run(args.date, names, apply_changes, args.limit, args.with_price_history)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
