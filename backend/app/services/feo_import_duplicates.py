"""Полные совпадения имени плановой позиции (Ур.5) в ОДНОЙ и той же категории
в пределах одного файла импорта ФЭО — волна 4, п.23 (слова владельца дословно):

    «Если 5 строк с наименованием «чайник» — с ценой 4000, 5000, 6000 — то не
    надо ставить только одну плановую позицию «Чайник» с ценой 6000. Должно
    быть предложение оставить как есть — это три строки «чайник», каждая со
    своей ценой, или объединить со средней ценой».

Решение принимает человек, ПО КАЖДОЙ ГРУППЕ ОТДЕЛЬНО (уточнение владельца) —
по умолчанию «оставить как есть» (файл читается буквально, ни одна строка не
теряется молча), объединение — только по явному выбору
`duplicate_resolutions[group_key] == "merge"`, переданному с фронта.

ДО этой правки `feo_import_apply.py` молча брал ПОСЛЕДНЮЮ строку с таким же
именем в категории («последняя побеждает», warning `duplicate_row_in_file`)
— ровно то поведение, которое владелец запретил («не делать это самовольно и
не брать только последнее значение»). Тот старый warning убран целиком
(Правило №6 — не держать два механизма объяснения одного и того же): вместо
него — `state.duplicate_groups` (показывается на шаге предпросмотра мастера,
FeoImportWizard.vue) и, при выборе «объединить», информационный warning
`duplicate_group_merged` (см. `_upsert_single_item` ниже).

Группировка — ПОЛНОЕ совпадение после нормализации (Правило проекта: fuzzy
matching в этом коде уже один раз слипал разные товары, см. Lessons.md
«Дедуп товаров — только точное совпадение») — `feo_import_common.norm` же
самое, что схлопывает соседние уровни (level_duplicate) и матчит позиции при
повторном импорте.

Ключ группы строится из (subsidy_id, нормализованные имена узлов пути,
нормализованное имя позиции) — НЕ из id категории: id категории — реальный
autoincrement, назначенный `db.flush()` внутри ТЕКУЩЕЙ транзакции, и не
совпадает между dry-run предпросмотром и последующим боевым вызовом
(rollback dry-run не откатывает последовательность id в Postgres). Текстовый
ключ стабилен между обоими вызовами — фронт может отправить `duplicate_
resolutions`, посчитанные по ответу dry-run, во время боевого вызова.

Публичный API этого модуля:
    group_key(subsidy_id, path_names, item_name) -> str
    register_pending_item(state, group_key, leaf, row_data) -> None
    finalize_lvl5_items(state) -> None   — вызывается ПОСЛЕ apply_rows,
                                            ДО apply_collected_plan (см.
                                            feo_import_core.py) — единственное
                                            место, где Ур.5-строки файла
                                            превращаются в FeoPlannedItem.
"""
from decimal import Decimal

from sqlalchemy import select

from app.models.feo_planned_item import FeoPlannedItem
from app.services.feo_import_common import QUANT, ZERO, format_rows, level_label, norm
from app.services.feo_import_common import fmt as _fmt

ONE = Decimal("1")


def group_key(subsidy_id, path_names: list, item_name: str) -> str:
    """Единственное место построения ключа группы дублей (Правило №6) — тот
    же нормализатор (`norm`/`normalize_feo_name`), что и везде в импорте
    ФЭО (level_duplicate, повторный импорт того же файла и т.д.), поэтому
    «Чайник» / «чайник» / «  Чайник  » — одна группа, а «Чайник» и «Чайники»
    (или любое другое имя, отличающееся по существу) — разные, как и
    потребовал владелец («совпадение должно быть полным»)."""
    parts = [norm(p or "") for p in path_names]
    parts.append(norm(item_name or ""))
    return f"{subsidy_id}::" + "/".join(parts)


def register_pending_item(state, key: str, leaf, row_data: dict) -> None:
    """Строка файла с заполненной «Плановой позицией» — не создаёт
    FeoPlannedItem немедленно (как было раньше), а копится по ключу группы;
    реальная запись в БД — в `finalize_lvl5_items`, после того как собран ВЕСЬ
    файл и известно, сколько строк реально попало в одну группу."""
    row_data = dict(row_data)
    row_data["leaf"] = leaf
    state.pending_lvl5_items.setdefault(key, []).append(row_data)


