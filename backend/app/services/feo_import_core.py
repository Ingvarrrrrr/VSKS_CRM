"""Оркестратор импорта категорий ФЭО из Excel-подобных строк — `_do_feo_import`.

Разрезано на этапы (Правило №5) из монолитной функции `_do_feo_import`
(~1230 строк, была единственным `def` в этом модуле) по её же явно
размеченным комментариями блокам:

    feo_import_snapshot.py  — снимок дерева категорий ДО импорта
    feo_import_gate.py      — затронутые субсидии + гейт записи по субсидии
    feo_import_apply.py     — снимок версии + основной цикл по строкам файла
    feo_import_plan.py      — collected_plan → FeoPlannedItem, родитель/дети
    feo_import_report.py    — отчёт «несопоставленные узлы» (только анализ)
    feo_import_remap.py     — N2б: переезд + удаление опустевших узлов
    feo_import_common.py    — чистые хелперы разбора ячеек (get_cell/to_dec/...)

Общее состояние между этапами — один `@dataclass FeoImportState` ниже.
Локальные переменные оригинала, которые читались более поздним кодом той же
функции, стали полями state; остальные (нужные только внутри одного этапа)
остались обычными локальными переменными внутри своего файла-этапа. Порядок
вызова этапов и порядок side-effect'ов (flush/commit, накопление
warnings/errors) не менялся — каждый этап делает ровно то же, что и
соответствующий блок оригинала, просто читает свои входы из `state` вместо
замыкания над локальными переменными `_do_feo_import`.

AST-эквивалентность оригиналу здесь недостижима (в отличие от feo_plan, где
резались уже существующие top-level функции) — новые границы функций внутри
одной раньше неделимой функции неизбежно меняют текст. Проверено вместо
этого: (1) построчная AST-эквивалентность каждого перенесённого БЛОКА
(if/for узлы) исходной функции при применении ровно тех текстовых замен,
которые описаны в докстринге каждого файла-этапа (переход от замыканий
`_full_path`/`_get_root_id`/`_subtree_ids_local`/`_canon_path` к модульным
функциям того же имени с явным параметром `existing_by_id`/
`existing_children` из feo_import_snapshot.py); (2) сквозной прогон
реального импорта одного файла до/после разрезания с сравнением снимков
`feo_categories`/`feo_planned_items`/отчёта функции.

`_do_feo_import` ниже сохраняет прежнюю сигнатуру один-в-один — вызывающий
код (app/routers/feo_import.py, app/routers/feo_categories.py через ленивый
ре-экспорт) не видит разницы.
"""
import json
from dataclasses import dataclass, field
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feo_category import FeoCategory
from app.utils.text import normalize_feo_name
from app.routers import feo_categories as fc

from app.services.feo_import_apply import apply_rows
from app.services.feo_import_gate import assert_write_gate, collect_affected_subsidies
from app.services.feo_import_plan import apply_collected_plan
from app.services.feo_import_remap import remap_and_prune
from app.services.feo_import_report import build_unmatched_report
from app.services.feo_import_snapshot import snapshot_tree_before


