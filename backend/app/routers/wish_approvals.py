"""Wish approvers router — многоуровневое согласование заявок с авто-каскадом.

Endpoints:
  GET    /api/wishes/{wid}/approvers                        — список согласующих
  POST   /api/wishes/{wid}/approvers/cascade                — построить восходящую цепочку
  POST   /api/wishes/{wid}/approvers                        — добавить согласующего вручную
  DELETE /api/wishes/{wid}/approvers/{approval_id}          — удалить согласующего (pending)
  POST   /api/wishes/{wid}/approvers/{approval_id}/decide   — согласовать/отклонить
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user, get_org_filter, MANAGER_ROLES, OWNER_ROLES
from app.auth.permissions import has_org_key
from app.models.user import User
from app.models.wish import Wish
from app.models.wish_approval import WishApproval
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.approval_chain import build_ascending_chain
from app.services.authorized_approvers import list_users_with_org_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wishes", tags=["wish-approvals"])


def _approval_dict(a: WishApproval, names: dict[int, str] | None = None) -> dict:
    """names — пакетно резолвленные ФИО (см. _resolve_decided_names), только
    для строк, у которых нет снапшота decided_by_username (историчные)."""
    names = names or {}
    decided_by_name = None
    if a.decided_by_user_id is not None:
        decided_by_name = a.decided_by_username or names.get(a.decided_by_user_id)
    return {
        "id": a.id,
        "wish_id": a.wish_id,
        "user_id": a.user_id,
        "order_num": a.order_num,
        "role_name": a.role_name,
        "full_name": a.approver_full_name,
        "is_auto": a.is_auto,
        "status": a.status,
        "comment": a.comment,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "decided_by_user_id": a.decided_by_user_id,
        "decided_by_name": decided_by_name,
        "is_on_behalf": a.decided_by_user_id is not None and a.decided_by_user_id != a.user_id,
    }


async def _resolve_decided_names(rows: list[WishApproval], db: AsyncSession) -> dict[int, str]:
    """Резолвит ФИО решивших ОДНИМ SELECT, без N+1 (образец:
    purchase_approvals.py::list_approvals). Резолвит только id, у которых нет
    снапшота decided_by_username — исторические строки без снапшота."""
    ids = {a.decided_by_user_id for a in rows if a.decided_by_user_id and not a.decided_by_username}
    if not ids:
        return {}
    rows_u = (await db.execute(
        select(User.id, User.full_name, User.username).where(User.id.in_(ids))
    )).all()
    return {uid: (full_name or username) for uid, full_name, username in rows_u}


async def _approval_dicts(rows: list[WishApproval], db: AsyncSession) -> list[dict]:
    names = await _resolve_decided_names(rows, db)
    return [_approval_dict(a, names) for a in rows]


async def _get_wish_or_403(wid: int, current_user: User, db: AsyncSession) -> Wish:
    wish = await db.get(Wish, wid)
    if wish is None:
        raise HTTPException(404, "Заявка не найдена")
    org_ids = get_org_filter(current_user)
    if org_ids is not None and wish.org_id not in org_ids:
        raise HTTPException(403, "Нет доступа к этой заявке")
    return wish


def _is_saas(user: User) -> bool:
    return user.role in OWNER_ROLES


async def _load_approvals(wid: int, db: AsyncSession) -> list[WishApproval]:
    return (await db.execute(
        select(WishApproval).where(WishApproval.wish_id == wid).order_by(WishApproval.order_num)
    )).scalars().all()


# ── Верхний согласующий обязан иметь право корректировать субсидию ─────────────
# Владелец: «Верхним согласующим необходимости закупки можно ставить только
# того, кто имеет право корректировать субсидию. Иначе каждый сотрудник будет
# сам себя ставить и сам себе согласовывать». Право «корректировать субсидию» —
# ТА ЖЕ проверка, что у PUT/DELETE субсидии (has_org_key(..., 'subsidy.edit',
# subsidy_id=...), см. subsidies.py) — второй расчёт прав не заводим (ПРАВИЛО №6).

async def _effective_subsidy_id_for_wish(wish: Wish, db: AsyncSession) -> int | None:
    """Субсидия, по которой проверяется право 'subsidy.edit' для верхнего
    согласующего этой заявки: своя subsidy_id, иначе — субсидия закупки-
    компаньона (авансовый отчёт, Purchase.wish_id == wish.id), иначе None
    (в этом случае проверяем право просто по организации)."""
    if wish.subsidy_id:
        return wish.subsidy_id
    purchase_subsidy_id = (await db.execute(
        select(Purchase.subsidy_id)
        .where(Purchase.wish_id == wish.id, Purchase.subsidy_id.isnot(None))
        .limit(1)
    )).scalar_one_or_none()
    return purchase_subsidy_id


async def _validate_top_approver(
    wish: Wish, top_user_id: int, db: AsyncSession,
) -> None:
    """400, если top_user_id не может быть верхним согласующим этой заявки —
    у него нет права 'subsidy.edit' по субсидии заявки/закупки-компаньона (по
    организации, если субсидии нет). Владелец (2026-09-29, уточнение): если
    сам автор заявки имеет это право — он МОЖЕТ быть верхним согласующим и
    провести всю заявку в одиночку; отдельного запрета «автор == согласующий»
    НЕТ — единственный критерий это subsidy.edit."""
    subsidy_id = await _effective_subsidy_id_for_wish(wish, db)
    top_user = await db.get(User, top_user_id)
    if top_user is None:
        raise HTTPException(404, "Пользователь не найден")
    if not await has_org_key(top_user, db, wish.org_id, "subsidy.edit", subsidy_id=subsidy_id):
        subsidy_name = None
        if subsidy_id:
            subsidy_name = (await db.execute(
                select(Subsidy.name).where(Subsidy.id == subsidy_id)
            )).scalar_one_or_none()
        raise HTTPException(
            400,
            "Верхним согласующим может быть только сотрудник с правом корректировать "
            f"субсидию {subsidy_name or 'этой организации'}",
        )


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get("/{wid}/approvers")
async def list_wish_approvers(
    wid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_wish_or_403(wid, current_user, db)
    rows = await _load_approvals(wid, db)
    return await _approval_dicts(rows, db)


# ── GET candidates для «Верхний согласующий» ───────────────────────────────────

@router.get("/{wid}/approvers/candidates")
async def list_top_approver_candidates(
    wid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Кандидаты в «верхний согласующий» — пользователи, у которых есть право
    'subsidy.edit' по субсидии заявки/закупки-компаньона (или по организации,
    если субсидии нет). Тот же расчёт кандидатов, что и у согласующих
    превышения ФЭО (app.services.authorized_approvers.list_users_with_org_key,
    ПРАВИЛО №6 — второй расчёт не заводим). Автор заявки НЕ исключается —
    владелец (2026-09-29): если у автора есть subsidy.edit, он вправе сам
    быть верхним согласующим собственной заявки."""
    wish = await _get_wish_or_403(wid, current_user, db)
    subsidy_id = await _effective_subsidy_id_for_wish(wish, db)
    users = await list_users_with_org_key(
        db, wish.org_id, "subsidy.edit", subsidy_id=subsidy_id,
    )
    return [
        {"id": u.id, "full_name": u.full_name or u.username, "role": u.role}
        for u in users
    ]


