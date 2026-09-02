"""tz_excess_approval.py — согласование превышения ТЗ позиции над её ПЛАНОВОЙ
ПОЗИЦИЕЙ (FeoPlannedItem), а не над бюджетом ФЭО категории целиком.

Владелец продукта (2026-09-02), дословно: «это же заявка согласуется, это
согласуется её необходимость, попасть должно в План-закупок, финансист (тот,
у кого есть право согласовывать превышение) видит, что люди просят, и решает —
пропускает её или нет. Но дальше двигаться нельзя по закупке без его
согласования».

Живой случай (прод): заявка №52, позиция «Логистические услуги», категория ФЭО
«Организационные расходы на содержание штаба» (id 125). Бюджет категории
330 100 ₽, свободно 318 830 ₽ — денег полно. Но единственная плановая позиция
внутри (id 1417) — всего 11 270,19 ₽, а ТЗ 48 935,05 ₽. app.services.feo_plan.
assert_tz_not_over_plan/assert_tz_batch_not_over_plan бросают жёсткий 409 БЕЗ
единого обхода по правам — согласующий с правом plan_excess.decide не мог
пропустить заявку никак.

── Почему это ТРЕТИЙ, независимый вид превышения (не входит в
   app.services.feo_plan.assert_no_unapproved_excess) ──────────────────────
compute_feo_plan_tree (feo_plan.py) знает только про ТРИ вида превышения на
уровне УЗЛА ДЕРЕВА ФЭО: план дороже бюджета категории (excess_over_feo), факт
дороже плана (excess_fact_over_plan) и Σ плановых позиций дороже ручного плана
(excess_plan_over_manual). Ни один из них не видит рассинхрон ОДНОЙ строки ТЗ
с её КОНКРЕТНОЙ плановой позицией сразу — доказано анализом:
  - plan_manual категории = Σ AMOUNT активных FeoPlannedItem (эта сумма не
    меняется от того, что чья-то PurchaseItem.total_price её превышает — сама
    плановая позиция как запись в БД остаётся 11 270,19 ₽);
  - позиции с валидной feo_planned_item_id ИСКЛЮЧЕНЫ из «consumed»/«ordered»
    (exclude_planned_item_linked=True) — «уже учтены своей плановой строкой»;
  - «fact» (excess_fact_over_plan) начинает видеть эту сумму ТОЛЬКО когда
    purchase.status уже в FACT_PRICED_STATUSES (work_in_progress и далее) И
    заполнены contract_price/ContractItem/final_total — то есть НЕ в момент
    согласования заявки (закупка ещё в plan_schedule), а значительно позже.
Поэтому регистрировать превышение приходится ЗДЕСЬ, отдельным (но
переиспользующим ту же таблицу) запросом PlanExcessApproval, а не полагаясь
на то, что assert_no_unapproved_excess когда-нибудь его увидит сам.

── Как это согласуется ──────────────────────────────────────────────────────
Используется СУЩЕСТВУЮЩАЯ модель app.models.plan_excess_approval.PlanExcessApproval
(та же таблица, тот же список «Согласование превышения плана ФЭО», тот же набор
уполномоченных — app.routers.plan_excess._authorized_plan_excess_approvers,
переиспользуется как есть, копии логики НЕТ). Кто именно уполномочен решать —
задаётся действием 'plan_excess.decide', как и у остальных трёх видов
превышения; финализирующее approved-решение по КАТЕГОРИИ снимает блокировку
для ВСЕХ видов сразу (см. feo_plan.compute_feo_plan_tree — «latest_approval_by_cat»
берёт последний запрос по категории независимо от того, какой вид превышения
его породил).

Комментарии здесь и в вызывающем коде (app/routers/wishes.py, app/routers/
purchases.py) написаны так, чтобы НЕ трогать app/services/feo_plan.py вообще —
это прямой запрет задачи (там незакоммиченная работа другого исполнителя).

── Блокировка дальнейшего движения (assert_no_pending_tz_excess) ──────────
compute_feo_plan_tree узнаёт про approved-запрос по категории и учитывает его
в excess_fact_approved и т.п., НО сам факт появления excess_fact_over_plan (а
значит и сам гейт assert_no_unapproved_excess) включается для ЭТОГО вида
превышения только на «Ведущейся работе» с заполненной ценой договора — то
есть ПОЗЖЕ первого форвард-перехода «План закупок» → «Ведётся работа». Значит
assert_no_unapproved_excess САМ ПО СЕБЕ НЕ блокирует самый первый шаг движения
закупки дальше «Плана закупок» для этого вида превышения — дыра ровно та, на
которую указывает формулировка задачи («если не покрывает — предложи
минимальное решение, не правя feo_plan.py»). assert_no_pending_tz_excess ниже
закрывает её независимым, отдельным гейтом (пересчитывает нарушения ТЗ по
живым PurchaseItem закупки и проверяет ПОСЛЕДНИЙ PlanExcessApproval по
затронутым категориям — та же семантика «approved снимает блок», что и у
assert_no_unapproved_excess, но не дублирует её код и не трогает feo_plan.py).
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feo_plan import assert_tz_not_over_plan


def _tz_check_units(items, fallback_category_id: Optional[int]) -> list[dict]:
    """Разбивка списка строк ТЗ на «единицы проверки» — ТОЧНАЯ копия группировки
    (individuals/groups по feo_planned_item_id) из
    app.services.feo_plan.assert_tz_batch_not_over_plan, вынесенная сюда ТОЛЬКО
    потому, что batch-версия бросает исключение на ПЕРВОМ нарушении и
    останавливается — нам нужно проверить КАЖДУЮ группу отдельно, поймав
    исключение каждой по отдельности, чтобы не пропустить второе/третье
    нарушение в одной операции. Сама проверка (сравнение с планом) НЕ
    продублирована — вызывается настоящая feo_plan.assert_tz_not_over_plan
    ниже, единственный источник истины для «что считается превышением».
    """
    groups: dict[int, list] = {}
    individuals: list = []
    for row in items:
        if getattr(row, "over_plan", False):
            continue
        fpi_id = getattr(row, "feo_planned_item_id", None)
        if fpi_id:
            groups.setdefault(fpi_id, []).append(row)
        else:
            individuals.append(row)

    units: list[dict] = []
    for row in individuals:
        units.append({
            "feo_planned_item_id": None,
            "feo_category_id": getattr(row, "feo_category_id", None) or fallback_category_id,
            "quantity": row.quantity,
            "unit_price": row.unit_price,
            "total_price": row.total_price,
            "item_name": row.item_name,
            "sibling_quantity": 0,
            "sibling_total": 0,
        })

    for fpi_id, group_rows in groups.items():
        first = group_rows[0]
        siblings = group_rows[1:]

        max_price = Decimal("0")
        for r in group_rows:
            r_price = Decimal(str(r.unit_price)) if r.unit_price is not None else Decimal("0")
            if r_price > max_price:
                max_price = r_price

        own_qty = Decimal(str(first.quantity)) if first.quantity is not None else Decimal("0")
        own_price = Decimal(str(first.unit_price)) if first.unit_price is not None else Decimal("0")
        own_total = Decimal(str(first.total_price)) if first.total_price is not None else (own_qty * own_price)

        sib_qty = Decimal("0")
        sib_total = Decimal("0")
        for r in siblings:
            r_qty = Decimal(str(r.quantity)) if r.quantity is not None else Decimal("0")
            r_price = Decimal(str(r.unit_price)) if r.unit_price is not None else Decimal("0")
            r_total = Decimal(str(r.total_price)) if r.total_price is not None else (r_qty * r_price)
            sib_qty += r_qty
            sib_total += r_total

        name = (first.item_name or "").strip() or "позиция"
        if len(group_rows) > 1:
            name = f"{name} и ещё {len(group_rows) - 1} поз."
        units.append({
            "feo_planned_item_id": fpi_id,
            "feo_category_id": (getattr(first, "feo_category_id", None) or fallback_category_id),
            "quantity": own_qty,
            "unit_price": max_price,
            "total_price": own_total,
            "item_name": name,
            "sibling_quantity": sib_qty,
            "sibling_total": sib_total,
        })
    return units


async def collect_tz_over_plan_violations(
    db: AsyncSession, items, fallback_category_id: Optional[int] = None,
) -> list[dict]:
    """Считает ТЕ ЖЕ нарушения, что бросил бы
    feo_plan.assert_tz_batch_not_over_plan(db, items, fallback_category_id=...),
    но НЕ бросает — ловит HTTPException каждой единицы (см. _tz_check_units) по
    отдельности и возвращает список {feo_category_id, item_name, amount, message}.

    Пустой список — превышений нет (обычный путь для подавляющего большинства
    заявок — вызывающему коду ничего дальше делать не нужно).
    """
    violations: list[dict] = []
    for unit in _tz_check_units(items, fallback_category_id):
        try:
            await assert_tz_not_over_plan(
                db,
                feo_planned_item_id=unit["feo_planned_item_id"],
                feo_category_id=unit["feo_category_id"],
                quantity=unit["quantity"],
                unit_price=unit["unit_price"],
                total_price=unit["total_price"],
                item_name=unit["item_name"],
                sibling_quantity=unit["sibling_quantity"],
                sibling_total=unit["sibling_total"],
            )
        except HTTPException as e:
            msg = e.detail if isinstance(e.detail, str) else str(e.detail)
            total = Decimal(str(unit["total_price"] or 0)) + Decimal(str(unit["sibling_total"] or 0))
            violations.append({
                "feo_category_id": unit["feo_category_id"],
                "feo_planned_item_id": unit["feo_planned_item_id"],
                "item_name": unit["item_name"],
                "amount": float(total),
                "message": msg,
            })
    return violations


async def register_tz_excess_approvals(
    db: AsyncSession,
    violations: list[dict],
    *,
    subsidy_id: Optional[int],
    current_user,
    context_label: str,
) -> list[dict]:
    """Регистрирует превышения из collect_tz_over_plan_violations как запросы
    PlanExcessApproval (СУЩЕСТВУЮЩИЙ механизм — app.models.plan_excess_approval,
    та же таблица/уполномоченные, что у согласования превышения плана над
    бюджетом ФЭО, см. app.routers.plan_excess). Один запрос на КАТЕГОРИЮ —
    несколько нарушенных строк в одной категории схлопываются в один запрос
    (текст перечисляет все).

    ГРАНИЦА задачи (обязательна): «нельзя, чтобы превышение молча проходило».
    Если по категории уже нет ни одного пользователя с правом
    'plan_excess.decide' — запрос зарегистрировать некому, и функция БРОСАЕТ
    HTTPException 409 (не пропускает молча) — тот же принцип отказа, что был
    у исходного assert_tz_not_over_plan/assert_tz_batch_not_over_plan, просто
    с объяснением, что согласовывать некому. Существующий pending-запрос по
    той же категории переиспользуется (идемпотентность — повторное
    согласование заявки не плодит дубли).

    Возвращает список словарей запросов (тот же формат, что
    app.routers.plan_excess._approval_dict) — для видимости в ответе API
    (по образцу excess_warnings/_collect_excess_warnings в app.routers.wishes).
    commit НЕ делает — на вызывающем (тот же принцип, что и у остальных
    гейтов/сборщиков в этом модуле).
    """
    if not violations or not subsidy_id:
        return []

    from app.models.subsidy import Subsidy
    from app.models.feo_category import FeoCategory
    from app.models.plan_excess_approval import PlanExcessApproval, PlanExcessApprovalStep
    from app.auth.jwt import get_single_org_id
    # Лениво импортируем из РОУТЕРА plan_excess — тот же приём, что уже
    # используется в этом проекте сплошь и рядом (например, feo_plan.py сам
    # импортирует app.routers.subsidies/purchase_budget лениво), чтобы не
    # плодить вторую копию _authorized_plan_excess_approvers/уведомлений.
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
            "Не удалось определить организацию субсидии — согласование превышения ТЗ над "
            "плановой позицией невозможно настроить.",
        )

    by_cat: dict[int, list[dict]] = {}
    for v in violations:
        cid = v.get("feo_category_id")
        if cid:
            by_cat.setdefault(cid, []).append(v)

    results: list[dict] = []
    requester_name = current_user.full_name or current_user.username

    for cid, cat_violations in by_cat.items():
        cat = await db.get(FeoCategory, cid)
        cat_name = cat.name if cat else f"#{cid}"

        existing_pending = (await db.execute(
            select(PlanExcessApproval).where(
                PlanExcessApproval.feo_category_id == cid,
                PlanExcessApproval.status == "pending",
            ).order_by(PlanExcessApproval.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if existing_pending:
            full = await _load_approval(existing_pending.id, db)
            results.append(_approval_dict(full))
            continue

        approvers = await _authorized_plan_excess_approvers(
            db, org_id, subsidy_id, exclude_user_id=current_user.id,
        )
        if not approvers:
            names = "; ".join(f"«{it['item_name']}»" for it in cat_violations[:5])
            raise HTTPException(
                409,
                f"ТЗ по категории ФЭО «{cat_name}» превышает плановую позицию ({names}), а "
                f"согласовать это превышение некому: ни у одного пользователя организации нет "
                f"права «Согласование превышения плана ФЭО» (plan_excess.decide). Выдайте это "
                f"право нужному кругу лиц (например, финансисту или владельцу организации) и "
                f"повторите {context_label}.",
            )

        total_excess = sum(Decimal(str(it["amount"])) for it in cat_violations)
        items_desc = "; ".join(
            f"«{it['item_name']}» ({Decimal(str(it['amount'])):,.2f} ₽): {it['message']}"
            for it in cat_violations
        )
        approval = PlanExcessApproval(
            feo_category_id=cid,
            subsidy_id=subsidy_id,
            excess_amount=total_excess,
            plan_amount=None,
            budget_amount=None,
            status="pending",
            mode="sequential",
            requested_by_id=current_user.id,
            comment=(
                f"ТЗ позиции превышает СВОЮ плановую позицию (бюджет ФЭО категории при этом "
                f"может быть свободен) — {context_label}. {items_desc}"
            ),
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
        try:
            await _notify_pending_plan_excess_approvers(full, db, requester_name, cat_name)
        except Exception:
            import logging as _log
            _log.getLogger(__name__).warning("notify tz-excess approvers failed for cat %s", cid)

    return results


async def assert_no_pending_tz_excess(
    db: AsyncSession, items, fallback_category_id: Optional[int] = None,
) -> None:
    """Блокирует ДАЛЬНЕЙШЕЕ движение закупки, пока item-level превышение ТЗ над
    плановой позицией (зарегистрированное register_tz_excess_approvals выше) не
    согласовано — закрывает дыру, описанную в докстринге модуля
    (assert_no_unapproved_excess из feo_plan.py сам по себе не видит этот вид
    превышения на самом первом форвард-переходе).

    Пересчитывает нарушения ПРЯМО СЕЙЧАС по переданным `items` (НЕ полагается на
    снимок violations на момент регистрации — состав закупки мог измениться),
    затем для каждой затронутой категории смотрит на ПОСЛЕДНИЙ (по created_at)
    PlanExcessApproval — approved снимает блокировку (та же семантика «последний
    запрос решает», что и в feo_plan.compute_feo_plan_tree latest_approval_by_cat),
    pending/rejected/отсутствует — блокирует.

    items — ЖИВЫЕ строки, которые реально будут в закупке после этого действия:
    вызывающий код сам решает, что подставить — уже персистентные
    Purchase.items (переход статуса существующей закупки, состав не меняется,
    см. purchase_transitions.py) ИЛИ ещё не сохранённые items_data (PUT
    заменяет все позиции целиком — старый p.items тут не годится, см. update_purchase).
    Ничего не пишет в БД, не коммитит.
    """
    from app.models.plan_excess_approval import PlanExcessApproval
    from app.models.feo_category import FeoCategory

    items = list(items or [])
    if not items:
        return
    violations = await collect_tz_over_plan_violations(
        db, items, fallback_category_id=fallback_category_id,
    )
    if not violations:
        return

    by_cat: dict[int, list[dict]] = {}
    for v in violations:
        cid = v.get("feo_category_id")
        if cid:
            by_cat.setdefault(cid, []).append(v)

    for cid, cat_violations in by_cat.items():
        appr = (await db.execute(
            select(PlanExcessApproval)
            .where(PlanExcessApproval.feo_category_id == cid)
            .order_by(PlanExcessApproval.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if appr is not None and appr.status == "approved":
            continue

        cat = await db.get(FeoCategory, cid)
        cat_name = cat.name if cat else f"#{cid}"
        names = "; ".join(f"«{it['item_name']}»" for it in cat_violations[:5])
        status_txt = {
            "pending": "запрос на согласование ещё не решён",
            "rejected": "запрос на согласование отклонён",
        }.get(appr.status if appr else None, "запрос на согласование ещё не создан")
        raise HTTPException(
            409,
            {
                "code": "TZ_EXCESS_OVER_PLANNED_ITEM_PENDING",
                "message": (
                    f"ТЗ по категории ФЭО «{cat_name}» превышает плановую позицию ({names}) — "
                    f"{status_txt}. Дальнейшее движение закупки (смена стадии/договор) "
                    f"заблокировано, пока уполномоченный (право «Согласование превышения плана "
                    f"ФЭО») не одобрит превышение."
                ),
                "feo_category_id": cid,
                "plan_excess_approval_id": appr.id if appr else None,
            },
        )