def _num(v) -> float | None:
    if v is None:
        return None
    return float(v)


def _combine_rows(rows: list) -> dict:
    """Объединение группы дублей в ОДНУ позицию (владелец, уточнение №2):
    суммы и количества СКЛАДЫВАЮТСЯ, цена за единицу выводится делением —
    деньги не должны измениться ни на рубль. `amount` объединённой позиции —
    точная сумма amount всех строк (без промежуточного округления через
    цену), поэтому инвариант «сумма не изменилась» выполняется тождественно,
    а не в пределах округления.

    То же самое — ОТДЕЛЬНО — для комплекта «по ФЭО» (feo_qty/feo_unit/
    feo_amount, боевой инцидент 2026-09-16, см. feo_import_apply.py у
    объявления item_plan_qty): без этого объединение группы дублей молча
    брало ФЭО-числа ПОСЛЕДНЕЙ строки (через `dict(rows[-1])`), и они переставали
    сходиться с объединённым планом/суммой."""
    total_amount = sum((r["amount"] or ZERO) for r in rows)
    total_qty = sum((r["qty"] if r["qty"] is not None else ONE) for r in rows)
    unit = next((r["unit"] for r in rows if r["unit"]), None)
    unit_price = (total_amount / total_qty).quantize(QUANT) if total_qty else None
    total_feo_amount = sum((r.get("feo_amount") or ZERO) for r in rows)
    total_feo_qty = sum((r.get("feo_qty") or ZERO) for r in rows)
    feo_unit = next((r.get("feo_unit") for r in rows if r.get("feo_unit")), None)
    feo_unit_price = (total_feo_amount / total_feo_qty).quantize(QUANT) if total_feo_qty else None
    merged = dict(rows[-1])  # берём последние флаги/тип как есть — они одинаковы по построению группы
    merged["qty"] = total_qty
    merged["unit"] = unit
    merged["amount"] = total_amount
    merged["unit_price"] = unit_price
    merged["feo_qty"] = total_feo_qty or None
    merged["feo_unit"] = feo_unit
    merged["feo_unit_price"] = feo_unit_price
    merged["feo_amount"] = total_feo_amount or None
    merged["row"] = rows[-1]["row"]
    return merged


def _describe_group(key: str, name: str, rows: list) -> dict:
    total_amount = sum((r["amount"] or ZERO) for r in rows)
    total_qty = sum((r["qty"] if r["qty"] is not None else ONE) for r in rows)
    unit = next((r["unit"] for r in rows if r["unit"]), None)
    merged_price = (total_amount / total_qty).quantize(QUANT) if total_qty else None
    path_names = rows[0].get("path") or []
    return {
        "key": key,
        "category_path": " / ".join(path_names),
        "name": name,
        "rows": [
            {
                "row": r["row"],
                "qty": _num(r["qty"]),
                "unit": r["unit"],
                "amount": _num(r["amount"]),
            }
            for r in rows
        ],
        "count": len(rows),
        "sum_before": _num(total_amount),
        "qty_before": _num(total_qty),
        "merged_preview": {
            "qty": _num(total_qty),
            "unit": unit,
            "price": _num(merged_price),
            "amount": _num(total_amount),
        },
    }


async def _matching_items(db, leaf_id: int, name: str) -> list:
    """Единственное место сопоставления существующей плановой позиции с
    именем строки файла — ПОЛНОЕ совпадение после нормализации (Правило №6;
    раньше здесь было точное строковое равенство `FeoPlannedItem.name ==
    lvl5_name`, ловившее только совпадение день-в-день по регистру —
    расхождение с тем, как имена сравниваются при группировке дублей). Без
    фильтра по is_active — так же, как и раньше: неактивная позиция того же
    имени тоже должна быть найдена и обновлена, а не задвоена."""
    rows = (await db.execute(
        select(FeoPlannedItem).where(FeoPlannedItem.feo_category_id == leaf_id)
    )).scalars().all()
    target = norm(name)
    return sorted((it for it in rows if norm(it.name or "") == target), key=lambda it: it.id)


