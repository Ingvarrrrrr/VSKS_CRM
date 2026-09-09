"""Этап 4 импорта ФЭО: собранный план строки → FeoPlannedItem + проверка
родитель/сумма детей.

Перенесено из тела `_do_feo_import` (было ~строки 894–1066 в
app/services/feo_import_engine.py до разрезания на этапы, Правило №5) без
изменения логики и порядка side-effect'ов (flush в том же месте цикла).

Делается ПОСЛЕ основного цикла по строкам (feo_import_apply.py), потому что
только тогда окончательно видно: у категории есть подкатегории (группа) или
нет (лист), и получила ли она в этом же импорте отдельные позиции Ур.5.
"""
from decimal import Decimal

from sqlalchemy import select

from app.models.feo_category import FeoCategory
from app.services.feo_import_common import ZERO, level_label, fmt as _fmt


async def apply_collected_plan(state) -> None:
    db = state.db
    cat_cache = state.cat_cache
    collected_plan = state.collected_plan
    lvl5_leaves = state.lvl5_leaves
    lvl5_sum_by_cat = state.lvl5_sum_by_cat
    touched_parents = state.touched_parents
    warnings = state.warnings
    created_details = state.created_details
    updated_details = state.updated_details
    created = state.created
    updated = state.updated

    # Собираем актуальные объекты категорий по id через cat_cache (все объекты
    # уже в сессии) — нужно и для обработки collected_plan ниже, и для проверки
    # "родитель vs сумма детей" после неё.
    cat_by_db_id: dict[int, FeoCategory] = {c.id: c for c in cat_cache.values() if c.id is not None}

    # --- Обработка collected_plan: план строки → FeoPlannedItem внутри
    # категории, а не поля категории (см. комментарий у объявления collected_plan
    # выше цикла по строкам). Делается ЗДЕСЬ, после цикла по всем строкам файла,
    # потому что только сейчас окончательно видно: у категории есть подкатегории
    # (группа) или нет (лист), и получила ли она в этом же импорте отдельные
    # позиции Ур.5.
    if collected_plan:
        from app.models.feo_planned_item import FeoPlannedItem

        _plan_ids = list(collected_plan.keys())
        # Кто из собранных категорий — родитель (группа): есть хотя бы один
        # ребёнок — существующий или только что созданный в этом же импорте
        # (find_or_create уже сделал flush, поэтому дети видны через запрос).
        _parent_rows = (await db.execute(
            select(FeoCategory.parent_id).where(FeoCategory.parent_id.in_(_plan_ids))
        )).scalars().all()
        _groups_with_plan = {pid for pid in _parent_rows if pid is not None}

        for _cat_id, _pdata in collected_plan.items():
            _cat_obj = cat_by_db_id.get(_cat_id)
            if _cat_obj is None:
                continue
            _plan_name = _pdata["name"]
            _plan_row = _pdata["row"]

            if _cat_id in _groups_with_plan:
                # Категория-ГРУППА: собственный план группы в compute_feo_plan_tree
                # (app/services/feo_plan.py) вообще не участвует в расчёте — план
                # группы считается только по сумме подкатегорий. Оставлять здесь
                # значения — мёртвые данные, которые незаметно всплывают и ломают
                # числа, если подкатегория потом пропадёт из файла (боевой случай:
                # категория «Микроавтобус (автобус)» после исчезновения подкатегории
                # (DONGFENG) JUNFENG K33 внезапно показала цену 10 130 000 за штуку
                # и превышение на «Транспорт и техника»).
                if _cat_obj.planned_quantity is not None:
                    _cat_obj.planned_quantity = None
                if _cat_obj.planned_amount is not None:
                    _cat_obj.planned_amount = None
                warnings.append({
                    "kind": "group_plan_ignored",
                    "row": _plan_row,
                    "name": _plan_name,
                    "message": f"План строки «{_plan_name}» не записан: у категории есть подкатегории, план группы считается по ним",
                })
                continue

            if _cat_id in lvl5_leaves:
                # Лист уже описан отдельными позициями Ур.5 в этом же импорте —
                # план строки дублировал бы их сумму, отдельную позицию с именем
                # самой категории не создаём.
                if _cat_obj.planned_quantity is not None:
                    _cat_obj.planned_quantity = None
                if _cat_obj.planned_amount is not None:
                    _cat_obj.planned_amount = None
                _items_sum = lvl5_sum_by_cat.get(_cat_id, ZERO)
                if abs(_items_sum - (_pdata["amount"] or ZERO)) > Decimal("0.01"):
                    # Честное указание источника (задача владельца): если этот план
                    # строки на самом деле собран старым фолбэком из чисел «по ФЭО»
                    # (см. from_feo_fallback выше — плановых кол-ва/цены в файле не
                    # было), пользователь не должен думать, что цифра пришла из
                    # плановых колонок — уточняем происхождение прямо в тексте.
                    _fallback_note = (
                        " (взят из чисел по ФЭО, плановые колонки пустые)"
                        if _pdata.get("from_feo_fallback") else ""
                    )
                    warnings.append({
                        "kind": "plan_vs_items_mismatch",
                        "row": _plan_row,
                        "name": _plan_name,
                        "message": (
                            f"План строки «{_plan_name}» = {_fmt(_pdata['amount'])}{_fallback_note}, а сумма строк "
                            f"«{level_label(5)}» = {_fmt(_items_sum)} — расхождение, план строки не записан"
                        ),
                    })
                continue

            # ЛИСТ без своих позиций Ур.5 в этом импорте — план строки описывает
            # саму категорию; реализуем плановой позицией с именем категории.
            # Ищем существующую активную позицию по точному совпадению имени
            # (TRIM+LOWER) — повторная загрузка того же файла обязана найти и
            # обновить именно её, а не плодить дубли.
            _name_norm = (_plan_name or "").strip().lower()
            _existing_items = (await db.execute(
                select(FeoPlannedItem).where(
                    FeoPlannedItem.feo_category_id == _cat_id,
                    FeoPlannedItem.is_active == True,  # noqa: E712
                )
            )).scalars().all()
            _match_item = next(
                (it for it in _existing_items if (it.name or "").strip().lower() == _name_norm),
                None,
            )
            if _match_item is not None:
                _ch = False
                if _pdata["qty"] is not None and _match_item.quantity != _pdata["qty"]:
                    _match_item.quantity = _pdata["qty"]; _ch = True
                if _pdata["unit"] is not None and _match_item.unit != _pdata["unit"]:
                    _match_item.unit = _pdata["unit"]; _ch = True
                if _pdata["amount"] is not None and _match_item.amount != _pdata["amount"]:
                    _match_item.amount = _pdata["amount"]; _ch = True
                if _pdata.get("item_type") is not None and hasattr(_match_item, "item_type") and _match_item.item_type != _pdata["item_type"]:
                    _match_item.item_type = _pdata["item_type"]; _ch = True
                if _ch:
                    updated += 1
                    updated_details.append({"row": _plan_row, "name": _plan_name, "reason": "плановая позиция из плана строки"})
            else:
                _other_active = [it for it in _existing_items if (it.amount or ZERO) != ZERO]
                if _other_active:
                    # У категории уже есть свои плановые позиции — не задваиваем.
                    warnings.append({
                        "kind": "plan_skipped_has_items",
                        "row": _plan_row,
                        "name": _plan_name,
                        "message": f"У категории «{_plan_name}» уже есть плановые позиции — план строки не записан, чтобы не задвоить",
                    })
                else:
                    _pi_kwargs = dict(
                        feo_category_id=_cat_id,
                        name=(_plan_name or "")[:500],
                        quantity=_pdata["qty"],
                        unit=_pdata["unit"],
                        amount=_pdata["amount"],
                        is_active=True,
                        notes="из импорта ФЭО",
                    )
                    if hasattr(FeoPlannedItem, "item_type"):
                        _pi_kwargs["item_type"] = _pdata.get("item_type")
                    # Происхождение (владелец, 2026-09-01): эта ветка — колонка
                    # «Плановая» на категории целиком, БЕЗ построчной разбивки ФЭО
                    # (см. докстринг миграции aa1b2c3d4e5f_feo_planned_item_origin.py) —
                    # is_internal_plan, не is_feo_breakdown.
                    if hasattr(FeoPlannedItem, "is_internal_plan"):
                        _pi_kwargs["is_internal_plan"] = True
                    _pi = FeoPlannedItem(**_pi_kwargs)
                    db.add(_pi)
                    await db.flush()
                    created += 1
                    created_details.append({"row": _plan_row, "name": _plan_name, "reason": "плановая позиция из плана строки"})

            if _cat_obj.planned_quantity is not None:
                _cat_obj.planned_quantity = None
            if _cat_obj.planned_amount is not None:
                _cat_obj.planned_amount = None

    # Проверка родитель vs сумма ВСЕХ дочерних узлов (до commit)
    for parent_id in touched_parents:
        if parent_id not in cat_by_db_id:
            continue
        parent_cat = cat_by_db_id[parent_id]
        parent_budget = parent_cat.budget or ZERO
        if not parent_budget:
            continue
        # Сумма budget всех прямых детей из cat_cache (весь справочник)
        children_sum = sum(
            (c.budget or ZERO)
            for c in cat_cache.values()
            if c.parent_id == parent_id and c.id is not None
        )
        if abs(parent_budget - children_sum) > Decimal("0.01"):
            warnings.append({
                "kind": "parent_sum_mismatch",
                "row": None,
                "name": parent_cat.name,
                "message": (
                    f"Родитель «{parent_cat.name}»: бюджет {_fmt(parent_budget)} ≠ "
                    f"сумма всех дочерних узлов {_fmt(children_sum)}; победит значение родителя"
                ),
            })

    state.created, state.updated = created, updated
