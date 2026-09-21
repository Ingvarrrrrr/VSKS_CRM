"""plan_excess_kinds.py — единственный источник истины для «вида превышения
плана» (PlanExcessApproval.kind) и его русских подписей (ПРАВИЛО №6 — второго
словаря видов/подписей в проекте быть не должно, все потребители читают
отсюда).

Задача владельца (план ancient-prancing-music.md, раздел D, 2026-09-21): одно
approved-решение по категории раньше гасило ВСЕ виды превышения узла дерева
сразу (app.services.feo_plan_tree.latest_approval_by_cat, ДО этой задачи) —
согласования должны быть независимыми ПО ВИДУ (kind) и ПО УРОВНЮ (category —
конкретный узел ФЭО, subsidy — запись на субсидию целиком, feo_category_id
IS NULL).
"""
from typing import Optional

LEGACY = "legacy"
OVER_FEO = "over_feo"
FACT_OVER_PLAN = "fact_over_plan"
PLAN_OVER_MANUAL = "plan_over_manual"
TZ_OVER_PLANNED_ITEM = "tz_over_planned_item"
CONTRACT_OVER_TZ = "contract_over_tz"

# Зарезервированы для будущего разделения превышения по товары/услуги
# (item_type_split.py — пишет параллельный агент, вне файлов этой задачи).
# Константы и подписи заведены здесь заранее, чтобы обе стороны ссылались на
# ОДИН словарь видов — вычисление/учёт этих видов в текущей задаче НЕ
# реализуется.
PLAN_OVER_FEO_GOODS = "plan_over_feo_goods"
PLAN_OVER_FEO_SERVICES = "plan_over_feo_services"
FACT_OVER_PLAN_GOODS = "fact_over_plan_goods"
FACT_OVER_PLAN_SERVICES = "fact_over_plan_services"

LEVEL_CATEGORY = "category"
LEVEL_SUBSIDY = "subsidy"

KIND_LABELS: dict[str, str] = {
    LEGACY: "Превышение плана (запись до разделения по видам)",
    OVER_FEO: "План превышает финансирование по ФЭО",
    FACT_OVER_PLAN: "Факт (итог закупки/КП) превышает план",
    PLAN_OVER_MANUAL: "Плановые позиции превышают вручную заданный план",
    TZ_OVER_PLANNED_ITEM: "ТЗ превышает свою плановую позицию",
    CONTRACT_OVER_TZ: "Договор превышает закупку/ТЗ",
    PLAN_OVER_FEO_GOODS: "План (товары) превышает финансирование по ФЭО",
    PLAN_OVER_FEO_SERVICES: "План (услуги) превышает финансирование по ФЭО",
    FACT_OVER_PLAN_GOODS: "Факт (товары) превышает план",
    FACT_OVER_PLAN_SERVICES: "Факт (услуги) превышает план",
}

# СТАРЫЕ три вида узла дерева ФЭО (compute_feo_plan_tree), которые ДО этой
# задачи гасились ОДНОЙ approved-записью по категории независимо от вида —
# legacy-фолбэк (kind=LEGACY) продолжает гасить любой из них, см.
# app.services.feo_plan_tree._latest_approval и app.services.tz_excess_approval/
# contract_excess_approval — «старые данные продолжают гасить все три вида».
LEGACY_FALLBACK_KINDS = (OVER_FEO, FACT_OVER_PLAN, PLAN_OVER_MANUAL)


def kind_label(kind: Optional[str]) -> str:
    return KIND_LABELS.get(kind or LEGACY, KIND_LABELS[LEGACY])


def level_for_category_id(feo_category_id: Optional[int]) -> str:
    """Уровень записи по наличию feo_category_id: NULL = согласование по
    субсидии целиком, иначе — по конкретному узлу ФЭО."""
    return LEVEL_SUBSIDY if feo_category_id is None else LEVEL_CATEGORY
