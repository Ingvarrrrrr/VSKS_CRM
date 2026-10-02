"""Корректировка утверждённой субсидии через проверку — HTTP-слой.

Волна 3A (02.10.2026). Вся логика — в app.services.subsidy_revision_ops/
_preview/_apply/_floor/_notify/_pending (ПРАВИЛО №6: роутер только разбирает
запрос/права и форматирует ответ, не считает и не пишет сам). Гейт
direct/revision/forbidden — app.services.subsidy_revision_guard (закоммичено).

Флаг выключен (SUBSIDY_REVISION_ENABLED != '1') — все ручки, кроме GET
/context, отвечают 404 «функция выключена»; /context всегда отдаёт
mode='direct' (не ломает фронт, которому ещё рано знать про корректировки).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func

from app.database import get_db
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key
from app.models.user import User
from app.models.subsidy import Subsidy
from app.models.subsidy_revision import SubsidyRevision, SubsidyRevisionOp
from app.services.subsidy_revision_guard import revision_enabled, subsidy_edit_mode, MODE_REVISION
from app.services import subsidy_revision_ops as ops_svc
from app.services.subsidy_revision_preview import preview as preview_svc
from app.services.subsidy_revision_apply import decide_and_apply
from app.services.subsidy_revision_notify import notify_submitted

router = APIRouter(prefix="/api/subsidy-revisions", tags=["subsidy-revisions"])


async def _ops_count(db: AsyncSession, revision_id: int) -> int:
    """Количество строк корректировки — явный count-запрос, НЕ `revision.ops`
    (ленивая связь ORM роняет AsyncSession вне явного await, см. докстринг
    subsidy_revision_ops.load_ops)."""
    return (await db.execute(
        select(func.count()).select_from(SubsidyRevisionOp).where(SubsidyRevisionOp.revision_id == revision_id)
    )).scalar() or 0


def _feature_gate() -> None:
    if not revision_enabled():
        raise HTTPException(404, "Функция «Корректировка субсидии» выключена")


async def _can_review(db: AsyncSession, user: User, subsidy: Subsidy) -> bool:
    if user.role == "superadmin":
        return True
    return await has_org_key(user, db, subsidy.org_id, "subsidy.edit", subsidy_id=subsidy.id)


async def _load_revision(db: AsyncSession, revision_id: int) -> SubsidyRevision:
    rev = (await db.execute(
        select(SubsidyRevision).where(SubsidyRevision.id == revision_id)
    )).scalar_one_or_none()
    if rev is None:
        raise HTTPException(404, "Корректировка не найдена")
    return rev


async def _require_participant(db: AsyncSession, user: User, revision: SubsidyRevision, subsidy: Subsidy) -> None:
    if user.role == "superadmin" or user.id == revision.author_id:
        return
    if await _can_review(db, user, subsidy):
        return
    raise HTTPException(403, "Нет доступа к этой корректировке")


def _human_path(op: SubsidyRevisionOp, cat_names: dict, item_names: dict) -> str:
    if op.entity_type == ops_svc.ENTITY_SUBSIDY:
        return "Субсидия"
    if op.entity_type == ops_svc.ENTITY_ITEM:
        name = (op.after or {}).get("name") or item_names.get(op.target_id) or op.target_ref or "новая позиция"
        return f"Плановая позиция → {name}"
    name = (op.after or {}).get("name") or cat_names.get(op.target_id) or op.target_ref or "новая статья"
    return f"Статья ФЭО → {name}"


def _op_dict(op: SubsidyRevisionOp, cat_names: dict, item_names: dict, author_name: Optional[str]) -> dict:
    return {
        "id": op.id,
        "seq": op.seq,
        "op_type": op.op_type,
        "entity_type": op.entity_type,
        "target_id": op.target_id,
        "target_ref": op.target_ref,
        "parent_ref": op.parent_ref,
        "depends_on_op_id": op.depends_on_op_id,
        "field_group": op.field_group,
        "before": op.before,
        "after": op.after,
        "reviewer_after": op.reviewer_after,
        "added_by_reviewer": op.added_by_reviewer,
        "bundle_no": op.bundle_no,
        "status": op.status,
        "review_comment": op.review_comment,
        "applied_entity_id": op.applied_entity_id,
        "path": _human_path(op, cat_names, item_names),
        "author_name": author_name,
    }


@router.get("/context")
async def get_context(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """{mode, can_approve, draft, pending_review} — ВСЕГДА отвечает, даже при
    выключенном флаге (mode='direct' тогда)."""
    subsidy = await db.get(Subsidy, subsidy_id)
    if subsidy is None:
        raise HTTPException(404, "Субсидия не найдена")

    mode = await subsidy_edit_mode(db, current_user, subsidy_id)
    can_approve = await _can_review(db, current_user, subsidy) if revision_enabled() else False

    draft = None
    if revision_enabled():
        draft_row = (await db.execute(
            select(SubsidyRevision).where(
                SubsidyRevision.subsidy_id == subsidy_id,
                SubsidyRevision.author_id == current_user.id,
                SubsidyRevision.status.in_(ops_svc.OPEN_STATUSES),
            )
        )).scalar_one_or_none()
        if draft_row is not None:
            ops_count = await _ops_count(db, draft_row.id)
            draft = {
                "id": draft_row.id, "number": draft_row.number, "status": draft_row.status,
                "ops_count": ops_count,
            }

    pending_review = []
    if revision_enabled() and can_approve:
        rows = (await db.execute(
            select(SubsidyRevision).where(
                SubsidyRevision.subsidy_id == subsidy_id,
                SubsidyRevision.status.in_(("submitted", "partially_decided")),
            ).order_by(SubsidyRevision.submitted_at)
        )).scalars().all()
        for r in rows:
            author = await db.get(User, r.author_id) if r.author_id else None
            pending_review.append({
                "id": r.id, "number": r.number, "status": r.status,
                "author_name": (author.full_name or author.username) if author else "—",
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "ops_count": await _ops_count(db, r.id),
            })

    return {"mode": mode, "can_approve": can_approve, "draft": draft, "pending_review": pending_review}


@router.post("/draft")
async def create_draft(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    subsidy_id = body.get("subsidy_id")
    if not subsidy_id:
        raise HTTPException(422, "Обязателен subsidy_id")
    mode = await subsidy_edit_mode(db, current_user, subsidy_id)
    if mode != MODE_REVISION:
        raise HTTPException(
            409,
            detail={
                "code": "revision_not_applicable",
                "message": "Корректировка нужна только для правки утверждённой субсидии без права «Утверждать субсидию»",
            },
        )
    rev = await ops_svc.get_or_create_draft(db, current_user, subsidy_id)
    await db.commit()
    return {"id": rev.id, "number": rev.number, "status": rev.status}


async def _cat_item_names(db: AsyncSession, ops: list[SubsidyRevisionOp]) -> tuple[dict, dict]:
    from app.models.feo_category import FeoCategory
    from app.models.feo_planned_item import FeoPlannedItem
    cat_ids = {o.target_id for o in ops if o.entity_type == ops_svc.ENTITY_CATEGORY and o.target_id}
    item_ids = {o.target_id for o in ops if o.entity_type == ops_svc.ENTITY_ITEM and o.target_id}
    cat_names, item_names = {}, {}
    if cat_ids:
        rows = (await db.execute(select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids)))).all()
        cat_names = {r.id: r.name for r in rows}
    if item_ids:
        rows = (await db.execute(select(FeoPlannedItem.id, FeoPlannedItem.name).where(FeoPlannedItem.id.in_(item_ids)))).all()
        item_names = {r.id: r.name for r in rows}
    return cat_names, item_names


@router.get("/{revision_id}")
async def get_revision(
    revision_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    subsidy = await db.get(Subsidy, revision.subsidy_id)
    await _require_participant(db, current_user, revision, subsidy)

    author = await db.get(User, revision.author_id) if revision.author_id else None
    author_name = (author.full_name or author.username) if author else "—"
    ops = await ops_svc.load_ops(db, revision.id)
    cat_names, item_names = await _cat_item_names(db, ops)

    return {
        "id": revision.id,
        "number": revision.number,
        "subsidy_id": revision.subsidy_id,
        "status": revision.status,
        "author_id": revision.author_id,
        "author_name": author_name,
        "author_comment": revision.author_comment,
        "reviewer_comment": revision.reviewer_comment,
        "submitted_at": revision.submitted_at.isoformat() if revision.submitted_at else None,
        "closed_at": revision.closed_at.isoformat() if revision.closed_at else None,
        "ops": [_op_dict(o, cat_names, item_names, author_name) for o in ops],
    }


@router.post("/{revision_id}/ops")
async def add_op_endpoint(
    revision_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    if revision.author_id != current_user.id:
        raise HTTPException(403, "Добавлять строки может только автор корректировки")
    result = await ops_svc.add_op(db, revision, current_user, body)
    await db.commit()
    if result is None:
        return {"id": None, "message": "Правка совпала с текущим значением — строка не создана"}
    if isinstance(result, list):
        # field_group не был передан, присланные поля легли на НЕСКОЛЬКО групп
        # (см. докстринг ops_svc.add_op) — одна строка на группу, фронт получает
        # список вместо одиночного id.
        for op in result:
            await db.refresh(op)
        rows = [
            {"id": op.id, "target_ref": op.target_ref, "status": op.status, "field_group": op.field_group}
            for op in result
        ]
        return {"id": rows[0]["id"], "target_ref": rows[0]["target_ref"], "status": rows[0]["status"], "ops": rows}
    await db.refresh(result)
    return {"id": result.id, "target_ref": result.target_ref, "status": result.status}


@router.patch("/{revision_id}/ops/{op_id}")
async def patch_op_endpoint(
    revision_id: int,
    op_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    if revision.author_id != current_user.id:
        raise HTTPException(403, "Править строки может только автор корректировки")
    if revision.status != "draft":
        raise HTTPException(409, "Строки правятся только в черновике")
    op = (await db.execute(
        select(SubsidyRevisionOp).where(
            SubsidyRevisionOp.id == op_id, SubsidyRevisionOp.revision_id == revision_id,
        )
    )).scalar_one_or_none()
    if op is None:
        raise HTTPException(404, "Строка не найдена")
    if "bundle_no" in body:
        op.bundle_no = ops_svc.parse_bundle_no(body["bundle_no"])
    if "after" in body:
        allowed = set(ops_svc.FIELD_GROUPS[op.entity_type].get(op.field_group, ())) if op.field_group else None
        new_after = body["after"]
        if allowed is not None:
            bad = set(new_after.keys()) - allowed
            if bad:
                raise HTTPException(422, f"Поля {sorted(bad)} не входят в группу «{op.field_group}»")
        # ТА ЖЕ склейка/no-op-удаление, что у повторного add_op (ПРАВИЛО №6 —
        # не второй алгоритм слияния after для PATCH).
        merged, is_noop = ops_svc.merge_after_fields(op.before or {}, op.after or {}, new_after)
        if is_noop:
            await db.delete(op)
            await db.commit()
            return {"id": None, "message": "Правка совпала с текущим значением — строка удалена"}
        op.after = merged
    await db.commit()
    return {"id": op.id, "status": op.status}


@router.post("/{revision_id}/bundles")
async def set_bundle_endpoint(
    revision_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Назначает выбранным строкам НОВУЮ связку (bundle_no = max+1 по этой
    корректировке) — body = {op_ids: [...], free_money?: bool}. free_money —
    пояснение для UI/лога (строки «высвобождают» деньги, а не перераспределяют
    их на другую строку той же связки); модель bundle_no не хранит это как
    отдельный признак (ПРАВИЛО №6 — bundle_no остаётся единственным, простым
    группирующим числом), поэтому значение только эхом возвращается в ответе.
    Расформировать связку — PATCH /{revision_id}/ops/{op_id} {bundle_no: null}
    на каждую строку (второй способ снять bundle_no здесь не заводим)."""
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    subsidy = await db.get(Subsidy, revision.subsidy_id)
    await _require_participant(db, current_user, revision, subsidy)
    if revision.status not in ("draft", "submitted", "partially_decided"):
        raise HTTPException(409, "Связки можно менять только у открытой корректировки")

    op_ids = body.get("op_ids") or []
    if not isinstance(op_ids, list) or not op_ids:
        raise HTTPException(422, "Нужен хотя бы один op_id в op_ids")
    free_money = bool(body.get("free_money"))

    rows = (await db.execute(
        select(SubsidyRevisionOp).where(
            SubsidyRevisionOp.revision_id == revision_id,
            SubsidyRevisionOp.id.in_(op_ids),
        )
    )).scalars().all()
    found_ids = {o.id for o in rows}
    missing = sorted(set(op_ids) - found_ids)
    if missing:
        raise HTTPException(422, f"Строки {missing} не найдены в этой корректировке")

    max_bundle = (await db.execute(
        select(func.max(SubsidyRevisionOp.bundle_no)).where(SubsidyRevisionOp.revision_id == revision_id)
    )).scalar() or 0
    new_bundle_no = max_bundle + 1
    for o in rows:
        o.bundle_no = new_bundle_no
    await db.commit()
    return {"bundle_no": new_bundle_no, "op_ids": sorted(found_ids), "free_money": free_money}


