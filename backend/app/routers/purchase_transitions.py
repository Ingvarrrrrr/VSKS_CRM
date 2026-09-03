"""Purchase state-machine transitions router — extracted from purchases.py (Phase 16-06).

Handles:
  POST /api/purchases/{pid}/transition       — forward-only status transition with field guards
  POST /api/purchases/{pid}/convert-to-order — convert service_note basis to plan_schedule

G-08: TRANSITION_REQUIRED dict lives here (only transition endpoint uses it).
STATUS_ORDER stays in purchases.py (G-08 — used by CRUD + members + my-tasks).
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contract_item import ContractItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.models.user import User
from app.auth.jwt import get_current_user, require_role, ADMIN_ROLES, MANAGER_ROLES, OWNER_ROLES
from app.auth.permissions import require_action
from app.routers.contracts import ensure_contract_linked
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from app.routers.purchases import (
    _purchase_to_full, _item_to_out, STATUS_ORDER, _sync_purchase_from_contract,
    is_framework_head,
)
from app.schemas.schemas import PurchaseOutFull
from app.services.feo_plan import assert_no_unapproved_excess
from app.services.tz_excess_approval import assert_no_pending_tz_excess
from app.services.price_actualization import actualize_product_price

router = APIRouter(prefix="/api/purchases", tags=["purchase-transitions"])

# G-08: TRANSITION_REQUIRED lives HERE (only transition endpoint uses it)

STATUS_LABELS: dict[str, str] = {
    "planned":        "Запланирован",
    "contracted":     "Заключён договор",
    "ordered":        "Заказано",
    "delivered":      "Поставлено",
    "paid":           "Оплачено",
    "wishes":         "Заявка",
    "plan_schedule":  "План закупок",
    "work_in_progress": "Ведётся работа",
    "cancelled":      "Отменён",
}

FIELD_LABELS: dict[str, str] = {
    "contract_number":       "Номер договора",
    "contract_date":          "Дата договора",
    "acceptance_doc_name":     "Наименование акта приёмки",
    "acceptance_doc_date":     "Дата акта приёмки",
    "acceptance_doc_number":   "Номер акта приёмки",
    "acceptance_doc_amount":   "Сумма акта приёмки",
    "payment_doc_number":      "Номер платёжного поручения",
    "payment_doc_date":        "Дата платежа",
    "payment_amount":          "Сумма платежа",
}

TRANSITION_REQUIRED: dict[str, list[str]] = {
    "contracted": ["contract_number", "contract_date"],
    "delivered": ["acceptance_doc_name", "acceptance_doc_date", "acceptance_doc_number", "acceptance_doc_amount"],
    "paid": ["payment_doc_number", "payment_doc_date", "payment_amount"],
}


async def _autofill_accepted_fields(purchase: Purchase, db: AsyncSession) -> None:
    """5-я стадия жизненного цикла позиции («приняли») — автозаполнение при delivered.

    Для каждой purchase_item, у которой accepted_name ещё NULL: берём name/quantity/unit
    из связанной ContractItem (по source_item_id), а если договорной строки нет — из самой
    purchase_item (item_name/quantity/unit). Позиции, где accepted_name уже заполнен
    (ручная правка PATCH-ем или повторный переход), не трогаем.
    """
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


@router.post("/{pid}/transition", response_model=PurchaseOutFull)
async def transition_status(
    pid: int,
    target_status: str = Query(..., alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Forward-only status transition.
    wishes → plan_schedule → work_in_progress → contracted → delivered → paid
    (рамочные договоры: work_in_progress → delivered, минуя contracted)
    """
    if target_status not in STATUS_ORDER:
        raise HTTPException(422, f"Недопустимый статус: {target_status}")

    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # assert_no_unapproved_excess ниже больше не бросает 409 за перекос
    # ОТДЕЛЬНОЙ категории (excess_amount), возвращает список предупреждений —
    # копим сюда, отдаём в ответе (excess_warnings, см. конец функции). Тот же
    # паттерн, что уже применён в app.routers.wishes/purchases.py.
    _excess_warnings: list[dict] = []

    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    # SaaS-bypass: superadmin/account_owner — force-set статус минуя любые guard'ы.
    if current_user.role in OWNER_ROLES:
        p.status = target_status
        if target_status == "delivered":
            await _autofill_accepted_fields(p, db)
        await db.commit()
        await db.refresh(p)
        return p

    current_idx = STATUS_ORDER.index(p.status) if p.status in STATUS_ORDER else 0
    target_idx = STATUS_ORDER.index(target_status)

    # 27.4-12: advance owner bypass — ограничен.
    # Сотрудник (даже владелец авансового) может двигать ТОЛЬКО forward
    # и ТОЛЬКО когда закупка уже направлена в работу (work_in_progress+).
    is_advance_owner = (
        getattr(p, 'purchase_method', None) == 'advance'
        and getattr(p, 'reimbursement_user_id', None) == current_user.id
    )
    is_manager_plus = current_user.role in MANAGER_ROLES
    WORK_IN_PROGRESS_IDX = STATUS_ORDER.index("work_in_progress")

    if is_advance_owner and not is_manager_plus:
        if current_idx < WORK_IN_PROGRESS_IDX:
            raise HTTPException(
                403,
                "Закупка должна быть направлена в работу "
                "(статус «Направлено в закупку» или позже) перед изменением сотрудником"
            )
        if target_idx <= current_idx:
            raise HTTPException(
                403,
                "Сотрудник может двигать статус только вперёд. "
                "Откат разрешён только администратору"
            )
    elif not is_manager_plus:
        # Не владелец авансового и не manager+ → требуется permission action
        from app.auth.permissions import get_effective_actions, _active_org
        actions = await get_effective_actions(current_user, db, _active_org(current_user))
        if 'purchase.status_change' not in actions:
            raise HTTPException(403, "Нужно разрешение «Изменение статуса закупки»")

    # Direction check: forward-only for non-admin
    if target_idx <= current_idx:
        if current_user.role not in ADMIN_ROLES:
            raise HTTPException(422, "Откат статуса разрешён только администратору")

    # Framework skip: рамочные договоры пропускают стадию «Заключён договор».
    # Данные берутся из головного рамочного договора — отдельный договор не заключается.
    _is_framework = p.purchase_contract_type in FRAMEWORK_TYPES
    if _is_framework and target_status == "contracted" and current_user.role not in OWNER_ROLES:
        raise HTTPException(
            422,
            "Закупка по рамочному договору не проходит стадию «Заключён договор»: "
            "используйте переход сразу в «Поставлено»."
        )

    # Approval guard: block contracted transition if approval is pending/rejected
    if target_status == "contracted" and p.approval_status and p.approval_status not in ("approved",):
        raise HTTPException(
            422,
            f"Закупка должна быть согласована перед заключением договора. "
            f"Текущий статус согласования: {p.approval_status}"
        )

    # Field guards for specific target statuses
    if target_status in TRANSITION_REQUIRED:
        # phase26-j-2: если contract_id установлен, подтягиваем поля из contracts перед валидацией.
        # Это закрывает кейс: purchase.contract_date=NULL, contracts[cid].date заполнена →
        # переход не блокируется, данные синхронизируются автоматически.
        if p.contract_id:
            await _sync_purchase_from_contract(p, db)

        required_fields = TRANSITION_REQUIRED[target_status]
        if target_status == "delivered":
            # acceptance_docs JSONB overrides legacy flat fields.
            # True if at least one entry has name+number+date+amount all filled.
            def _has_acceptance_doc(purchase) -> bool:
                # Legacy flat fields
                if (purchase.acceptance_doc_name and purchase.acceptance_doc_number
                        and purchase.acceptance_doc_date and purchase.acceptance_doc_amount):
                    return True
                # New JSONB array (keys: name/number/date/amount as written by frontend)
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
        # Phase 23.4: для авансовых отчётов с привязанными чеками acceptance_doc не обязательны
        if target_status == "delivered" and getattr(p, "purchase_method", None) == "advance":
            from app.models.purchase_receipt import PurchaseReceipt
            rcpt_result = await db.execute(
                select(PurchaseReceipt).where(PurchaseReceipt.purchase_id == p.id).limit(1)
            )
            if rcpt_result.first() is not None:
                required_fields = [f for f in required_fields if not f.startswith("acceptance_doc")]
        missing = [
            f for f in required_fields
            if not getattr(p, f, None)
        ]
        if missing:
            is_advance = getattr(p, "purchase_method", None) == "advance"
            # Доработка 5 мая: для авансового «Дата договора» переименовываем
            # в «Дата документа основания» (чек/УПД) — пользователю иначе непонятно,
            # что это поле принимает дату чека.
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

    # Phase 27.1 D-06: CONTRACT_ITEMS_REQUIRED — strict gate before contracted transition
    # Phase 26-MM: для авансовых отчётов чек/закр.документ заменяет договор — смягчить guard.
    if target_status == "contracted":
        ci_count_res = await db.execute(
            select(func.count()).select_from(ContractItem).where(ContractItem.purchase_id == pid)
        )
        ci_count = ci_count_res.scalar() or 0
        if ci_count == 0:
            if p.purchase_method == 'advance':
                from app.models.purchase_receipt import PurchaseReceipt
                # PurchaseItem уже импортирован на уровне модуля
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
                # Авто-создать ContractItem из PurchaseItem (idempotent)
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
                # Re-check count после autocreate
                ci_count_res2 = await db.execute(
                    select(func.count()).select_from(ContractItem).where(ContractItem.purchase_id == pid)
                )
                ci_count = ci_count_res2.scalar() or 0
            # Если всё ещё 0 (не advance, или advance без purchase_items) — strict guard
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
        # Phase 27.1 D-07: recompute contract_price (если не рамочный головной,
        # см. is_framework_head() в purchases.py — единый хелпер для этой проверки)
        if not is_framework_head(p):
            ci_sum_res = await db.execute(
                select(func.sum(ContractItem.total)).where(ContractItem.purchase_id == pid)
            )
            ci_sum = ci_sum_res.scalar() or Decimal('0')
            if ci_sum > 0:
                p.contract_price = ci_sum

    # Задача владельца, план zany-fluttering-mountain.md п.4 «Превышение: показать
    # виновника и заблокировать новые закупки» (2026-08-10), дословно: «дальнейшие
    # действия по заключению новых закупок должны быть заблокированы до того
    # момента, пока не будет снижено и приведено в соответствие с ФЭО план
    # закупки» + план: «пока по категории есть непогашенное превышение над ФЭО,
    # новые закупки по ней НЕ СОЗДАЮТСЯ И НЕ ДВИГАЮТСЯ ДАЛЬШЕ ПО СТАДИЯМ». Раньше
    # гейт стоял ТОЛЬКО на target_status == "contracted" (шаг C, сессия 2026-08-06,
    # исходно — превентивный контроль факт-над-планом при подписании договора).
    # Теперь — на КАЖДОМ forward-переходе (target_idx > current_idx), иначе
    # закупка «проплывает» через Заказано/Поставлено/Оплачено мимо непогашенного
    # превышения плана над финансированием ФЭО (excess_amount/excess_over_feo).
    # assert_no_unapproved_excess по-прежнему проверяет ОБА вида превышения
    # (план>ФЭО и факт>план) — это сохраняет прежнее поведение шага C как частный
    # случай более общего правила. OWNER_ROLES (superadmin/account_owner) уже
    # обошли ВСЮ функцию раньше (см. bypass в начале) — этот гейт видят все
    # остальные роли, включая ADMIN_ROLES (в отличие от PUT /api/purchases/{pid},
    # где admin_override — explicit query-флаг только для ADMIN_ROLES; здесь
    # такого параметра нет, обход только через OWNER_ROLES).
    if target_idx > current_idx:
        _gate_cat_ids: set[int] = set()
        for _it in p.items:
            _cid = _it.feo_category_id or p.feo_category_id
            if _cid:
                _gate_cat_ids.add(_cid)
        if not _gate_cat_ids and p.feo_category_id:
            _gate_cat_ids.add(p.feo_category_id)
        for _cid in _gate_cat_ids:
            _excess_warnings.extend(await assert_no_unapproved_excess(db, _cid))
        # Владелец (2026-09-02): «попасть должно в План-закупок... но дальше
        # двигаться нельзя по закупке без его согласования» — ТЗ позиции дороже
        # её КОНКРЕТНОЙ плановой позиции (feo_category_id) больше не 409 при
        # согласовании заявки (см. app.routers.wishes/purchases.create_purchase),
        # но assert_no_unapproved_excess ЭТОТ вид превышения не видит (см.
        # докстринг app/services/tz_excess_approval.py — компонент дерева ФЭО,
        # excess_fact_over_plan, включается только на «Ведётся работа» с уже
        # заполненной ценой договора, т.е. ПОЗЖЕ самого первого форвард-перехода).
        # Отдельный, независимый гейт закрывает именно этот момент.
        await assert_no_pending_tz_excess(db, p.items, fallback_category_id=p.feo_category_id)

    old_status = p.status
    p.status = target_status

    # Стадия «Приняли» — автозаполнение accepted_* у позиций при переходе в delivered
    if target_status == "delivered":
        await _autofill_accepted_fields(p, db)

    # При переходе в contracted — обновить цены в каталоге товаров
    # (владелец 2026-08-29: заодно проставить метаданные актуализации —
    # цена «по контракту» одно из двух легитимных оснований актуализации,
    # см. app/services/price_actualization.py).
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
            await actualize_product_price(
                db, product,
                price=item_price,
                source="contract",
                source_ref=p.contract_number,
                contractor_id=getattr(p, "contractor_id", None),
                collected_at=p.contract_date,
                user=current_user,
            )

    # Auto-create/link contract record when moving to contracted status
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

        notify_user_ids: set[int] = set()
        notify_users = []

        # 1. Purchase members
        members_r = await db.execute(
            select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
        )
        for m in members_r.scalars().all():
            if m.user_id != current_user.id:
                notify_user_ids.add(m.user_id)

        # 2. Assigned user of purchase
        if p.assigned_user_id and p.assigned_user_id != current_user.id:
            notify_user_ids.add(p.assigned_user_id)

        # 3. All assignees of tasks linked to this purchase
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

        # Load user objects
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

    # Re-fetch with eager loads after commit
    result2 = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result2.scalar_one()
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    out = _purchase_to_full(p, contractors, subsidies)
    if _excess_warnings:
        out.excess_warnings = _excess_warnings
    return out


@router.post("/{pid}/convert-to-order", response_model=PurchaseOutFull)
async def convert_service_note_to_order(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action('purchase.transition_status')),
):
    """Конвертировать служебную записку на выдачу в закупку (меняет purchase_basis на plan_schedule)."""
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if p.purchase_basis != 'service_note':
        raise HTTPException(422, "Конвертация доступна только для служебных записок")
    p.purchase_basis = 'plan_schedule'
    await db.commit()
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    return _purchase_to_full(p, contractors, subsidies)