async def _upsert_one(state, leaf, item_data: dict, *, extra_reason: str | None, matches: list) -> None:
    """Создаёт/обновляет ОДНУ FeoPlannedItem — общий хвост и для обычной
    (не-дублирующейся) позиции, и для объединённой группы. `matches` — уже
    посчитанный список существующих позиций с этим именем в категории
    (`_matching_items`), чтобы при объединении вызывающий код мог сам решить
    судьбу «лишних» существующих позиций (см. `_upsert_merge`)."""
    db = state.db
    name = item_data["name"]
    row_num = item_data["row"]
    existing_item = matches[0] if matches else None

    if existing_item is None:
        _fpi_kwargs = dict(
            feo_category_id=leaf.id, name=name,
            quantity=item_data["qty"], unit=item_data["unit"], amount=item_data["amount"],
            is_active=item_data["is_active"],
        )
        if hasattr(FeoPlannedItem, "item_type"):
            _fpi_kwargs["item_type"] = item_data.get("item_type")
        if hasattr(FeoPlannedItem, "is_feo_breakdown"):
            _fpi_kwargs["is_feo_breakdown"] = item_data.get("is_feo_breakdown", False)
        if hasattr(FeoPlannedItem, "is_internal_plan"):
            _fpi_kwargs["is_internal_plan"] = item_data.get("is_internal_plan", True)
        # Боевой инцидент 2026-09-16 (субсидия «Абхазия_2»): цена за единицу и
        # раздельный комплект «по ФЭО» (см. FeoPlannedItem.unit_price/feo_quantity/
        # feo_unit_price/feo_amount, миграции z1a2b3c4d5e6/c2d4e6f8a0b2) раньше
        # никогда не заполнялись импортом — hasattr-проверка тут по тому же
        # стилю, что и у item_type/is_feo_breakdown выше (совместимость со
        # старыми тестовыми моделями).
        if hasattr(FeoPlannedItem, "unit_price"):
            _fpi_kwargs["unit_price"] = item_data.get("unit_price")
        if hasattr(FeoPlannedItem, "feo_quantity"):
            _fpi_kwargs["feo_quantity"] = item_data.get("feo_qty")
        if hasattr(FeoPlannedItem, "feo_unit_price"):
            _fpi_kwargs["feo_unit_price"] = item_data.get("feo_unit_price")
        if hasattr(FeoPlannedItem, "feo_amount"):
            _fpi_kwargs["feo_amount"] = item_data.get("feo_amount")
        pi = FeoPlannedItem(**_fpi_kwargs)
        db.add(pi)
        await db.flush()
        state.created += 1
        reason = extra_reason or f"плановая позиция ({level_label(5)})"
        state.created_details.append({"row": row_num, "name": name, "reason": reason})
        return

    ch2 = False
    if item_data["qty"] is not None and existing_item.quantity != item_data["qty"]:
        existing_item.quantity = item_data["qty"]; ch2 = True
    if item_data["unit"] is not None and existing_item.unit != item_data["unit"]:
        existing_item.unit = item_data["unit"]; ch2 = True
    if item_data["amount"] is not None and existing_item.amount != item_data["amount"]:
        existing_item.amount = item_data["amount"]; ch2 = True
    if item_data.get("item_type") is not None and hasattr(existing_item, "item_type") and existing_item.item_type != item_data["item_type"]:
        existing_item.item_type = item_data["item_type"]; ch2 = True
    if hasattr(existing_item, "is_feo_breakdown") and existing_item.is_feo_breakdown != item_data.get("is_feo_breakdown", False):
        existing_item.is_feo_breakdown = item_data.get("is_feo_breakdown", False); ch2 = True
    if hasattr(existing_item, "is_internal_plan") and existing_item.is_internal_plan != item_data.get("is_internal_plan", True):
        existing_item.is_internal_plan = item_data.get("is_internal_plan", True); ch2 = True
    if item_data.get("unit_price") is not None and hasattr(existing_item, "unit_price") and existing_item.unit_price != item_data["unit_price"]:
        existing_item.unit_price = item_data["unit_price"]; ch2 = True
    if item_data.get("feo_qty") is not None and hasattr(existing_item, "feo_quantity") and existing_item.feo_quantity != item_data["feo_qty"]:
        existing_item.feo_quantity = item_data["feo_qty"]; ch2 = True
    if item_data.get("feo_unit_price") is not None and hasattr(existing_item, "feo_unit_price") and existing_item.feo_unit_price != item_data["feo_unit_price"]:
        existing_item.feo_unit_price = item_data["feo_unit_price"]; ch2 = True
    if item_data.get("feo_amount") is not None and hasattr(existing_item, "feo_amount") and existing_item.feo_amount != item_data["feo_amount"]:
        existing_item.feo_amount = item_data["feo_amount"]; ch2 = True
    if ch2:
        state.updated += 1
        reason = extra_reason or "обновлена позиция — значения перезаписаны из файла"
        state.updated_details.append({"row": row_num, "name": name, "reason": reason})
    else:
        state.skipped += 1
        state.skipped_details.append({"row": row_num, "name": name, "reason": "без изменений"})


