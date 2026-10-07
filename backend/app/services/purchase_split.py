"""Тело разбиения закупки на дочерние (POST /api/purchases/{pid}/split) —
вынесено из app/routers/purchase_ops.py (ПРАВИЛО №5, модульность; роутер
остаётся тонким — только auth/HTTP-обвязка).

Баг (прод, субсидия «ЛНР» id 74, закупка РЕЕ-2026-00957, задача 07.10.2026):
закупку в статусе paid (с договором — временный номер, 4 позиции, ручной
платёж из импорта факта) владелец «Разбил» на 4 части — все части получились
'planned', без договора/контрагента/платежей, а платёж остался на исходной
(статус 'split', дашборд её не считает) — деньги и статья ФЭО потерялись.

Это исправление: часть НАСЛЕДУЕТ стадию исходной (если та уже «в договоре» —
contracted/ordered/delivered/paid), получает СВОЙ договор (или разрез ТОГО ЖЕ
реального договора — см. docstring split_purchase_core) и СВОЮ долю платежей
(пропорционально сумме своих позиций). ПРАВИЛО №6: списки полей ниже —
ЕДИНСТВЕННЫЙ источник того, что переносится при разбиении; тот же список
переиспользует backend/scripts/fix_split_paid_957.py для починки уже
созданных (сломанных) частей на проде — не копия, а вызов этих же функций.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contract import Contract
from app.models.contract_item import ContractItem
from app.models.payment import Payment
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.purchase_event import PurchaseEvent, PurchaseMember
from app.models.subsidy import Subsidy
from app.models.user import User

LOCKED_STATUSES = {"contracted", "delivered", "paid"}

# Статусы, на которых закупка уже «в договоре» — часть разбиения наследует ТОТ
# ЖЕ статус (не откатывается в 'planned'), иначе разбиение задним числом
# теряло бы договор/оплату. Тот же набор значений (другая семантика — «можно
# ли наследовать стадию», не «ранг для сравнения»), что historical_fact_import/
# existing_update.py::RANK содержит для рангов 2..5.
STAGE_STATUSES = {"contracted", "ordered", "delivered", "paid"}

# Поля PurchaseItem, переносимые в копию при разбиении (сверх purchase_id,
# который выставляется явно). Сознательно НЕ копируются: id, receipt_id
# (чек исходной закупки не «расщепляется» между частями), split_column_key
# (черновик раскладки канбана именно исходной закупки — бессмысленен в копии).
ITEM_COPY_FIELDS = [
    "product_id", "item_name", "item_type", "quantity", "unit", "unit_price",
    "total_price", "final_unit_price", "final_total",
    "planned_quantity", "planned_unit_price", "planned_total",
    "country_origin", "feo_planned_item_id", "feo_category_id",
    "match_confirmed", "contractor_id", "contractor_inn", "contractor_name",
    "vat_rate", "vat_amount", "total_with_vat", "vat_on_top",
    "needed_date", "wish_item_id", "over_plan",
    "accepted_name", "accepted_quantity", "accepted_unit", "item_form",
]

# Поля Purchase, которые часть наследует от исходной ТОЛЬКО когда исходная уже
# «в договоре» (purchase.status in STAGE_STATUSES) — денормализованные поля
# договора/условий уже заключённой сделки. contract_number/contract_date сюда
# НЕ входят — обрабатываются отдельно (см. split_purchase_core: реальный номер
# наследуется явно на все части, временный генерируется заново КАЖДОЙ частью).
STAGE_CONTRACT_FIELDS = [
    "contractor_id", "purchase_method", "competitive_form", "is_prepayment",
    "prepayment_date", "purchase_contract_type", "contract_form", "methodology",
    "vat_applicable", "vat_rate", "vat_exemption_article", "tz_vat_on_top",
    "contract_vat_on_top", "vat_mode", "payment_basis_type", "purchase_basis",
    "responsible_person", "description_mode", "third_party_involved",
    "delivery_by_supplier", "has_stages", "warranty_period_days",
    "warranty_period_unit", "is_retroactive", "acceptance_term_days",
    "penalty_rate", "contractor_ogrnip_date",
    "commission_member_1_name", "commission_member_2_name", "commission_member_3_name",
    "delivery_address", "delivery_region", "delivery_city", "delivery_street",
    "delivery_house", "delivery_building", "delivery_postcode",
    "delivery_location", "delivery_location_kind", "region",
    "service_period_type", "service_start_date", "service_end_date",
    "service_term_mode", "service_term_days", "service_term_type",
    "service_deadline_date", "submission_deadline", "execution_term",
    "execution_term_changed", "delivery_date", "country_origin",
    "treasury_code", "has_pretension", "agreement_number", "agreement_date",
    "order_date", "etp_url", "payment_term_days", "applications_review_date",
    "commitment_quarter", "planned_payment_month", "vehicle_id",
    "repair_request_number", "procurement_protocol_number", "procurement_order_number",
]

# Поля Payment, копируемые на каждую части при разбиении платежа (сверх
# purchase_id/amount, которые выставляются явно для каждой доли).
PAYMENT_COPY_FIELDS = [
    "contract_id", "document_number", "payment_purpose", "payment_date",
    "import_run_id", "bank_payment_id", "matched_confirmed", "payment_source",
    "confirmed_by_statement", "expense_code", "basis_kind", "basis_number",
    "basis_date", "basis_key", "basis_label", "service_period",
]


def ensure_payments_splittable(payments: list[Payment]) -> None:
    """Платёж, подтверждённый выпиской (confirmed_by_statement=True) или
    привязанный к строке выписки (bank_payment_id) — разносится казначейской
    сверкой на ОДНУ закупку; дробить такой платёж молча означало бы либо
    потерять связь со строкой выписки, либо задвоить её на несколько записей.
    Отказываем явно — владелец сначала отменяет сопоставление (вкладка
    «Сверка» субсидии), потом повторяет разбиение."""
    for pay in payments:
        if pay.confirmed_by_statement or pay.bank_payment_id is not None:
            doc = f" №{pay.document_number}" if pay.document_number else ""
            dt = f" от {pay.payment_date}" if pay.payment_date else ""
            raise HTTPException(
                400,
                f"Закупка с платежом, подтверждённым выпиской{doc}{dt}, не разбивается — "
                f"сначала отмените сопоставление с выпиской (вкладка «Сверка» субсидии), "
                f"затем повторите разбиение",
            )


def split_payments_amount(total_amount: Decimal, group_totals: list[Decimal]) -> list[Decimal]:
    """Пропорционально group_totals делит total_amount на len(group_totals) долей,
    последняя доля — остаток (Σ долей == total_amount до копейки, без потерь на
    округлении). Если Σgroup_totals == 0 — делит поровну."""
    n = len(group_totals)
    grand = sum(group_totals, Decimal("0"))
    remaining = total_amount
    shares: list[Decimal] = []
    for i in range(n - 1):
        if grand > 0:
            share = (total_amount * group_totals[i] / grand).quantize(Decimal("0.01"))
        else:
            share = (total_amount / n).quantize(Decimal("0.01"))
        shares.append(share)
        remaining -= share
    shares.append(remaining)
    return shares


async def materialize_part_contract(db: AsyncSession, new_p: Purchase, source: Purchase) -> None:
    """Даёт части договор. ПРАВИЛО №6 — переиспользует
    historical_fact_import/existing_update.py::materialize_contract (та же
    последовательность: временный номер если пуст → ContractItem → Contract
    find-or-create → пересчёт денег), а не копию.

    Решение по реальному договору (владелец, задача 07.10.2026): если у
    исходной закупки contract_number_is_temporary=False (настоящий номер) —
    ВСЕ части получают ТОТ ЖЕ contract_number/contract_date (реальный
    договор один, части — его разрезы, а не отдельные договоры). Это
    безопасно — app/services/contracts_linking.py::ensure_contract_linked уже
    ищет Contract по (number, contractor_id, date, inn) и находит/привязывает
    ОДИН И ТОТ ЖЕ Contract всем частям с одинаковым номером (ровно тот же
    механизм, которым сегодня один рамочный договор уже делится несколькими
    закупками разных субсидий — см. докстринг ensure_contract_linked).
    contract_price/ContractItem при этом считаются ПО КАЖДОЙ закупке отдельно
    (contract_items_materialize.copy_items_to_contract и purchase_money_writer
    scoped по purchase_id) — суммы частей не задваиваются и не путаются.

    Если номер временный (или отсутствует) — каждая часть генерирует СВОЙ
    временный номер (force_temp_number=True), т.к. единого реального договора
    всё равно ещё нет."""
    from app.services.historical_fact_import.existing_update import materialize_contract

    if source.contract_number and not source.contract_number_is_temporary:
        new_p.contract_number = source.contract_number
        new_p.contract_date = source.contract_date
        new_p.contract_number_is_temporary = False
        await materialize_contract(db, new_p, force_temp_number=False)
    else:
        new_p.contract_number = None
        await materialize_contract(db, new_p, force_temp_number=True)


async def cleanup_source_contract(db: AsyncSession, purchase: Purchase) -> None:
    """После того как позиции исходной закупки перенесены в части и сама она
    помечена status='split' — её ContractItem больше ни к чему не привязаны
    (их source_item_id ссылался на уже удалённые PurchaseItem). Чистим явно
    (у исходной закупки Purchase-строка НЕ удаляется, поэтому ON DELETE CASCADE
    по purchase_id не срабатывает — тот механизм, которым полагается
    app/routers/purchases.py::delete_purchase_core, здесь неприменим).

    Если после этого у Contract не осталось ни ContractItem, ни других
    Purchase, ссылающихся на него (contract_id) — договор удаляется целиком,
    тем же простым способом, что app/routers/contracts.py::delete_contract
    (db.delete(contract) — каскады на уровне БД для ContractSubsidy и пр.).

    contract_price/planned_total_price и пр. зануляются ЗДЕСЬ явно, а не через
    recalc_purchase_money — тот модуль СОЗНАТЕЛЬНО не трогает деньги закупки,
    у которой нет вообще ни одной строки (ни PurchaseItem, ни ContractItem) —
    чтобы не затирать легаси-импорт без позиций (см. его докстринг, п.3). Для
    закупки 'split' (позиции разъехались по частям) это ровно наш случай, и
    здесь нам НУЖНО занулить, а не сохранить старое число."""
    await db.execute(delete(ContractItem).where(ContractItem.purchase_id == purchase.id))

    contract_id = purchase.contract_id
    purchase.contract_id = None
    purchase.planned_total_price = 0
    purchase.total_nmck = 0
    purchase.nmck = 0
    purchase.contract_price = 0
    purchase.payment_amount = None
    purchase.payment_amount_declared = None
    await db.flush()

    if contract_id is not None:
        other_items = (await db.execute(
            select(ContractItem.id).where(ContractItem.contract_id == contract_id).limit(1)
        )).scalar_one_or_none()
        other_purchase = (await db.execute(
            select(Purchase.id).where(Purchase.contract_id == contract_id).limit(1)
        )).scalar_one_or_none()
        if other_items is None and other_purchase is None:
            contract = await db.get(Contract, contract_id)
            if contract is not None:
                await db.delete(contract)


async def split_purchase_core(
    pid: int,
    body: dict,
    db: AsyncSession,
    current_user: User,
    *,
    org_filter_ids: Optional[list[int]],
    admin_roles: tuple,
) -> dict:
    """Разбить закупку на N дочерних по группам позиций — полная логика (см.
    модуль docstring). Вызывается из app/routers/purchase_ops.py::split_purchase,
    который делает только auth/depends обвязку и передаёт готовые org_filter_ids/
    admin_roles (чтобы этот модуль не тянул app.auth.jwt напрямую — отделяет
    HTTP-слой от бизнес-логики, ПРАВИЛО №5)."""
    from app.services.purchase_payments import recompute_purchase_payments

    res = await db.execute(
        select(Purchase).options(selectinload(Purchase.items)).where(Purchase.id == pid)
    )
    purchase = res.scalar_one_or_none()
    if purchase is None:
        raise HTTPException(404, "Закупка не найдена")

    if org_filter_ids is not None:
        subsidy_res = await db.execute(select(Subsidy).where(Subsidy.id == purchase.subsidy_id))
        subsidy = subsidy_res.scalar_one_or_none()
        if subsidy and subsidy.org_id not in org_filter_ids:
            raise HTTPException(403, "Нет доступа к закупке")

    if purchase.status in LOCKED_STATUSES and current_user.role not in admin_roles:
        raise HTTPException(403, "Перераспределять закупку в статусе 'Договор' и далее могут только администраторы")
    if purchase.status == "split":
        raise HTTPException(400, "Закупка уже разбита")

    groups = body.get("groups") or []
    groups = [g for g in groups if g.get("item_ids")]
    if len(groups) < 2:
        raise HTTPException(400, "Разбиение требует минимум 2 непустые группы")

    own_item_ids = {it.id for it in purchase.items}
    all_supplied_ids: list[int] = []
    for g in groups:
        for iid in g["item_ids"]:
            if iid not in own_item_ids:
                raise HTTPException(400, f"Позиция {iid} не принадлежит закупке {pid}")
            all_supplied_ids.append(iid)
    if len(all_supplied_ids) != len(set(all_supplied_ids)):
        raise HTTPException(400, "Одна позиция указана в нескольких группах")
    if set(all_supplied_ids) != own_item_ids:
        raise HTTPException(400, "Не все позиции распределены по группам")

    # Платежи исходной — проверяем ДО всего остального: если хоть один привязан
    # к строке выписки, отказываем сразу, не трогая закупку (п.3 задачи).
    payments_res = await db.execute(select(Payment).where(Payment.purchase_id == pid))
    source_payments = list(payments_res.scalars().all())
    ensure_payments_splittable(source_payments)

    mem_res = await db.execute(select(PurchaseMember).where(PurchaseMember.purchase_id == pid))
    source_members = mem_res.scalars().all()

    status_before = purchase.status
    stage_status = purchase.status if purchase.status in STAGE_STATUSES else None
    items_by_id = {it.id: it for it in purchase.items}
    created_ids: list[int] = []
    parts: list[tuple[Purchase, Decimal]] = []  # (новая закупка, Σ total_price её позиций)

    try:
        for g in groups:
            column_key = (g.get("column_key") or "").strip() or "__uncategorized__"
            display_key = "Не определено" if column_key == "__uncategorized__" else column_key
            group_items = [items_by_id[iid] for iid in g["item_ids"]]
            total = sum(float(it.total_price or 0) for it in group_items)
            group_total_dec = sum(
                (Decimal(str(it.total_price)) if it.total_price is not None else Decimal("0")
                 for it in group_items),
                Decimal("0"),
            )

            base_subject = (purchase.subject or purchase.item_name or "").strip()
            new_subject = f"{base_subject} — {display_key}".strip(" —") if base_subject else display_key

            new_p = Purchase(
                subsidy_id=purchase.subsidy_id,
                feo_category_id=purchase.feo_category_id,
                item_name=new_subject or f"Закупка #{purchase.id}",
                subject=new_subject,
                planned_total_price=total,
                total_nmck=total,
                nmck=total,
                status=stage_status or ("wishes" if purchase.status == "wishes" else "planned"),
                assigned_user_id=purchase.assigned_user_id,
                service_note_text=purchase.service_note_text,
                service_note_by=purchase.service_note_by,
                parent_purchase_id=purchase.id,
            )
            if stage_status:
                for f in STAGE_CONTRACT_FIELDS:
                    setattr(new_p, f, getattr(purchase, f))
            db.add(new_p)
            await db.flush()
            created_ids.append(new_p.id)

            for src_it in group_items:
                kwargs = {f: getattr(src_it, f) for f in ITEM_COPY_FIELDS}
                kwargs["extra_attrs"] = dict(getattr(src_it, "extra_attrs", None) or {})
                # Снимок плана (если его ещё не было — fallback на текущие значения,
                # как в исходном коде split_purchase, до этой правки).
                if kwargs.get("planned_quantity") is None:
                    kwargs["planned_quantity"] = src_it.quantity
                if kwargs.get("planned_unit_price") is None:
                    kwargs["planned_unit_price"] = src_it.unit_price
                if kwargs.get("planned_total") is None:
                    kwargs["planned_total"] = src_it.total_price
                db.add(PurchaseItem(purchase_id=new_p.id, **kwargs))

            for m in source_members:
                db.add(PurchaseMember(
                    purchase_id=new_p.id, user_id=m.user_id, role=m.role,
                    added_by_id=current_user.id, consent_pending=False,
                ))
            await db.flush()

            if stage_status:
                await materialize_part_contract(db, new_p, purchase)

            db.add(PurchaseEvent(
                purchase_id=new_p.id, user_id=current_user.id,
                event_type="split_created",
                data={"source_purchase_id": pid, "column_key": display_key, "status": new_p.status},
            ))

            parts.append((new_p, group_total_dec))
            await db.flush()

        # Платежи исходной — распределяем пропорционально суммам позиций частей.
        group_totals = [gt for _, gt in parts]
        for pay in source_payments:
            shares = split_payments_amount(Decimal(str(pay.amount or 0)), group_totals)
            for (new_p, _), share in zip(parts, shares):
                copy_kwargs = {f: getattr(pay, f) for f in PAYMENT_COPY_FIELDS}
                db.add(Payment(purchase_id=new_p.id, amount=share, **copy_kwargs))
            await db.delete(pay)
        await db.flush()

        for new_p, _ in parts:
            await recompute_purchase_payments(db, new_p.id)

        # Исходная: позиции удаляются, статус 'split', договор/деньги чистим.
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
        purchase.status = "split"
        await db.flush()
        if stage_status:
            await cleanup_source_contract(db, purchase)
        if source_payments:
            await recompute_purchase_payments(db, pid)

        db.add(PurchaseEvent(
            purchase_id=pid, user_id=current_user.id,
            event_type="split_source",
            data={"purchase_ids": created_ids, "status_from": status_before},
        ))

        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Ошибка разбиения закупки: {e}")

    return {"source_purchase_id": pid, "purchase_ids": created_ids, "count": len(created_ids)}
