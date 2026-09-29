"""Ядро форвард-перехода статуса закупки — вынесено из
app/routers/purchase_transitions.py::transition_status (Правило №5/№6).

Раньше вся логика (обязательные поля по TRANSITION_REQUIRED, гейты превышения
ФЭО/ТЗ/типа, сама смена статуса и побочные эффекты — пересчёт денег,
автозаполнение приёмки, привязка договора, лог события, уведомления) жила
ТОЛЬКО внутри FastAPI-эндпоинта, вместе с permission/direction-проверками
конкретного HTTP-запроса. Понадобилась ВТОРАЯ точка входа — автоматический
перевод авансовой закупки из 'wishes' дальше по плану сразу после финального
согласования её компаньона (см. app/services/wish_distribution.py, владелец
2026-09-29: «авансовый должен идти дальше сам, как обычная заявка»). Второй
копии гейтов заводить нельзя (ПРАВИЛО №6) — это системное действие, а не
прямой запрос пользователя, поэтому permission-проверки (кто вправе жать
кнопку) и forward-only направление остаются ТОЛЬКО в роутере (или заведомо
не нужны вызывающему — wish_distribution.py всегда переводит вперёд по
STATUS_ORDER); а вот обязательные поля и превышение — ЕДИНЫЙ код для обеих
точек входа, вызывается отсюда.

apply_purchase_status_transition бросает HTTPException при отказе гейта —
как и раньше в роутере. Автоматический вызывающий (wish_distribution.py)
обязан сам ловить это исключение и не падать — записать причину в
PurchaseEvent/комментарий и оставить закупку в 'wishes' (кнопка «→ План
закупок» в карточке закупки остаётся доступна для ручного повтора).
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.feo_plan import assert_no_unapproved_excess
from app.services.tz_excess_approval import assert_no_pending_tz_excess
from app.services.type_excess_approval import (
    collect_type_excess_violations, register_type_excess_approvals,
)
from app.services.price_actualization import actualize_product_price


async def _autofill_accepted_fields(purchase: Purchase, db: AsyncSession) -> None:
    """Дословная копия app/routers/purchase_transitions.py::_autofill_accepted_fields
    невозможна без циклического импорта роутера сюда — обе функции держим
    идентичными вручную (см. её докстринг там); переносить сюда насовсем не
    стал, т.к. роутер её тоже использует отдельно на своём пути (SaaS-bypass)."""
    items_res = await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
    )
    items = items_res.scalars().all()
    if not items:
        return
    item_ids = [it.id for it in items]
    ci_res = await db.execute(
        select(ContractItem).where(ContractItem.source_item_id.in_(item_ids))
    )
    ci_by_source: dict[int, ContractItem] = {}
    for ci in ci_res.scalars().all():
        if ci.source_item_id not in ci_by_source:
            ci_by_source[ci.source_item_id] = ci
    for it in items:
        if it.accepted_name is not None:
            continue
        ci = ci_by_source.get(it.id)
        if ci is not None:
            it.accepted_name = ci.name
            it.accepted_quantity = ci.quantity
            it.accepted_unit = ci.unit
        else:
            it.accepted_name = it.item_name
            it.accepted_quantity = it.quantity
            it.accepted_unit = it.unit


async def apply_purchase_status_transition(
    p: Purchase, pid: int, target_status: str, current_user, db: AsyncSession,
    current_idx: int, target_idx: int,
) -> list[dict]:
    """Гейты + смена статуса + побочные эффекты — БЕЗ permission/direction
    проверок (это ответственность вызывающего). current_idx/target_idx —
    позиции в STATUS_ORDER, уже посчитанные вызывающим (нужны только для
    гейта превышения ниже: он срабатывает на любом forward-переходе).
    Возвращает excess_warnings (мягкие предупреждения — владелец, 2026-09-03:
    «перекос ветки — предупреждение, не блокировка»). Коммитит сам (как и
    раньше — единый db.commit() перехода).
    """
    # Ленивые импорты — во избежание цикла роутер↔сервис (тем же приёмом, что
    # app/services/wish_distribution.py тянет хелперы app/routers/wishes.py).
    from app.routers.purchase_transitions import TRANSITION_REQUIRED, FIELD_LABELS, STATUS_LABELS
    from app.routers.purchases import _sync_purchase_from_contract
    from app.routers.contracts import ensure_contract_linked

    excess_warnings: list[dict] = []

    # Field guards for specific target statuses
    if target_status in TRANSITION_REQUIRED:
        if p.contract_id:
            await _sync_purchase_from_contract(p, db)

        required_fields = TRANSITION_REQUIRED[target_status]
        if target_status == "delivered":
            def _has_acceptance_doc(purchase) -> bool:
                if (purchase.acceptance_doc_name and purchase.acceptance_doc_number
                        and purchase.acceptance_doc_date and purchase.acceptance_doc_amount):
                    return True
                docs = purchase.acceptance_docs or []
                for d in docs:
                    if not isinstance(d, dict):
                        continue
                    if (d.get("name") and d.get("number")
                            and d.get("date") and d.get("amount") not in (None, "", 0)):
                        return True
                return False

            if _has_acceptance_doc(p):
                required_fields = [f for f in required_fields if not f.startswith("acceptance_doc")]
        if target_status == "delivered" and getattr(p, "purchase_method", None) == "advance":
            from app.models.purchase_receipt import PurchaseReceipt
            rcpt_result = await db.execute(
                select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == p.id).limit(1)
            )
            if rcpt_result.first() is not None:
                required_fields = [f for f in required_fields if not f.startswith("acceptance_doc")]
        missing = [f for f in required_fields if not getattr(p, f, None)]
        if missing:
            is_advance = getattr(p, "purchase_method", None) == "advance"
            field_label_map = dict(FIELD_LABELS)
            if is_advance:
                field_label_map["contract_date"] = "Дата документа основания (чек/УПД)"
                field_label_map["contract_number"] = "Номер документа основания (№ чека/УПД)"
            missing_labels = [field_label_map.get(f, f) for f in missing]
            status_label = STATUS_LABELS.get(target_status, target_status)

            if is_advance and target_status == "contracted":
                advance_hint = (
                    " Заполните в карточке закупки дату/номер чека или УПД."
                    " Либо загрузите чек через QR/Файл — тогда поля заполнятся автоматически."
                )
            elif is_advance and target_status == "delivered":
                advance_hint = (
                    " Для авансового отчёта добавьте чек через сканирование QR"
                    " или загрузку JSON/изображения. После добавления чека статус «Поставлено» доступен."
                )
            else:
                advance_hint = (
                    " Для авансового отчёта рекомендуется загрузить чек через QR —"
                    " большинство полей заполнятся автоматически."
                ) if is_advance else ""

            raise HTTPException(
                422,
                detail={
                    "code": "STATUS_TRANSITION_BLOCKED",
                    "message": (
                        f"Для перехода в статус «{status_label}» заполните:"
                        f" {', '.join(missing_labels)}.{advance_hint}"
                    ),
                    "missing_fields": missing,
                    "status": target_status,
                    "status_label": status_label,
                },
            )

    if target_status == "contracted":
        ci_count_res = await db.execute(
            select(func.count()).select_from(ContractItem).where(ContractItem.purchase_id == pid)
        )
        ci_count = ci_count_res.scalar() or 0
        if ci_count == 0:
            if p.purchase_method == 'advance':
                from app.models.purchase_receipt import PurchaseReceipt
                receipts_count = (await db.execute(
                    select(func.count()).select_from(PurchaseReceipt).where(PurchaseReceipt.purchase_id == pid)
                )).scalar() or 0
                has_acceptance_docs = bool(p.acceptance_docs)
                if receipts_count == 0 and not has_acceptance_docs:
                    raise HTTPException(
                        422,
                        detail={
                            "code": "CONTRACT_ITEMS_REQUIRED",
                            "message": (
                                "Для авансового отчёта загрузите чек (сканировать QR / "
                                "загрузить чек / вручную) или прикрепите закрывающий документ "
                                "перед переходом в «Заключён договор»."
                            ),
                            "missing_fields": ["receipts_or_acceptance_docs"],
                            "status": "contracted",
                            "status_label": "Заключён договор",
                        },
                    )
                pi_q = await db.execute(
                    select(PurchaseItem).where(PurchaseItem.purchase_id == pid)
                )
                for pi in pi_q.scalars().all():
                    exists_ci = (await db.execute(
                        select(ContractItem).where(
                            ContractItem.purchase_id == pid,
                            ContractItem.source_item_id == pi.id,
                        ).limit(1)
                    )).scalar_one_or_none()
                    if exists_ci:
                        continue
                    db.add(ContractItem(
                        purchase_id=pid,
                        source_item_id=pi.id,
                        name=pi.item_name or "Позиция",
                        quantity=pi.quantity,
                        unit=pi.unit or 'шт.',
                        unit_price=pi.unit_price,
                        total=pi.total_price,
                        match_confirmed=True,
                    ))
                await db.flush()
                ci_count_res2 = await db.execute(
                    select(func.count()).select_from(ContractItem).where(ContractItem.purchase_id == pid)
                )
                ci_count = ci_count_res2.scalar() or 0
            if ci_count == 0:
                raise HTTPException(
                    422,
                    detail={
                        "code": "CONTRACT_ITEMS_REQUIRED",
                        "message": (
                            "Для перехода в статус «Заключён договор» необходимо заполнить позиции "
                            "договора. Используйте кнопку «Скопировать из заявки» или «Импорт из "
                            "файла/QR» в карточке закупки."
                        ),
                        "missing_fields": ["contract_items"],
                        "status": "contracted",
                        "status_label": "Заключён договор",
                    },
                )
        from app.services.purchase_money_writer import recalc_purchase_money as _recalc
        await _recalc(db, p)

    if target_idx > current_idx:
        _gate_cat_ids: set[int] = set()
        for _it in p.items:
            _cid = _it.feo_category_id or p.feo_category_id
            if _cid:
                _gate_cat_ids.add(_cid)
        if not _gate_cat_ids and p.feo_category_id:
            _gate_cat_ids.add(p.feo_category_id)
        for _cid in _gate_cat_ids:
            excess_warnings.extend(await assert_no_unapproved_excess(db, _cid))
        await assert_no_pending_tz_excess(db, p.items, fallback_category_id=p.feo_category_id)
        _type_violations = await collect_type_excess_violations(db, p.subsidy_id, _gate_cat_ids)
        if _type_violations:
            excess_warnings.extend(await register_type_excess_approvals(
                db, _type_violations, subsidy_id=p.subsidy_id, current_user=current_user,
                context_label=(
                    f"переход закупки №{p.purchase_number or p.id} в статус "
                    f"«{STATUS_LABELS.get(target_status, target_status)}»"
                ),
            ))

    old_status = p.status
    p.status = target_status

    if target_status == "delivered":
        await _autofill_accepted_fields(p, db)

    if target_status == "contracted" and p.items:
        sub = await db.get(Subsidy, p.subsidy_id) if p.subsidy_id else None
        contract_org_id = sub.org_id if sub else None
        for item in p.items:
            if not item.product_id:
                continue
            product = await db.get(Product, item.product_id)
            if not product:
                continue
            item_price = item.unit_price
            product.contract_price = item_price
            product.contract_number = p.contract_number
            product.contract_date = p.contract_date
            product.contract_org_id = contract_org_id
            _dup_history = (await db.execute(
                select(ProductPriceHistory.id).where(
                    ProductPriceHistory.product_id == product.id,
                    ProductPriceHistory.source == "contract",
                    ProductPriceHistory.source_ref == p.contract_number,
                    ProductPriceHistory.collected_at == p.contract_date,
                ).limit(1)
            )).scalar_one_or_none()
            await actualize_product_price(
                db, product,
                price=item_price,
                source="contract",
                source_ref=p.contract_number,
                contractor_id=getattr(p, "contractor_id", None),
                collected_at=p.contract_date,
                user=current_user,
                write_history=_dup_history is None,
            )

    if target_status == "contracted":
        await ensure_contract_linked(p, db)

    await db.commit()

    # Auto-log status change event
    try:
        from app.models.purchase_event import PurchaseEvent
        db.add(PurchaseEvent(
            purchase_id=pid,
            user_id=getattr(current_user, "id", None),
            event_type="status_changed",
            data={"from": old_status, "to": target_status},
        ))
        await db.commit()
    except Exception:
        pass

    # Notify purchase members + linked task assignees about status change
    try:
        from app.notifications import notify_purchase_status_changed
        from app.models.purchase_event import PurchaseMember
        from app.models.task import Task, TaskAssignee
        from app.models.user import User

        notify_user_ids: set[int] = set()
        notify_users = []

        members_r = await db.execute(
            select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
        )
        for m in members_r.scalars().all():
            if m.user_id != current_user.id:
                notify_user_ids.add(m.user_id)

        if p.assigned_user_id and p.assigned_user_id != current_user.id:
            notify_user_ids.add(p.assigned_user_id)

        linked_tasks_r = await db.execute(
            select(Task.id).where(Task.purchase_id == pid)
        )
        linked_task_ids = [r[0] for r in linked_tasks_r.all()]
        if linked_task_ids:
            ta_r = await db.execute(
                select(TaskAssignee.user_id).where(
                    TaskAssignee.task_id.in_(linked_task_ids)
                )
            )
            for r in ta_r.all():
                if r[0] != current_user.id:
                    notify_user_ids.add(r[0])

        for uid in notify_user_ids:
            u = await db.get(User, uid)
            if u:
                notify_users.append(u)

        if notify_users:
            await notify_purchase_status_changed(
                p, current_user.full_name or current_user.username,
                target_status, notify_users
            )
    except Exception:
        pass

    return excess_warnings