# ── POST cascade ──────────────────────────────────────────────────────────────

@router.post("/{wid}/approvers/cascade")
async def cascade_wish_approvers(
    wid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Построить восходящую цепочку согласующих от отдела автора до top_user_id."""
    wish = await _get_wish_or_403(wid, current_user, db)
    top_user_id = int(body.get("top_user_id", 0))
    mode = body.get("mode", "sequential")
    if mode not in ("sequential", "parallel"):
        mode = "sequential"
    if not top_user_id:
        raise HTTPException(422, "top_user_id обязателен")

    if not _is_saas(current_user) and wish.status not in ("draft", "rejected"):
        raise HTTPException(400, "Цепочку можно менять только у черновика или отклонённой заявки")

    await _validate_top_approver(wish, top_user_id, db)

    author_id = wish.created_by or current_user.id
    chain, chain_warning = await build_ascending_chain(db, author_id, top_user_id, wish.org_id)
    if not chain:
        raise HTTPException(400, "Не удалось построить цепочку согласующих — проверьте иерархию отдела")

    # Пересобираем авто-цепочку; добавленных вручную сохраняем (перенумеруем после цепочки)
    manual: list[WishApproval] = []
    chain_user_ids = {step["user_id"] for step in chain}
    for a in await _load_approvals(wid, db):
        if not a.is_auto and a.user_id not in chain_user_ids:
            manual.append(a)
        else:
            await db.delete(a)
    await db.flush()

    for step in chain:
        db.add(WishApproval(
            wish_id=wid,
            user_id=step["user_id"],
            order_num=step["order_num"],
            role_name=step["role_name"],
            approver_full_name=step["full_name"],
            is_auto=True,
            status="pending",
        ))
    for i, a in enumerate(manual):
        a.order_num = len(chain) + i

    # Статус заявки НЕ меняем: на согласование отправляет только кнопка
    # «Отправить на согласование» (POST /wishes/{id}/submit).
    wish.approval_mode = mode
    await db.commit()

    rows = await _load_approvals(wid, db)
    return {"approval_mode": mode, "approvers": await _approval_dicts(rows, db), "warning": chain_warning}


# ── POST add manual ───────────────────────────────────────────────────────────

@router.post("/{wid}/approvers", status_code=201)
async def add_wish_approver(
    wid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wish = await _get_wish_or_403(wid, current_user, db)
    if not _is_saas(current_user):
        if wish.status in ("draft", "rejected"):
            pass  # разрешено всем, кто имеет доступ к заявке
        elif wish.status == "submitted":
            # При submitted: только менеджер+ или согласующий из цепочки
            if current_user.role not in MANAGER_ROLES:
                in_chain = (await db.execute(
                    select(WishApproval.id).where(
                        WishApproval.wish_id == wid,
                        WishApproval.user_id == current_user.id,
                    ).limit(1)
                )).scalar_one_or_none()
                if not in_chain:
                    raise HTTPException(
                        403,
                        "Добавить согласующего к отправленной заявке может только менеджер+ или "
                        "участник цепочки согласования этой заявки"
                    )
        else:
            raise HTTPException(
                400,
                f"Добавить согласующего можно только к черновику, отклонённой или отправленной на согласование заявке "
                f"(текущий статус: {wish.status})"
            )
    user_id = int(body.get("user_id", 0))
    if not user_id:
        raise HTTPException(422, "user_id обязателен")
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Пользователь не найден")

    existing = (await db.execute(
        select(WishApproval).where(
            WishApproval.wish_id == wid,
            WishApproval.user_id == user_id,
        )
    )).scalar_one_or_none()
    if existing:
        return (await _approval_dicts([existing], db))[0]

    max_order = (await db.execute(
        select(func.max(WishApproval.order_num)).where(WishApproval.wish_id == wid)
    )).scalar()
    next_order = (max_order + 1) if max_order is not None else 0

    # Ручное назначение ЕДИНСТВЕННОГО (= одновременно верхнего) согласующего —
    # без цепочки это прямой аналог top_user_id в cascade (см. UI:
    # useWishApprovers.ensureApprovers — «не нажал кнопку, согласующим
    # становится ровно тот, кто выбран»). Та же проверка, что и в cascade:
    # 400, если у него нет права 'subsidy.edit' по субсидии заявки (автор
    # заявки с этим правом — легитимный кандидат, см. _validate_top_approver).
    if max_order is None:
        await _validate_top_approver(wish, user_id, db)

    a = WishApproval(
        wish_id=wid,
        user_id=user_id,
        order_num=next_order,
        role_name=body.get("role_name") or "Согласующий",
        approver_full_name=target.full_name or target.username,
        is_auto=False,
        status="pending",
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return (await _approval_dicts([a], db))[0]


# ── POST reorder ──────────────────────────────────────────────────────────────

@router.post("/{wid}/approvers/reorder")
async def reorder_wish_approvers(
    wid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Задать порядок согласующих: body.ids — все approval_id в новом порядке."""
    wish = await _get_wish_or_403(wid, current_user, db)
    if not _is_saas(current_user) and wish.status not in ("draft", "rejected"):
        raise HTTPException(400, "Порядок можно менять только у черновика или отклонённой заявки")
    # Владелец: «Согласующих можно менять местами только при последовательном
    # согласовании» — при parallel все решают одновременно, порядок не значим.
    if wish.approval_mode == "parallel":
        raise HTTPException(409, "Порядок согласующих меняется только при последовательном согласовании")
    ids = body.get("ids") or []
    rows = await _load_approvals(wid, db)
    by_id = {a.id: a for a in rows}
    if set(ids) != set(by_id.keys()):
        raise HTTPException(422, "ids должны содержать всех согласующих заявки без пропусков")
    for i, aid in enumerate(ids):
        by_id[aid].order_num = i
    await db.commit()
    return await _approval_dicts(await _load_approvals(wid, db), db)


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.delete("/{wid}/approvers/{approval_id}")
async def remove_wish_approver(
    wid: int,
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wish = await _get_wish_or_403(wid, current_user, db)
    a = await db.get(WishApproval, approval_id)
    if a and a.wish_id == wid:
        if not _is_saas(current_user) and wish.status not in ("draft", "rejected"):
            raise HTTPException(400, "Согласующих можно менять только у черновика или отклонённой заявки")
        if a.status != "pending":
            raise HTTPException(400, "Нельзя удалить согласующего, который уже принял решение")
        await db.delete(a)
        await db.commit()
    return {"ok": True}


# ── POST decide ───────────────────────────────────────────────────────────────

@router.post("/{wid}/approvers/{approval_id}/decide")
async def decide_wish_approval(
    wid: int,
    approval_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wish = await _get_wish_or_403(wid, current_user, db)
    a = await db.get(WishApproval, approval_id)
    if a is None or a.wish_id != wid:
        raise HTTPException(404, "Согласующий не найден")

    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision должен быть 'approved' или 'rejected'")
    convert_error: str | None = None
    _convert_warning: str | None = None
    _created_ids: list[int] = []
    _created_purchases: list[dict] = []
    _plan_warning: list[str] = []
    _purchase_sync: dict | None = None
    _duplicate_warnings: list[dict] = []

    if not _is_saas(current_user) and wish.status != "submitted":
        raise HTTPException(400, "Заявка ещё не отправлена на согласование (статус должен быть 'submitted')")

    # Владелец (2026-09-29, уточнение): отдельного запрета «автор заявки не
    # согласовывает свою же заявку» НЕТ — единственный критерий для верхнего
    # согласующего это subsidy.edit (см. _validate_top_approver). Если автор
    # сам обладает этим правом, он законно оказывается в цепочке (top_user_id
    # == created_by пройдёт cascade) и вправе решить свой же шаг.

    # Права: решать может сам назначенный согласующий или менеджер+/SaaS
    if not _is_saas(current_user) and current_user.role not in MANAGER_ROLES and a.user_id != current_user.id:
        raise HTTPException(403, "Решение может принять только назначенный согласующий или менеджер+")

    if a.status != "pending":
        raise HTTPException(400, f"По этому согласующему уже принято решение: {a.status}")

    # Sequential: нельзя согласовать, пока нижестоящие (меньший order_num) ещё pending
    if wish.approval_mode == "sequential":
        lower_pending = (await db.execute(
            select(func.count()).select_from(WishApproval).where(
                WishApproval.wish_id == wid,
                WishApproval.order_num < a.order_num,
                WishApproval.status == "pending",
            )
        )).scalar() or 0
        if lower_pending > 0:
            raise HTTPException(
                400,
                "Последовательное согласование: сначала должны согласовать нижестоящие в цепочке.",
            )

    # Задача 2 (владелец, 2026-08-20): решение ЗА ДРУГОГО (менеджер+/SaaS решает
    # вместо назначенного согласующего) обязано называть причину — без неё
    # непонятно, почему согласующий не решил сам. Собственное решение (a.user_id
    # == current_user.id) комментария по-прежнему не требует. Не путать с
    # массовым «Одобрить без согласования остальных» (_ensure_no_pending_approvals
    # в wishes.py) — там уже пишется собственный поясняющий комментарий.
    raw_comment = body.get("comment")
    if a.user_id != current_user.id and not (raw_comment and raw_comment.strip()):
        who = a.approver_full_name or (f"пользователя #{a.user_id}" if a.user_id else "назначенного согласующего")
        raise HTTPException(
            400,
            f"Вы принимаете решение за {who}. Укажите причину — например, что "
            "согласующий в отпуске или поручил вам.",
        )

    # Владелец (30.09): галочка «Без ТЗ (мелкие закупки)» — согласующий этого
    # конкретного шага (тот же круг лиц, что прошёл проверку прав выше) может
    # выдать заявке то же послабление гейта ТЗ, что исторически есть у
    # авансовых (см. app.services.tz_items.tz_required). Ставится ПРИ ЛЮБОМ
    # approved-решении в цепочке (не только последнем) и остаётся включённой
    # до конвертации — сброшенной галочкой на другом шаге её не снять.
    if decision == "approved" and body.get("tz_not_required") and not wish.tz_not_required:
        # Владелец (30.09, уточнение): «Это должно быть ОТДЕЛЬНОЕ разрешение
        # в ролях — кому можно отменять необходимость ТЗ, а кому нет» —
        # отдельное от права решать по заявке (проверка a.user_id/MANAGER_ROLES
        # выше). См. permission_seeds.py::_purchase_tz_waive_action.
        if not await has_org_key(current_user, db, wish.org_id, 'purchase.tz_waive', subsidy_id=wish.subsidy_id):
            raise HTTPException(
                403,
                "Нет права «Отмена необходимости ТЗ» — обратитесь к администратору за разрешением purchase.tz_waive",
            )
        wish.tz_not_required = True
        wish.tz_waived_by_user_id = current_user.id

    a.status = decision
    a.comment = raw_comment
    a.decided_at = datetime.now(timezone.utc)
    a.decided_by_user_id = current_user.id
    a.decided_by_username = current_user.full_name or current_user.username
    await db.flush()

    creator = await db.get(User, wish.created_by) if wish.created_by else None
    decided_name = current_user.full_name or current_user.username

    if decision == "rejected":
        wish.status = "rejected"
        wish.rejection_reason = body.get("comment")
        # Владелец (2026-08-19): «нужно, чтобы было видно, кто отклонил» —
        # см. Wish.rejected_by/rejected_at (models/wish.py). Ставим ДО
        # _reset_approvals ниже — сама заявка это переживает, в отличие от
        # WishApproval-строки отклонившего (та без keep_user_id тоже стёрлась бы).
        wish.rejected_by = current_user.id
        wish.rejected_at = datetime.now(timezone.utc)
        # Согласующий отклонил — если по заявке уже есть закупка в Плане закупок
        # (например от параллельного потока действий), убираем её из плана.
        from app.routers.wishes import _withdraw_wish_from_plan
        # Пред-существующий баг: action_text — обязательный именованный параметр
        # (см. wishes.py::_withdraw_wish_from_plan), без него вызов падал с
        # TypeError на КАЖДОМ отклонении через эту цепочку. Значение — как в
        # аналогичном вызове reject_wish (wishes.py, строка ~2094).
        _plan_warning = await _withdraw_wish_from_plan(wish.id, db, action_text="отклонить")
        # Владелец (2026-08-19): «если заявка отклоняется одним из согласующих, она
        # отклоняется у всех, потому что заявку могут изменить именно так, с чем
        # остальные согласующие могут не согласиться. И надо будет повторить заново» —
        # отклонение ОДНИМ согласующим сбрасывает решения ВСЕХ согласующих цепочки
        # обратно в pending (включая решение самого отклонившего — заявка идёт на
        # повторный круг согласования целиком), а не только правит wish.status.
        # Тот же helper и тот же паттерн, что уже применяется в wishes.py::reject_wish
        # (см. _reset_approvals там, строка ~2105).
        from app.routers.wishes import _reset_approvals
        await _reset_approvals(wish.id, db, keep_user_id=a.user_id)
        await db.commit()
        if creator and creator.id != current_user.id:
            try:
                from app.notifications import notify_wish_rejected
                await notify_wish_rejected(wish, creator, decided_name, body.get("comment"))
            except Exception as e:
                logger.warning("notify_wish_rejected failed: %s", e)
    else:
        # approved — если все approved → заявка полностью согласована
        remaining = (await db.execute(
            select(func.count()).select_from(WishApproval).where(
                WishApproval.wish_id == wid,
                WishApproval.status == "pending",
            )
        )).scalar() or 0
        # Владелец (2026-09-29, «про то, что это дубликат, ничего не написано»):
        # ДО создания закупки — проверить, не заняты ли плановые позиции этой
        # заявки уже ЧУЖОЙ закупкой (другая заявка того же плана уже сконвертирована
        # раньше). ДО, а не после (в отличие от _excess_warnings ниже, которая
        # намеренно считает ПОСЛЕ создания закупки) — иначе свежесозданная закупка
        # ЭТОЙ заявки попала бы в свой же список «дублей». См. app.services.
        # plan_duplicate_warning — переиспользует те же linked_purchases, что и
        # GET /feo-categories/plan-positions (ПРАВИЛО №6, второй расчёт не заводим).
        if wish.items:
            from app.services.plan_duplicate_warning import collect_plan_duplicate_warnings
            _duplicate_warnings = await collect_plan_duplicate_warnings(db, list(wish.items), exclude_wish_id=wish.id)
        if remaining == 0:
            wish.status = "approved"
            wish.approved_by = current_user.id
            # A2: автоконвертация в план закупок при полном согласовании
            # (аналогично кнопке /approve в wishes.py)
            if wish.items:
                try:
                    from app.routers.wishes import _distribute_wish_to_purchases
                    _created_ids = await _distribute_wish_to_purchases(wish, db, current_user, split=False)
                    wish.status = "converted"
                    _convert_warning = getattr(wish, "_convert_warning", None)
                    # Повторное согласование заявки, у которой уже была закупка
                    # (владелец, план crystalline-soaring-heron.md, п.2) — см.
                    # wishes.py::_sync_purchase_from_wish.
                    _purchase_sync = getattr(wish, "_purchase_sync", None)
                    # Владелец (2026-08-20): согласование последним в цепочке САМО создаёт
                    # закупку и переводит заявку в 'converted' здесь. Фронт раньше не знал
                    # об этом и после этого ответа отдельно дёргал POST /convert — тот бился
                    # об гейт «должна быть approved» (заявка уже converted), пользователь видел
                    # красную ошибку поверх настоящего успеха. Отдаём id+номер созданной
                    # закупки сразу в ЭТОМ ответе, чтобы фронт не звал /convert вообще.
                    if _created_ids:
                        from app.models.purchase import Purchase as _Purchase
                        _p_res = await db.execute(
                            select(_Purchase.id, _Purchase.registry_number)
                            .where(_Purchase.id.in_(_created_ids))
                        )
                        _created_purchases = [
                            {"id": pid, "registry_number": rn} for pid, rn in _p_res.all()
                        ]
                except HTTPException:
                    # Приёмка 2026-08-07 (владелец): гейты «ТЗ не выше плана» /
                    # «превышение ФЭО» — тоже HTTPException, а он наследник Exception,
                    # поэтому раньше тонул в широком except ниже: согласующий получал
                    # 200, заявка зависала в 'approved' без закупки, причина отказа
                    # была видна только в логе. Для цепочки из 2+ согласующих это
                    # делало гейт цены НЕВИДИМЫМ — ровно тот сценарий, который владелец
                    # просил закрыть. Пробрасываем как есть — тот же статус (409) и
                    # тот же текст (какая позиция, что именно превышено, что делать),
                    # что видит пользователь на прямом /wishes/{id}/approve.
                    #
                    # Атомарность («либо оба изменения, либо ни одного», владелец):
                    # решение согласующего (a.status/decided_at/decided_by, строки выше)
                    # и wish.status='approved' на этот момент только flush()-нуты, ещё
                    # НЕ закоммичены — до них в этом запросе не было ни одного commit().
                    # rollback() отменяет их одним махом: заявка остаётся 'submitted',
                    # этот WishApproval — 'pending', ровно как до вызова /decide.
                    # Согласующему нужно нажать «согласовать» ещё раз после того как
                    # цену/план поправят — никакого «наполовину согласовано» состояния
                    # не возникает. (get_db закрыл бы сессию и откатил незакоммиченное
                    # неявно и сам — rollback() здесь явный, по образцу ветки
                    # body.status == "converted" в force_wish_status, wishes.py.)
                    await db.rollback()
                    raise
                except Exception as _exc:
                    # Действительно неожиданная ошибка (не гейт цены/плана) — поведение
                    # НЕ меняем по просьбе владельца: логируем и оставляем заявку в
                    # 'approved' без закупки (решение согласующего всё равно сохранится
                    # ниже), согласующий получает 200 — разбираться по логу вручную.
                    logger.warning("auto-convert wish %s to purchases failed: %s", wish.id, _exc)
            await db.commit()
            if creator:
                try:
                    from app.notifications import notify_wish_approved
                    await notify_wish_approved(wish, creator)
                except Exception as e:
                    logger.warning("notify_wish_approved failed: %s", e)
            # Сообщение в чате (если есть assigned_to)
            if wish.assigned_to:
                try:
                    from app.routers.purchase_members import _create_assignment_chat_room
                    from app.models.chat_message import ChatMessage
                    org_id = wish.org_id
                    room_id = await _create_assignment_chat_room(
                        db, current_user.id, wish.assigned_to, org_id,
                        f"Заявка №{wish.id}: {wish.title or 'без названия'}",
                    )
                    db.add(ChatMessage(
                        room_id=room_id,
                        sender_id=current_user.id,
                        content=f"✅ Заявка полностью согласована и передана в план закупок: {wish.title or '(без названия)'}.",
                    ))
                    await db.flush()
                    await db.commit()
                except Exception as e:
                    logger.warning("chat message on full approval failed: %s", e)
        else:
            await db.commit()
            # sequential — уведомить следующего согласующего
            if wish.approval_mode == "sequential":
                nxt = (await db.execute(
                    select(WishApproval).where(
                        WishApproval.wish_id == wid,
                        WishApproval.status == "pending",
                    ).order_by(WishApproval.order_num).limit(1)
                )).scalar_one_or_none()
                if nxt and nxt.user_id:
                    try:
                        nxt_user = await db.get(User, nxt.user_id)
                        if nxt_user:
                            from app.notifications import notify_wish_approval_step
                            await notify_wish_approval_step(wish, nxt_user, decided_name)
                    except Exception as e:
                        logger.warning("notify_wish_approval_step failed: %s", e)

    rows = await _load_approvals(wid, db)
    return {
        "status": wish.status,
        "convert_error": convert_error,
        "convert_warning": _convert_warning,
        "purchase_ids": _created_ids,
        "purchases": _created_purchases,
        "approvers": await _approval_dicts(rows, db),
        "plan_warning": _plan_warning,
        # Превышение ФЭО больше не отказ, а предупреждение (владелец, 2026-08-12):
        # _distribute_wish_to_purchases складывает его в wish._excess_warnings, и этот
        # путь — согласование ЦЕПОЧКОЙ — обязан доносить его до согласующего так же,
        # как прямой /wishes/{id}/approve. Иначе последний согласующий создаёт закупку
        # с перерасходом и не видит об этом ни слова.
        # Владелец (2026-09-29): дубли (см. _duplicate_warnings выше) в ТОМ ЖЕ
        # канале, что и превышение ФЭО — фронт уже умеет показывать excess_warnings
        # согласующему (useWishesContext.showExcessWarnings), второй канал не заводим.
        "excess_warnings": _duplicate_warnings + getattr(wish, "_excess_warnings", []),
        "purchase_sync": _purchase_sync,
        # Владелец (2026-09-29): авансовая закупка после финального согласования
        # компаньона пробует уйти дальше 'wishes' сама (см. wish_distribution.py) —
        # если гейт (обязательные поля/превышение) отказал, тут причина, чтобы
        # согласующий не терялся в догадках, почему закупка осталась на месте.
        "advance_purchase_transition_warning": getattr(wish, "_advance_purchase_transition_warning", None),
    }
