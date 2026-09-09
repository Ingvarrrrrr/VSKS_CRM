"""Разовые операции над закупкой(ами), не относящиеся к CRUD ядра purchases.py:
цепочка согласующих рамочной головы, массовое удаление, рассылка, разбиение
закупки на дочерние, backfill денормализованных полей из contracts.

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения. `DELETE /bulk` зарегистрирован в app/routes.py ДО purchases.router —
иначе Starlette матчит "/bulk" на catch-all "/{pid}" (pid: int) и падает с 422,
так и не доходя до этого роута (тот же класс проблемы, что и payment-groups/
payment-candidates — см. app/routers/purchase_payment_matching.py).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.auth.jwt import get_current_user, get_org_filter, ADMIN_ROLES
from app.auth.permissions import require_tab, require_action
from app.routers.purchases import is_framework_head, _sync_purchase_from_contract

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


async def _build_framework_chain_approvals(
    p: Purchase, db: AsyncSession, current_user: User, mode: Optional[str] = None,
) -> Optional[str]:
    """Строит восходящую цепочку согласующих рамочной ГОЛОВЫ договора — ТЕМ ЖЕ
    механизмом, что и у заявок (app.services.approval_chain.build_ascending_chain,
    см. app/routers/wish_approvals.py::cascade_wish_approvers), чтобы правило
    подчинения не разъезжалось по двум местам (см. историю framework_limited/
    framework_with_amount выше — дублирование уже один раз стоило прод-инцидента).

    Владелец (2026-09-03): «выбирают при создании рамочного договора, надо
    выбрать, кто будет согласовывать то, что этот договор вообще нужен» —
    эта функция БОЛЬШЕ НЕ вызывается автоматически при создании рамочной
    головы (было так 2026-09-02 — контракт.py::get_or_create_approval_purchase
    вызывал её сама, никого не спрашивая; владелец это прямо отменил). Теперь
    она вызывается ТОЛЬКО явным действием пользователя — кнопкой «Построить
    цепочку» (POST /purchases/{pid}/approvers/cascade ниже). Основной путь —
    автор добавляет согласующих вручную по одному (POST /purchases/{pid}/
    approvals/add, см. purchase_approvals.py::add_approver — как и у заявки).

    Верхом цепочки берём руководителя организации (Organization.head_user_id)
    автоматически — у рамочной головы нет отдельного экрана выбора «верхнего
    согласующего», как у заявки. Если он не задан — цепочку строить не из
    чего, согласование не запускается (approval_status остаётся NULL), чтобы
    не создать пустую/бессмысленную цепочку.

    mode — 'sequential' (по умолчанию) или 'parallel'; передаётся явно, когда
    вызывающий (cascade-эндпоинт) уже знает выбор пользователя. Не путать с
    p.approval_mode, если он уже был выставлен раньше (например, добавлением
    первого согласующего вручную) — новый mode, если передан, имеет приоритет.

    Результат сохраняется в PurchaseApproval — той же таблице, тем же
    решением (POST /purchases/{pid}/approvals/{aid}/decide), что уже
    используется для обычного (SubsidyApprover-based) согласования закупок:
    второй параллельный движок согласования не заводится.

    Возвращает warning от build_ascending_chain (см. её docstring) или None.
    """
    if not is_framework_head(p):
        return None

    from app.services.approval_chain import build_ascending_chain
    from app.routers.purchase_approvals import _resolve_purchase_org_id
    from app.models.organization import Organization
    from app.models.purchase_approval import PurchaseApproval

    org_id = await _resolve_purchase_org_id(db, p, current_user)
    if not org_id:
        return None
    org = await db.get(Organization, org_id)
    top_user_id = getattr(org, "head_user_id", None) if org else None
    if not top_user_id:
        return None

    author_id = p.assigned_user_id or p.service_note_by or current_user.id
    chain, warning = await build_ascending_chain(db, author_id, top_user_id, org_id)
    if not chain:
        return warning

    # Идемпотентно — как start_approval() при повторном запуске (purchase_approvals.py).
    old = (await db.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == p.id)
    )).scalars().all()
    for row in old:
        await db.delete(row)
    await db.flush()

    for step in chain:
        db.add(PurchaseApproval(
            purchase_id=p.id,
            order_num=step["order_num"],
            role_name=step["role_name"],
            approver_full_name=step["full_name"] or "",
            user_id=step["user_id"],
            status="pending",
        ))
    p.approval_status = "in_progress"
    _valid_mode = mode if mode in ("sequential", "parallel") else None
    p.approval_mode = _valid_mode or p.approval_mode or "sequential"
    return warning


@router.post("/{pid}/approvers/cascade")
async def cascade_purchase_approvers(
    pid: int,
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Построить цепочку согласующих рамочной ГОЛОВЫ договора — по аналогии с
    POST /wishes/{wid}/approvers/cascade, тем же общим механизмом
    (build_ascending_chain). Владелец (2026-09-03): вызывается ТОЛЬКО явным
    нажатием кнопки «Построить цепочку» — автозапуска при заведении рамочной
    головы больше нет (см. contracts.py::get_or_create_approval_purchase).
    Также доступен, чтобы перестроить цепочку — например, после смены
    руководителя организации.

    body.mode — необязательный 'sequential'/'parallel', выбранный пользователем
    в блоке согласования (см. ApprovalPanel.vue); по умолчанию 'sequential'.
    """
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if not is_framework_head(p):
        raise HTTPException(400, "Цепочка согласующих по этому механизму доступна только для рамочной головы договора")

    mode = (body or {}).get("mode")
    warning = await _build_framework_chain_approvals(p, db, current_user, mode=mode)
    await db.commit()

    from app.models.purchase_approval import PurchaseApproval
    from app.routers.purchase_approvals import _to_out
    rows = (await db.execute(
        select(PurchaseApproval).where(PurchaseApproval.purchase_id == pid).order_by(PurchaseApproval.order_num)
    )).scalars().all()
    return {
        "approval_mode": p.approval_mode,
        "approval_status": p.approval_status,
        "approvers": [_to_out(a) for a in rows],
        "warning": warning,
    }


