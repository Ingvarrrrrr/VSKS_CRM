"""Строки корректировки утверждённой субсидии (SubsidyRevisionOp) — сбор
черновика и склейка повторных правок. Применение пачки к БД (apply_ops) —
subsidy_revision_apply.py (Правило №5). Модели — app.models.subsidy_revision
(bfb81880), гейт — app.services.subsidy_revision_guard. ПРАВИЛО №6: запись
только через существующие сервисы (feo_category_write/feo_tree_write/
feo_item_write/subsidy_write), второй create/update/delete здесь не заводится.

ПОЛЯ И ИХ ГРУППЫ (field_group) — одна строка правит РОВНО одну группу полей
одной сущности; повторная правка той же сущности и группы сливается в уже
существующую строку (см. add_op/merge_after_fields). Качественно разные вещи
(деньги по ФЭО / план / описание / положение в дереве) не блокируют и не
склеиваются друг с другом. Сами группы (FIELD_GROUPS/ALL_FIELDS/SERVICE_FIELDS)
и разбор field_group/bundle_no вынесены в subsidy_revision_fields.py (ПРАВИЛО
№5) — реэкспортированы отсюда (см. импорт ниже), поэтому ops_svc.FIELD_GROUPS
и т.п. продолжают работать для существующих вызывающих мест (роутер/apply).
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subsidy_revision import SubsidyRevision, SubsidyRevisionOp
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.subsidy import Subsidy

from app.services.subsidy_revision_fields import (  # noqa: F401 (реэкспорт — ops_svc.FIELD_GROUPS и т.п. читает роутер)
    ENTITY_SUBSIDY, ENTITY_CATEGORY, ENTITY_ITEM, ENTITIES,
    FIELD_GROUPS, ALL_FIELDS, SERVICE_FIELDS,
    field_group_for, split_after_fields, parse_bundle_no,
    assert_entity_in_subsidy,
)

OP_CREATE = "create"
OP_UPDATE = "update"
OP_DELETE = "delete"
OP_MOVE = "move"
OP_TYPES = (OP_CREATE, OP_UPDATE, OP_DELETE, OP_MOVE)

OPEN_STATUSES = ("draft", "submitted", "partially_decided")

MODELS = {ENTITY_SUBSIDY: Subsidy, ENTITY_CATEGORY: FeoCategory, ENTITY_ITEM: FeoPlannedItem}

_REF_PREFIX = {ENTITY_CATEGORY: "c", ENTITY_ITEM: "i", ENTITY_SUBSIDY: "s"}


def _serialize(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


async def _load_live(db: AsyncSession, entity_type: str, target_id: int, fields) -> dict:
    model = MODELS[entity_type]
    obj = await db.get(model, target_id)
    if obj is None:
        raise HTTPException(404, f"Сущность «{entity_type}» №{target_id} не найдена")
    return {f: _serialize(getattr(obj, f, None)) for f in fields}


def _values_equal(a: dict, b: dict) -> bool:
    return all(_serialize(a.get(k)) == _serialize(b.get(k)) for k in set(a) | set(b))


def merge_after_fields(before: dict, current_after: dict, new_after: dict) -> tuple:
    """Сливает new_after в current_after, говорит вернулась ли строка к before
    (no-op). Единственная точка (ПРАВИЛО №6) — зовут и add_op, и PATCH
    /{id}/ops/{op_id}, чтобы не плодить второй алгоритм слияния."""
    merged = dict(current_after or {})
    merged.update(new_after)
    is_noop = bool(before) and _values_equal(before, merged)
    return merged, is_noop


async def get_or_create_draft(db: AsyncSession, user, subsidy_id: int) -> SubsidyRevision:
    """Одна открытая корректировка на (автора, субсидию) — см. частичный
    уникальный индекс модели. Если открытая уже submitted/partially_decided —
    строки добавлять нельзя, надо сперва отозвать."""
    existing = (await db.execute(
        select(SubsidyRevision).where(
            SubsidyRevision.subsidy_id == subsidy_id,
            SubsidyRevision.author_id == user.id,
            SubsidyRevision.status.in_(OPEN_STATUSES),
        )
    )).scalar_one_or_none()
    if existing is not None:
        if existing.status != "draft":
            raise HTTPException(
                409,
                detail={
                    "code": "revision_under_review",
                    "message": "Корректировка на проверке — отзовите её (withdraw), чтобы продолжить правку",
                },
            )
        return existing

    max_number = (await db.execute(
        select(func.max(SubsidyRevision.number)).where(SubsidyRevision.subsidy_id == subsidy_id)
    )).scalar() or 0
    rev = SubsidyRevision(subsidy_id=subsidy_id, number=max_number + 1, author_id=user.id, status="draft")
    db.add(rev)
    await db.flush()
    return rev


async def _next_ref(db: AsyncSession, revision_id: int, entity_type: str) -> str:
    prefix = _REF_PREFIX[entity_type]
    rows = (await db.execute(
        select(SubsidyRevisionOp.target_ref).where(
            SubsidyRevisionOp.revision_id == revision_id,
            SubsidyRevisionOp.target_ref.like(f"{prefix}%"),
        )
    )).scalars().all()
    nums = []
    for r in rows:
        try:
            nums.append(int(r[len(prefix):]))
        except (TypeError, ValueError):
            continue
    return f"{prefix}{(max(nums) + 1) if nums else 1}"


async def load_ops(db: AsyncSession, revision_id: int) -> list[SubsidyRevisionOp]:
    """Строки по seq — ЕДИНСТВЕННЫЙ способ их читать (ПРАВИЛО №6). НЕ через
    ленивую связь `revision.ops` — роняет AsyncSession MissingGreenlet вне
    явного await; модель чужая, её lazy-стратегию не трогаем."""
    return (await db.execute(
        select(SubsidyRevisionOp)
        .where(SubsidyRevisionOp.revision_id == revision_id)
        .order_by(SubsidyRevisionOp.seq)
    )).scalars().all()


async def _next_seq(db: AsyncSession, revision_id: int) -> int:
    max_seq = (await db.execute(
        select(func.max(SubsidyRevisionOp.seq)).where(SubsidyRevisionOp.revision_id == revision_id)
    )).scalar() or 0
    return max_seq + 1


async def _find_create_op_by_ref(db: AsyncSession, revision_id: int, ref: str) -> Optional[SubsidyRevisionOp]:
    return (await db.execute(
        select(SubsidyRevisionOp).where(
            SubsidyRevisionOp.revision_id == revision_id,
            SubsidyRevisionOp.target_ref == ref,
            SubsidyRevisionOp.op_type == OP_CREATE,
        )
    )).scalar_one_or_none()


async def _find_pending_update_op(
    db: AsyncSession, revision_id: int, entity_type: str, target_id: int, field_group: str,
) -> Optional[SubsidyRevisionOp]:
    return (await db.execute(
        select(SubsidyRevisionOp).where(
            SubsidyRevisionOp.revision_id == revision_id,
            SubsidyRevisionOp.entity_type == entity_type,
            SubsidyRevisionOp.target_id == target_id,
            SubsidyRevisionOp.field_group == field_group,
            SubsidyRevisionOp.op_type.in_((OP_UPDATE, OP_MOVE)),
            SubsidyRevisionOp.status == "pending",
        )
    )).scalar_one_or_none()


async def _collect_dependents(db: AsyncSession, revision_id: int, op_id: int) -> list[int]:
    """Id строк, прямо/транзитивно зависящих (depends_on_op_id) от op_id —
    для отклонения (auto_rejected) и удаления создающей строки."""
    all_ops = (await db.execute(
        select(SubsidyRevisionOp.id, SubsidyRevisionOp.depends_on_op_id).where(
            SubsidyRevisionOp.revision_id == revision_id
        )
    )).all()
    children: dict[int, list[int]] = {}
    for oid, dep in all_ops:
        if dep is not None:
            children.setdefault(dep, []).append(oid)
    out: list[int] = []
    frontier = [op_id]
    while frontier:
        cur = frontier.pop()
        for child in children.get(cur, []):
            if child not in out:
                out.append(child)
                frontier.append(child)
    return out


async def add_op(
    db: AsyncSession, revision: SubsidyRevision, user, payload: dict,
    *, added_by_reviewer: bool = False,
) -> "Optional[SubsidyRevisionOp | list[SubsidyRevisionOp]]":
    """Добавляет/сливает одну строку корректировки. payload = {entity_type,
    op_type, target_id?, target_ref?, parent_ref?, field_group?, after: {...},
    bundle_no?}. added_by_reviewer=True — вызов из decide_and_apply (строка
    проверяющего), проверка "только draft" не применяется. Возвращает:
      - None, если правка оказалась no-op (after==before) — ни одной строки
        не создано/изменено;
      - одну SubsidyRevisionOp — обычный случай (ровно одна группа полей);
      - list[SubsidyRevisionOp] — только для update/move БЕЗ явного
        field_group, когда присланные поля after распределились по
        НЕСКОЛЬКИМ группам (см. split_after_fields) — одна строка на группу
        (например amount+feo_amount -> строки 'qty_price' и 'funding').
    """
    if not added_by_reviewer and revision.status != "draft":
        raise HTTPException(
            409,
            detail={
                "code": "revision_not_draft",
                "message": "Корректировка не в черновике — строки можно добавлять только в draft",
            },
        )

    entity_type = payload.get("entity_type")
    op_type = payload.get("op_type")
    if entity_type not in ENTITIES:
        raise HTTPException(422, f"Неизвестный тип сущности: {entity_type}")
    if op_type not in OP_TYPES:
        raise HTTPException(422, f"Неизвестный тип операции: {op_type}")

    after = dict(payload.get("after") or {})
    target_id = payload.get("target_id")
    target_ref = payload.get("target_ref")
    parent_ref = payload.get("parent_ref")
    bundle_no = parse_bundle_no(payload.get("bundle_no"))

    if op_type == OP_CREATE:
        field_group = None
        new_ref = await _next_ref(db, revision.id, entity_type)
        depends_on_op_id = None
        if parent_ref:
            parent_op = await _find_create_op_by_ref(db, revision.id, parent_ref)
            if parent_op is None:
                raise HTTPException(422, f"Родитель «{parent_ref}» не найден среди строк этой корректировки")
            depends_on_op_id = parent_op.id
        else:
            # Родитель — ЖИВАЯ сущность (не строка этой же корректировки):
            # category.parent_id / item.feo_category_id в after — IDOR-гейт
            # (ПРАВИЛО №6, assert_entity_in_subsidy).
            live_parent_id = (
                after.get("parent_id") if entity_type == ENTITY_CATEGORY
                else after.get("feo_category_id") if entity_type == ENTITY_ITEM
                else None
            )
            if live_parent_id is not None:
                await assert_entity_in_subsidy(db, revision.subsidy_id, ENTITY_CATEGORY, live_parent_id)
        op = SubsidyRevisionOp(
            revision_id=revision.id,
            seq=await _next_seq(db, revision.id),
            op_type=OP_CREATE,
            entity_type=entity_type,
            target_ref=new_ref,
            parent_ref=parent_ref,
            depends_on_op_id=depends_on_op_id,
            field_group=field_group,
            before=None,
            after=after,
            bundle_no=bundle_no,
            added_by_reviewer=added_by_reviewer,
            status="pending",
        )
        db.add(op)
        await db.flush()
        return op

    if op_type == OP_DELETE:
        if target_ref and not target_id:
            # Удаление сущности, созданной этой же корректировкой — убираем
            # строку create и всё, что от неё зависело.
            create_op = await _find_create_op_by_ref(db, revision.id, target_ref)
            if create_op is None:
                raise HTTPException(422, f"Сущность «{target_ref}» не найдена среди строк этой корректировки")
            dependents = await _collect_dependents(db, revision.id, create_op.id)
            for dep_id in dependents:
                dep_op = await db.get(SubsidyRevisionOp, dep_id)
                if dep_op is not None:
                    await db.delete(dep_op)
            await db.delete(create_op)
            await db.flush()
            return None
        if target_id is None:
            raise HTTPException(422, "Для удаления обязателен target_id или target_ref")
        await assert_entity_in_subsidy(db, revision.subsidy_id, entity_type, target_id)
        before = await _load_live(db, entity_type, target_id, ALL_FIELDS[entity_type])
        # Законтрактованное НА МОМЕНТ удаления — снимок для subsidy_revision_floor.
        # check_floor (ПРАВИЛО №6, committed_amounts/compute_feo_plan_tree —
        # единственные источники) не может прочитать committed удалённого узла
        # ПОСЛЕ применения ops (строки/категории к тому моменту уже нет в БД),
        # поэтому значение фиксируется здесь, в момент добавления строки.
        if entity_type == ENTITY_ITEM:
            from app.services.committed_amounts import committed_by_planned_item
            c = (await committed_by_planned_item(db, [target_id])).get(target_id) or {}
            before["_committed_amount"] = c.get("amount", 0.0)
            before["_committed_quantity"] = c.get("quantity", 0.0)
        elif entity_type == ENTITY_CATEGORY:
            from app.services.feo_plan_tree import compute_feo_plan_tree
            _tree = await compute_feo_plan_tree(db, [revision.subsidy_id])
            _node = _tree.get(target_id) or {}
            before["_committed"] = _node.get("committed", 0.0)
        op = SubsidyRevisionOp(
            revision_id=revision.id,
            seq=await _next_seq(db, revision.id),
            op_type=OP_DELETE,
            entity_type=entity_type,
            target_id=target_id,
            field_group=None,
            before=before,
            after=None,
            bundle_no=bundle_no,
            added_by_reviewer=added_by_reviewer,
            status="pending",
        )
        db.add(op)
        await db.flush()
        return op

    # update / move — field_group ОПЦИОНАЛЕН (владелец, приёмка 02.10.2026):
    # фронт шлёт только РЕАЛЬНО изменившиеся поля (diff), которые могут
    # относиться сразу к нескольким группам (amount+feo_amount —
    # 'qty_price'+'funding') — раскладываем сами и заводим/сливаем ПО СТРОКЕ
    # НА ГРУППУ, вместо падения на несуществующем ключе FIELD_GROUPS[...][...].
    explicit_group = payload.get("field_group")
    if explicit_group is not None:
        if explicit_group not in FIELD_GROUPS.get(entity_type, {}):
            raise HTTPException(
                422,
                detail={
                    "code": "unknown_field_group",
                    "message": f"Группа «{explicit_group}» не существует для «{entity_type}»",
                },
            )
        allowed = set(FIELD_GROUPS[entity_type][explicit_group])
        service = SERVICE_FIELDS.get(entity_type, frozenset())
        group_after: dict = {}
        dropped: list = []
        bad: list = []
        for f, v in after.items():
            if f in allowed:
                group_after[f] = v
            elif f in service:
                dropped.append(f)
            else:
                bad.append(f)
        if bad:
            raise HTTPException(422, f"Поля {sorted(bad)} не входят в группу «{explicit_group}» сущности «{entity_type}»")
        groups_after = {explicit_group: group_after} if group_after else {}
    else:
        groups_after, dropped = split_after_fields(entity_type, after)

    if not groups_after:
        # После вычета служебных флагов/дроп-полей менять нечего — честный
        # no-op, не пустая строка корректировки.
        return None

    created: list[SubsidyRevisionOp] = []
    for group_name, group_after in groups_after.items():
        op = await _add_single_update_op(
            db, revision, entity_type, group_name, group_after,
            target_id=target_id, target_ref=target_ref, parent_ref=parent_ref,
            bundle_no=bundle_no, added_by_reviewer=added_by_reviewer,
        )
        if op is not None:
            created.append(op)

    if not created:
        return None
    if len(created) == 1:
        return created[0]
    return created


async def _add_single_update_op(
    db: AsyncSession, revision: SubsidyRevision, entity_type: str, field_group: str, after: dict,
    *, target_id, target_ref, parent_ref, bundle_no, added_by_reviewer: bool,
) -> Optional[SubsidyRevisionOp]:
    """Заводит/сливает РОВНО одну строку update/move одной группы полей —
    вынесено из add_op (ПРАВИЛО №5), чтобы при раскладке after на несколько
    групп (см. add_op) один и тот же алгоритм слияния применялся к каждой
    группе по отдельности, без второй копии."""
    if target_ref and not target_id:
        # Правка сущности, созданной этой же корректировкой — вливаем прямо в
        # её строку create (своей строки "before" у неё ещё нет).
        create_op = await _find_create_op_by_ref(db, revision.id, target_ref)
        if create_op is None:
            raise HTTPException(422, f"Сущность «{target_ref}» не найдена среди строк этой корректировки")
        merged_after = dict(create_op.after or {})
        merged_after.update(after)
        create_op.after = merged_after
        if field_group == "structure" and parent_ref:
            create_op.parent_ref = parent_ref
            parent_op = await _find_create_op_by_ref(db, revision.id, parent_ref)
            if parent_op is not None:
                create_op.depends_on_op_id = parent_op.id
        await db.flush()
        return create_op

    if target_id is None:
        raise HTTPException(422, "Для правки обязателен target_id или target_ref")

    await assert_entity_in_subsidy(db, revision.subsidy_id, entity_type, target_id)
    if field_group == "structure" and not parent_ref:
        # move на ЖИВОГО нового родителя (не строку этой же корректировки) —
        # новый parent_id/feo_category_id идёт напрямую в after.
        new_live_parent_id = (
            after.get("parent_id") if entity_type == ENTITY_CATEGORY
            else after.get("feo_category_id") if entity_type == ENTITY_ITEM
            else None
        )
        if new_live_parent_id is not None:
            await assert_entity_in_subsidy(db, revision.subsidy_id, ENTITY_CATEGORY, new_live_parent_id)

    existing_op = await _find_pending_update_op(db, revision.id, entity_type, target_id, field_group)
    existing_before = dict(existing_op.before or {}) if existing_op is not None else {}
    existing_after = dict(existing_op.after or {}) if existing_op is not None else {}

    # Приёмка 02.10.2026, п.1 (паразитная строка 'meta' на каждую правку
    # суммы): раньше before грузился ЦЕЛИКОМ по всей группе (`allowed`), а
    # after нёс только реально присланные поля — разница всплывала как
    # "Наименование: X → —" и т.п. для полей, которые никто не трогал. Теперь
    # живой снимок берём ТОЛЬКО под поля, которых ещё нет в уже накопленном
    # before строки (existing_before — исходная база, не трогаем повторно),
    # и в саму строку кладём ТОЛЬКО поля, чьё значение в after реально
    # отличается от живого — остальные молча отбрасываются (не часть правки).
    new_fields = set(after) - set(existing_before)
    live_extra = await _load_live(db, entity_type, target_id, new_fields) if new_fields else {}
    baseline = {**existing_before, **live_extra}

    merged_after_raw = dict(existing_after)
    merged_after_raw.update(after)

    filtered_after = {
        k: v for k, v in merged_after_raw.items()
        if _serialize(v) != _serialize(baseline.get(k))
    }

    if not filtered_after:
        # Ни одно поле группы реально не отличается от живого значения —
        # честный no-op, строка не нужна (или уже не нужна, если была).
        if existing_op is not None:
            await db.delete(existing_op)
            await db.flush()
        return None

    filtered_before = {k: baseline[k] for k in filtered_after}

    if existing_op is not None:
        existing_op.before = filtered_before
        existing_op.after = filtered_after
        if field_group == "structure" and parent_ref:
            existing_op.parent_ref = parent_ref
        if bundle_no is not None:
            existing_op.bundle_no = bundle_no
        await db.flush()
        return existing_op

    op = SubsidyRevisionOp(
        revision_id=revision.id,
        seq=await _next_seq(db, revision.id),
        op_type=OP_MOVE if field_group == "structure" else OP_UPDATE,
        entity_type=entity_type,
        target_id=target_id,
        parent_ref=parent_ref if field_group == "structure" else None,
        field_group=field_group,
        before=filtered_before,
        after=filtered_after,
        bundle_no=bundle_no,
        added_by_reviewer=added_by_reviewer,
        status="pending",
    )
    db.add(op)
    await db.flush()
    return op


# ── Применение набора строк к БД (общий код для preview/apply) — simulate()/
# revision_author_for()/_effective_after()/_op_attr() живут в
# subsidy_revision_sim.py (ПРАВИЛО №5), реэкспортированы отсюда, чтобы
# ops_svc.simulate и т.п. продолжали работать для существующих вызывающих
# мест/тестов. ──────────────────────────────────────────────────────────────
from app.services.subsidy_revision_sim import (  # noqa: F401,E402
    simulate, revision_author_for, _effective_after, _op_attr,
)
