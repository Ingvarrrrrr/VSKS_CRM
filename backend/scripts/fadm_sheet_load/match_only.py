"""--match-only: ТОЛЬКО сопоставление + отчёт, ничего не создаёт (владелец,
04.10.2026 — нужно прогнать сопоставление на проде без единой записи).

НАМЕРЕННО не импортирует build.py и ни одной функции записи (insert_purchase_
with_items, find_or_create_contractor, create_auto_planned_item,
copy_feo_tree и т.п.) — только parse.py/match.py (чистое чтение). __main__.py
вызывает run_match_only ТОЛЬКО в ветке --match-only, build.py там даже не
импортируется (см. его модульный докстринг).

Контрагента в этом режиме НЕ ищем «найдётся ли среди всех» писателем — ровно
та же логика выбора, что build.py применяет к закупке/голове (twin с
contractor_id — чужого контрагента не трогаем вовсе; рамочная голова всегда
резолвит контрагента группы, независимо от twin'ов заказов), но здесь только
СЧИТАЕМ существующий/новый, не вызывая find_or_create_contractor."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from .contractor_norm import normalize_contractor_name
from .match import (
    find_na_category, find_source_subsidy, load_contractor_lookup, load_old_purchases, run_matching,
)
from .parse import SheetRow, group_rows, is_monthly_group, iter_match_units


@dataclass
class MatchOnlyResult:
    source_subsidy_id: int
    source_subsidy_name: str
    matched: list = field(default_factory=list)        # [{label, old_registry, method, assigned_user_id}]
    unmatched: list = field(default_factory=list)       # [{label, amount}]
    ambiguous: list = field(default_factory=list)       # [{label, amount}]
    old_without_pair: list = field(default_factory=list)
    contractors_existing: int = 0
    contractors_would_create: list = field(default_factory=list)


async def run_match_only(db: AsyncSession, rows: list[SheetRow], source_name: str) -> MatchOnlyResult:
    source = await find_source_subsidy(db, source_name)
    old_purchases = await load_old_purchases(db, source.id)
    lookup = await load_contractor_lookup(db)
    groups, _planned_only_rows = group_rows(rows)
    units = iter_match_units(groups)
    matcher, matches = run_matching(groups, units, old_purchases)

    result = MatchOnlyResult(source_subsidy_id=source.id, source_subsidy_name=source.name)

    for u in units:
        m = matches.get(u.key)
        if m and m.twin:
            result.matched.append({
                "label": u.label, "old_registry": m.twin.registry_number,
                "method": m.method, "assigned_user_id": m.twin.assigned_user_id,
            })
        elif m and m.ambiguous:
            result.ambiguous.append({"label": u.label, "amount": str(u.total_amount)})
        else:
            result.unmatched.append({"label": u.label, "amount": str(u.total_amount)})

    # Рамочная ГОЛОВА не входит в units (см. parse.iter_match_units) — её
    # собственный twin (правило «контрагент, сумма пустая», правки 3) виден
    # только через head_key — добавляем в «сопоставлено» отдельно, как и
    # build.build_framework это же делает при реальной сборке.
    for g in groups:
        if len(g.distinct_order_nos) < 2 or is_monthly_group(g):
            continue
        head_key = (g.contractor_norm, g.purchase_no, None)
        m = matches.get(head_key)
        if m and m.twin:
            result.matched.append({
                "label": f"{g.contractor} №{g.purchase_no} (рамочная голова)",
                "old_registry": m.twin.registry_number,
                "method": m.method, "assigned_user_id": m.twin.assigned_user_id,
            })

    # Контрагент — та же раскладка решений, что build._resolve_contractor/
    # build_framework применяют к реальной закупке (см. докстринг модуля):
    # рамочная голова использует СВОЙ twin (head_key), если он есть (правило
    # «контрагент, сумма пустая»), иначе всегда резолвит контрагента заново.
    # created_this_run — в РЕАЛЬНОМ build.py find_or_create_contractor сам
    # находит контрагента, созданного МИНУТУ назад в этой же транзакции
    # (свежий SELECT по всей таблице на каждый вызов) — повторные группы
    # одного контрагента (ЦЫГАНОВ, ЕГОРОВА...) там НЕ плодят дублей. Здесь,
    # в чистом превью без единой записи, это нужно сымитировать явно —
    # иначе один и тот же контрагент попал бы в «были бы созданы» столько
    # раз, сколько у него групп закупок.
    created_this_run: set = set()
    for g in groups:
        # Один и тот же ключ (contractor_norm, purchase_no, None) — и для
        # «своего» twin'а разовой/помесячной группы, и для twin'а рамочной
        # головы (правило «контрагент, сумма пустая»).
        key = (g.contractor_norm, g.purchase_no, None)
        m = matches.get(key)
        twin = m.twin if m else None
        if twin and twin.contractor_id:
            continue  # контрагент переиспользуется от двойника — ничего не ищем/не создаём
        if not g.contractor:
            continue
        norm = normalize_contractor_name(g.contractor)
        if lookup.find_one(g.contractor) or norm in created_this_run:
            result.contractors_existing += 1
        elif not lookup.ambiguous(g.contractor):
            result.contractors_would_create.append(g.contractor)
            created_this_run.add(norm)

    result.old_without_pair = [
        {"registry_number": op.registry_number, "contractor": op.contractor_name,
         "amount": str(op.total), "status": op.status}
        for op in matcher.unused()
    ]
    return result
