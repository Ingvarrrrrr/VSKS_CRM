"""Дедуп контрагентов по ИНН (волна 4b, D8/D9 — Правило №6).

ПЕРЕНЕСЕНО (не скопировано) из app/startup/backfills.py::
_phase26_qq_contractor_dedup_by_inn, где логика раньше выполнялась при
КАЖДОМ старте приложения. Слияние дублей по ИНН — разовый data-fix
(устранение уже накопленных дублей + защитный partial unique index), а не
часть жизненного цикла старта: после первого успешного прогона повторное
сканирование всей таблицы contractors на каждом рестарте не находит новых
дублей (create_contractor и уникальный индекс их больше не допускают).

Единственный вызывающий — backend/scripts/merge_duplicates_by_inn.py.
Уникальный индекс ix_contractors_inn_unique остаётся частью этой функции
(она же его создаёт) — сам индекс объявлен в legacy_ddl/alembic и здесь не
трогается, только создаётся IF NOT EXISTS как раньше.
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# FK-колонки, ссылающиеся на contractors.id. Список унаследован из
# _phase26_qq_contractor_dedup_by_inn (grep моделей на момент её написания);
# сверен заново с живой схемой при переносе (2026-09-07) — "commercial_requests"
# убран из списка: контрагент этой таблицы давно ссылается через
# purchases.contractor_id (commercial_requests.contractor_id в схеме нет,
# UPDATE по нему падал бы "column does not exist" на каждом мерже).
FK_TABLES = [
    ("bank_payments", "matched_contractor_id"),
    ("contracts", "contractor_id"),
    ("organizations", "contractor_id"),
    ("purchases", "contractor_id"),
    ("purchase_items", "contractor_id"),
    ("subsidies", "contractor_id"),
    ("subsidy_contractor_overrides", "contractor_id"),
]


async def find_duplicate_contractor_groups(db: AsyncSession):
    """Группы дублей contractors по TRIM(inn): строки (norm_inn, ids, n).

    ids отсортированы по возрастанию — ids[0] станет survivor (keep_id) при
    слиянии. Ничего не пишет.
    """
    result = await db.execute(text("""
        SELECT TRIM(inn) AS norm_inn, ARRAY_AGG(id ORDER BY id) AS ids, COUNT(*) AS n
        FROM contractors
        WHERE inn IS NOT NULL AND TRIM(inn) != ''
        GROUP BY TRIM(inn)
        HAVING COUNT(*) > 1
    """))
    return result.all()


async def merge_duplicate_contractors_by_inn(db: AsyncSession, *, dry_run: bool = False) -> dict:
    """Идемпотентный мерж дублей contractors по ИНН.

    Алгоритм (1:1 со старой backfill-версией):
    - survivor = MIN(id) в группе (keep_id), остальные — дубли.
    - FK на дубли перевешиваются на survivor (FK_TABLES, генерируется UPDATE,
      ошибка отдельной таблицы не фатальна — таблица могла не существовать).
    - Пустые поля survivor'а заполняются значениями из дублей (COALESCE).
    - Дубли удаляются.
    - После всех групп создаётся (IF NOT EXISTS) partial unique index
      ix_contractors_inn_unique — защита от новых дублей.

    dry_run=True — НИЧЕГО не пишет (ни rewire, ни merge полей, ни DELETE, ни
    CREATE INDEX), только возвращает размер групп для отчёта в CLI.

    Возвращает {"groups": число групп дублей, "merged": суммарное число
    слитых (удалённых бы) строк contractors}.
    """
    log = logging.getLogger(__name__)
    groups = await find_duplicate_contractor_groups(db)

    if not groups:
        return {"groups": 0, "merged": 0}

    if dry_run:
        return {"groups": len(groups), "merged": sum(row.n - 1 for row in groups)}

    total_merged = 0
    for row in groups:
        ids = list(row.ids)
        keep_id = ids[0]
        dup_ids = ids[1:]

        for tbl, col in FK_TABLES:
            # SAVEPOINT (db.begin_nested) — тот же приём, что и в
            # org_dedup.py::_merge_duplicate_orgs_by_inn: без него ошибка
            # одной таблицы (напр. колонка удалена схемой позже, чем
            # писался FK_TABLES) поднимает Postgres-транзакцию в aborted
            # state, и ВСЕ последующие statement'ы (merge полей, DELETE,
            # CREATE INDEX) валятся с InFailedSQLTransactionError — даже
            # притом что try/except тут ловит исключение для КОНКРЕТНОЙ
            # таблицы. Проверено на живых данных: commercial_requests
            # больше не имеет contractor_id — без SAVEPOINT это гасило
            # мерж целиком (тихо, через внешний non-fatal except в
            # вызывающем коде).
            try:
                async with db.begin_nested():
                    await db.execute(text(
                        f"UPDATE {tbl} SET {col} = :keep WHERE {col} = ANY(:dups)"
                    ), {"keep": keep_id, "dups": dup_ids})
            except Exception as inner_e:
                log.warning(
                    f"contractor-merge rewire {tbl}.{col} failed (table may not exist): {inner_e}"
                )

        await db.execute(text("""
            UPDATE contractors keep SET
                name = COALESCE(NULLIF(keep.name, ''), dup.name),
                kpp = COALESCE(NULLIF(keep.kpp, ''), dup.kpp),
                ogrn = COALESCE(NULLIF(keep.ogrn, ''), dup.ogrn),
                address = COALESCE(NULLIF(keep.address, ''), dup.address),
                phone = COALESCE(NULLIF(keep.phone, ''), dup.phone),
                email = COALESCE(NULLIF(keep.email, ''), dup.email),
                signatory = COALESCE(NULLIF(keep.signatory, ''), dup.signatory)
            FROM contractors dup
            WHERE keep.id = :keep AND dup.id = ANY(:dups)
        """), {"keep": keep_id, "dups": dup_ids})

        await db.execute(text("DELETE FROM contractors WHERE id = ANY(:dups)"), {"dups": dup_ids})
        total_merged += len(dup_ids)

    await db.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_contractors_inn_unique
        ON contractors (TRIM(inn))
        WHERE inn IS NOT NULL AND TRIM(inn) != ''
    """))
    await db.commit()

    log.info(f"contractor-merge по ИНН: групп {len(groups)}, слито {total_merged}")
    return {"groups": len(groups), "merged": total_merged}