@router.delete("/bulk")
async def bulk_delete_purchases(
    ids: List[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_tab('purchases')),
):
    deleted, failed = [], []
    for pid in ids:
        try:
            result = await db.execute(select(Purchase).where(Purchase.id == pid))
            p = result.scalar_one_or_none()
            if not p:
                failed.append({"id": pid, "reason": "Не найдено"})
                continue
            await db.delete(p)
            await db.flush()
            deleted.append(pid)
        except Exception as e:
            await db.rollback()
            failed.append({"id": pid, "reason": str(e)[:200]})
    if deleted:
        await db.commit()
    return {"deleted": deleted, "failed": failed}


@router.post("/{pid}/broadcast")
async def broadcast_from_purchase(
    pid: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Broadcast from purchase context."""
    from app.models.organization import Organization
    from app.models.department import Department
    from app.models.user_organization import UserOrganization as _UO_broadcast
    from app.models.purchase_comment import PurchaseComment
    from app.notifications import notify_user, _esc, _purchase_url

    BROADCAST_ROLES = ("superadmin", "org_admin", "admin", "manager")
    if current_user.role not in BROADCAST_ROLES:
        raise HTTPException(403, "Рассылка доступна только администраторам и менеджерам")

    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Текст сообщения обязателен")

    scope = body.get("scope", "")
    scope_id = body.get("scope_id")

    q = select(User).where(User.id != current_user.id)  # superadmin-bypass-ok: broadcast notifications, not a user-list endpoint returned to client
    if scope == "department" and scope_id:
        member_uids = select(_UO_broadcast.user_id).where(_UO_broadcast.dept_id == int(scope_id))
        q = q.where(User.id.in_(member_uids))
    elif scope == "organization" and scope_id:
        q = q.where(User.org_id == int(scope_id))
    elif scope == "all":
        org_ids = get_org_filter(current_user)
        if org_ids is not None:
            q = q.where(User.org_id.in_(org_ids))
    else:
        raise HTTPException(422, "Укажите scope")

    users = (await db.execute(q)).scalars().all()

    sender_name = current_user.full_name or current_user.username
    subject = _esc(p.subject or f"Закупка №{p.purchase_number}")
    msg = (
        f"📢 <b>Рассылка</b>\n\n"
        f"📌 <b>{subject}</b>\n"
        f"👤 <i>{_esc(sender_name)}</i>:\n"
        f"{_esc(text)}"
    )

    sent = 0
    for u in users:
        if getattr(u, "telegram_id", None) or getattr(u, "max_chat_id", None):
            await notify_user(u, msg, button_url=_purchase_url(p.id), button_label="Открыть закупку")
            sent += 1

    # Save as comment
    scope_label = {"department": "отделу", "organization": "организации", "all": "всем"}.get(scope, scope)
    db.add(PurchaseComment(
        purchase_id=pid, user_id=current_user.id, user_name=sender_name,
        text=f"[Рассылка {scope_label}] {text}",
    ))
    await db.commit()

    return {"ok": True, "sent": sent, "total_users": len(users)}


@router.post("/{pid}/split")
async def split_purchase(
    pid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Разбить закупку на N дочерних по группам позиций.

    Body: {"groups": [{"column_key": "str", "item_ids": [int, ...]}, ...]}
    - N <= 1 → 400.
    - До status in (contracted, delivered, paid) — разрешено всем, кто имеет доступ.
    - В этих статусах — только ADMIN_ROLES.
    - Наследует subsidy_id, feo_category_id, assigned_user_id, service_note_*, members.
    - Копирует PurchaseItem по item_ids в соответствующие дочерние.
    - Исходная помечается status='split'.
    """
    from app.models.purchase_event import PurchaseMember

    # Load purchase with items
    res = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items))
        .where(Purchase.id == pid)
    )
    purchase = res.scalar_one_or_none()
    if purchase is None:
        raise HTTPException(404, "Закупка не найдена")

    # Org isolation
    org_ids = get_org_filter(current_user)
    if org_ids is not None:
        subsidy_res = await db.execute(select(Subsidy).where(Subsidy.id == purchase.subsidy_id))
        subsidy = subsidy_res.scalar_one_or_none()
        if subsidy and subsidy.org_id not in org_ids:
            raise HTTPException(403, "Нет доступа к закупке")

    LOCKED_STATUSES = {"contracted", "delivered", "paid"}
    if purchase.status in LOCKED_STATUSES and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Перераспределять закупку в статусе 'Договор' и далее могут только администраторы")
    if purchase.status == "split":
        raise HTTPException(400, "Закупка уже разбита")

    groups = body.get("groups") or []
    groups = [g for g in groups if g.get("item_ids")]
    if len(groups) < 2:
        raise HTTPException(400, "Разбиение требует минимум 2 непустые группы")

    # Validate all item_ids belong to this purchase and are unique + complete
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

    # Load members of source
    mem_res = await db.execute(
        select(PurchaseMember).where(PurchaseMember.purchase_id == pid)
    )
    source_members = mem_res.scalars().all()

    items_by_id = {it.id: it for it in purchase.items}
    created_ids: list[int] = []

    try:
        for g in groups:
            column_key = (g.get("column_key") or "").strip() or "__uncategorized__"
            display_key = "Не определено" if column_key == "__uncategorized__" else column_key
            group_items = [items_by_id[iid] for iid in g["item_ids"]]
            total = sum(float(it.total_price or 0) for it in group_items)

            base_subject = (purchase.subject or purchase.item_name or "").strip()
            new_subject = f"{base_subject} — {display_key}".strip(" —") if base_subject else display_key

            new_p = Purchase(
                subsidy_id=purchase.subsidy_id,
                feo_category_id=purchase.feo_category_id,
                item_name=purchase.item_name or f"Закупка #{purchase.id}",
                subject=new_subject,
                planned_total_price=total,
                total_nmck=total,
                nmck=total,
                status="wishes" if purchase.status == "wishes" else "planned",
                assigned_user_id=purchase.assigned_user_id,
                service_note_text=purchase.service_note_text,
                service_note_by=purchase.service_note_by,
                parent_purchase_id=purchase.id,
            )
            db.add(new_p)
            await db.flush()
            created_ids.append(new_p.id)

            # Copy items into new purchase
            for src_it in group_items:
                db.add(PurchaseItem(
                    purchase_id=new_p.id,
                    product_id=src_it.product_id,
                    item_name=src_it.item_name,
                    item_type=src_it.item_type,
                    quantity=src_it.quantity,
                    unit=src_it.unit,
                    unit_price=src_it.unit_price,
                    total_price=src_it.total_price,
                    extra_attrs=getattr(src_it, 'extra_attrs', None) or {},
                    # Снимок плана (Шаг 1): разбиение закупки на подгруппы — переносим
                    # УЖЕ зафиксированный план исходной позиции, а не текущую цену
                    # (иначе разбиение задним числом «размораживало» бы план). Fallback
                    # на текущие значения только если снимка ещё не было (позиция создана
                    # до этой миграции/до бэкофилла).
                    planned_quantity=src_it.planned_quantity if src_it.planned_quantity is not None else src_it.quantity,
                    planned_unit_price=src_it.planned_unit_price if src_it.planned_unit_price is not None else src_it.unit_price,
                    planned_total=src_it.planned_total if src_it.planned_total is not None else src_it.total_price,
                    country_origin=src_it.country_origin,
                    feo_planned_item_id=src_it.feo_planned_item_id,
                    over_plan=getattr(src_it, 'over_plan', False) or False,
                ))
            # Copy members
            for m in source_members:
                db.add(PurchaseMember(
                    purchase_id=new_p.id,
                    user_id=m.user_id,
                    role=m.role,
                    added_by_id=current_user.id,
                    consent_pending=False,
                ))
            await db.flush()

        # Delete original items (explicit — keeps source row stable with status='split')
        await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
        purchase.status = "split"
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Ошибка разбиения закупки: {e}")

    return {"source_purchase_id": pid, "purchase_ids": created_ids, "count": len(created_ids)}


