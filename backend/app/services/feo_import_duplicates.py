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
from app.services.feo_import_comments import record_item_id
from app.services import feo_history

def _sum_qty(rows: list) -> Decimal | None:
    """Единственное место суммирования количества группы дублей (Правило №6
    — `_combine_rows` и `_describe_group` обязаны звать именно её, а не
    считать сумму каждая по-своему).

    Баг владельца (22.09, группа «Спасательный конец Александрова в
    чехле», строки 269/270): у ОБЕИХ строк количество в файле не задано
    (пустая ячейка — см. `get_cell`/`to_dec` в feo_import_common.py), а
    старый код `r["qty"] if r["qty"] is not None else ONE` подставлял 1 за
    каждую такую строку и показывал в предпросмотре «кол-во 2» и цену
    0,00 ₽/ед. — оба числа выдуманы, реального количества в файле нет.

    Правило теперь: складываются только строки, где количество РЕАЛЬНО
    задано в файле; если ни у одной строки группы количества нет —
    результат None (не 0 и не подстановка единицы). Если известно только у
    части строк — результат частичная сумма (используется вызывающей
    стороной вместе с проверкой «известно ли количество у ВСЕХ строк
    группы», см. `_combine_rows`/`_describe_group`, — цена за единицу при
    частично известном количестве не выводится, чтобы не показать цену,
    посчитанную на угаданном числителе)."""
    known = [r["qty"] for r in rows if r["qty"] is not None]
    if not known:
        return None
    return sum(known, ZERO)


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


def _row_unit_price(r: dict) -> Decimal | None:
    """Цена за единицу ОДНОЙ строки группы — явная `unit_price` строки, если
    задана, иначе `amount/qty` при известном `qty` и `amount`. Используется
    `_merge_totals` ниже, чтобы решить, одинакова ли цена у ВСЕХ строк
    группы — никакого деления Σamount/Σqty на уровне ОДНОЙ строки тут нет."""
    up = r.get("unit_price")
    if up is not None:
        return up
    amt = r.get("amount")
    qty = r.get("qty")
    if amt is not None and qty:
        return (amt / qty).quantize(QUANT)
    return None


def _row_feo_unit_price(r: dict) -> Decimal | None:
    """Сестра `_row_unit_price` для комплекта «по ФЭО» (feo_unit_price/
    feo_amount/feo_qty) — тот же приём, отдельная функция, т.к. поля другие."""
    up = r.get("feo_unit_price")
    if up is not None:
        return up
    amt = r.get("feo_amount")
    qty = r.get("feo_qty")
    if amt is not None and qty:
        return (amt / qty).quantize(QUANT)
    return None


def _common_price(rows: list, price_fn) -> tuple[Decimal | None, bool]:
    """Цена за единицу ОБЪЕДИНЁННОЙ позиции (владелец, 12.10.2026, экран
    дублей загрузки плана ФЭО: «не должно быть так, что цена делится
    равномерно. Это разные закупки» — пример «Gaz A22R35 Х920АЕ 180»: план
    352 400 на ремонт машины складывается из 4 ОТДЕЛЬНЫХ закупок 317 400 /
    20 000 / 10 000 / 5 000 — цена «28 000 за ед.», полученная делением
    352 400/4 (количество «услуг»), ничего не значит и не может быть ценой
    закупки).

    Возвращает (цена, prices_differ): цена — ТОЛЬКО если она известна У
    ВСЕХ строк группы (`price_fn(r)` не None ни у одной) И совпадает
    (±0,01 — округление квантования) у всех строк; иначе None. `prices_differ`
    — True, когда цена известна у всех строк, но они РАЗНЫЕ (используется
    и в тексте предупреждения/экрана дублей, и отличает этот случай от
    случая «цена неизвестна хотя бы у одной строки» — у них разные причины
    для человека)."""
    prices = [price_fn(r) for r in rows]
    if any(p is None for p in prices):
        return None, False
    first = prices[0]
    if all(abs(p - first) <= Decimal("0.01") for p in prices[1:]):
        return first, False
    return None, True