async def _upsert_merge(state, leaf, rows: list, key: str) -> None:
    merged = _combine_rows(rows)
    matches = await _matching_items(state.db, leaf.id, merged["name"])
    _rows_str = format_rows([r["row"] for r in rows])
    _reason = f"объединено из {len(rows)} строк файла ({_rows_str}) — суммы сложены, цена усреднена делением"
    await _upsert_one(state, leaf, merged, extra_reason=_reason, matches=matches)
    # «Лишние» существующие позиции того же имени (например, файл раньше
    # импортировался с выбором «оставить как есть», и теперь при повторном
    # импорте с тем же именем пользователь выбрал «объединить») — деактивируем,
    # а не удаляем (проектный паттерн is_active вместо DELETE) и не оставляем
    # молча висеть: иначе их суммы задвоились бы с объединённой позицией.
    for extra in matches[1:]:
        if extra.is_active:
            extra.is_active = False
            state.updated += 1
            state.updated_details.append({
                "row": None, "name": extra.name,
                "reason": f"деактивирована как лишний дубль после объединения группы ({_rows_str})",
            })
    total_before = sum((r["amount"] or ZERO) for r in rows)
    state.warnings.append({
        "kind": "duplicate_group_merged",
        "row": None,
        "name": merged["name"],
        "message": (
            f"«{merged['name']}» — объединены {len(rows)} строк файла ({_rows_str}): "
            f"количество {_fmt(merged['qty'])}, сумма {_fmt(merged['amount'])} "
            f"(было по строкам: {_fmt(total_before)} — сумма не изменилась)"
        ),
    })


async def _upsert_keep_separate(state, leaf, rows: list) -> None:
    """«Оставить как есть» (по умолчанию, владелец: решение принимает
    человек, автоматического объединения быть не должно) — каждая строка
    группы становится ОТДЕЛЬНОЙ плановой позицией со своими количеством/
    ценой/суммой. Сопоставление с уже существующими позициями — ПОРЯДКОВОЕ
    (i-я по номеру строки файла строка группы ↔ i-я по id существующая
    позиция с этим именем): устойчиво для идемпотентного повторного импорта
    ТОГО ЖЕ файла (тот же порядок строк — тот же порядок существующих
    позиций), но не гарантирует стабильность, если между импортами позиции
    этой группы были вручную переставлены/удалены — сознательное упрощение,
    вне сценариев владельца из задания."""
    name = rows[0]["name"]
    matches = await _matching_items(state.db, leaf.id, name)
    for i, row_data in enumerate(rows):
        m = matches[i:i + 1]
        await _upsert_one(state, leaf, row_data, extra_reason=None, matches=m)


async def finalize_lvl5_items(state) -> None:
    """Единственное место, где `state.pending_lvl5_items` (собран
    `feo_import_apply.py` во время основного цикла по строкам) превращается
    в реальные FeoPlannedItem. Группа из ОДНОЙ строки — старое поведение
    (создать/обновить по точному-после-нормализации имени), без предупреждений
    о дублях. Группа из 2+ строк — решение по `state.duplicate_resolutions`
    (ключ группы → 'merge'/'keep', см. `group_key`), по умолчанию 'keep' —
    владелец явно запретил автоматическое объединение."""
    for key, rows in state.pending_lvl5_items.items():
        leaf = rows[0]["leaf"]
        name = rows[0]["name"]

        if len(rows) == 1:
            matches = await _matching_items(state.db, leaf.id, name)
            await _upsert_one(state, leaf, rows[0], extra_reason=None, matches=matches)
            continue

        resolution = state.duplicate_resolutions.get(key, "keep")
        group_info = _describe_group(key, name, rows)
        group_info["resolution"] = resolution
        state.duplicate_groups.append(group_info)

        if resolution == "merge":
            await _upsert_merge(state, leaf, rows, key)
        else:
            await _upsert_keep_separate(state, leaf, rows)
