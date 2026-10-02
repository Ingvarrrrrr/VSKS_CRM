"""Применение решения проверяющего по корректировке (POST /{id}/apply).

ПРАВИЛО №6: ни запись, ни расчёт порога/баланса здесь не дублируются —
apply_ops (subsidy_revision_ops.py) и check_floor/compute_balance
(subsidy_revision_floor.py) делают всю работу, здесь — только транзакционная
оркестровка (блокировка строки, разбор зависимостей отклонённых строк,
статусы, ОДНА версия дерева плана, уведомление автора).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy_revision import SubsidyRevision, SubsidyRevisionOp
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy import Subsidy
from app.services.subsidy_revision_ops import (
    add_op, load_ops, _collect_dependents, _values_equal, _op_attr, _effective_after,
    ALL_FIELDS, _load_live, ENTITY_CATEGORY, ENTITY_ITEM, ENTITY_SUBSIDY, OP_CREATE, OP_DELETE, OP_MOVE,
    assert_entity_in_subsidy,
)
from app.services.subsidy_revision_floor import check_floor, compute_balance


async def _lock_revision(db: AsyncSession, revision_id: int) -> SubsidyRevision:
    rev = (await db.execute(
        select(SubsidyRevision).where(SubsidyRevision.id == revision_id).with_for_update()
    )).scalar_one_or_none()
    if rev is None:
        raise HTTPException(404, "Корректировка не найдена")
    return rev


def _op_key(op, idx: int):
    if isinstance(op, SubsidyRevisionOp):
        return op.id
    return op.get("_key", f"extra{idx}")


async def apply_ops(
    db: AsyncSession, user, subsidy_id: int, ops: list,
    *, reviewer_overrides: Optional[dict] = None, source_ref: Optional[int] = None,
    create_version: bool = False, reason: Optional[str] = None,
) -> dict:
    """Применяет СПИСОК операций (persisted SubsidyRevisionOp ИЛИ transient
    dict того же формата, для /preview с ещё не сохранёнными extra_ops) к БД
    ЧЕРЕЗ существующие сервисы записи (ПРАВИЛО №6: feo_category_write/
    feo_tree_write/feo_item_write/subsidy_write — второй раз create/update/
    delete здесь НЕ пишутся). Не коммитит — вызывающий код (preview —
    SAVEPOINT+rollback через subsidy_revision_ops.simulate, apply — настоящий
    commit в decide_and_apply) решает сам.

    Возвращает {"ref_map": {ref: id}, "applied": {op_key: entity_id},
    "problems": [{"op_id", "code", "message"}]}.
    """
    from app.services import feo_category_write as fcw
    from app.services import feo_tree_write as ftw
    from app.services import feo_item_write as fiw
    from app.services import subsidy_write as sw
    from app.schemas.subsidies import FeoCategoryCreate
    from app.schemas.feo import FeoPlannedItemCreate

    def _serialize(v):
        from decimal import Decimal
        from datetime import date
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, date):
            return v.isoformat()
        return v

    reviewer_overrides = reviewer_overrides or {}
    ref_map: dict[str, int] = {}
    applied: dict = {}
    problems: list[dict] = []

    for idx, op in enumerate(ops):
        entity_type = _op_attr(op, "entity_type")
        op_type = _op_attr(op, "op_type")
        target_id = _op_attr(op, "target_id")
        target_ref = _op_attr(op, "target_ref")
        parent_ref = _op_attr(op, "parent_ref")
        after = _effective_after(op, reviewer_overrides)
        key = _op_key(op, idx)

        try:
            # IDOR-гейт (ПРАВИЛО №6) — повторная проверка перед записью: строки
            # автора и extra_ops проверяющего могли сослаться на target_id из
            # ЧУЖОЙ субсидии (add_op/_add_single_update_op уже проверяли это
            # при добавлении строки, но между добавлением и apply сущность
            # могли перенести в другую субсидию).
            await assert_entity_in_subsidy(db, subsidy_id, entity_type, target_id)

            if entity_type == ENTITY_CATEGORY:
                if op_type == OP_CREATE:
                    parent_id = after.get("parent_id")
                    if parent_ref:
                        if parent_ref not in ref_map:
                            raise HTTPException(422, f"Родительская категория «{parent_ref}» ещё не создана")
                        parent_id = ref_map[parent_ref]
                    elif parent_id is not None:
                        await assert_entity_in_subsidy(db, subsidy_id, ENTITY_CATEGORY, parent_id)
                    # Только РЕАЛЬНО переданные поля — непереданные остаются на
                    # дефолтах схемы (is_active: bool = True и т.п.); передать
                    # None туда, где схема не допускает Optional, уронило бы
                    # валидацию.
                    cat_payload = {
                        f: after[f] for f in ALL_FIELDS[ENTITY_CATEGORY] if f != "parent_id" and f in after
                    }
                    cat_payload["parent_id"] = parent_id
                    cat_payload["subsidy_id"] = subsidy_id
                    cat_payload["name"] = after.get("name") or "Без названия"
                    cat_payload["plan_source"] = cat_payload.get("plan_source") or "planned_items"
                    data = FeoCategoryCreate(**cat_payload)
                    cat = await fcw.create_category(db, user, data, source="revision", source_ref=source_ref)
                    entity_id = cat.id
                else:
                    real_id = target_id if target_id is not None else ref_map.get(target_ref)
                    if real_id is None:
                        raise HTTPException(422, f"Категория «{target_ref}» не найдена к моменту применения")
                    cat = await db.get(FeoCategory, real_id)
                    if cat is None:
                        raise HTTPException(404, f"Категория №{real_id} не найдена")
                    if op_type == OP_DELETE:
                        await fcw.delete_category(db, user, cat, source="revision", source_ref=source_ref)
                        entity_id = real_id
                    elif op_type == OP_MOVE or (set(after.keys()) == {"parent_id"}):
                        new_parent_id = after.get("parent_id")
                        if parent_ref:
                            new_parent_id = ref_map.get(parent_ref, new_parent_id)
                        elif new_parent_id is not None:
                            await assert_entity_in_subsidy(db, subsidy_id, ENTITY_CATEGORY, new_parent_id)
                        await ftw.move_category(
                            db, user, cat, new_parent_id, source="revision", source_ref=source_ref,
                        )
                        entity_id = real_id
                    else:
                        merged = {f: _serialize(getattr(cat, f)) for f in ALL_FIELDS[ENTITY_CATEGORY] if f != "parent_id"}
                        merged.update({k: v for k, v in after.items() if k != "parent_id"})
                        merged["subsidy_id"] = cat.subsidy_id
                        merged["parent_id"] = cat.parent_id
                        data = FeoCategoryCreate(**merged)
                        await fcw.update_category(
                            db, user, cat, data, source="revision", source_ref=source_ref,
                            create_version=create_version,
                        )
                        entity_id = cat.id

            elif entity_type == ENTITY_ITEM:
                if op_type == OP_CREATE:
                    feo_category_id = after.get("feo_category_id")
                    if parent_ref:
                        if parent_ref not in ref_map:
                            raise HTTPException(422, f"Категория «{parent_ref}» ещё не создана")
                        feo_category_id = ref_map[parent_ref]
                    elif feo_category_id is not None:
                        await assert_entity_in_subsidy(db, subsidy_id, ENTITY_CATEGORY, feo_category_id)
                    if feo_category_id is None:
                        raise HTTPException(422, "Не задана категория ФЭО для новой плановой позиции")
                    cat = await db.get(FeoCategory, feo_category_id)
                    if cat is None:
                        raise HTTPException(404, "Категория ФЭО не найдена")
                    item_payload = {
                        f: after[f] for f in ALL_FIELDS[ENTITY_ITEM] if f != "feo_category_id" and f in after
                    }
                    item_payload["feo_category_id"] = feo_category_id
                    item_payload["name"] = after.get("name") or "Без названия"
                    item_payload["payment_mode"] = item_payload.get("payment_mode") or "one_time"
                    item_payload["allow_duplicate_name"] = True
                    data = FeoPlannedItemCreate(**item_payload)
                    item = await fiw.create_planned_item(
                        db, user, cat, data, sync_catalog=False, source="revision",
                        source_ref=source_ref, create_version=create_version,
                    )
                    entity_id = item.id
                else:
                    real_id = target_id if target_id is not None else ref_map.get(target_ref)
                    if real_id is None:
                        raise HTTPException(422, f"Плановая позиция «{target_ref}» не найдена к моменту применения")
                    item = await db.get(FeoPlannedItem, real_id)
                    if item is None:
                        raise HTTPException(404, f"Плановая позиция №{real_id} не найдена")
                    if op_type == OP_DELETE:
                        cat = await db.get(FeoCategory, item.feo_category_id)
                        await fiw.delete_planned_item(
                            db, user, item, cat, source="revision", source_ref=source_ref,
                            create_version=create_version,
                        )
                        entity_id = real_id
                    else:
                        merged = {f: _serialize(getattr(item, f)) for f in ALL_FIELDS[ENTITY_ITEM] if f != "feo_category_id"}
                        merged.update({k: v for k, v in after.items() if k != "feo_category_id"})
                        new_cat_id = after.get("feo_category_id")
                        if parent_ref:
                            new_cat_id = ref_map.get(parent_ref, new_cat_id)
                        elif new_cat_id is not None:
                            await assert_entity_in_subsidy(db, subsidy_id, ENTITY_CATEGORY, new_cat_id)
                        merged["feo_category_id"] = new_cat_id if new_cat_id is not None else item.feo_category_id
                        data = FeoPlannedItemCreate(**merged)
                        await fiw.update_planned_item(
                            db, user, item, data, sync_catalog=False, source="revision",
                            source_ref=source_ref, create_version=create_version,
                        )
                        entity_id = item.id

            elif entity_type == ENTITY_SUBSIDY:
                real_id = target_id or subsidy_id
                sub = await db.get(Subsidy, real_id)
                if sub is None:
                    raise HTTPException(404, "Субсидия не найдена")
                await sw.apply_subsidy_update(db, user, sub, dict(after), reason=reason)
                entity_id = sub.id

            else:
                raise HTTPException(422, f"Неизвестный тип сущности: {entity_type}")

            applied[key] = entity_id
            if target_ref and entity_id is not None:
                ref_map[target_ref] = entity_id
            await db.flush()
        except HTTPException as e:
            detail = e.detail
            message = detail.get("message") if isinstance(detail, dict) else str(detail)
            code = detail.get("code") if isinstance(detail, dict) else "apply_error"
            problems.append({"op_id": key, "code": code or "apply_error", "message": message})

    return {"ref_map": ref_map, "applied": applied, "problems": problems}


async def decide_and_apply(
    db: AsyncSession, revision: SubsidyRevision, reviewer,
    decisions: dict, extra_ops: Optional[list] = None, force: bool = False,
) -> dict:
    """decisions = {op_id: {"decision": "accept"|"reject", "comment": str?,
    "reviewer_after": dict?}}. extra_ops — строки, которых не было у автора,
    добавленные самим проверяющим при разборе (payload того же формата, что и
    add_op), сохраняются в корректировку (added_by_reviewer=True).

    Возвращает {"revision_status", "applied": {...}, "rejected": [...],
    "auto_rejected": [...], "balance": {...}}.
    """
    extra_ops = extra_ops or []
    revision = await _lock_revision(db, revision.id)
    if revision.status not in ("submitted", "partially_decided"):
        raise HTTPException(
            409,
            detail={
                "code": "revision_not_submitted",
                "message": "Решать можно только корректировку на проверке (submitted/partially_decided)",
            },
        )

    all_ops: dict[int, SubsidyRevisionOp] = {o.id: o for o in await load_ops(db, revision.id)}

    # 1) Сохраняем строки проверяющего (added_by_reviewer=True) — через тот же
    #    add_op, что и у автора (ПРАВИЛО №6: один способ собрать строку).
    for payload in extra_ops:
        op_result = await add_op(db, revision, reviewer, payload, added_by_reviewer=True)
        # add_op может вернуть НЕСКОЛЬКО строк (update/move без field_group,
        # после разложен на несколько групп — см. докстринг add_op) — решение
        # проверяющего "accept" ставится на каждую.
        for op in ([op_result] if op_result is not None and not isinstance(op_result, list) else (op_result or [])):
            all_ops[op.id] = op
            decisions.setdefault(op.id, {"decision": "accept"})

    pending_ops = [o for o in all_ops.values() if o.status == "pending"]

    # 2) Расхождение before/live — 409 'stale', если не force.
    if not force:
        stale: list[dict] = []
        for op in pending_ops:
            if op.target_id is None or not op.before:
                continue
            # Ключи "_committed*" — служебный снимок для subsidy_revision_floor
            # (см. add_op), не реальные поля сущности — сверке живых значений
            # не подлежат (их и нет на ORM-объекте).
            compare_fields = [f for f in op.before.keys() if not f.startswith("_")]
            if not compare_fields:
                continue
            live = await _load_live(db, op.entity_type, op.target_id, compare_fields)
            before_compare = {f: op.before.get(f) for f in compare_fields}
            if not _values_equal(before_compare, live):
                stale.append({"op_id": op.id, "before": before_compare, "live": live})
        if stale:
            raise HTTPException(409, detail={"code": "stale", "ops": stale})

    # 3) Разбор решений + каскад auto_rejected для зависимых от отклонённых.
    auto_rejected_ids: set[int] = set()
    rejected_ids: list[int] = []
    accepted_ids: list[int] = []

    for op in pending_ops:
        decision = decisions.get(op.id)
        if decision is None:
            continue  # отложено на следующий проход (partially_decided)
        if decision.get("decision") == "reject":
            op.status = "rejected"
            op.review_comment = decision.get("comment")
            rejected_ids.append(op.id)
            for dep_id in await _collect_dependents(db, revision.id, op.id):
                dep_op = all_ops.get(dep_id) or await db.get(SubsidyRevisionOp, dep_id)
                if dep_op is not None and dep_op.status == "pending":
                    dep_op.status = "auto_rejected"
                    dep_op.review_comment = f"Зависела от строки №{op.id} (отклонена)"
                    auto_rejected_ids.add(dep_op.id)
        elif decision.get("decision") == "accept":
            reviewer_after = decision.get("reviewer_after")
            if reviewer_after:
                op.reviewer_after = reviewer_after
            accepted_ids.append(op.id)
        else:
            raise HTTPException(422, f"Неизвестное решение для строки №{op.id}: {decision.get('decision')}")

    # Принять дочернюю без принятого/применённого родителя — 422 (нельзя
    # применить create-позиции внутри ещё не применённой create-категории).
    for op_id in accepted_ids:
        op = all_ops[op_id]
        if op.depends_on_op_id is not None:
            parent = all_ops.get(op.depends_on_op_id) or await db.get(SubsidyRevisionOp, op.depends_on_op_id)
            if parent is not None and parent.status not in ("accepted", "applied") and parent.id not in accepted_ids:
                raise HTTPException(
                    422,
                    f"Нельзя принять строку №{op.id} без родителя №{parent.id} "
                    "(создание категории/позиции, от которой она зависит)",
                )

    accepted_ops = [all_ops[i] for i in accepted_ids]

    # 4) Применение принятых строк + ранее applied строк прошлых проходов
    #    остаются применёнными (не трогаем). ОДИН источник записи — apply_ops.
    from app.services.feo_plan_tree import compute_feo_plan_tree
    tree_before = await compute_feo_plan_tree(db, [revision.subsidy_id])

    result = await apply_ops(
        db, reviewer, revision.subsidy_id, accepted_ops,
        source_ref=revision.id, create_version=False,
        reason=f"Корректировка №{revision.number}",
    )

    if result["problems"]:
        raise HTTPException(409, detail={"code": "apply_error", "problems": result["problems"]})

    tree_after = await compute_feo_plan_tree(db, [revision.subsidy_id])
    floor_problems = await check_floor(db, revision.subsidy_id, accepted_ops, tree_after)
    if floor_problems:
        raise HTTPException(409, detail={"code": "below_committed", "problems": floor_problems})
    balance = await compute_balance(db, revision.subsidy_id, accepted_ops, tree_before, tree_after)
    if not balance["can_apply"]:
        raise HTTPException(409, detail={"code": "balance", "balance": balance})

    for op in accepted_ops:
        op.status = "applied"
        applied_id = result["applied"].get(op.id)
        if applied_id is not None:
            op.applied_entity_id = applied_id

    # 5) Снапшот версии плана — ОДИН на весь пакет (create_version=False во
    #    всех write-сервисах выше, снапшот берётся тут одним вызовом).
    if accepted_ops:
        from app.routers.purchases import _create_plan_graph_version
        await _create_plan_graph_version(
            subsidy_id=revision.subsidy_id, db=db, user=reviewer,
            note=f"Корректировка №{revision.number}",
        )

    # 6) Бюджет субсидии — BudgetHistory уже пишет subsidy_write.apply_subsidy_update
    #    внутри apply_ops (reason передан выше), второй записи не нужно.

    # 7) Статус корректировки.
    remaining = [o for o in all_ops.values() if o.status == "pending"]
    revision.status = "partially_decided" if remaining else "closed"
    if not remaining:
        revision.closed_at = datetime.now(timezone.utc)
    revision.decided_by_id = reviewer.id

    await db.commit()

    try:
        from app.services.subsidy_revision_notify import notify_revision_decided
        await notify_revision_decided(db, revision)
    except Exception:
        pass

    return {
        "revision_status": revision.status,
        "applied": [o.id for o in accepted_ops],
        "rejected": rejected_ids,
        "auto_rejected": sorted(auto_rejected_ids),
        "balance": balance,
    }