@router.post("/sync-from-contracts")
async def sync_all_purchases_from_contracts(
    only_mismatched: bool = Query(True, description="Только закупки где denorm-поля расходятся с contract"),
    current_user=Depends(require_action('purchases.edit')),
    db: AsyncSession = Depends(get_db),
):
    """Phase 26-lll: глобальный backfill денормализованных полей purchases из contracts.

    Для каждой purchase с contract_id IS NOT NULL прогоняет
    _sync_purchase_from_contract — выравнивает contract_number / contract_date /
    purchase_contract_type / contractor_id с реальным contracts.*.

    Чинит исторические рассинхронизации до Phase 26-j-1 (sync на save) и до
    Phase 26-k-2 (UPDATE 2 row backfill — недостаточно). Также покрывает баг
    «Контрагент пустой в реестре закупок» — раньше sync не копировал
    contractor_id из contract.
    """
    q = await db.execute(
        select(Purchase).where(Purchase.contract_id.is_not(None))
    )
    purchases_list = q.scalars().all()
    stats = {"total": len(purchases_list), "updated": 0, "skipped_no_contract": 0, "details": []}
    for p in purchases_list:
        before = (p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id)
        await _sync_purchase_from_contract(p, db)
        after = (p.contract_number, p.contract_date, p.purchase_contract_type, p.contractor_id)
        if before != after:
            stats["updated"] += 1
            if len(stats["details"]) < 50:  # cap response size
                stats["details"].append({
                    "purchase_id": p.id,
                    "registry_number": p.registry_number,
                    "contract_id": p.contract_id,
                    "before": {"number": before[0], "date": str(before[1]) if before[1] else None,
                               "type": before[2], "contractor_id": before[3]},
                    "after": {"number": after[0], "date": str(after[1]) if after[1] else None,
                              "type": after[2], "contractor_id": after[3]},
                })
    await db.commit()
    # NB (найдено при рефакторинге 16-XX, НЕ исправлено — вне мандата задачи):
    # функция строит `stats`, но не возвращает его — эндпоинт всегда отдаёт
    # null. Поведение сохранено как было в purchases.py до переноса.
