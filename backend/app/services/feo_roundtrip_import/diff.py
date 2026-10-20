"""Иерархия + предпросмотр загрузки обратно «Выгрузить ФЭО» (задача
владельца 20.10.2026). Читает БД (категории/позиции текущей субсидии), НЕ
пишет — apply.py выполняет построенный здесь план через существующие
сервисы записи.

Иерархия строк (владелец, п.2):
  уровень = outline_level строки, если ХОТЬ ОДНА строка файла его несёт;
  иначе уровень = (число ведущих пробелов в «Наименование») // 2 (файл
  набран человеком руками, без группировки Excel).
  Родитель строки — ближайшая ВЫШЕ строка с МЕНЬШИМ уровнем, чей тип —
  категория («Категория»/«Категория без позиций»); стек по уровню, файл уже
  в родитель-перед-детьми порядке (тот же порядок, что пишет
  feo_export_xlsx.py).
  Тип строки пустой -> «Позиция», если следующая строка не глубже (т.е. эта
  строка — лист); иначе «Категория» (у нее дальше идут более глубокие
  строки).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.services.subsidy_budget import _active_feo_items_with_amount
from app.services.feo_roundtrip_import.amount_resolve import resolve_amount
from app.services.feo_roundtrip_import.parse import (
    CATEGORY_TYPES, FORMAT_VERSION, MetaInfo, ParsedRow, POSITION_TYPE,
)

KIND_CATEGORY = "category"
KIND_POSITION = "position"


@dataclass
class ResolvedRow:
    parsed: ParsedRow
    level: int = 0
    kind: str = KIND_POSITION
    parent_index: Optional[int] = None  # индекс в resolved-списке, None = корень
    has_children_in_file: bool = False
    entity_kind: Optional[str] = None  # 'category'|'item', None пока не определено
    entity_id: Optional[int] = None    # существующая сущность (по row_id)
    is_new: bool = True
    error: Optional[str] = None
    # Эффективные суммы позиции (после сведения «сумма vs кол-во×цена» —
    # см. amount_resolve.resolve_amount), считаются ОДИН раз в build_preview
    # и переиспользуются apply.py (ПРАВИЛО №6 — второй расчёт не заводим).
    # Только для kind == KIND_POSITION.
    resolved_feo_amount: Optional[Decimal] = None
    resolved_plan_amount: Optional[Decimal] = None


@dataclass
class PreviewResult:
    changes: list = field(default_factory=list)
    created: list = field(default_factory=list)
    moved: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # resolved — для apply.py (не идёт в ответ API как есть, но нужен, чтобы
    # не парсить/резолвить дерево дважды — preview и apply делят один и тот
    # же план).
    resolved: list = field(default_factory=list)


def _row_type(raw: str) -> Optional[str]:
    """None — пусто (вывести тип по следующей строке в build_hierarchy);
    иначе нормализованный тип из CATEGORY_TYPES/POSITION_TYPE, либо «?» для
    нераспознанного текста (трактуется как «Позиция» — безопасный дефолт)."""
    t = (raw or "").strip()
    if not t:
        return None
    if t in CATEGORY_TYPES:
        return "category"
    if t == POSITION_TYPE:
        return "position"
    return "position"


def build_hierarchy(parsed_rows: list) -> list[ResolvedRow]:
    """Строит уровень/тип/родителя для каждой строки — см. докстринг модуля.
    `parsed_rows` — list[ParsedRow] в порядке файла (родитель перед детьми,
    как пишет feo_export_xlsx.py)."""
    use_outline = any(r.outline_level for r in parsed_rows)
    levels = [
        (r.outline_level if use_outline else (r.leading_spaces // 2))
        for r in parsed_rows
    ]

    # Тип пустой строки зависит от уровня СЛЕДУЮЩЕЙ строки — вычисляем типы
    # заранее одним проходом справа налево.
    explicit_types: list[Optional[str]] = [_row_type(r.row_type_raw) for r in parsed_rows]
    resolved_type: list[str] = [""] * len(parsed_rows)
    for i in range(len(parsed_rows) - 1, -1, -1):
        if explicit_types[i] is not None:
            resolved_type[i] = explicit_types[i]
            continue
        is_leaf = (i == len(parsed_rows) - 1) or (levels[i + 1] <= levels[i])
        resolved_type[i] = "position" if is_leaf else "category"

    out: list[ResolvedRow] = []
    stack: list[tuple[int, int]] = []  # (level, index in out) — только категории
    for i, r in enumerate(parsed_rows):
        level = levels[i]
        kind = resolved_type[i]
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_index = stack[-1][1] if stack else None

        rr = ResolvedRow(parsed=r, level=level, kind=kind, parent_index=parent_index)
        if kind == KIND_POSITION and parent_index is None:
            rr.error = f"Строка {r.row_num}: «{r.name}» — позиция без родительской категории"
        out.append(rr)

        if kind == KIND_CATEGORY:
            stack.append((level, i))

    for rr in out:
        if rr.parent_index is not None:
            out[rr.parent_index].has_children_in_file = True
    return out


def _norm_name(s: Optional[str]) -> str:
    """Сравнение названий «как видит человек»: ведущие/конечные пробелы и
    повторные пробелы внутри НЕ считаются изменением (баг 46/953 — в БД
    «  Аренда автотранспортных…» с ведущими пробелами, в файле без них;
    экспорт сам добавляет отступ «  »*depth к имени, поэтому лишние пробелы
    у категорий — частый шум, не реальная правка)."""
    return re.sub(r"\s+", " ", (s or "").strip())


def _parse_row_id(raw: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    if not raw:
        return None, None
    raw = raw.strip()
    if len(raw) < 2:
        return None, None
    prefix, rest = raw[0], raw[1:]
    if prefix not in ("c", "p") or not rest.isdigit():
        return None, None
    return prefix, int(rest)


def check_meta_mismatch(meta: Optional[MetaInfo], subsidy_id: int) -> Optional[str]:
    """Файл выгружен из ДРУГОЙ субсидии (лист _meta) — жёсткий отказ, без
    флага-обхода (владелец выбрал безопасный вариант — см. докстринг задачи):
    строки файла могли случайно совпасть по № записи с сущностями ЭТОЙ
    субсидии только по счастливой нумерации id, подмена категории/позиции
    под другим именем была бы трудно заметна человеком в предпросмотре.
    Роутер вызывает это ПЕРЕД build_preview, чтобы вернуть явный HTTP 400, а
    не прятать ошибку внутри обычного списка `errors` предпросмотра."""
    if meta is not None and meta.subsidy_id is not None and meta.subsidy_id != subsidy_id:
        return (
            f"Файл выгружен из другой субсидии (id={meta.subsidy_id}) — "
            f"загрузка в субсидию id={subsidy_id} отклонена. Выгрузите файл "
            "заново из этой субсидии."
        )
    return None


async def build_preview(
    db, subsidy_id: int, parsed_rows: list, meta: Optional[MetaInfo],
) -> PreviewResult:
    """Главная функция модуля: иерархия + сопоставление с БД + диффы.
    НЕ пишет в БД (только SELECT)."""
    result = PreviewResult()

    _mismatch = check_meta_mismatch(meta, subsidy_id)
    if _mismatch:
        result.errors.append({"row": None, "message": _mismatch})
        return result
    if meta is not None and meta.format_version and meta.format_version != FORMAT_VERSION:
        result.warnings.append({
            "message": f"Версия формата файла ({meta.format_version}) отличается от текущей ({FORMAT_VERSION})",
        })

    resolved = build_hierarchy(parsed_rows)
    result.resolved = resolved

    # Сведение «сумма vs кол-во × цена за единицу» (задача владельца, п.3) —
    # считается ОДИН раз для каждой строки-позиции, ДО диффа и ДО apply
    # (apply.py переиспользует rr.resolved_feo_amount/resolved_plan_amount,
    # второй расчёт там не заводится).
    for rr in resolved:
        if rr.kind != KIND_POSITION:
            continue
        p = rr.parsed
        feo_amt, feo_warn = resolve_amount(p.feo_qty, p.feo_unit_price, p.feo_amount)
        plan_amt, plan_warn = resolve_amount(p.plan_qty, p.plan_unit_price, p.plan_amount)
        rr.resolved_feo_amount = feo_amt
        rr.resolved_plan_amount = plan_amt
        if feo_warn:
            result.warnings.append({"row": p.row_num, "message": f"Строка {p.row_num}: «{p.name}» — по ФЭО {feo_warn}"})
        if plan_warn:
            result.warnings.append({"row": p.row_num, "message": f"Строка {p.row_num}: «{p.name}» — по плану {plan_warn}"})

    # --- существующие категории/позиции субсидии (для missing + сопоставления) ---
    cats = (await db.execute(select(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id))).scalars().all()
    cat_by_id = {c.id: c for c in cats}
    cat_ids = set(cat_by_id)
    item_rows = (await db.execute(
        select(FeoPlannedItem).join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )).scalars().all()
    item_by_id = {it.id: it for it in item_rows}
    # «Нет в файле» считается ТОЛЬКО по множеству, которое выгрузка реально
    # выводит (ПРАВИЛО №6 — тот же фильтр app.services.subsidy_budget.
    # _active_feo_items_with_amount, что и build_feo_export_workbook, не
    # копия условия is_active/feo_amount по месту): неактивные позиции и
    # позиции без feo_amount (план без ФЭО) никогда не попадают в файл, так
    # что их отсутствие в файле — не сигнал «удалить/разобраться», а норма.
    exportable_items = await _active_feo_items_with_amount(db, list(cat_ids))
    exportable_item_ids = {it.id for it in exportable_items}

    seen_cat_ids: set[int] = set()
    seen_item_ids: set[int] = set()

    for rr in resolved:
        if rr.error:
            result.errors.append({"row": rr.parsed.row_num, "message": rr.error})
            continue
        prefix, ent_id = _parse_row_id(rr.parsed.row_id_raw)
        if prefix is None and rr.parsed.row_id_raw:
            rr.error = f"Строка {rr.parsed.row_num}: нераспознанный «№ в системе» «{rr.parsed.row_id_raw}»"
            result.errors.append({"row": rr.parsed.row_num, "message": rr.error})
            continue

        expected_prefix = "c" if rr.kind == KIND_CATEGORY else "p"
        if prefix is not None and prefix != expected_prefix:
            rr.error = (
                f"Строка {rr.parsed.row_num}: «№ в системе» «{rr.parsed.row_id_raw}» "
                f"не соответствует типу строки «{rr.parsed.row_type_raw or ('Позиция' if rr.kind == KIND_POSITION else 'Категория')}»"
            )
            result.errors.append({"row": rr.parsed.row_num, "message": rr.error})
            continue

        if prefix is None:
            rr.is_new = True
            continue

        if rr.kind == KIND_CATEGORY:
            cat = cat_by_id.get(ent_id)
            if cat is None:
                rr.error = f"Строка {rr.parsed.row_num}: категория №{ent_id} не найдена в этой субсидии"
                result.errors.append({"row": rr.parsed.row_num, "message": rr.error})
                continue
            rr.is_new = False
            rr.entity_kind = "category"
            rr.entity_id = ent_id
            seen_cat_ids.add(ent_id)
        else:
            item = item_by_id.get(ent_id)
            if item is None:
                rr.error = f"Строка {rr.parsed.row_num}: плановая позиция №{ent_id} не найдена в этой субсидии"
                result.errors.append({"row": rr.parsed.row_num, "message": rr.error})
                continue
            rr.is_new = False
            rr.entity_kind = "item"
            rr.entity_id = ent_id
            seen_item_ids.add(ent_id)

    # --- родитель, помеченный ошибкой, тянет ошибку на детей (fail-safe) ---
    error_indices = {i for i, rr in enumerate(resolved) if rr.error}
    changed = True
    while changed:
        changed = False
        for i, rr in enumerate(resolved):
            if rr.error:
                continue
            if rr.parent_index is not None and rr.parent_index in error_indices:
                rr.error = f"Строка {rr.parsed.row_num}: пропущена из-за ошибки в родительской строке"
                result.errors.append({"row": rr.parsed.row_num, "message": rr.error})
                error_indices.add(i)
                changed = True

    # --- diff per row (только строки без ошибок) ---
    resolved_parent_name = lambda rr: (resolved[rr.parent_index].parsed.name if rr.parent_index is not None else None)
    for rr in resolved:
        if rr.error:
            continue
        if rr.is_new:
            result.created.append({
                "row": rr.parsed.row_num,
                "kind": "category" if rr.kind == KIND_CATEGORY else "position",
                "name": rr.parsed.name,
                "parent_name": resolved_parent_name(rr),
            })
            continue

        if rr.kind == KIND_CATEGORY:
            cat = cat_by_id[rr.entity_id]
            _diff_category_fields(rr, cat, result)
            # перенос — родитель в файле отличается от cat.parent_id
            new_parent_row = resolved[rr.parent_index] if rr.parent_index is not None else None
            new_parent_id = None
            if new_parent_row is not None and not new_parent_row.is_new:
                new_parent_id = new_parent_row.entity_id
            old_parent_id = cat.parent_id
            if new_parent_row is not None and new_parent_row.is_new:
                # родитель — НОВАЯ категория этого же файла: перенос
                # зафиксируется автоматически при создании (apply всегда
                # ставит parent_id из своего резолва) — отдельно не считаем
                # дифф-строку "перемещена", т.к. технически это создание под
                # новым узлом, не перемещение существующей записи.
                pass
            elif old_parent_id != new_parent_id:
                result.moved.append({
                    "row": rr.parsed.row_num, "kind": "category",
                    "id": cat.id, "name": cat.name,
                    "old_parent_name": cat_by_id[old_parent_id].name if old_parent_id in cat_by_id else None,
                    "new_parent_name": resolved_parent_name(rr),
                })
        else:
            item = item_by_id[rr.entity_id]
            _diff_item_fields(rr, item, result)
            new_parent_row = resolved[rr.parent_index] if rr.parent_index is not None else None
            new_parent_id = new_parent_row.entity_id if (new_parent_row is not None and not new_parent_row.is_new) else None
            if new_parent_row is not None and not new_parent_row.is_new and item.feo_category_id != new_parent_id:
                old_cat = cat_by_id.get(item.feo_category_id)
                result.moved.append({
                    "row": rr.parsed.row_num, "kind": "position",
                    "id": item.id, "name": item.name,
                    "old_parent_name": old_cat.name if old_cat else None,
                    "new_parent_name": resolved_parent_name(rr),
                })

    missing_cat_ids = cat_ids - seen_cat_ids
    missing_item_ids = exportable_item_ids - seen_item_ids
    for cid in sorted(missing_cat_ids):
        result.missing.append({"id": cid, "name": cat_by_id[cid].name, "type": "category"})
    for iid in sorted(missing_item_ids):
        result.missing.append({"id": iid, "name": item_by_id[iid].name, "type": "position"})

    return result


def _num_eq(a, b) -> bool:
    fa = float(a) if a is not None else None
    fb = float(b) if b is not None else None
    if fa is None and fb is None:
        return True
    if fa is None or fb is None:
        return False
    return abs(fa - fb) < 0.005


def _diff_category_fields(rr: ResolvedRow, cat: FeoCategory, result: PreviewResult) -> None:
    p = rr.parsed
    if p.name and _norm_name(p.name) != _norm_name(cat.name):
        result.changes.append({"row": p.row_num, "kind": "category", "id": cat.id, "name": cat.name, "field": "name", "old": cat.name, "new": p.name})
    if p.code is not None and (p.code or None) != (cat.code or None):
        result.changes.append({"row": p.row_num, "kind": "category", "id": cat.id, "name": cat.name, "field": "code", "old": cat.code, "new": p.code})
    if p.appendix is not None and (p.appendix or None) != (cat.appendix or None):
        result.changes.append({"row": p.row_num, "kind": "category", "id": cat.id, "name": cat.name, "field": "appendix", "old": cat.appendix, "new": p.appendix})
    if p.is_active is not None and p.is_active != cat.is_active:
        result.changes.append({"row": p.row_num, "kind": "category", "id": cat.id, "name": cat.name, "field": "is_active", "old": cat.is_active, "new": p.is_active})
    # «Есть дети в файле» -> ФЭО — формула-сумма на экспорте, НЕ редактируется
    # загрузкой обратно (задача владельца, п.2).
    if not rr.has_children_in_file and p.feo_amount is not None and not _num_eq(p.feo_amount, cat.budget):
        result.changes.append({
            "row": p.row_num, "kind": "category", "id": cat.id, "name": cat.name,
            "field": "feo_amount", "old": float(cat.budget) if cat.budget is not None else None,
            "new": float(p.feo_amount),
        })
    # «Запланировано» категории без детей — вычисляется из закупок,
    # привязанных напрямую к категории (см. feo_export_xlsx.py:own_plan),
    # полю БД не соответствует — загрузка обратно его не меняет (только
    # предупреждает, если пользователь явно вписал другое число).


def _diff_item_fields(rr: ResolvedRow, item: FeoPlannedItem, result: PreviewResult) -> None:
    """ДВА независимых комплекта чисел позиции (см. докстринг FeoPlannedItem):
    feo_qty/feo_unit_price/resolved_feo_amount -> feo_quantity/feo_unit_price/
    feo_amount («по ФЭО»); plan_qty/plan_unit_price/resolved_plan_amount ->
    quantity/unit_price/amount («план»). `unit` — общее поле, одна колонка
    «Ед.» на оба количества. resolved_* — уже сведённые кол-во×цена/сумма
    (см. build_preview выше, amount_resolve.resolve_amount)."""
    p = rr.parsed
    if p.name and _norm_name(p.name) != _norm_name(item.name):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "name", "old": item.name, "new": p.name})
    if p.feo_qty is not None and not _num_eq(p.feo_qty, item.feo_quantity):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "feo_quantity", "old": float(item.feo_quantity) if item.feo_quantity is not None else None, "new": float(p.feo_qty)})
    if p.feo_unit is not None and (p.feo_unit or None) != (item.unit or None):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "unit", "old": item.unit, "new": p.feo_unit})
    if p.feo_unit_price is not None and not _num_eq(p.feo_unit_price, item.feo_unit_price):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "feo_unit_price", "old": float(item.feo_unit_price) if item.feo_unit_price is not None else None, "new": float(p.feo_unit_price)})
    if rr.resolved_feo_amount is not None and not _num_eq(rr.resolved_feo_amount, item.feo_amount):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "feo_amount", "old": float(item.feo_amount) if item.feo_amount is not None else None, "new": float(rr.resolved_feo_amount)})
    if p.plan_qty is not None and not _num_eq(p.plan_qty, item.quantity):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "quantity", "old": float(item.quantity) if item.quantity is not None else None, "new": float(p.plan_qty)})
    if p.plan_unit_price is not None and not _num_eq(p.plan_unit_price, item.unit_price):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "unit_price", "old": float(item.unit_price) if item.unit_price is not None else None, "new": float(p.plan_unit_price)})
    if rr.resolved_plan_amount is not None and not _num_eq(rr.resolved_plan_amount, item.amount):
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "amount", "old": float(item.amount) if item.amount is not None else None, "new": float(rr.resolved_plan_amount)})
    if p.is_active is not None and p.is_active != item.is_active:
        result.changes.append({"row": p.row_num, "kind": "position", "id": item.id, "name": item.name, "field": "is_active", "old": item.is_active, "new": p.is_active})