@router.delete("/{revision_id}/ops/{op_id}")
async def delete_op_endpoint(
    revision_id: int,
    op_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    if revision.author_id != current_user.id:
        raise HTTPException(403, "Удалять строки может только автор корректировки")
    if revision.status != "draft":
        raise HTTPException(409, "Строки удаляются только в черновике")
    op = (await db.execute(
        select(SubsidyRevisionOp).where(
            SubsidyRevisionOp.id == op_id, SubsidyRevisionOp.revision_id == revision_id,
        )
    )).scalar_one_or_none()
    if op is None:
        raise HTTPException(404, "Строка не найдена")
    for dep_id in await ops_svc._collect_dependents(db, revision_id, op.id):
        dep_op = await db.get(SubsidyRevisionOp, dep_id)
        if dep_op is not None:
            await db.delete(dep_op)
    await db.delete(op)
    await db.commit()
    return {"deleted": True}


@router.post("/{revision_id}/submit")
async def submit_revision(
    revision_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone

    _feature_gate()
    revision = await _load_revision(db, revision_id)
    if revision.author_id != current_user.id:
        raise HTTPException(403, "Отправить на проверку может только автор корректировки")
    if revision.status != "draft":
        raise HTTPException(409, "Отправить на проверку можно только черновик")
    if await _ops_count(db, revision.id) == 0:
        raise HTTPException(422, "Корректировка пуста — добавьте хотя бы одну правку")

    # ПРАВИЛО №6 — тот же путь, что и GET-предпросмотр (preview_svc), не вторая
    # копия проверки порога/баланса: раньше здесь звался ops_svc.simulate(),
    # который применяет пачку, но НЕ зовёт check_floor/compute_balance — порог
    # «не ниже законтрактованного» и дефицит субсидии можно было обойти,
    # отправив на проверку то, что /preview уже показал бы как проблему.
    preview_result = await preview_svc(db, revision, include_before=False)
    problems = list(preview_result["problems"])
    if not preview_result["can_apply"] and not problems:
        bal = preview_result["balance"]
        problems.append({
            "op_id": None,
            "code": "balance",
            "message": f"Корректировка превышает доступный остаток субсидии на {bal.get('shortfall', 0):,.2f} ₽",
        })
    if problems:
        raise HTTPException(422, detail={"code": "revision_problems", "problems": problems})

    revision.author_comment = body.get("comment")
    revision.status = "submitted"
    revision.submitted_at = datetime.now(timezone.utc)
    await db.commit()

    await notify_submitted(db, revision)
    return {"id": revision.id, "status": revision.status}


@router.post("/{revision_id}/withdraw")
async def withdraw_revision(
    revision_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    if revision.author_id != current_user.id:
        raise HTTPException(403, "Отозвать может только автор корректировки")
    if revision.status not in ("submitted", "partially_decided"):
        raise HTTPException(409, "Отозвать можно только корректировку на проверке")
    revision.status = "draft"
    revision.submitted_at = None
    await db.commit()
    return {"id": revision.id, "status": revision.status}


@router.post("/{revision_id}/preview")
async def preview_revision(
    revision_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    subsidy = await db.get(Subsidy, revision.subsidy_id)
    await _require_participant(db, current_user, revision, subsidy)

    raw_overrides = body.get("reviewer_overrides") or {}
    reviewer_overrides = {int(k): v for k, v in raw_overrides.items()}

    result = await preview_svc(
        db, revision,
        accepted_op_ids=body.get("accepted_op_ids"),
        reviewer_overrides=reviewer_overrides,
        extra_ops=body.get("extra_ops"),
        include_before=bool(body.get("include_before", True)),
    )
    return result


@router.post("/{revision_id}/apply")
async def apply_revision(
    revision_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_gate()
    revision = await _load_revision(db, revision_id)
    subsidy = await db.get(Subsidy, revision.subsidy_id)
    if not await _can_review(db, current_user, subsidy):
        raise HTTPException(403, "Решать по корректировке может только обладатель права «Утверждать субсидию»")

    # Тело JSON даёт ключи decisions строками — приводим к int (id строки).
    raw_decisions = body.get("decisions") or {}
    decisions = {int(k): v for k, v in raw_decisions.items()}

    result = await decide_and_apply(
        db, revision, current_user,
        decisions=decisions,
        extra_ops=body.get("extra_ops"),
        force=bool(body.get("force")),
    )
    return result