def _merge_totals(rows: list) -> dict:
    """Единственное место вычисления «итогов объединения» группы дублей —
    Правило №6 (раньше `_combine_rows` и `_describe_group` считали одну и ту
    же формулу количества/цены раздельно, каждая своими словами).

    Количество складывается (Σ), ТОЛЬКО если оно задано У ВСЕХ строк группы
    И единица измерения одна и та же у всех строк после нормализации —
    иначе None (нельзя складывать штуки с часами, и нельзя выдавать
    количество, часть которого угадана). Цена за единицу — см. `_common_price`
    (НЕ усредняется делением общей суммы на общее количество — владелец,
    12.10.2026). Сумма (amount) — всегда точная Σ amount всех строк,
    независимо от кол-ва/цены — деньги не зависят от того, разложена ли
    сумма на кол-во/цену."""
    total_amount = sum((r["amount"] or ZERO) for r in rows)
    all_qty_known = all(r["qty"] is not None for r in rows)
    units_normed = {norm(r.get("unit") or "") for r in rows}
    unit_uniform = len(units_normed) == 1
    total_qty = _sum_qty(rows) if (all_qty_known and unit_uniform) else None
    unit = rows[0].get("unit") if (unit_uniform and total_qty is not None) else None
    unit_price, prices_differ = _common_price(rows, _row_unit_price)

    total_feo_amount = sum((r.get("feo_amount") or ZERO) for r in rows)
    total_feo_qty = sum((r.get("feo_qty") or ZERO) for r in rows)
    feo_unit = next((r.get("feo_unit") for r in rows if r.get("feo_unit")), None)
    feo_unit_price, feo_prices_differ = _common_price(rows, _row_feo_unit_price)

    return {
        "qty": total_qty, "unit": unit, "amount": total_amount, "unit_price": unit_price,
        "prices_differ": prices_differ,
        "feo_qty": total_feo_qty or None, "feo_unit": feo_unit,
        "feo_amount": total_feo_amount or None, "feo_unit_price": feo_unit_price,
        "feo_prices_differ": feo_prices_differ,
    }


def _build_parts(rows: list) -> list[dict]:
    """Состав объединённой позиции (владелец, 12.10.2026, план
    merged-item-parts.md) — ОДНА строка файла группы = ОДНА часть
    («Gaz A22R35 Х920АЕ 180»: 317 400 + 20 000 + 10 000 + 5 000 — 4 разные
    закупки внутри одной позиции, а не одна усреднённая цена). key = номер
    строки файла СТРОКОЙ — стабилен между повторными импортами того же файла
    (тот же файл даёт те же номера строк), поэтому привязка закупки к части
    (purchase_items.feo_plan_part_key) переживает повторную загрузку плана.

    JSON-совместимые типы ТОЛЬКО (str/float/int — Decimal роняет транзакцию
    при записи в JSONB, см. ПРАВИЛО проекта): Decimal → float здесь, один раз,
    единственное место сборки parts (Правило №6 — _combine_rows зовёт только
    её, сама не собирает второй вариант)."""
    return [
        {
            "key": str(r["row"]),
            "row": r["row"],
            "qty": _num(r.get("qty")),
            "unit": r.get("unit"),
            "unit_price": _num(_row_unit_price(r)),
            "amount": _num(r.get("amount")),
        }
        for r in rows
    ]


def _combine_rows(rows: list) -> dict:
    """Объединение группы дублей в ОДНУ позицию (владелец, уточнение №2):
    суммы и количества СКЛАДЫВАЮТСЯ — деньги не должны измениться ни на
    рубль. `amount` объединённой позиции — точная сумма amount всех строк
    (без промежуточного округления через цену), поэтому инвариант «сумма не
    изменилась» выполняется тождественно, а не в пределах округления. Цена
    за единицу — см. `_merge_totals`/`_common_price`: НЕ усредняется делением,
    если строки группы — разные закупки с разными ценами (владелец,
    12.10.2026)."""
    totals = _merge_totals(rows)
    merged = dict(rows[-1])  # берём последние флаги/тип как есть — они одинаковы по построению группы
    merged["qty"] = totals["qty"]
    merged["unit"] = totals["unit"]
    merged["amount"] = totals["amount"]
    merged["unit_price"] = totals["unit_price"]
    merged["feo_qty"] = totals["feo_qty"]
    merged["feo_unit"] = totals["feo_unit"]
    merged["feo_unit_price"] = totals["feo_unit_price"]
    merged["feo_amount"] = totals["feo_amount"]
    merged["row"] = rows[-1]["row"]
    merged["_prices_differ"] = totals["prices_differ"]
    merged["parts"] = _build_parts(rows)
    return merged


