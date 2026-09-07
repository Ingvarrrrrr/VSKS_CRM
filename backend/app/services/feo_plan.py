"""feo_plan.py — единый расчёт «расхода плана» по дереву ФЭО.

Вынесено из _calculate_feo_planned_tree_bulk (app/routers/subsidies.py) и
GET /api/feo-planned-items/residuals, чтобы формула не расходилась между
эндпоинтами KPI субсидий (subsidies.py) и справочником плановых позиций
(feo_categories.py /plan-positions).

⚠️ Изоляция субсидий (сессия 2026-08-05): позиция закупки учитывается ТОЛЬКО
если Purchase.subsidy_id совпадает с subsidy_id той FeoCategory, к которой
она фактически отнесена (COALESCE(PurchaseItem.feo_category_id,
Purchase.feo_category_id)). Раньше _calculate_feo_planned_tree_bulk проверял
лишь «Purchase.subsidy_id ∈ запрошенный батч subsidy_ids» и «категория ∈
категории запрошенного батча» — НЕЗАВИСИМО друг от друга. Из-за этого закупка
субсидии A с feo_category_id, указывающей в дерево субсидии B (в т.ч. когда
Purchase.subsidy_id вовсе NULL — не совпадает ни с чем), прибавлялась к
«Запланировано» субсидии B, если та просто присутствовала в том же батче.
Результат зависел от состава батча (на проде разъезжалось: батч по всем
субсидиям давал 6 201 370.73, одиночный вызов для subsidy_id=7 — 6 188 648.23,
расхождение 12 722.50 на 3 позициях). Каждая субсидия обязана считать только
свои вкладки — деньги не должны «перепрыгивать» между субсидиями.

--------------------------------------------------------------------------
РЕФАКТОРИНГ (сессия 2026-09-08, без изменения поведения, см. ПРАВИЛО №5 —
модульность кода): файл был 2558 строк, разрезан по ответственностям на:
  - feo_plan_common.py    — приватный хелпер, общий для 2+ модулей
                             (_leaf_plan_manual — единая формула плана листа
                             при plan_source='manual_sum', ПРАВИЛО №6)
  - feo_plan_fact.py      — единая формула «факта» позиции закупки
                             (purchase_item_fact_amount, SSOT факта) + расход
                             плана по категории/позиции
  - feo_plan_tree.py      — дерево плана ФЭО (compute_feo_plan_tree)
  - feo_plan_excess.py    — виновник превышения + блокирующий контроль
                             (find_excess_culprit, assert_no_unapproved_excess)
  - feo_plan_tz_checks.py — контроль «ТЗ не выше плана»
  - feo_plan_totals.py    — итог по субсидии, пути/предки категорий
  - feo_plan_forecast.py  — прогноз потолка субсидии

Этот файл остаётся ФАСАДОМ — все имена, которые раньше импортировались из
app.services.feo_plan (включая приватные — часть уже так использовалась
внешним кодом, см. feo_plan_reads.py), продолжают быть доступны отсюда же
(явный re-export ниже, без `import *`). Потребители НЕ переписывались.
"""
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_ as sqland, case, func, or_ as sqlor, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.feo_category import FeoCategory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.services.purchase_summary import purchase_summaries_by_id
from app.services.acceptance_docs import total_amount as _acceptance_total_amount

from app.services.feo_plan_common import _leaf_plan_manual

from app.services.feo_plan_fact import (
    FACT_CONFIRMED_STATUSES,
    ORDERED_STATUSES,
    FACT_PRICED_STATUSES,
    FACT_ELIGIBLE_STATUSES,
    _CENTS,
    apply_wish_item_exclusion,
    purchase_item_fact_amount,
    _contract_item_totals,
    _purchase_item_totals,
    plan_consumption_by_category,
    unlinked_actual_by_category,
    ordered_consumption_by_category,
    fact_consumption_by_category,
    planned_item_consumption,
)

from app.services.feo_plan_tree import compute_feo_plan_tree

from app.services.feo_plan_excess import find_excess_culprit, assert_no_unapproved_excess

from app.services.feo_plan_tz_checks import (
    _fmt_qty,
    _fmt_money,
    assert_tz_not_over_plan,
    assert_tz_batch_not_over_plan,
)

from app.services.feo_plan_totals import (
    feo_plan_subsidy_totals,
    build_category_path,
    build_ancestor_ids,
)

from app.services.feo_plan_forecast import (
    _MONTHLY_ACCRUAL_STATUSES,
    _calendar_months_inclusive,
    _monthly_full_schedule_amount,
    _one_off_committed_totals_bulk,
    _monthly_committed_totals_bulk,
    calculate_ceiling_forecasts_bulk,
    calculate_ceiling_forecast,
)

__all__ = [
    "FACT_CONFIRMED_STATUSES",
    "ORDERED_STATUSES",
    "FACT_PRICED_STATUSES",
    "FACT_ELIGIBLE_STATUSES",
    "apply_wish_item_exclusion",
    "purchase_item_fact_amount",
    "plan_consumption_by_category",
    "unlinked_actual_by_category",
    "ordered_consumption_by_category",
    "fact_consumption_by_category",
    "planned_item_consumption",
    "compute_feo_plan_tree",
    "find_excess_culprit",
    "assert_no_unapproved_excess",
    "assert_tz_not_over_plan",
    "assert_tz_batch_not_over_plan",
    "feo_plan_subsidy_totals",
    "build_category_path",
    "build_ancestor_ids",
    "calculate_ceiling_forecasts_bulk",
    "calculate_ceiling_forecast",
]