@dataclass
class FeoImportState:
    """Общее состояние между этапами импорта ФЭО (см. докстринг модуля).

    Поля сгруппированы так же, как они были сгруппированы в оригинале:
    вход (параметры `_do_feo_import`) → справочники, посчитанные один раз до
    цикла → снимок дерева → гейт/версия → счётчики и детали → отчёт
    «несопоставленные узлы» → собранный план строки → переезд/удаление.
    """

    # --- вход (параметры _do_feo_import, не меняются после инициализации) ---
    db: AsyncSession
    user: object
    dry_run: bool
    apply_remap: bool
    default_subsidy_id: int | None
    rows: list = field(default_factory=list)
    remap_list: list = field(default_factory=list)

    c_subsidy: int | None = None
    c_lvl2: int | None = None
    c_lvl3: int | None = None
    c_lvl4: int | None = None
    c_lvl5: int | None = None
    c_qty: int | None = None
    c_unit: int | None = None
    c_item_amt: int | None = None
    c_code: int | None = None
    c_appendix: int | None = None
    c_budget: int | None = None
    c_active: int | None = None
    c_qty_lvl2: int | None = None
    c_qty_lvl3: int | None = None
    c_qty_lvl4: int | None = None
    c_unit_lvl2: int | None = None
    c_unit_lvl3: int | None = None
    c_unit_lvl4: int | None = None
    c_amt_lvl2: int | None = None
    c_amt_lvl3: int | None = None
    c_amt_lvl4: int | None = None
    c_feo_qty_lvl2: int | None = None
    c_feo_qty_lvl3: int | None = None
    c_feo_qty_lvl4: int | None = None
    c_feo_unit_lvl2: int | None = None
    c_feo_unit_lvl3: int | None = None
    c_feo_unit_lvl4: int | None = None
    c_feo_amt_lvl2: int | None = None
    c_feo_amt_lvl3: int | None = None
    c_feo_amt_lvl4: int | None = None
    c_feo_sum_lvl2: int | None = None
    c_feo_sum_lvl3: int | None = None
    c_feo_sum_lvl4: int | None = None
    c_plan_sum_lvl2: int | None = None
    c_plan_sum_lvl3: int | None = None
    c_plan_sum_lvl4: int | None = None
    c_item_price: int | None = None
    c_row_feo_qty: int | None = None
    c_row_feo_unit: int | None = None
    c_row_feo_price: int | None = None
    c_row_feo_sum: int | None = None
    c_row_plan_qty: int | None = None
    c_row_plan_unit: int | None = None
    c_row_plan_price: int | None = None
    c_row_plan_sum: int | None = None
    c_item_type: int | None = None

    # --- справочники, посчитанные один раз до цикла (feo_import_core.py) ---
    sub_rows: list = field(default_factory=list)
    sub_by_name: dict = field(default_factory=dict)
    existing_cats: list = field(default_factory=list)
    cat_cache: dict = field(default_factory=dict)

    # --- снимок дерева ДО импорта (feo_import_snapshot.py) ---
    existing_by_id: dict = field(default_factory=dict)
    existing_children: dict = field(default_factory=dict)

    # --- гейт/версия (feo_import_gate.py, feo_import_apply.py) ---
    touched_subsidies: set = field(default_factory=set)
    version_created: bool = False

    # --- счётчики и детали (растут в feo_import_apply.py и feo_import_plan.py) ---
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    created_details: list = field(default_factory=list)
    updated_details: list = field(default_factory=list)
    skipped_details: list = field(default_factory=list)

    # --- для отчёта "несопоставленные узлы" (пишет feo_import_apply.py,
    # читают feo_import_report.py и feo_import_remap.py) ---
    seen_ids: set = field(default_factory=set)
    seen_roots: set = field(default_factory=set)
    new_paths: list = field(default_factory=list)
    new_path_cats: dict = field(default_factory=dict)
    unmatched: list = field(default_factory=list)

    # --- собранный план строки → FeoPlannedItem (feo_import_apply.py пишет,
    # feo_import_plan.py читает и обрабатывает) ---
    collected_plan: dict = field(default_factory=dict)
    lvl5_leaves: set = field(default_factory=set)
    lvl5_sum_by_cat: dict = field(default_factory=dict)
    touched_parents: set = field(default_factory=set)

    # --- переезд/удаление (feo_import_remap.py) ---
    relinked_count: int = 0
    deleted_count: int = 0
    remap_applied: list = field(default_factory=list)
    deleted_details: list = field(default_factory=list)
    remap_aborted_reason: str | None = None


