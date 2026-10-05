"""--relink: точка входа режима (вызывается из __main__.py). Работает с УЖЕ
существующей целевой субсидией (ничего не создаёт/не удаляет закупок/дерева —
в отличие от run_build) в ОДНОЙ транзакции:
  1. relink_plan.py — пересопоставление + позиционная привязка к уже
     созданным закупкам (см. её докстринг про сломанный task_comment).
  2. advance.py — исполнитель по правилу владельца / признак авансового /
     статус дочерних заказов рамочного.
  3. files_copy.py — документы двойника → новая закупка.
Отчёт — report_relink.py."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy

from .advance import RelinkCounters, apply_relink_fields, cleanup_employee_contractors, load_employee_lookup
from .build import find_existing_target_subsidy
from .employees import EnsureEmployeeResult, ensure_employees
from .files_copy import DocCopyCounters, copy_purchase_documents
from .match import find_source_subsidy, load_old_purchases, run_matching
from .parse import SheetRow, group_rows, iter_match_units
from .relink_plan import PlanEntry, RelinkPlanMismatch, build_creation_plan, zip_plan_with_purchases


@dataclass
class RelinkResult:
    source: Subsidy
    target: Subsidy
    pairs: list = field(default_factory=list)          # [(PlanEntry, Purchase)]
    relink_counters: RelinkCounters = None
    doc_counters: DocCopyCounters = None
    ensured_employees: list = field(default_factory=list)  # [EnsureEmployeeResult]


async def run_relink(
    db: AsyncSession, *, rows: list[SheetRow], source_name: str, target_name: str,
    ensure_employee_names: Optional[list[str]] = None,
) -> RelinkResult:
    source = await find_source_subsidy(db, source_name)
    target = await find_existing_target_subsidy(db, target_name, source.id)
    if target is None:
        raise ValueError(
            f"Субсидия {target_name!r} (copied_from_id={source.id}) не найдена — "
            f"--relink работает только с уже существующей целевой субсидией (создайте её обычным прогоном без --relink)."
        )

    ensured_employees: list[EnsureEmployeeResult] = []
    if ensure_employee_names:
        if not target.org_id:
            raise ValueError(
                f"У целевой субсидии {target_name!r} не задан org_id — --ensure-employee некуда привязать."
            )
        # ДО матчинга/lookup — свежезаведённые сотрудники должны попасть в
        # load_employee_lookup ниже (та же транзакция, flush делает их видимыми).
        ensured_employees = await ensure_employees(db, target.org_id, ensure_employee_names)

    old_purchases = await load_old_purchases(db, source.id)
    groups, _planned_only_rows = group_rows(rows)
    units = iter_match_units(groups)
    _matcher, matches = run_matching(groups, units, old_purchases)

    plan = build_creation_plan(groups, matches)

    purchases = (await db.execute(
        select(Purchase).where(Purchase.subsidy_id == target.id).order_by(Purchase.id)
    )).scalars().all()

    try:
        pairs = zip_plan_with_purchases(plan, purchases)
    except RelinkPlanMismatch:
        raise

    lookup = await load_employee_lookup(db, target.org_id)

    # Контрагент ДО правки — нужен, чтобы после apply_relink_fields (которая
    # может обнулить/заменить Purchase.contractor_id на авансовых) узнать,
    # какой именно contractor_id был там раньше (загрузчик мог создать его
    # СЕГОДНЯ по имени из таблицы — см. advance.cleanup_employee_contractors).
    original_contractor_id_by_purchase_id: dict[int, Optional[int]] = {
        purchase.id: purchase.contractor_id for _entry, purchase in pairs
    }

    relink_counters = RelinkCounters()
    await apply_relink_fields(db, pairs, lookup, relink_counters)

    doc_counters = DocCopyCounters()
    for entry, purchase in pairs:
        if entry.twin is not None:
            await copy_purchase_documents(db, entry.twin.id, purchase.id, doc_counters)

    # Кандидаты на удаление — старый (ДО relink) contractor_id авансовой
    # закупки, ЕСЛИ его имя нормализовано совпадает с ФИО сотрудника (значит
    # загрузчик завёл этого «контрагента» по ошибке из ФИО, а не из названия
    # реального магазина/поставщика).
    candidate_ids: set[int] = set()
    for e in relink_counters.advance_entries:
        old_cid = original_contractor_id_by_purchase_id.get(e.purchase_id)
        if not old_cid or old_cid == e.contractor_id:
            continue
        contractor = await db.get(Contractor, old_cid)
        if contractor and lookup.is_employee(contractor.name or ""):
            candidate_ids.add(old_cid)

    await cleanup_employee_contractors(db, candidate_ids, relink_counters)

    return RelinkResult(source=source, target=target, pairs=pairs,
                         relink_counters=relink_counters, doc_counters=doc_counters,
                         ensured_employees=ensured_employees)
