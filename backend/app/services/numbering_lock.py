"""Общий хелпер блокировки для «следующий номер = max(существующих)+1»
(ПРАВИЛО №6 — один механизм, не плодить второй).

Повод: `assign_procurement_order_number_if_missing`
(app/services/purchase_order_numbering.py) и `generate_temp_contract_number`
(app/services/temp_contract_number.py) оба читают текущий максимум/занятые
номера и пишут следующий без защиты — два одновременных вызова для одной
организации/года (или одной закупки) могут прочитать один и тот же max и
присвоить одинаковый номер. `pg_advisory_xact_lock` держит блокировку до
конца ТЕКУЩЕЙ транзакции (коммит или rollback) — вызывающий код обязан
читать max и писать результат в той же сессии/транзакции, что и захват
блокировки; если документ коммитится позже — блокировка просто держится
дольше, это ожидаемо и безопасно.

На SQLite (локальные скрипты/альтернативные тесты) — функция тихо ничего не
делает: `pg_advisory_xact_lock` специфична для PostgreSQL, а конкурентных
писателей на SQLite в наших сценариях не бывает.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_KEY_PREFIX = "vsks_numbering"


async def acquire_numbering_lock(db: AsyncSession, *key_parts: object) -> None:
    """Захватывает advisory-блокировку транзакции по ключу из `key_parts`.

    Вызывать ДО чтения текущего максимума/занятых номеров, в той же сессии,
    что затем пишет и коммитит новый номер. Разные `key_parts` (например,
    (org_id, year) или (purchase_id,)) дают разные независимые блокировки —
    конкуренты с одинаковым ключом сериализуются, с разным — не мешают друг
    другу.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return

    key = "|".join(str(part) for part in (_KEY_PREFIX, *key_parts))
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