def _describe_group(key: str, name: str, rows: list) -> dict:
    totals = _merge_totals(rows)
    total_amount = sum((r["amount"] or ZERO) for r in rows)
    total_qty = _sum_qty(rows)
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
            "qty": _num(totals["qty"]),
            "unit": totals["unit"],
            "price": _num(totals["unit_price"]),
            "amount": _num(totals["amount"]),
            # Владелец, 12.10.2026: экран дублей должен различать «цена не
            # задана, т.к. у строк разные цены (это отдельные закупки)» и
            # «цена не задана, т.к. неизвестны количество/цена хотя бы у
            # одной строки» — фронт (DuplicateMergeDialog.vue/FeoImportWizard.vue)
            # показывает разный текст по этому флагу.
            "prices_differ": totals["prices_differ"],
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


async def _upsert_one(state, leaf, item_data: dict, *, extra_reason: str | None, matches: list) -> FeoPlannedItem:
    """Создаёт/обновляет ОДНУ FeoPlannedItem — общий хвост и для обычной
    (не-дублирующейся) позиции, и для объединённой группы. `matches` — уже
    посчитанный список существующих позиций с этим именем в категории
    (`_matching_items`), чтобы при объединении вызывающий код мог сам решить
    судьбу «лишних» существующих позиций (см. `_upsert_merge`).

    Возвращает итоговую FeoPlannedItem (созданную или найденную) — владелец,
    22.09: вызывающий код (feo_import_comments.record_item_id) привязывает
    к ней комментарий строки файла по её реальному id (Правило №6 — второй
    механизм разрешения строка→позиция здесь не заводим)."""
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
        # Владелец, 2026-10-04: «Нужность» (need_level, ревизия
        # p1q3r5s7t9v1) — hasattr-проверка тем же приёмом, что и у
        # item_type/is_feo_breakdown выше (совместимость, пока миграция
        # колонки другого агента не применена).
        if hasattr(FeoPlannedItem, "need_level"):
            _fpi_kwargs["need_level"] = item_data.get("need_level")
        # Состав объединённой позиции (план merged-item-parts.md) — [] у
        # обычной (не объединённой — item_data без "parts") позиции.
        if hasattr(FeoPlannedItem, "parts"):
            _fpi_kwargs["parts"] = item_data.get("parts") or []
        pi = FeoPlannedItem(**_fpi_kwargs)
        db.add(pi)
        await db.flush()
        state.created += 1
        reason = extra_reason or f"плановая позиция ({level_label(5)})"
        state.created_details.append({"row": row_num, "name": name, "reason": reason})
        if state.import_run_id is not None:
            await feo_history.record_created(
                db, feo_history.ENTITY_FEO_ITEM, pi.id, state.user,
                source=feo_history.SOURCE_IMPORT, source_ref=state.import_run_id, commit=False,
            )
        return pi

    _tracked = (
        "quantity", "unit", "amount", "item_type", "is_feo_breakdown", "is_internal_plan",
        "unit_price", "feo_quantity", "feo_unit_price", "feo_amount", "need_level", "parts",
    )
    _old_vals = {f: getattr(existing_item, f, None) for f in _tracked}
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
    if item_data.get("need_level") is not None and hasattr(existing_item, "need_level") and existing_item.need_level != item_data["need_level"]:
        existing_item.need_level = item_data["need_level"]; ch2 = True
    # Состав объединённой позиции (план merged-item-parts.md) — "parts"
    # присутствует в item_data ТОЛЬКО когда ЭТА загрузка объединяет группу
    # (_combine_rows); обычная/разделённая строка её не несёт (item_data.get
    # возвращает None) — старый состав прежней загрузки НЕ затирается пустым
    # списком молча. Повторная загрузка ТОГО ЖЕ файла с тем же «Объединить» —
    # те же key (номера строк) — пересчитанный parts обычно совпадёт с
    # сохранённым и ch2 не взведётся.
    if item_data.get("parts") is not None and hasattr(existing_item, "parts") and (existing_item.parts or []) != item_data["parts"]:
        existing_item.parts = item_data["parts"]; ch2 = True
    if ch2:
        state.updated += 1
        reason = extra_reason or "обновлена позиция — значения перезаписаны из файла"
        state.updated_details.append({"row": row_num, "name": name, "reason": reason})
        if state.import_run_id is not None:
            _new_vals = {f: getattr(existing_item, f, None) for f in _tracked}
            await feo_history.record_updated(
                db, feo_history.ENTITY_FEO_ITEM, existing_item.id, state.user,
                _old_vals, _new_vals,
                source=feo_history.SOURCE_IMPORT, source_ref=state.import_run_id, commit=False,
            )
    else:
        state.skipped += 1
        state.skipped_details.append({"row": row_num, "name": name, "reason": "без изменений"})
    return existing_item