async def _do_feo_import(
    rows: list,
    c_subsidy: int | None,
    c_lvl2: int | None,
    c_lvl3: int | None,
    c_lvl4: int | None,
    c_lvl5: int | None,
    c_qty: int | None,
    c_unit: int | None,
    c_item_amt: int | None,
    c_code: int | None,
    c_appendix: int | None,
    c_budget: int | None,
    c_active: int | None,
    db: AsyncSession,
    c_qty_lvl2: int | None = None,
    c_qty_lvl3: int | None = None,
    c_qty_lvl4: int | None = None,
    c_unit_lvl2: int | None = None,
    c_unit_lvl3: int | None = None,
    c_unit_lvl4: int | None = None,
    c_amt_lvl2: int | None = None,
    c_amt_lvl3: int | None = None,
    c_amt_lvl4: int | None = None,
    c_feo_qty_lvl2: int | None = None,
    c_feo_qty_lvl3: int | None = None,
    c_feo_qty_lvl4: int | None = None,
    c_feo_unit_lvl2: int | None = None,
    c_feo_unit_lvl3: int | None = None,
    c_feo_unit_lvl4: int | None = None,
    c_feo_amt_lvl2: int | None = None,
    c_feo_amt_lvl3: int | None = None,
    c_feo_amt_lvl4: int | None = None,
    c_feo_sum_lvl2: int | None = None,
    c_feo_sum_lvl3: int | None = None,
    c_feo_sum_lvl4: int | None = None,
    c_plan_sum_lvl2: int | None = None,
    c_plan_sum_lvl3: int | None = None,
    c_plan_sum_lvl4: int | None = None,
    c_item_price: int | None = None,
    # Новый 18-колоночный шаблон (2026-08-14): числа «по ФЭО»/«плана» — ОДНА пара
    # колонок на всю строку (не по уровням), см. блок «плоские числа» в
    # feo_import_apply.py.
    c_row_feo_qty: int | None = None,
    c_row_feo_unit: int | None = None,
    c_row_feo_price: int | None = None,
    c_row_feo_sum: int | None = None,
    c_row_plan_qty: int | None = None,
    c_row_plan_unit: int | None = None,
    c_row_plan_price: int | None = None,
    c_row_plan_sum: int | None = None,
    c_item_type: int | None = None,
    default_subsidy_id: int | None = None,
    dry_run: bool = False,
    user=None,
    remap: str = "",
    apply_remap: bool = False,
) -> dict:
    """Core import logic shared by /import и /import-mapped endpoints.

    dry_run=True: вся обработка выполняется, но транзакция откатывается.
    Возвращает {created, updated, skipped, errors, warnings, ...}.

    N2б: `remap` — JSON-список {"old_id": int, "new_path": str} для явного
    переезда несопоставленных узлов на новые (переезд + удаление опустевших
    старых узлов выполняются после основного цикла, см. feo_import_remap.py).
    Фаза переезда/удаления выполняется ТОЛЬКО при apply_remap=True — иначе
    (обычная загрузка без мастера сопоставления) выполняется только анализ.
    """
    if c_lvl2 is None:
        raise HTTPException(400, "Не найден обязательный столбец: 'Уровень 2 (Направление расходов)'")
    if c_subsidy is None and default_subsidy_id is None:
        raise HTTPException(400, "Укажите столбец 'Субсидия' или выберите субсидию назначения")
    if remap and not apply_remap:
        raise HTTPException(400, "Параметр remap передан без apply_remap=true")

    remap_list: list[dict] = []
    if remap:
        try:
            _raw_remap = json.loads(remap)
            if not isinstance(_raw_remap, list):
                raise ValueError("ожидался список")
            for _item in _raw_remap:
                if not isinstance(_item, dict) or "old_id" not in _item or "new_path" not in _item:
                    raise ValueError("каждый элемент должен содержать old_id и new_path")
                remap_list.append({
                    "old_id": int(_item["old_id"]),
                    "new_path": str(_item["new_path"]).strip(),
                })
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Неверный формат параметра remap: {e}")

    # Все ~50 колоночных параметров (c_subsidy, c_lvl2, ..., c_item_type) идут в
    # state 1:1 по имени через locals() — сигнатура функции не меняется для
    # вызывающего кода (app/routers/feo_import.py передаёт их по имени как и
    # раньше), а здесь не приходится дважды перечислять 50 имён вручную.
    column_kwargs = {k: v for k, v in locals().items() if k.startswith("c_")}
    state = FeoImportState(
        db=db, user=user, dry_run=dry_run, apply_remap=apply_remap,
        default_subsidy_id=default_subsidy_id, rows=rows, remap_list=remap_list,
        **column_kwargs,
    )

    from app.models.subsidy import Subsidy
    state.sub_rows = (await db.execute(select(Subsidy))).scalars().all()
    state.sub_by_name = {s.name.lower().strip(): s.id for s in state.sub_rows}

    # B (баг 2026-09-09, прод): touched_subsidies вычисляется РАНЬШЕ, чем раньше
    # (было после снимка existing_cats) — теперь используется ещё и для того,
    # чтобы existing_cats/cat_cache грузили категории ТОЛЬКО целевых субсидий,
    # а не всей БД. Раньше при default_subsidy_id, заданном для НОВОЙ пустой
    # субсидии, cat_cache всё равно тянул категории ВСЕХ субсидий (в т.ч. чужих
    # с сотнями узлов) — сама привязка find_or_create по (subsidy_id, parent_id,
    # name) не давала им ложно матчиться, но отчёт «несопоставленные узлы»
    # (build_unmatched_report/remap_and_prune) видел чужие деревья целиком.
    # collect_affected_subsidies не имеет побочных эффектов и не зависит от
    # cat_cache/existing_cats — переставить её раньше безопасно.
    collect_affected_subsidies(state)

    state.existing_cats = (await db.execute(
        select(FeoCategory).where(FeoCategory.subsidy_id.in_(state.touched_subsidies))
    )).scalars().all() if state.touched_subsidies else []
    cat_cache: dict[tuple, FeoCategory] = {}
    for c in state.existing_cats:
        cat_cache[(c.subsidy_id, c.parent_id, c.name.lower().strip())] = c
    state.cat_cache = cat_cache

    snapshot_tree_before(state)
    await assert_write_gate(state)
    await apply_rows(state)
    await apply_collected_plan(state)
    await build_unmatched_report(state)
    await remap_and_prune(state)

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    # Схлопываем одинаковые предупреждения по ключу (kind, name, message-без-суффикса)
    # Сохраняем номер строки первого вхождения и порядок появления
    _seen: dict[tuple, int] = {}   # ключ → индекс в _dedup_warnings
    _dedup_counts: list[int] = []
    _dedup_warnings: list[dict] = []
    for w in state.warnings:
        key = (w.get("kind"), w.get("name"), w.get("message"))
        if key in _seen:
            _dedup_counts[_seen[key]] += 1
        else:
            _seen[key] = len(_dedup_warnings)
            _dedup_warnings.append(dict(w))
            _dedup_counts.append(1)
    for i, cnt in enumerate(_dedup_counts):
        if cnt > 1:
            _dedup_warnings[i]["message"] = _dedup_warnings[i]["message"] + f" (строк: {cnt})"
    warnings = _dedup_warnings

    return {
        "created": state.created, "updated": state.updated, "skipped": state.skipped,
        "errors": state.errors, "warnings": warnings,
        "created_details": state.created_details,
        "updated_details": state.updated_details, "skipped_details": state.skipped_details,
        "dry_run": dry_run,
        "unmatched": state.unmatched,
        "new_paths": state.new_paths,
        "deleted_count": state.deleted_count,
        "relinked_count": state.relinked_count,
        "deleted_details": state.deleted_details,
        "remap_applied": state.remap_applied,
        "remap_aborted_reason": state.remap_aborted_reason,
        "version_created": state.version_created,
        "deletes_applied": bool(apply_remap),
    }
