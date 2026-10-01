"""Запись правки субсидии (PUT /api/subsidies/{id}) — вынесено из
app/routers/subsidies.py::update_subsidy (волна «Корректировка утверждённой
субсидии через проверку», 02.10.2026, план breezy-mixing-lovelace.md), по той
же причине, что и app/services/feo_item_write.py (см. его докстринг):
применение накопленных правок корректировки позже обязано пройти ТУ ЖЕ
проверку дубля имени и ТУ ЖЕ запись BudgetHistory, что и прямая правка.

НЕ проверяет права доступа (subsidy.edit / черновик-автор — остаётся в
роутере) и НЕ коммитит транзакцию. Роутер вокруг этой функции сохраняет
СВОЙ ALTER-fallback (db_subsidy пересоздаётся после rollback при
ProgrammingError/IntegrityError, см. его докстринг) — повторный вызов этой же
функции на свежезагруженном db_subsidy даёт тот же результат, что и повтор
setattr-цикла в оригинале (old_budget пересчитывается внутри функции заново из
db_subsidy.budget ДО setattr — после отката первой попытки это то же исходное
значение, что и раньше, расхождения нет).
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy import Subsidy


async def apply_subsidy_update(
    db: AsyncSession,
    user,
    db_subsidy: Subsidy,
    payload: dict,
    *,
    reason: Optional[str] = None,
) -> None:
    """Дубль-проверка имени + setattr по payload + запись BudgetHistory при
    изменении budget. Мутирует db_subsidy на месте, ничего не возвращает."""
    _upd_name = (payload.get('name') or '').strip()
    if _upd_name:
        _dup = (await db.execute(
            select(Subsidy.id).where(
                func.lower(func.trim(Subsidy.name)) == _upd_name.lower(),
                Subsidy.id != db_subsidy.id,
            )
        )).first()
        if _dup:
            raise HTTPException(status_code=409, detail=f"Субсидия с названием «{_upd_name}» уже существует")

    old_budget = db_subsidy.budget  # capture BEFORE setattr loop

    for key, value in payload.items():
        setattr(db_subsidy, key, value)
    # calculated_budget — deprecated колонка (Правило №6), НЕ пишется — см.
    # app.services.subsidy_budget, считается на чтении.

    if old_budget != db_subsidy.budget:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=db_subsidy.id,
            purchase_id=None,
            entity_type="subsidy",
            old_value=float(old_budget) if old_budget is not None else None,
            new_value=float(db_subsidy.budget) if db_subsidy.budget is not None else None,
            changed_by_id=user.id,
            changed_by_name=getattr(user, 'full_name', None) or user.username,
            reason=reason,
        ))
