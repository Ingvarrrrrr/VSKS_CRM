"""type_excess_approval.py — согласование превышения плана/факта ПО ТИПУ
(товары/услуги), независимого от «план над ФЭО»/«ТЗ над плановой позицией»
(план ancient-prancing-music.md, раздел E, 2026-09-21).

Владелец продукта (21.09, ночь, AskUserQuestion): два НОВЫХ контроля превышения,
каждый со своим согласованием — «план по товарам (услугам) над ФЭО по товарам
(услугам)» и «закупки по товарам (услугам) над планом по товарам (услугам)» —
на ДВУХ уровнях (категория ФЭО И субсидия целиком), согласование — «как
существующее превышение»: те же моменты срабатывания и те же согласующие
субсидии (право 'plan_excess.decide'), в запросе виден вид контроля.

Написан по образцу app.services.tz_excess_approval (тот же общий механизм —
СУЩЕСТВУЮЩАЯ модель app.models.plan_excess_approval.PlanExcessApproval,
переиспользуются app.routers.plan_excess._authorized_plan_excess_approvers/
_notify_pending_plan_excess_approvers/_load_approval/_approval_dict —
копии этой логики здесь НЕТ, ПРАВИЛО №6). Сама величина «превышение по типу»
считается ОДНИМ местом — app.services.feo_plan_tree.compute_feo_plan_tree
(узловые поля plan_goods/feo_goods/fact_goods и т.п., excess_plan_over_feo_goods
и 3 других) и её же app.services.feo_plan_tree.compute_subsidy_type_summary
(уровень субсидии) — этот файл их не пересчитывает, только читает.

Отличие от tz_excess_approval.py: там нарушение — рассинхрон ОДНОЙ строки ТЗ
с её ПЛАНОВОЙ ПОЗИЦИЕЙ (feo_planned_item_id), собираемый заново по «живым»
items на каждый вызов. Здесь нарушение — уже готовое агрегированное число
УЗЛА ДЕРЕВА (или субсидии целиком), видов четыре (kind, см.
app.services.plan_excess_kinds): PLAN_OVER_FEO_GOODS/SERVICES,
FACT_OVER_PLAN_GOODS/SERVICES, на двух уровнях (LEVEL_CATEGORY/LEVEL_SUBSIDY,
feo_category_id=None для уровня субсидии).

Точки вызова (РЕШЕНИЕ ВЛАДЕЛЬЦА от 21.09, повторное уточнение — контроль по
типу МЯГКИЙ везде, не только на create/PUT/wish; изначальный план «жёстко на
переходах» ниже пересмотрен):
  - routers/purchase_transitions.py — МЯГКО: collect_type_excess_violations +
    register_type_excess_approvals на КАЖДОМ forward-переходе закупки, тем же
    набором категорий (_gate_cat_ids), что уже проверяет
    assert_no_unapproved_excess (тоже мягкий) — результат подмешивается в
    excess_warnings ответа перехода. Жёсткий гейт «ТЗ над плановой позицией»
    (assert_no_pending_tz_excess) на переходах НЕ затронут — остаётся 409.
    assert_no_pending_type_excess (жёсткая версия, ниже) здесь БОЛЬШЕ НЕ
    вызывается — оставлена в файле про запас (прямые тесты — см.
    tests/test_type_excess_approval.py);
  - routers/purchases.py create/PUT — МЯГКО: collect_type_excess_violations +
    register_type_excess_approvals, результат подмешивается в excess_warnings
    (тот же паттерн, что и остальные предупреждения этих эндпоинтов);
  - routers/wish_convert.py, services/wish_distribution.py — МЯГКО, там же,
    где уже регистрируются превышения ТЗ (register_tz_excess_approvals).
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import plan_excess_kinds as PEK

# (kind, поле-разница-узла, поле-«сверху», поле-«снизу») — четыре вида, оба
# уровня (категория/субсидия) используют ОДНИ И ТЕ ЖЕ имена полей (compute_
# feo_plan_tree.node и compute_subsidy_type_summary.totals используют
# одинаковые ключи plan_goods/feo_goods/... нарочно, см. их докстринги).
_NODE_SPECS = (
    (PEK.PLAN_OVER_FEO_GOODS, "excess_plan_over_feo_goods", "plan_goods", "feo_goods"),
    (PEK.PLAN_OVER_FEO_SERVICES, "excess_plan_over_feo_services", "plan_services", "feo_services"),
    (PEK.FACT_OVER_PLAN_GOODS, "excess_fact_over_plan_goods", "fact_goods", "plan_goods"),
    (PEK.FACT_OVER_PLAN_SERVICES, "excess_fact_over_plan_services", "fact_services", "plan_services"),
)
_SUMMARY_SPECS = (
    (PEK.PLAN_OVER_FEO_GOODS, "plan_over_feo_goods", "plan_goods", "feo_goods"),
    (PEK.PLAN_OVER_FEO_SERVICES, "plan_over_feo_services", "plan_services", "feo_services"),
    (PEK.FACT_OVER_PLAN_GOODS, "fact_over_plan_goods", "fact_goods", "plan_goods"),
    (PEK.FACT_OVER_PLAN_SERVICES, "fact_over_plan_services", "fact_services", "plan_services"),
)


def _violation_message(kind: str, name: str, top_amount: float, bottom_amount: float, excess: float, *, is_subsidy: bool = False) -> str:
    """Единственный источник текста нарушения — и предупреждение
    (excess_warnings), и комментарий к запросу согласования, и 409 читают
    отсюда (ПРАВИЛО №6 — не дублировать текст по роутерам)."""
    label = PEK.kind_label(kind)
    scope = f"по субсидии «{name}» целиком" if is_subsidy else f"по категории ФЭО «{name}»"
    top_d = Decimal(str(top_amount))
    bottom_d = Decimal(str(bottom_amount))
    excess_d = Decimal(str(excess))
    if kind in (PEK.PLAN_OVER_FEO_GOODS, PEK.PLAN_OVER_FEO_SERVICES):
        return (
            f"{label} {scope}: план {top_d:,.2f} ₽, финансирование по ФЭО (по этому типу) "
            f"{bottom_d:,.2f} ₽, превышение {excess_d:,.2f} ₽."
        )
    return (
        f"{label} {scope}: план {bottom_d:,.2f} ₽, факт {top_d:,.2f} ₽, превышение {excess_d:,.2f} ₽."
    )


async def collect_type_excess_violations(
    db: AsyncSession, subsidy_id: Optional[int], category_ids,
) -> list[dict]:
    """Считает 4 вида превышения ПО ТИПУ (см. _NODE_SPECS/_SUMMARY_SPECS) — по
    КАЖДОЙ переданной категории (уровень 'category') И по субсидии целиком
    (уровень 'subsidy', проверяется ВСЕГДА, если subsidy_id задан — она не
    привязана к конкретному набору категорий). НЕ бросает — только собирает,
    как и app.services.tz_excess_approval.collect_tz_over_plan_violations.

    Возвращает список {kind, level, feo_category_id, plan_amount, budget_amount,
    excess_amount, message}. Пустой список — превышений нет."""
    if not subsidy_id:
        return []
    from app.models.feo_category import FeoCategory
    from app.models.subsidy import Subsidy
    from app.services.feo_plan_tree import compute_feo_plan_tree, compute_subsidy_type_summary

    cat_ids = sorted({c for c in (category_ids or []) if c})
    tree = await compute_feo_plan_tree(db, [subsidy_id])
    violations: list[dict] = []

    cat_names: dict[int, str] = {}
    if cat_ids:
        rows = (await db.execute(select(FeoCategory.id, FeoCategory.name).where(FeoCategory.id.in_(cat_ids)))).all()
        cat_names = {r.id: r.name for r in rows}

    for cid in cat_ids:
        node = tree.get(cid)
        if node is None:
            continue
        name = cat_names.get(cid, f"#{cid}")
        for kind, excess_key, top_key, bottom_key in _NODE_SPECS:
            amt = node.get(excess_key) or 0.0
            if amt <= 0.005:
                continue
            top_v = node.get(top_key) or 0.0
            bottom_v = node.get(bottom_key) or 0.0
            violations.append({
                "kind": kind,
                "level": PEK.LEVEL_CATEGORY,
                "feo_category_id": cid,
                "category_name": name,
                "plan_amount": top_v,
                "budget_amount": bottom_v,
                "excess_amount": amt,
                "message": _violation_message(kind, name, top_v, bottom_v, amt),
            })

    summary = await compute_subsidy_type_summary(db, subsidy_id, tree)
    subsidy = await db.get(Subsidy, subsidy_id)
    subsidy_name = subsidy.name if subsidy else f"#{subsidy_id}"
    for kind, excess_key, top_key, bottom_key in _SUMMARY_SPECS:
        exc = (summary.get("excess") or {}).get(excess_key) or {}
        amt = exc.get("amount") or 0.0
        if amt <= 0.005:
            continue
        top_v = (summary.get("totals") or {}).get(top_key) or 0.0
        bottom_v = (summary.get("totals") or {}).get(bottom_key) or 0.0
        violations.append({
            "kind": kind,
            "level": PEK.LEVEL_SUBSIDY,
            "feo_category_id": None,
            "category_name": subsidy_name,
            "plan_amount": top_v,
            "budget_amount": bottom_v,
            "excess_amount": amt,
            "message": _violation_message(kind, subsidy_name, top_v, bottom_v, amt, is_subsidy=True),
        })
    return violations


async def register_type_excess_approvals(
    db: AsyncSession,
    violations: list[dict],
    *,
    subsidy_id: Optional[int],
    current_user,
    context_label: str,
) -> list[dict]:
    """Регистрирует превышения из collect_type_excess_violations как запросы
    PlanExcessApproval — ОДИН запрос на (feo_category_id, kind) — переиспользует
    pending той же пары, как и остальные виды (см. compute_feo_plan_tree.
    _latest_approval/latest_approval_by_cat_kind).

    ГРАНИЦА (та же, что у register_tz_excess_approvals — «нельзя, чтобы
    превышение молча проходило»): нет ни одного уполномоченного
    ('plan_excess.decide') на организацию субсидии → HTTPException 409 (не
    пропускает молча).

    Возвращает список словарей запросов (app.routers.plan_excess._approval_dict)
    — для excess_warnings/аналогичных полей ответа. commit НЕ делает.
    """
    if not violations or not subsidy_id:
        return []
    from app.models.subsidy import Subsidy
    from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
    from app.auth.jwt import get_single_org_id
    # Лениво из РОУТЕРА plan_excess (тот же приём, что и в tz_excess_approval.py) —
    # не заводим вторую копию _authorized_plan_excess_approvers/уведомлений.
    from app.routers.plan_excess import (
        _authorized_plan_excess_approvers,
        _notify_pending_plan_excess_approvers,
        _load_approval,
        _approval_dict,
    )

    subsidy = await db.get(Subsidy, subsidy_id)
    if subsidy is None:
        return []
    org_id = subsidy.org_id or get_single_org_id(current_user)
    if not org_id:
        raise HTTPException(
            409,
            "Не удалось определить организацию субсидии — согласование превышения по типу "
            "(товары/услуги) невозможно настроить.",
        )

    results: list[dict] = []
    requester_name = current_user.full_name or current_user.username

    for v in violations:
        cid = v.get("feo_category_id")
        kind = v["kind"]

        existing_q = select(PlanExcessApproval).where(
            PlanExcessApproval.subsidy_id == subsidy_id,
            PlanExcessApproval.kind == kind,
            PlanExcessApproval.status == "pending",
        )
        existing_q = existing_q.where(PlanExcessApproval.feo_category_id.is_(None)) if cid is None \
            else existing_q.where(PlanExcessApproval.feo_category_id == cid)
        existing_pending = (await db.execute(
            existing_q.order_by(PlanExcessApproval.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if existing_pending:
            full = await _load_approval(existing_pending.id, db)
            results.append(_approval_dict(full))
            continue

        approvers = await _authorized_plan_excess_approvers(
            db, org_id, subsidy_id, exclude_user_id=current_user.id,
        )
        if not approvers:
            raise HTTPException(
                409,
                f"{v['message']} Согласовать некому: ни у одного пользователя организации нет права "
                f"«Согласование превышения плана ФЭО» (plan_excess.decide). Выдайте это право нужному "
                f"кругу лиц (например, финансисту или владельцу организации) и повторите {context_label}.",
            )

        approval = PlanExcessApproval(
            feo_category_id=cid,
            subsidy_id=subsidy_id,
            kind=kind,
            excess_amount=Decimal(str(v["excess_amount"])),
            plan_amount=Decimal(str(v["plan_amount"])) if v.get("plan_amount") is not None else None,
            budget_amount=Decimal(str(v["budget_amount"])) if v.get("budget_amount") is not None else None,
            status="pending",
            mode="sequential",
            requested_by_id=current_user.id,
            comment=f"{v['message']} — {context_label}.",
        )
        db.add(approval)
        await db.flush()

        for i, u in enumerate(approvers):
            db.add(PlanExcessApprovalStep(
                approval_id=approval.id,
                user_id=u.id,
                order_num=i,
                role_name="Уполномочен на согласование превышения",
                approver_full_name=u.full_name or u.username,
                status="pending",
            ))
        await db.flush()

        full = await _load_approval(approval.id, db)
        results.append(_approval_dict(full))
        cat_label = "субсидии целиком" if cid is None else v.get("category_name") or f"#{cid}"
        try:
            await _notify_pending_plan_excess_approvers(full, db, requester_name, cat_label)
        except Exception:
            import logging as _log
            _log.getLogger(__name__).warning(
                "notify type-excess approvers failed for kind %s cat %s", kind, cid,
            )

    return results


async def assert_no_pending_type_excess(
    db: AsyncSession, subsidy_id: Optional[int], category_ids,
) -> None:
    """Блокирует ДАЛЬНЕЙШЕЕ движение закупки, пока превышение по типу (любой
    из 4 видов, на затронутых категориях И на субсидии целиком) не согласовано
    — тот же принцип, что и assert_no_pending_tz_excess (жёстко на forward-
    переходе закупки, см. routers/purchase_transitions.py). Пересчитывает
    нарушения ПРЯМО СЕЙЧАС (через collect_type_excess_violations — то же
    дерево, что видит фронт), approved снимает блокировку ИМЕННО для своего
    (feo_category_id, kind) — без legacy-фолбэка (виды новые, легаси их не
    гасит, см. app.services.plan_excess_kinds.LEGACY_FALLBACK_KINDS).

    Ничего не пишет в БД, не коммитит."""
    if not subsidy_id:
        return
    violations = await collect_type_excess_violations(db, subsidy_id, category_ids)
    if not violations:
        return

    from app.models.plan_excess_approval import PlanExcessApproval

    for v in violations:
        cid = v.get("feo_category_id")
        kind = v["kind"]
        q = select(PlanExcessApproval).where(
            PlanExcessApproval.subsidy_id == subsidy_id,
            PlanExcessApproval.kind == kind,
        )
        q = q.where(PlanExcessApproval.feo_category_id.is_(None)) if cid is None \
            else q.where(PlanExcessApproval.feo_category_id == cid)
        appr = (await db.execute(q.order_by(PlanExcessApproval.created_at.desc()).limit(1))).scalar_one_or_none()
        if appr is not None and appr.status == "approved":
            continue

        status_txt = {
            "pending": "запрос на согласование ещё не решён",
            "rejected": "запрос на согласование отклонён",
        }.get(appr.status if appr else None, "запрос на согласование ещё не создан")
        raise HTTPException(
            409,
            {
                "code": "TYPE_EXCESS_PENDING",
                "message": (
                    f"{v['message']} {status_txt}. Дальнейшее движение закупки (смена стадии/договор) "
                    f"заблокировано, пока уполномоченный (право «Согласование превышения плана ФЭО») "
                    f"не одобрит превышение."
                ),
                "feo_category_id": cid,
                "kind": kind,
                "level": v["level"],
                "plan_excess_approval_id": appr.id if appr else None,
            },
        )
