"""plan_excess.py — согласование превышения плана ФЭО над финансированием узла.

Требование владельца (2026-08-05): «Если где-то превысил план ФЭО, значит
где-то надо снимать. Должны быть заблокированы действия, пока план закупок не
загонять обратно в размеры ФЭО. Согласование превышения должно быть цепочкой,
организации бывают разные, к директору не всегда простой сотрудник может
попасть».

Уточнение владельца (2026-08-29): «Превышение не может согласовывать любой из
цепочки согласования. Это только определённые люди… Такие права могут быть,
например, только у владельцев или только у финансистов. У начальника отдела
таких прав быть не может, но он точно знает, что эта закупка необходима. И
надо добавить, что согласование — это именно согласование НЕОБХОДИМОСТИ
закупки. Это не согласование превышения». Право выдаётся точечно (галочкой),
никому не полагается по умолчанию — см. app.auth.permissions.has_org_key и
action-ключ 'plan_excess.decide'. Цепочка (см. _authorized_plan_excess_approvers
ниже) строится НЕ оргструктурой (в отличие от заявок/wishes, у которых остаётся
app.services.approval_chain.build_ascending_chain), а списком пользователей,
у которых это право есть (персонально или по данной субсидии).

Endpoints:
  GET  /api/plan-excess?subsidy_id=            — список запросов по субсидии (вкладка
                                                  feo_categories ИЛИ право plan_excess.decide —
                                                  точечно назначенный согласующий обязан видеть
                                                  список, иначе решать ему нечего, см. п. ниже)
  POST /api/plan-excess                        — запросить согласование превышения по узлу
  POST /api/plan-excess/{id}/decide             — решение шага (approve/reject; тоже без
                                                  require_tab('feo_categories') — см. её докстринг)

Влияние на app.services.feo_plan.compute_feo_plan_tree — см. её docstring и
assert_no_unapproved_excess (вызывается перед действиями, увеличивающими план,
в purchases.py/wishes.py).
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth.jwt import get_current_user, get_single_org_id, OWNER_ROLES
from app.auth.permissions import require_tab, has_org_key, _has_key_in_any_org, _ROLE_PRIORITY
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.models.user_org_access import UserOrgAccess
from app.models.user_subsidy_access import UserSubsidyAccess
from app.models.feo_category import FeoCategory
from app.models.subsidy import Subsidy
from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
from app.services.feo_plan import compute_feo_plan_tree

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/plan-excess", tags=["plan-excess"])


def _is_saas(user: User) -> bool:
    return user.role in OWNER_ROLES


async def _authorized_plan_excess_approvers(
    db: AsyncSession, org_id: int, subsidy_id: int, exclude_user_id: int | None = None,
) -> list[User]:
    """Уполномоченные на решение по превышению плана ФЭО — пользователи, у которых
    эффективно есть action-право 'plan_excess.decide' в организации субсидии (та
    же проверка, что и в гейте /decide — app.auth.permissions.has_org_key, — не
    дублируем логику).

    Кандидаты собираются из трёх источников (кто ВООБЩЕ может иметь это право):
    членство в организации (UserOrganization), явная орг-роль (UserOrgAccess) и
    персональный грант на саму субсидию (UserSubsidyAccess). Из них has_org_key
    отбирает тех, у кого право реально включено (по роли, орг-override или
    субсидийному гранту).

    Автор запроса (exclude_user_id) исключается — самосогласование запрещено
    (владелец, 2026-08-29: «согласование — это не согласование превышения»
    самим заявителем).

    Порядок результата — «по-человечески»: сначала более высокая роль, затем
    ФИО по алфавиту.
    """
    candidate_ids: set[int] = set()
    for stmt in (
        select(UserOrganization.user_id).where(UserOrganization.org_id == org_id),
        select(UserOrgAccess.user_id).where(UserOrgAccess.org_id == org_id),
        select(UserSubsidyAccess.user_id).where(UserSubsidyAccess.subsidy_id == subsidy_id),
    ):
        candidate_ids.update((await db.execute(stmt)).scalars().all())

    if exclude_user_id is not None:
        candidate_ids.discard(exclude_user_id)
    if not candidate_ids:
        return []

    users = (await db.execute(select(User).where(User.id.in_(candidate_ids)))).scalars().all()
    authorized: list[User] = []
    for u in users:
        if await has_org_key(u, db, org_id, "plan_excess.decide", subsidy_id=subsidy_id):
            authorized.append(u)

    def _sort_key(u: User):
        prio = _ROLE_PRIORITY.get(u.role or "", 0)
        name = (u.full_name or u.username or "").lower()
        return (-prio, name)

    authorized.sort(key=_sort_key)
    return authorized


def _step_dict(s: PlanExcessApprovalStep) -> dict:
    return {
        "id": s.id,
        "approval_id": s.approval_id,
        "user_id": s.user_id,
        "order_num": s.order_num,
        "role_name": s.role_name,
        "full_name": s.approver_full_name,
        "status": s.status,
        "comment": s.comment,
        "decided_at": s.decided_at.isoformat() if s.decided_at else None,
        "decided_by_user_id": s.decided_by_user_id,
    }


def _approval_dict(a: PlanExcessApproval) -> dict:
    return {
        "id": a.id,
        "feo_category_id": a.feo_category_id,
        "subsidy_id": a.subsidy_id,
        "excess_amount": float(a.excess_amount) if a.excess_amount is not None else 0.0,
        "plan_amount": float(a.plan_amount) if a.plan_amount is not None else None,
        "budget_amount": float(a.budget_amount) if a.budget_amount is not None else None,
        # Владелец, план zany-fluttering-mountain.md (2026-08-13): «план был X →
        # стал Y» — заполнено только для превышения вида plan_over_manual, см.
        # request_plan_excess_approval.
        "plan_before": float(a.plan_before) if a.plan_before is not None else None,
        "plan_after": float(a.plan_after) if a.plan_after is not None else None,
        "status": a.status,
        "mode": a.mode,
        "requested_by_id": a.requested_by_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "comment": a.comment,
        "steps": [_step_dict(s) for s in sorted(a.steps, key=lambda s: s.order_num)],
    }


async def _load_approval(approval_id: int, db: AsyncSession) -> PlanExcessApproval:
    a = (await db.execute(
        select(PlanExcessApproval)
        .options(selectinload(PlanExcessApproval.steps))
        .where(PlanExcessApproval.id == approval_id)
    )).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Запрос на согласование превышения не найден")
    return a


# ── GET list ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_plan_excess_approvals(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Владелец (2026-08-29): точечно назначенный на 'plan_excess.decide' согласующий
    # (например, финансист) может НЕ иметь вкладки 'feo_categories' вовсе — та же
    # логика, что и в /decide (см. её комментарий выше). Раньше этот список требовал
    # require_tab('feo_categories') безусловно, из-за чего такой согласующий получал
    # 403 и вообще не видел секцию превышения — то есть фикс /decide был бесполезен.
    # Пускаем по ЛЮБОМУ из двух условий: обычная вкладка feo_categories (как раньше)
    # ИЛИ action-право plan_excess.decide на организацию/субсидию — has_org_key,
    # та же проверка, что в /decide и в _authorized_plan_excess_approvers, логику не
    # дублируем.
    if current_user.role != "superadmin" and not await _has_key_in_any_org(current_user, db, "feo_categories"):
        subsidy = await db.get(Subsidy, subsidy_id)
        if subsidy is None:
            raise HTTPException(404, "Субсидия не найдена")
        org_id = subsidy.org_id or get_single_org_id(current_user)
        if not await has_org_key(current_user, db, org_id, "plan_excess.decide", subsidy_id=subsidy_id):
            raise HTTPException(
                403,
                "Нет доступа к списку запросов на согласование превышения плана ФЭО: "
                "требуется вкладка «Категории ФЭО» либо право «Согласование превышения "
                "плана ФЭО» (plan_excess.decide) по этой субсидии.",
            )

    rows = (await db.execute(
        select(PlanExcessApproval)
        .options(selectinload(PlanExcessApproval.steps))
        .where(PlanExcessApproval.subsidy_id == subsidy_id)
        .order_by(PlanExcessApproval.created_at.desc())
    )).scalars().all()
    return [_approval_dict(a) for a in rows]


async def _notify_pending_plan_excess_approvers(
    approval: PlanExcessApproval, db: AsyncSession, requester_name: str, cat_name: str,
) -> None:
    """Уведомляет согласующих из цепочки о необходимости решения по превышению плана ФЭО.

    По образцу app.routers.wishes._notify_pending_approvers:
    sequential → уведомить только первого (по order_num) pending-согласующего;
    parallel → уведомить всех pending сразу.
    """
    try:
        from app.notifications import notify_plan_excess_approval_step
        pending = sorted(
            (s for s in approval.steps if s.status == "pending"),
            key=lambda s: s.order_num,
        )
        if not pending:
            return
        targets = pending[:1] if approval.mode != "parallel" else pending
        for step in targets:
            if step.user_id and step.user_id != approval.requested_by_id:
                approver_user = await db.get(User, step.user_id)
                if approver_user:
                    await notify_plan_excess_approval_step(approval, approver_user, requester_name, cat_name)
    except Exception as e:
        logger.warning("notify plan-excess approvers failed: %s", e)


async def _notify_plan_excess_decision(
    approval: PlanExcessApproval, decided_step: PlanExcessApprovalStep,
    db: AsyncSession, decided_by_name: str, cat_name: str,
) -> None:
    """Уведомляет автора запроса о финальном решении и, для последовательного
    режима, следующего согласующего в очереди (если запрос ещё pending)."""
    try:
        from app.notifications import notify_plan_excess_decided, notify_plan_excess_approval_step
        if approval.status in ("approved", "rejected"):
            if approval.requested_by_id and approval.requested_by_id != decided_step.decided_by_user_id:
                requester = await db.get(User, approval.requested_by_id)
                if requester:
                    await notify_plan_excess_decided(
                        approval, requester, approval.status, decided_by_name,
                        decided_step.comment, cat_name,
                    )
        elif approval.status == "pending" and approval.mode != "parallel":
            nxt = next(
                (s for s in sorted(approval.steps, key=lambda s: s.order_num) if s.status == "pending"),
                None,
            )
            if nxt and nxt.user_id and nxt.user_id != approval.requested_by_id:
                nxt_user = await db.get(User, nxt.user_id)
                if nxt_user:
                    requester = await db.get(User, approval.requested_by_id) if approval.requested_by_id else None
                    requester_name = (requester.full_name or requester.username) if requester else "—"
                    await notify_plan_excess_approval_step(approval, nxt_user, requester_name, cat_name)
    except Exception as e:
        logger.warning("notify plan-excess decision failed: %s", e)


# ── POST request ──────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def request_plan_excess_approval(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab("feo_categories")),
):
    """Запросить согласование превышения плана по узлу ФЭО. body:
    {feo_category_id, mode?}. Кому направить запрос решает НЕ автор (никакого
    top_user_id) — цепочка строится из уполномоченных, см.
    _authorized_plan_excess_approvers."""
    feo_category_id = int(body.get("feo_category_id", 0))
    if not feo_category_id:
        raise HTTPException(422, "feo_category_id обязателен")

    cat = await db.get(FeoCategory, feo_category_id)
    if cat is None:
        raise HTTPException(404, "Категория ФЭО не найдена")

    subsidy = await db.get(Subsidy, cat.subsidy_id)
    if subsidy is None:
        raise HTTPException(404, "Субсидия не найдена")

    tree = await compute_feo_plan_tree(db, [cat.subsidy_id])
    node = tree.get(feo_category_id)
    if node is None:
        raise HTTPException(404, "Узел ФЭО не найден в дереве плана")

    # Задача владельца «план ≠ факт» (сессия 2026-08-06): узел может иметь ДВА
    # независимых превышения — «план дороже финансирования ФЭО» (excess_amount,
    # как раньше) и/или «факт (итог закупки/КП) дороже плана» (excess_fact_over_plan,
    # новое, см. compute_feo_plan_tree). Один и тот же механизм согласования
    # (PlanExcessApproval по категории) закрывает оба — approved снимает блокировку
    # для обоих видов сразу (см. assert_no_unapproved_excess).
    #
    # Задача владельца п.2 (2026-08-12): ТРЕТИЙ вид — сумма плановых позиций
    # категории превысила «ручной» план (excess_plan_over_manual, см.
    # compute_feo_plan_tree). Тот же механизм согласования закрывает и его —
    # см. assert_no_unapproved_excess, третья проверка в цепочке.
    excess_amount = node.get("excess_amount") or 0.0
    excess_fact_over_plan = node.get("excess_fact_over_plan") or 0.0
    excess_plan_over_manual = node.get("excess_plan_over_manual") or 0.0
    if excess_amount <= 0.005 and excess_fact_over_plan <= 0.005 and excess_plan_over_manual <= 0.005:
        raise HTTPException(400, f"По категории «{cat.name}» нет превышения плана")
    # Что именно согласуем в этом запросе — приоритет тот же, что и в
    # assert_no_unapproved_excess (сверху вниз: над финансированием ФЭО, затем
    # факт над планом, затем плановые позиции над ручным планом).
    if excess_amount > 0.005:
        excess_for_request = excess_amount
        excess_kind = "over_feo"
        excess_kind_label = "План превышает финансирование по ФЭО"
        excess_description = (
            f"Превышение плана над финансированием ФЭО по категории «{cat.name}»: "
            f"финансирование по ФЭО {Decimal(str(node.get('budget') or 0.0)):,.2f} ₽, "
            f"текущая плановая сумма {Decimal(str(node['plan'] + node['over'])):,.2f} ₽, "
            f"превышение {Decimal(str(excess_amount)):,.2f} ₽."
        )
    elif excess_fact_over_plan > 0.005:
        excess_for_request = excess_fact_over_plan
        excess_kind = "fact_over_plan"
        excess_kind_label = "Факт (итог закупки/КП) превышает план"
        excess_description = (
            f"Итог закупки (факт) по категории «{cat.name}» превышает план: "
            f"план {Decimal(str(node.get('plan') or 0.0)):,.2f} ₽, "
            f"факт {Decimal(str(node.get('fact') or 0.0)):,.2f} ₽, "
            f"превышение {Decimal(str(excess_fact_over_plan)):,.2f} ₽."
        )
    else:
        excess_for_request = excess_plan_over_manual
        excess_kind = "plan_over_manual"
        excess_kind_label = "Плановые позиции превышают вручную заданный план"
        _manual_entered = node.get("manual_plan_entered") or 0.0
        _plan_manual_total = node.get("plan_manual") or 0.0
        _items = node.get("excess_plan_items") or []
        _items_txt = ""
        if _items:
            _shown = "; ".join(
                f"«{it['name']}» ({Decimal(str(it['amount'])):,.2f} ₽)" for it in _items[:5]
            )
            _more = f" и ещё {len(_items) - 5} поз." if len(_items) > 5 else ""
            _items_txt = f" Позиции-виновники: {_shown}{_more}."
        excess_description = (
            f"Сумма плановых позиций категории «{cat.name}» превышает вручную заданный "
            f"план: ручной план {Decimal(str(_manual_entered)):,.2f} ₽, сумма плановых "
            f"позиций {Decimal(str(_plan_manual_total)):,.2f} ₽, превышение "
            f"{Decimal(str(excess_plan_over_manual)):,.2f} ₽.{_items_txt}"
        )

    existing_pending = (await db.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.feo_category_id == feo_category_id,
            PlanExcessApproval.status == "pending",
        ).order_by(PlanExcessApproval.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing_pending:
        full = await _load_approval(existing_pending.id, db)
        return _approval_dict(full)

    mode = body.get("mode", "sequential")
    if mode not in ("sequential", "parallel"):
        mode = "sequential"

    org_id = subsidy.org_id or get_single_org_id(current_user)
    if not org_id:
        raise HTTPException(
            409,
            "Не удалось определить организацию субсидии — согласование превышения плана невозможно настроить.",
        )

    # Владелец (2026-08-29): цепочка превышения — НЕ оргструктура (начальник
    # отдела/руководитель организации подтверждают НЕОБХОДИМОСТЬ закупки, но не
    # вправе решать по превышению). Уполномоченные — только те, у кого включено
    # действие 'plan_excess.decide' (выдаётся точечно, см. _authorized_plan_excess_approvers).
    approvers = await _authorized_plan_excess_approvers(
        db, org_id, cat.subsidy_id, exclude_user_id=current_user.id,
    )
    if not approvers:
        raise HTTPException(
            409,
            "Превышение плана ФЭО согласовать некому: ни у одного пользователя организации нет права "
            "«Согласование превышения плана ФЭО» (plan_excess.decide). Выдайте это право нужному кругу "
            "лиц — например, финансисту или владельцу организации, персонально или по этой субсидии — "
            "и повторите запрос.",
        )

    chain = [
        {
            "user_id": u.id,
            "role_name": "Уполномочен на согласование превышения",
            "full_name": u.full_name or u.username,
            "order_num": i,
        }
        for i, u in enumerate(approvers)
    ]
    chain_warning: str | None = None
    self_approval = False

    full_plan = node["plan"] + node["over"]  # текущая плановая сумма (до сжатия по бюджету)
    # Владелец, план zany-fluttering-mountain.md (2026-08-13): «прежний план обязан
    # сохраниться в базе» — для превышения вида plan_over_manual фиксируем
    # plan_before (вручную заданная сумма на момент запроса) / plan_after (Σ
    # плановых позиций на тот же момент), см. app.models.plan_excess_approval.
    # NULL для остальных двух видов (over_feo/fact_over_plan) — там понятия
    # «план был → стал» не было запрошено владельцем.
    plan_before = plan_after = None
    if excess_kind == "plan_over_manual":
        # ⚠️ node["plan_manual"] ЗДЕСЬ — ЕЩЁ вручную заданная сумма, не Σ позиций:
        # пока НЕТ approved-запроса, app.services.feo_plan._manual_plan_for держит
        # plan_manual == manual_plan_amount (план не подменяется, пока не согласовано —
        # см. её docstring), а этот запрос как раз ТОЛЬКО создаётся. Σ позиций
        # («стало») = manual_plan_entered + excess_plan_over_manual (excess = Σ
        # позиций минус ручная сумма, по определению).
        plan_before = Decimal(str(node.get("manual_plan_entered") or 0.0))
        plan_after = plan_before + Decimal(str(node.get("excess_plan_over_manual") or 0.0))

    # У PlanExcessApproval нет отдельного поля «вид превышения» — различаем вид
    # текстом в comment, см. excess_description выше. Тот же принцип, что и у
    # полей excess_amount/plan_amount/budget_amount ниже — они уже были общими
    # для всех трёх видов, comment теперь тоже общий, но содержательный per-вид.
    approval = PlanExcessApproval(
        feo_category_id=feo_category_id,
        subsidy_id=cat.subsidy_id,
        excess_amount=Decimal(str(excess_for_request)),
        plan_amount=Decimal(str(full_plan)),
        budget_amount=Decimal(str(node.get("budget") or 0)),
        plan_before=plan_before,
        plan_after=plan_after,
        status="pending",
        mode=mode,
        requested_by_id=current_user.id,
        comment=excess_description,
    )
    db.add(approval)
    await db.flush()

    for step in chain:
        db.add(PlanExcessApprovalStep(
            approval_id=approval.id,
            user_id=step["user_id"],
            order_num=step["order_num"],
            role_name=step.get("role_name"),
            approver_full_name=step.get("full_name"),
            status="pending",
        ))
    await db.commit()

    full = await _load_approval(approval.id, db)
    requester_name = current_user.full_name or current_user.username
    await _notify_pending_plan_excess_approvers(full, db, requester_name, cat.name)

    resp = _approval_dict(full)
    resp["warning"] = chain_warning
    resp["self_approval"] = self_approval
    # Вид согласуемого превышения — различаем три случая (см. компанию
    # excess_kind/excess_amount/excess_fact_over_plan/excess_plan_over_manual
    # выше в compute_feo_plan_tree и assert_no_unapproved_excess): "over_feo" —
    # план дороже финансирования ФЭО, "fact_over_plan" — факт дороже плана,
    # "plan_over_manual" — сумма плановых позиций дороже вручную заданного плана.
    resp["excess_kind"] = excess_kind
    resp["excess_kind_label"] = excess_kind_label
    resp["excess_description"] = excess_description
    return resp


# ── POST decide ───────────────────────────────────────────────────────────────

@router.post("/{approval_id}/decide")
async def decide_plan_excess_step(
    approval_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    # Владелец (2026-08-29): НЕ require_tab('feo_categories') — уполномоченный на
    # решение (например, точечно нанятый «финансист») может не иметь широкой
    # вкладки ФЭО вовсе, у него есть только персональное/субсидийное action-право
    # 'plan_excess.decide', которое и проверяется ниже (has_org_key). Внешний
    # тab-гейт здесь только исключал бы таких людей.
    current_user: User = Depends(get_current_user),
):
    approval = await _load_approval(approval_id, db)

    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(422, "decision должен быть 'approved' или 'rejected'")

    step_id = body.get("step_id")
    step: PlanExcessApprovalStep | None = None
    if step_id:
        step = next((s for s in approval.steps if s.id == int(step_id)), None)
    else:
        # Без явного step_id — первый pending-шаг, назначенный текущему пользователю
        step = next(
            (s for s in approval.steps if s.status == "pending" and s.user_id == current_user.id),
            None,
        )
    if step is None:
        raise HTTPException(404, "Шаг согласования не найден")

    if step.status != "pending":
        raise HTTPException(400, f"По этому шагу уже принято решение: {step.status}")

    subsidy = await db.get(Subsidy, approval.subsidy_id)
    if subsidy is None:
        raise HTTPException(404, "Субсидия не найдена")

    is_saas = _is_saas(current_user)

    # Владелец (2026-08-29): «превышение не может согласовывать любой из цепочки
    # согласования… только определённые люди — например, только владельцы или
    # только финансисты». Право выдаётся точечно (галочкой), никому не положено
    # по умолчанию — см. app.auth.permissions.has_org_key + action-ключ
    # 'plan_excess.decide'. SaaS-роли (superadmin/account_owner) — бессрочный
    # обход, как и везде в проекте.
    if not is_saas:
        if not await has_org_key(current_user, db, subsidy.org_id, "plan_excess.decide", subsidy_id=approval.subsidy_id):
            raise HTTPException(
                403,
                "Право на согласование превышения плана ФЭО не выдано, обратитесь к администратору",
            )

    # Нельзя решать за другого — даже имея право plan_excess.decide, закрыть
    # можно только СВОЙ назначенный шаг (кроме SaaS — им можно разрулить любой
    # зависший шаг).
    if not is_saas and step.user_id != current_user.id:
        raise HTTPException(403, "Это не ваш шаг согласования — решение может принять только назначенный согласующий")

    # Самосогласование запрещено: автор запроса не может согласовывать
    # собственное превышение плана (владелец, 2026-08-29: «согласование — это
    # не согласование превышения» самого заявителя).
    if not is_saas and approval.requested_by_id == current_user.id:
        raise HTTPException(403, "Автор запроса не может согласовывать собственное превышение плана")

    if approval.status != "pending":
        raise HTTPException(400, f"По этому запросу уже принято решение: {approval.status}")

    # Sequential: нельзя согласовать, пока нижестоящие (меньший order_num) ещё pending
    if approval.mode == "sequential":
        lower_pending = any(
            s.order_num < step.order_num and s.status == "pending" for s in approval.steps
        )
        if lower_pending:
            raise HTTPException(
                400,
                "Последовательное согласование: сначала должны согласовать нижестоящие в цепочке.",
            )

    step.status = decision
    step.comment = body.get("comment")
    step.decided_at = datetime.now(timezone.utc)
    step.decided_by_user_id = current_user.id
    await db.flush()

    if decision == "rejected":
        approval.status = "rejected"
        approval.resolved_at = datetime.now(timezone.utc)
        approval.comment = body.get("comment")
    else:
        remaining = any(s.status == "pending" for s in approval.steps)
        if not remaining:
            approval.status = "approved"
            approval.resolved_at = datetime.now(timezone.utc)

    step_id_decided = step.id
    decided_by_name = current_user.full_name or current_user.username
    await db.commit()
    full = await _load_approval(approval_id, db)

    cat = await db.get(FeoCategory, full.feo_category_id)
    cat_name = cat.name if cat else f"категория №{full.feo_category_id}"
    decided_step = next((s for s in full.steps if s.id == step_id_decided), None)
    if decided_step is not None:
        await _notify_plan_excess_decision(full, decided_step, db, decided_by_name, cat_name)

    return _approval_dict(full)