async def _upsert_merge(state, leaf, rows: list, key: str) -> None:
    merged = _combine_rows(rows)
    matches = await _matching_items(state.db, leaf.id, merged["name"])
    _rows_str = format_rows([r["row"] for r in rows])
    if merged["unit_price"] is not None:
        _price_part = "цена за единицу одинакова у всех строк"
    elif merged.get("_prices_differ"):
        _price_part = "цена за единицу не задана — у строк разные цены, это отдельные закупки"
    else:
        _price_part = "цена за единицу не задана"
    _reason = f"объединено из {len(rows)} строк файла ({_rows_str}) — суммы сложены, {_price_part}"
    item = await _upsert_one(state, leaf, merged, extra_reason=_reason, matches=matches)
    # Владелец, 22.09: ВСЕ исходные строки группы указывают на ОДНУ объединённую
    # позицию — комментарий любой из них должен резолвиться к её id.
    for _r in rows:
        record_item_id(state, _r["row"], item.id)
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
            if state.import_run_id is not None:
                await feo_history.record_updated(
                    state.db, feo_history.ENTITY_FEO_ITEM, extra.id, state.user,
                    {"is_active": True}, {"is_active": False},
                    source=feo_history.SOURCE_IMPORT, source_ref=state.import_run_id, commit=False,
                )
    total_before = sum((r["amount"] or ZERO) for r in rows)
    _qty_str = _fmt(merged["qty"]) if merged["qty"] is not None else "не задано"
    if merged["unit_price"] is not None:
        _price_clause = ""
    elif merged.get("_prices_differ"):
        _price_clause = "; цена за единицу не задана — у строк разные цены, это отдельные закупки"
    else:
        _price_clause = "; цена за единицу не задана"
    state.warnings.append({
        "kind": "duplicate_group_merged",
        "row": None,
        "name": merged["name"],
        "message": (
            f"«{merged['name']}» — объединены {len(rows)} строк файла ({_rows_str}): "
            f"количество {_qty_str}, сумма {_fmt(merged['amount'])} "
            f"(было по строкам: {_fmt(total_before)} — сумма не изменилась){_price_clause}"
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
        item = await _upsert_one(state, leaf, row_data, extra_reason=None, matches=m)
        record_item_id(state, row_data["row"], item.id)


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
            item = await _upsert_one(state, leaf, rows[0], extra_reason=None, matches=matches)
            record_item_id(state, rows[0]["row"], item.id)
            continue

        resolution = state.duplicate_resolutions.get(key, "keep")
        group_info = _describe_group(key, name, rows)
        group_info["resolution"] = resolution
        state.duplicate_groups.append(group_info)

        if resolution == "merge":
            await _upsert_merge(state, leaf, rows, key)
        else:
            await _upsert_keep_separate(state, leaf, rows)
