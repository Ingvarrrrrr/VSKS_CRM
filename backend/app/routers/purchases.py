import difflib
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import select, func, delete, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.contract import Contract
from app.models.subsidy import Subsidy
from app.models.product import Product
from app.models.feo_category import FeoCategory
from app.schemas.schemas import PurchaseCreate, PurchaseOut, PurchaseOutFull
from app.models.subsidy_allocation import PurchaseSubsidyAllocation
from app.auth.jwt import get_current_user, get_org_filter, get_single_org_id, ADMIN_ROLES
from app.auth.visibility import build_visibility_clause, get_visible_user_ids, get_visible_subsidy_ids
from app.utils.coerce import coerce_patch_value
from app.models.user import User
from app.routers.contracts import ensure_contract_linked
from app.routers.purchase_budget import _check_budget, _assign_framework_seq, FRAMEWORK_TYPES
from app.services.feo_plan import assert_no_unapproved_excess, assert_tz_not_over_plan, assert_tz_batch_not_over_plan, compute_feo_plan_tree
# Владелец (2026-09-02): превышение ТЗ над её КОНКРЕТНОЙ плановой позицией — на
# путях «заявка/авансовый отчёт/СЗ создаёт закупку» (create_purchase) и «прямое
# редактирование закупки» (update_purchase, PUT) — больше не 409, регистрируется
# как запрос на согласование (см. докстринг app/services/tz_excess_approval.py).
# patch_purchase_item (точечная правка ОДНОЙ позиции) и split (разбивка позиции)
# — в app/routers/purchase_items_edit.py — НЕ тронуты — там жёсткий отказ, как
# и раньше (см. отчёт задачи 16-XX, разрезание этого файла на модули).
from app.services.tz_excess_approval import (
    collect_tz_over_plan_violations, register_tz_excess_approvals, assert_no_pending_tz_excess,
)
# Владелец (2026-08-12, «закупка сама становится планом»): та же логика
# автозаведения плановой позиции, что и в wishes.py, нужна и здесь — для
# закупок, созданных/меняемых в обход заявки (см. вызов ниже в update_purchase;
# patch_purchase_item использует свою копию импорта в
# app/routers/purchase_items_edit.py). См. app/services/plan_autoassign.py.
from app.services.plan_autoassign import auto_assign_planned_items
# Правка прод-инцидента (сессия 2026-09-01): PUT ниже удаляет и пересоздаёт
# ВСЕ PurchaseItem закупки — ON DELETE SET NULL рвёт ContractItem.source_item_id.
# relink_contract_items восстанавливает связь после пересоздания, см. docstring
# в app/services/contract_item_link.py — там же полный диагноз.
from app.services.contract_item_link import relink_contract_items, build_purchase_item_id_map
from app.product_matcher import find_matching_product
from typing import List, Optional
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, date
# Разрезание монолита (Правило №5, сессия 2026-09-06): _purchase_to_full/
# _item_to_out (сериализация), _compute_purchase_feo_excess/
# _compute_purchase_feo_mismatch/_item_feo_mismatch/_category_within/
# _reset_incompatible_item_feo_links (проверки дерева ФЭО) и
# _create_plan_graph_version (снапшот плана) вынесены в app/services/ —
# единственный источник каждой из них (ПРАВИЛО №6), это ядро и остальные
# routers/purchase_*.py их переиспользуют, а не считают заново.
from app.services.purchase_serializers import _item_to_out, _purchase_to_full
from app.services.purchase_feo_checks import (
    _compute_purchase_feo_excess, _compute_purchase_feo_mismatch, _item_feo_mismatch,
    _category_within, _reset_incompatible_item_feo_links,
)
from app.services.plan_graph_versions import _create_plan_graph_version
router = APIRouter(prefix="/api/purchases", tags=["purchases"])

# Phase 31: fields tracked for diff-highlighting (D-05..D-09)
PURCHASE_TRACKED_FIELDS: set[str] = {
    "subject", "contractor_id", "planned_total_price",
    "status", "subsidy_id", "contract_number", "contract_date",
}


async def _sync_purchase_from_contract(p: Purchase, db: AsyncSession):
    """Когда установлен contract_id — копируем number/date/contract_type/contractor_id из contracts в purchases.

    Поля в purchases являются денормализованным снапшотом (для list-view без JOIN),
    но при наличии FK должны строго следовать связанному контракту.

    Phase 26-lll: contractor_id ОБЯЗАТЕЛЬНО синхронизируется — иначе в реестре
    закупок колонка «Контрагент» пустая (—), хотя в договоре контрагент есть.
    """
    if not p.contract_id:
        return
    c = await db.get(Contract, p.contract_id)
    if not c:
        return
    if c.number:
        p.contract_number = c.number.strip()
    if c.date:
        p.contract_date = c.date
    if c.contract_type:
        p.purchase_contract_type = c.contract_type
    if c.contractor_id and not p.contractor_id:
        # Не перетираем уже установленного контрагента (multi-contractor сценарии),
        # только заполняем NULL.
        p.contractor_id = c.contractor_id


async def _has_purchase_write_access(user: User, db: AsyncSession) -> bool:
    """True for any authenticated user.

    Дизайн: доступ к конкретной закупке гейтится через org_filter +
    _get_visible_user_ids в list_purchases. GET /{pid} вообще без auth — кто
    смог прочесть, тот может и сохранить (autosave PATCH). Бизнес-проверки
    (статус-переходы, согласование) — отдельные эндпоинты с require_action.

    Раньше эта функция гейтила MANAGER_ROLES + user_org_access — но у юзеров
    созданных давно (до Phase 17.1) могло не быть ни role, ни UOA-row,
    ни org_id (data-issue), что приводило к 403 при autosave формы закупки.
    """
    return user is not None


def is_framework_head(p) -> bool:
    """Истинно для рамочной ГОЛОВЫ договора: purchase_contract_type в
    FRAMEWORK_TYPES (framework_cumulative / framework_with_amount) И
    parent_purchase_id IS NULL (сама голова, не дочерняя закупка внутри
    рамочного — у дочерних позиции договора обязательны как обычно).

    Владелец (2026-08-31, «рамочные договора без закупок внутри должны
    согласовываться и печататься»): у головы может ещё не быть закупок
    внутри, но договор уже заключён на общую сумму (Purchase.contract_price) —
    вместо списка ContractItem. Единый источник истины для этой проверки:
    раньше purchases.py и purchase_transitions.py проверяли значение
    'framework_limited', которого в реальных данных НЕТ ВООБЩЕ (framework_
    cumulative — 11 закупок, framework_with_amount — 1, framework_limited —
    0; фронт шлёт именно 'framework_with_amount') — из-за этого рамочная
    голова нигде не распознавалась как рамочная, и её contract_price
    затирался суммой позиций при переходе в «Заключён договор». Теперь оба
    места (и documents.py) используют этот единственный хелпер, чтобы
    значения больше не могли разъехаться.
    """
    return (
        getattr(p, "purchase_contract_type", None) in FRAMEWORK_TYPES
        and getattr(p, "parent_purchase_id", None) is None
    )


async def _auto_match_feo_item(
    item_name: str,
    purchase_subsidy_id: Optional[int],
    purchase_feo_category_id: Optional[int],
    db: AsyncSession,
) -> Optional[tuple]:
    """
    Find best matching FeoPlannedItem for item_name.
    Returns (feo_planned_item_id, matched_name, confidence) or None.
    Threshold: 0.6.
    """
    from app.models.feo_planned_item import FeoPlannedItem as _FPI
    from app.models.feo_category import FeoCategory as _FC

    if not item_name:
        return None

    if purchase_feo_category_id:
        q = select(_FPI).where(
            _FPI.feo_category_id == purchase_feo_category_id,
            _FPI.is_active == True,
        )
    elif purchase_subsidy_id:
        q = (
            select(_FPI)
            .join(_FC, _FPI.feo_category_id == _FC.id)
            .where(_FC.subsidy_id == purchase_subsidy_id, _FPI.is_active == True)
        )
    else:
        return None

    candidates = (await db.execute(q)).scalars().all()
    if not candidates:
        return None

    name_lower = item_name.lower().strip()
    best_score = 0.0
    best_item = None
    for cand in candidates:
        score = difflib.SequenceMatcher(
            None, name_lower, cand.name.lower().strip()
        ).ratio()
        if score > best_score:
            best_score = score
            best_item = cand

    if best_score >= 0.6 and best_item is not None:
        return (best_item.id, best_item.name, round(best_score, 2))
    return None




# Status workflow
STATUS_ORDER = ["wishes", "plan_schedule", "work_in_progress", "contracted", "ordered", "delivered", "paid"]
VALID_SUBSTATUSES = ("tz_forming", "kp_collecting", "on_platform", "contractor_negotiations", "contract_signing")


@router.get("/", response_model=List[PurchaseOutFull])
async def list_purchases(
    contract_id: Optional[int] = Query(None),
    feo_category_id: Optional[int] = Query(None),
    subsidy_id: Optional[int] = Query(None),
    org_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    purchase_method: Optional[str] = Query(None),
    purchase_basis: Optional[str] = Query(None),
    framework_seq: Optional[int] = Query(None),
    vehicle_id: Optional[int] = Query(None),
    wish_id: Optional[int] = Query(None),
    limit: Optional[int] = Query(None),
    scope: Optional[str] = Query(None),
    with_feo_excess: bool = Query(
        False,
        description=(
            "Владелец (2026-08-12): значок «закупка создаёт превышение плана ФЭО» — "
            "считается ОПЦИОНАЛЬНО (compute_feo_plan_tree по субсидиям видимой страницы, "
            "не N+1, но заметно тяжелее обычного списка), фронт запрашивает явно."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.subsidy import Subsidy
    q = select(Purchase).options(
        selectinload(Purchase.contractor),
        selectinload(Purchase.feo_category),
        selectinload(Purchase.items).selectinload(PurchaseItem.product),
        selectinload(Purchase.files),
        selectinload(Purchase.event),
    )
    org_ids = get_org_filter(current_user)
    # #8: явный grant субсидии (user_subsidy_access) расширяет org-фильтр —
    # пользователь видит закупки субсидии вне своего контура.
    from app.models.user_subsidy_access import UserSubsidyAccess
    granted_ids = set((await db.execute(
        select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == current_user.id)
    )).scalars().all())
    _SCOPED_TABS = {"purchases", "advance_reports", "service_notes"}
    needs_subsidy_join = org_ids is not None or org_id is not None
    if scope is not None and scope in _SCOPED_TABS and org_id is None:
        # Двухуровневая видимость по конкретной вкладке (purchases / advance_reports / service_notes).
        vis = await get_visible_subsidy_ids(current_user, db, scope)
        if vis is not None:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            q = q.where(Subsidy.id.in_(vis))
    else:
        if needs_subsidy_join:
            q = q.join(Subsidy, Purchase.subsidy_id == Subsidy.id)
            if org_id is not None:
                # Explicit org filter takes precedence; still validate user has access to this org
                if org_ids is not None and org_id not in org_ids:
                    return []
                q = q.where(Subsidy.org_id == org_id)
            elif org_ids is not None:
                q = q.where(or_(Subsidy.org_id.in_(org_ids), Subsidy.id.in_(granted_ids)))
    # Phase 28: unified visibility helper.
    # — build_visibility_clause возвращает None для SaaS-ролей (фильтр не нужен),
    #   иначе or_() с правилами 1-5 (иерархия + участие).
    clause = await build_visibility_clause(current_user, db, 'purchase')
    if clause is not None:
        # Safety-net: для org-lead'ов всё ещё пропускаем закупки с
        # assigned_user_id IS NULL — на проде осталась 1 legacy-закупка
        # (id 779 без subsidy_id), будет удалена после ручного triage.
        # Org-lead = admin/account_owner ИЛИ есть head/managed dept/org/UOA.
        # Используем visible_user_ids: если size > 1 → user управляет ≥1 чел.
        vuids = await get_visible_user_ids(current_user, db)
        is_org_lead = (
            current_user.role in ADMIN_ROLES
            or (vuids is not None and len(vuids) > 1)
        )
        if is_org_lead:
            clause = or_(clause, Purchase.assigned_user_id.is_(None))
        q = q.where(clause)
    if contract_id:
        q = q.where(Purchase.contract_id == contract_id)
    if feo_category_id:
        # Фильтр по всему поддереву: закупки часто привязаны к дочерним категориям
        from app.routers.feo_categories import _collect_subtree_ids
        _sub_ids = await _collect_subtree_ids(feo_category_id, db)
        q = q.where(Purchase.feo_category_id.in_(_sub_ids))
    if subsidy_id:
        q = q.where(Purchase.subsidy_id == subsidy_id)
    if status:
        # Обратная совместимость: confirmed упразднён, маппируем в work_in_progress
        if status == "confirmed":
            status = "work_in_progress"
        q = q.where(Purchase.status == status)
    if purchase_method:
        q = q.where(Purchase.purchase_method == purchase_method)
    if purchase_basis:
        q = q.where(Purchase.purchase_basis == purchase_basis)
    if framework_seq is not None:
        q = q.where(Purchase.framework_seq == framework_seq)
    if vehicle_id is not None:
        q = q.where(Purchase.vehicle_id == vehicle_id)
    if wish_id is not None:
        q = q.where(Purchase.wish_id == wish_id)
    # Hide purchases that were split into children unless explicitly requested
    if status != "split":
        q = q.where(Purchase.status != "split")
    # Владелец (2026-08-21, дефект «отцеплённая закупка»): скрытые закупки
    # (status='wishes' — ещё не прошли гейт одобрения заявки ИЛИ принудительно
    # возвращены обратно через force_wish_status/_withdraw_wish_from_plan) не
    # должны попадать в реестр закупок — план они не расходуют, «не в работе»
    # (см. wishes.py._withdraw_wish_from_plan). Ограничено scope="purchases" —
    # ЕДИНСТВЕННЫЙ сценарий, которым пользуется реестр (OrdersView.vue грузит
    # /purchases/?scope=purchases, см. docstring duplicate_groups выше). Другие
    # места, где 'wishes' показывается НАМЕРЕННО (my-tasks/kanban «Желания
    # сотрудников», PlanView.vue scope=plan со справочным draft-чипом,
    # purchase_export.py, dashboard-виджеты), используют другие
    # запросы/scope и этим фильтром не затрагиваются. Явный status=wishes
    # запрос выполняем как есть (задан пользователем).
    if scope == "purchases" and status != "wishes":
        q = q.where(Purchase.status != "wishes")
    if search:
        like = f"%{search}%"
        from sqlalchemy import cast, String as SAString
        search_filters = [
            Purchase.item_name.ilike(like),
            Purchase.subject.ilike(like),
            Purchase.registry_number.ilike(like),
            Purchase.contract_number.ilike(like),
            Purchase.order_number.ilike(like),
        ]
        # Search by purchase_number if numeric
        if search.strip().isdigit():
            search_filters.append(Purchase.purchase_number == int(search.strip()))
        q = q.where(or_(*search_filters))
    q = q.order_by(Purchase.id.desc())
    if limit:
        q = q.limit(limit)
    result = await db.execute(q)
    purchases = result.scalars().all()

    contractors_r = await db.execute(select(Contractor))
    contractors_list = contractors_r.scalars().all()
    contractors = {c.id: c.name for c in contractors_list}
    contractor_inns = {c.id: c.inn for c in contractors_list}
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}

    # Batch-fetch reimbursement user names
    ru_ids = [p.reimbursement_user_id for p in purchases if p.reimbursement_user_id]
    ru_map: dict = {}
    if ru_ids:
        res = await db.execute(select(User.id, User.full_name).where(User.id.in_(ru_ids)))
        ru_map = {uid: name for uid, name in res.all()}

    # Остановка закупки (владелец, 2026-08-13): batch-fetch имён остановивших
    # (full_name или username, как для остальных «кто сделал» полей) — одним
    # запросом на всю страницу, без N+1.
    su_ids = [p.stopped_by for p in purchases if p.stopped_by]
    su_map: dict = {}
    if su_ids:
        res = await db.execute(select(User.id, User.full_name, User.username).where(User.id.in_(su_ids)))
        su_map = {uid: (fn or un) for uid, fn, un in res.all()}

    # Batch-fetch last receipt date for advance purchases
    from app.models.purchase_receipt import PurchaseReceipt
    adv_ids = [p.id for p in purchases if p.purchase_method == 'advance']
    receipt_map: dict = {}
    if adv_ids:
        res = await db.execute(
            select(PurchaseReceipt.purchase_id, func.max(PurchaseReceipt.receipt_datetime))
            .where(PurchaseReceipt.purchase_id.in_(adv_ids))
            .group_by(PurchaseReceipt.purchase_id)
        )
        receipt_map = {pid: dt for pid, dt in res.all()}

    # phase26-m: batch-load framework_contract_total (max_amount or SUM(contract_price))
    framework_contract_ids = {
        p.contract_id for p in purchases
        if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount')
    }
    display_total_by_contract: dict = {}
    if framework_contract_ids:
        contracts_r = await db.execute(
            select(Contract.id, Contract.max_amount).where(Contract.id.in_(framework_contract_ids))
        )
        contracts_by_id = {row[0]: row[1] for row in contracts_r.all()}
        for cid in framework_contract_ids:
            max_amount = contracts_by_id.get(cid)
            if max_amount is not None:
                display_total_by_contract[cid] = max_amount
            else:
                # ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки —
                # effective_amount_expr() вместо отдельной COALESCE-цепочки
                # (раньше не совпадала с purchase_amounts()/dashboard.py и т.д.).
                from app.services.purchase_amounts import effective_amount_expr as _eff_expr
                sum_r = await db.execute(
                    select(func.coalesce(func.sum(_eff_expr()), Decimal("0"))).where(Purchase.contract_id == cid)
                )
                display_total_by_contract[cid] = sum_r.scalar() or Decimal("0")

    # Phase 31: batch unseen_fields/unseen_changes_count (2 queries, no N+1) (D-05..D-09)
    purchase_ids = [p.id for p in purchases]
    unseen_map: dict[int, list[str]] = {}
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        unseen_map = await _get_unseen_map(db, 'purchase', purchase_ids, current_user.id)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen purchase map failed: %s", _exc)

    # Phase 31-04: batch contract_conflict — 1 query for all linked contracts (no N+1)
    linked_contract_ids = {p.contract_id for p in purchases if p.contract_id}
    contract_data_map: dict[int, tuple] = {}  # contract_id -> (number, date)
    if linked_contract_ids:
        _cr = await db.execute(
            select(Contract.id, Contract.number, Contract.date).where(Contract.id.in_(linked_contract_ids))
        )
        contract_data_map = {row[0]: (row[1], row[2]) for row in _cr.all()}

    # Владелец (2026-08-12): значок «закупка создаёт превышение плана ФЭО» — опционален
    # (?with_feo_excess=true), считается ОДНИМ вызовом compute_feo_plan_tree на все субсидии
    # видимой страницы (не N+1), без новых колонок в БД. Общий код с GET /{id} — см.
    # _compute_purchase_feo_excess (план crystalline-soaring-heron.md, п.4).
    _feo_excess_map: dict = {}
    if with_feo_excess and purchases:
        _feo_excess_map = await _compute_purchase_feo_excess(db, purchases)

    # Владелец (2026-09-02): «уведомление глобально, если позиция категории ФЭО
    # вверху и в каждом товаре не соответствует друг другу — об этом должен быть
    # алярм прям стоять». В отличие от feo_excess — считается ВСЕГДА (не под
    # флагом), одним батч-проходом на весь список (_compute_purchase_feo_mismatch),
    # чтобы в реестре можно было пометить строку без открытия карточки.
    _feo_mismatch_map: dict = {}
    if purchases:
        _feo_mismatch_map = await _compute_purchase_feo_mismatch(db, purchases)

    # ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки для всего списка —
    # 1 bulk-загрузка (см. load_purchase_amounts, без N+1), не по одному запросу
    # на закупку.
    from app.services.purchase_amounts import load_purchase_amounts as _load_purchase_amounts
    _amounts_map = await _load_purchase_amounts(db, purchase_ids) if purchase_ids else {}

    result_rows = []
    for p in purchases:
        out = _purchase_to_full(
            p, contractors, subsidies, contractor_inns=contractor_inns, receipt_map=receipt_map,
            ru_map=ru_map, su_map=su_map, feo_excess_map=_feo_excess_map,
            feo_mismatch_map=_feo_mismatch_map, amounts_map=_amounts_map,
        )
        if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount'):
            out.framework_contract_total = display_total_by_contract.get(p.contract_id)
        _unseen = unseen_map.get(p.id, [])
        out.unseen_fields = _unseen
        out.unseen_changes_count = len(_unseen)
        # contract_conflict: purchase has linked contract but copy of number/date doesn't match
        if p.contract_id and p.contract_id in contract_data_map:
            c_number, c_date = contract_data_map[p.contract_id]
            out.contract_conflict = (
                (c_number is not None and p.contract_number != c_number)
                or (c_date is not None and p.contract_date != c_date)
            )
        result_rows.append(out)
    return result_rows


@router.get("/{pid}", response_model=PurchaseOutFull)
async def get_purchase(pid: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(
        select(Purchase)
        .options(
            selectinload(Purchase.contractor),
            selectinload(Purchase.feo_category),
            selectinload(Purchase.items).selectinload(PurchaseItem.product),
            selectinload(Purchase.files),
            selectinload(Purchase.event),
            selectinload(Purchase.reimbursement_user),
            selectinload(Purchase.stopped_by_user),
        )
        .where(Purchase.id == pid)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")

    # Phase 26-Z-bootstrap: для advance закупок — silent idempotent recompute если
    # есть чеки и items с NULL contractor_id ИЛИ receipts без записи в acceptance_docs.
    if p.purchase_method == 'advance':
        try:
            from sqlalchemy import select as _sel
            from app.models.purchase_receipt import PurchaseReceipt as _PR
            from app.models.purchase_item import PurchaseItem as _PI
            receipts_count = (await db.execute(
                _sel(func.count(_PR.id)).where(_PR.purchase_id == pid)
            )).scalar() or 0
            if receipts_count > 0:
                null_items_count = (await db.execute(
                    _sel(func.count(_PI.id)).where(
                        _PI.purchase_id == pid,
                        _PI.contractor_id.is_(None),
                    )
                )).scalar() or 0
                current_docs = p.acceptance_docs or []
                receipt_ids_in_docs = {d.get("receipt_id") for d in current_docs if isinstance(d, dict) and d.get("receipt_id")}
                receipt_ids_actual = set((await db.execute(
                    _sel(_PR.id).where(_PR.purchase_id == pid)
                )).scalars().all())
                # Mismatch detection: позиция привязана к чеку, но контрагент не из этого чека
                mismatch_count = 0
                linked_items_q = await db.execute(
                    _sel(_PI).where(
                        _PI.purchase_id == pid,
                        _PI.receipt_id.is_not(None),
                    )
                )
                for _it in linked_items_q.scalars().all():
                    _r = await db.get(_PR, _it.receipt_id)
                    if not _r or not _r.seller_inn:
                        continue
                    if _it.contractor_inn != _r.seller_inn:
                        mismatch_count += 1
                        break  # достаточно одного для триггера
                # Phase 26-DD: receipts с raw_json items, но 0 PurchaseItem с этими receipt_id
                from app.routers.purchase_receipts import _extract_items as _ext_items
                orphan_receipts = 0
                if receipt_ids_actual:
                    for _rid in receipt_ids_actual:
                        _r = await db.get(_PR, _rid)
                        if not _r:
                            continue
                        _has_items = (await db.execute(
                            _sel(func.count(_PI.id)).where(_PI.receipt_id == _rid)
                        )).scalar() or 0
                        if _has_items == 0:
                            _raw_items = _ext_items(_r.raw_json or {})
                            if _raw_items:
                                orphan_receipts += 1
                                break
                need_recompute = bool(null_items_count) or bool(receipt_ids_actual - receipt_ids_in_docs) or bool(mismatch_count) or bool(orphan_receipts)
                if need_recompute:
                    from app.routers.purchase_receipts import _recompute_from_receipts_core
                    await _recompute_from_receipts_core(pid, db)
                    # Re-fetch p после recompute с теми же relationships
                    result = await db.execute(
                        select(Purchase)
                        .options(
                            selectinload(Purchase.contractor),
                            selectinload(Purchase.feo_category),
                            selectinload(Purchase.items).selectinload(PurchaseItem.product),
                            selectinload(Purchase.files),
                            selectinload(Purchase.event),
                            selectinload(Purchase.reimbursement_user),
                        )
                        .where(Purchase.id == pid)
                    )
                    p = result.scalar_one()
        except Exception as _re:
            import logging as _lg
            _lg.getLogger(__name__).warning(f"auto-recompute on GET /purchases/{pid} skipped: {_re}")

    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors = {c.id: c.name for c in contractors_r.scalars().all()}
    alloc_r = await db.execute(
        select(PurchaseSubsidyAllocation)
        .options(selectinload(PurchaseSubsidyAllocation.subsidy))
        .where(PurchaseSubsidyAllocation.purchase_id == pid)
    )
    allocations = alloc_r.scalars().all()
    single_ru_map: dict = {}
    if p.reimbursement_user_id and p.reimbursement_user:
        single_ru_map = {p.reimbursement_user_id: p.reimbursement_user.full_name}
    single_su_map: dict = {}
    if p.stopped_by and p.stopped_by_user:
        single_su_map = {p.stopped_by: (p.stopped_by_user.full_name or p.stopped_by_user.username)}

    # Превышение плана ФЭО (план crystalline-soaring-heron.md, п.4) — раньше
    # считалось только в списке (?with_feo_excess=true), карточка отдавала пусто.
    # Общий код с list_purchases — см. _compute_purchase_feo_excess.
    _single_feo_excess_map = await _compute_purchase_feo_excess(db, [p])

    # Расхождение категории ФЭО между шапкой/позицией/плановой позицией
    # (владелец, 2026-09-02) — см. _compute_purchase_feo_mismatch, тот же код
    # для списка и карточки.
    _single_feo_mismatch_map = await _compute_purchase_feo_mismatch(db, [p])

    # Остаток плановой позиции на КАЖДУЮ строку закупки (план п.4, «по позициям
    # отдавать остаток их плановой позиции, чтобы строку можно было подсветить»):
    #   - позиция привязана к FeoPlannedItem (Ур.5) — остаток берём с точностью
    #     до позиции (planned_item_consumption — тот же расчёт, что и в
    #     /feo-planned-items/residuals, БЕЗ exclude — это read-only карточка
    #     закупки, а не форма редактирования, своя же строка обязана входить в
    #     «съедено», иначе остаток был бы неправдой);
    #   - позиция только с feo_category_id (без Ур.5, план листа целиком) —
    #     остаток узла дерева ФЭО (compute_feo_plan_tree.residual), тот же расчёт,
    #     что использует /feo-categories/plan-positions для строк kind='feo_article'.
    _item_plan_map: dict = {}
    if p.items and p.subsidy_id:
        from app.models.feo_planned_item import FeoPlannedItem
        _fpi_ids = list({it.feo_planned_item_id for it in p.items if it.feo_planned_item_id})
        _fpi_residual: dict = {}
        if _fpi_ids:
            from app.services.feo_plan import planned_item_consumption as _planned_item_consumption
            _fpi_rows = (await db.execute(
                select(FeoPlannedItem.id, FeoPlannedItem.amount).where(FeoPlannedItem.id.in_(_fpi_ids))
            )).all()
            _fpi_amounts = {r[0]: float(r[1] or 0) for r in _fpi_rows}
            _fpi_cons = await _planned_item_consumption(db, _fpi_ids)
            for _fid in _fpi_ids:
                _amt = _fpi_amounts.get(_fid, 0.0)
                _used = (_fpi_cons.get(_fid) or {}).get("used", 0.0)
                _fpi_residual[_fid] = (_amt - _used, _amt)
        _need_tree = any(not it.feo_planned_item_id and (it.feo_category_id or p.feo_category_id) for it in p.items)
        _tree = await compute_feo_plan_tree(db, [p.subsidy_id]) if _need_tree else {}
        for it in p.items:
            if it.feo_planned_item_id and it.feo_planned_item_id in _fpi_residual:
                _item_plan_map[it.id] = _fpi_residual[it.feo_planned_item_id]
                continue
            _cid = it.feo_category_id or p.feo_category_id
            _node = _tree.get(_cid) if _cid else None
            if _node is not None:
                _item_plan_map[it.id] = (_node.get("residual"), _node.get("plan"))

    _wish_title_map: dict = {}
    _wish_status_map: dict = {}
    if p.wish_id:
        from app.models.wish import Wish as _Wish
        _w = await db.get(_Wish, p.wish_id)
        if _w:
            _wish_title_map[p.wish_id] = _w.title
            _wish_status_map[p.wish_id] = _w.status

    # ПРАВИЛО №6 (2026-09-05): единый расчёт суммы закупки — одна закупка,
    # load_purchase_amounts(db, [p.id]) переиспользует ту же bulk-функцию, что
    # и список (без второй формулы для detail-view).
    from app.services.purchase_amounts import load_purchase_amounts as _load_purchase_amounts_single
    _single_amounts_map = await _load_purchase_amounts_single(db, [p.id])

    out = _purchase_to_full(
        p, contractors, subsidies, allocations=allocations, ru_map=single_ru_map, su_map=single_su_map,
        feo_excess_map=_single_feo_excess_map, item_plan_map=_item_plan_map, wish_title_map=_wish_title_map,
        wish_status_map=_wish_status_map, feo_mismatch_map=_single_feo_mismatch_map,
        amounts_map=_single_amounts_map,
    )
    # phase26-m: populate framework_contract_total for single purchase view
    if p.contract_id and p.purchase_contract_type in ('framework_cumulative', 'framework_with_amount'):
        c = await db.get(Contract, p.contract_id)
        if c:
            if c.max_amount is not None:
                out.framework_contract_total = c.max_amount
            else:
                from app.services.purchase_amounts import effective_amount_expr as _eff_expr_single
                sum_r = await db.execute(
                    select(func.coalesce(func.sum(_eff_expr_single()), Decimal("0"))).where(Purchase.contract_id == p.contract_id)
                )
                out.framework_contract_total = sum_r.scalar() or Decimal("0")

    # Phase 31: unseen_fields for single purchase GET (D-05..D-09)
    try:
        from app.routers.entity_changes import get_unseen_map as _get_unseen_map
        _unseen_single = await _get_unseen_map(db, 'purchase', [pid], current_user.id)
        _unseen_fields = _unseen_single.get(pid, [])
        out.unseen_fields = _unseen_fields
        out.unseen_changes_count = len(_unseen_fields)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("unseen purchase single failed: %s", _exc)

    # Phase 31-04: contract_conflict — single GET (1 extra query, only if contract_id set)
    if p.contract_id:
        _c = await db.get(Contract, p.contract_id)
        if _c:
            out.contract_conflict = (
                (_c.number is not None and p.contract_number != _c.number)
                or (_c.date is not None and p.contract_date != _c.date)
            )

    return out


@router.post("/", response_model=PurchaseOut)
async def create_purchase(
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    context: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    is_advance = (data.purchase_method == 'advance')
    is_sn = (context == 'service_note_delivery')
    if not is_advance and not is_sn:
        raise HTTPException(
            403,
            detail="Прямое создание закупки отключено. Создайте заявку в разделе «Заявки на закупку» и отправьте на согласование — после одобрения она автоматически станет закупкой в «Плане закупок». Исключения: авансовые отчёты и СЗ на выдачу."
        )

    from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
    await assert_subsidy_approved_for_binding(db, data.subsidy_id)
    for _alloc in (data.subsidy_allocations or []):
        await assert_subsidy_approved_for_binding(db, _alloc.subsidy_id)

    items_data = data.items or []
    # Compute total_nmck from items
    total_nmck = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    if not admin_override and data.purchase_basis != 'service_note':
        await _check_budget(data.subsidy_id, total_nmck or data.planned_total_price, None, db)

    # Задача владельца (2026-08-05) «блокировать пока не согласовано превышение плана
    # ФЭО»: создание закупки — увеличивающее план действие. Проверяем по КАЖДОЙ
    # категории ФЭО, к которой отнесены позиции (per-item feo_category_id,
    # fallback — категория закупки целиком).
    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # assert_no_unapproved_excess больше не бросает 409 за перекос ОТДЕЛЬНОЙ
    # категории (excess_amount), возвращает список предупреждений вместо этого
    # (см. её docstring в feo_plan.py). Собираем их сюда для немедленного
    # ответа (excess_warnings в PurchaseOut) — тот же паттерн, что уже применён
    # в app.routers.wishes._collect_excess_warnings.
    _excess_warnings: list[dict] = []
    if not admin_override:
        _cat_amounts: dict[int, Decimal] = {}
        for _i in items_data:
            _cid = _i.feo_category_id or data.feo_category_id
            if _cid:
                _cat_amounts[_cid] = _cat_amounts.get(_cid, Decimal("0")) + (_i.total_price or Decimal("0"))
        if not _cat_amounts and data.feo_category_id:
            _cat_amounts[data.feo_category_id] = total_nmck or Decimal("0")
        for _cid, _amt in _cat_amounts.items():
            _excess_warnings.extend(await assert_no_unapproved_excess(db, _cid, adding_amount=_amt))

    # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): по каждой позиции,
    # ДО создания закупки. over_plan=true пропускаем — такая позиция сознательно
    # сверх плана и уже проходит через assert_no_unapproved_excess выше.
    # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): позиции, привязанные
    # к ОДНОЙ и той же плановой позиции, накапливаются в пределах ЭТОЙ закупки
    # (та же группировка, что у assert_tz_batch_not_over_plan) — иначе две строки
    # в сумме превышают план, каждая проходя поодиночке.
    # Владелец (2026-09-02): больше НЕ 409 здесь — этот путь тоже создаёт закупку
    # автоматически (авансовый отчёт/СЗ, см. is_advance/is_sn выше), симметрично
    # заявке. Собираем нарушения, регистрируем запрос на согласование ПОСЛЕ
    # создания закупки ниже (см. app.services.tz_excess_approval).
    _tz_violations: list[dict] = []
    if not admin_override:
        _tz_violations = await collect_tz_over_plan_violations(
            db, items_data, fallback_category_id=data.feo_category_id,
        )

    if not data.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        data.purchase_number = max_result.scalar() + 1

    dump = data.model_dump(exclude={"items", "subsidy_allocations"})
    dump["total_nmck"] = total_nmck
    # Phase 28 B4: validate provided assigned_user_id
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    # Auto-assign current user as owner when frontend did not specify one.
    # Без этого закупка с assigned_user_id=NULL становится невидимой для рядового
    # автора (list_purchases фильтрует по visible_user_ids; NULL IN (...) = false).
    if not dump.get("assigned_user_id"):
        dump["assigned_user_id"] = current_user.id
    # SN-UX: для СЗ авто-заполнить автора (текущий) и дату (сейчас) если фронт не прислал
    if dump.get("purchase_basis") == "service_note":
        if not dump.get("service_note_by"):
            dump["service_note_by"] = current_user.id
        if not dump.get("service_note_at"):
            from datetime import datetime, timezone
            dump["service_note_at"] = datetime.now(timezone.utc)
    p = Purchase(**dump)
    db.add(p)
    await db.flush()  # get p.id before commit

    year = date.today().year
    if not p.registry_number:
        p.registry_number = f"РЕЕ-{year}-{p.id:05d}"
    # removed in phase26-j-1: only set when single contract без FK на existing contracts row
    # auto-generate мусорит номером вида "2026/42" для рамочных закупок с реальным contract_id.
    if not p.contract_number and not p.contract_id:
        p.contract_number = f"{year}/{p.id}"

    # phase26-j-1: sync number/date/type из связанного контракта, если contract_id задан
    await _sync_purchase_from_contract(p, db)

    await _assign_framework_seq(p, db)

    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=p.id, **d)
        # Снимок плана (Шаг 1 «план ≠ факт»): позиция создаётся напрямую (не из
        # заявки) — план фиксируется как введённые сейчас значения, если снимок
        # не передан явно клиентом.
        if item.planned_quantity is None and item.planned_unit_price is None and item.planned_total is None:
            item.planned_quantity = item.quantity
            item.planned_unit_price = item.unit_price
            item.planned_total = item.total_price
        db.add(item)

    # Авансовый без wish_id → авто-заявка на возмещение (source='advance_report', status='submitted')
    if is_advance and not data.wish_id:
        from app.models.wish import Wish
        from app.models.wish_item import WishItem as WishItemModel
        wish_title = f"Возмещение по авансовому отчёту {p.registry_number or f'#{p.id}'}"
        auto_wish = Wish(
            source='advance_report',
            status='submitted',
            title=wish_title[:499],
            created_by=current_user.id,
            org_id=get_single_org_id(current_user) or current_user.org_id,
            subsidy_id=p.subsidy_id,
            feo_category_id=p.feo_category_id,
            event_id=p.event_id,
            justification=p.service_note_text,
            estimated_price=total_nmck,
        )
        db.add(auto_wish)
        await db.flush()  # get auto_wish.id
        p.wish_id = auto_wish.id
        # Копируем позиции закупки → WishItem
        for item_d in items_data:
            d = item_d.model_dump()
            db.add(WishItemModel(
                wish_id=auto_wish.id,
                item_name=d.get('item_name', ''),
                item_type=d.get('item_type'),
                quantity=d.get('quantity'),
                unit=d.get('unit'),
                unit_price=d.get('unit_price'),
                total_price=d.get('total_price'),
                country_origin=d.get('country_origin'),
                product_id=d.get('product_id'),
                feo_category_id=d.get('feo_category_id'),
            ))

    # Save subsidy allocations
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=p.id,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # ПРАВИЛО №6 (2026-09-05): единственный писатель денежных колонок — раньше
    # здесь была вторая копия «contract_price = Σ items» БЕЗ проверки статуса
    # (писала цену договора даже для закупки на стадии `wishes`, до всякого
    # договора — то самое «второе перо», конкурирующее с
    # _recalc_contract_price_from_contract_items). recalc_purchase_money сам
    # решает, писать ли contract_price, по стадии (см. purchase_money_writer.py).
    from app.services.purchase_money_writer import recalc_purchase_money
    _items_total_create = (
        sum((i.total_price or Decimal("0")) for i in items_data) if items_data else None
    )
    await recalc_purchase_money(db, p, items_total=_items_total_create, contract_items_total=None)

    # Budget history write hook — record initial planned_total_price
    if p.subsidy_id and p.planned_total_price:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=p.subsidy_id,
            purchase_id=p.id,
            entity_type="purchase",
            old_value=None,
            new_value=float(p.planned_total_price),
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
            reason=None,
        ))

    # Владелец (2026-09-02): регистрируем запрос(ы) на согласование превышения ТЗ
    # над плановой позицией ПОСЛЕ создания закупки/позиций (собраны выше, до
    # мутаций, см. _tz_violations) — reuse app.services.tz_excess_approval.
    if _tz_violations:
        await register_tz_excess_approvals(
            db, _tz_violations, subsidy_id=data.subsidy_id, current_user=current_user,
            context_label=f"создание закупки №{p.purchase_number or p.id}",
        )

    await db.commit()
    await db.refresh(p)
    if _excess_warnings:
        p.excess_warnings = _excess_warnings
    return p


@router.put("/{pid}")
async def update_purchase(
    pid: int,
    data: PurchaseCreate,
    admin_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    old_planned_total_price = p.planned_total_price  # capture BEFORE setattr loop
    # Задача владельца, план zany-fluttering-mountain.md п.4 (2026-08-10): PUT
    # заменяет ВСЕ позиции закупки (delete+recreate ниже), у каждой может быть
    # СВОЯ feo_category_id, отличная от p.feo_category_id. Старая проверка ниже
    # смотрела только на p.feo_category_id целиком — если позиции распределены
    # по нескольким категориям (feo_per_item), рост суммы в ОДНОЙ из них проходил
    # мимо гейта, пока «нетто» по закупке не рос. Снимок «сколько СЕЙЧАС числится
    # по каждой категории» — ДО удаления старых позиций — нужен для сравнения.
    old_item_cat_amounts: dict[int, Decimal] = {}
    for _oi in p.items:
        _ocid = _oi.feo_category_id or p.feo_category_id
        if _ocid:
            old_item_cat_amounts[_ocid] = old_item_cat_amounts.get(_ocid, Decimal("0")) + Decimal(str(_oi.total_price or 0))
    # Phase 31: capture old values for diff-tracking BEFORE any mutation
    _old_purchase_values = {f: getattr(p, f, None) for f in PURCHASE_TRACKED_FIELDS}
    # Employees/managers can save any purchase they have access to (org-level access checked at list level)
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    if admin_override and current_user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Обход бюджетного ограничения доступен только администратору")

    from app.services.subsidy_draft_guard import assert_subsidy_approved_for_binding
    await assert_subsidy_approved_for_binding(db, data.subsidy_id)
    for _alloc in (data.subsidy_allocations or []):
        await assert_subsidy_approved_for_binding(db, _alloc.subsidy_id)

    items_data = data.items or []
    items_sum = sum((i.total_price or Decimal("0")) for i in items_data) or data.nmck

    # Phase 28 B4: validate assigned_user_id on PUT
    if data.assigned_user_id is not None and data.assigned_user_id != 0:
        target = await db.get(User, data.assigned_user_id)
        if target is None:
            raise HTTPException(422, f"Пользователь {data.assigned_user_id} не найден")
    elif data.assigned_user_id == 0:
        raise HTTPException(422, "Укажите ответственного исполнителя")

    # Opportunistic backfill: legacy purchases с assigned_user_id=NULL
    # становятся видимыми создателю через первое же сохранение.
    if p.assigned_user_id is None and not getattr(data, "assigned_user_id", None):
        p.assigned_user_id = current_user.id

    # Auto-assign purchase_number if missing
    if not p.purchase_number:
        max_result = await db.execute(select(func.coalesce(func.max(Purchase.purchase_number), 0)))
        p.purchase_number = max_result.scalar() + 1

    # НМЦК logic: frozen after "contracted" status.
    # ПРАВИЛО №6 (2026-09-05): эта переменная (и статус, по которому она
    # считается — ДО setattr-цикла ниже, т.е. ещё старый p.status) теперь
    # используется ТОЛЬКО (a) для setattr-гейта payload'а ("не дать клиенту
    # перезаписать замороженный total_nmck/planned_total_price напрямую из
    # тела запроса", см. цикл ниже) и (b) для суммы бюджетной проверки здесь
    # (p.total_nmck ещё хранит значение из БД — сам пересчёт полей делает
    # ЕДИНСТВЕННЫЙ писатель денежных колонок, recalc_purchase_money, вызванный
    # ниже ПОСЛЕ setattr-цикла — там уже актуальный, новый статус этого PUT).
    # Раньше этот блок сам писал total_nmck/planned_total_price = items_sum —
    # второй писатель наряду с recalc_purchase_money, устранён здесь.
    CONTRACTED_STATUSES = ("contracted", "ordered", "delivered", "paid")
    is_contracted = p.status in CONTRACTED_STATUSES
    # Локальная (не персистентная) величина для двух проверок ниже — ТОЧНО та
    # же формула, что раньше физически записывалась в p.total_nmck на этом
    # месте; здесь она больше НЕ пишется в модель (это и есть устранённый
    # второй писатель), только используется как значение для гейтов.
    _total_nmck_for_checks = p.total_nmck if is_contracted else items_sum

    if not admin_override and data.purchase_basis != 'service_note':
        budget_amount = _total_nmck_for_checks
        # 12-02: per-item FEO budget check
        _feo_check_items = [
            {"feo_planned_item_id": i.feo_planned_item_id, "amount": i.total_price}
            for i in items_data
            if i.feo_planned_item_id and i.total_price
        ]
        await _check_budget(
            data.subsidy_id,
            budget_amount or data.planned_total_price,
            pid,
            db,
            feo_items=_feo_check_items,
            is_admin=current_user.role in ADMIN_ROLES,
        )

    # If contract_id or type changed, reset seq so it gets re-assigned
    old_contract_id = p.contract_id
    old_type = p.purchase_contract_type
    payload_dict = data.model_dump(exclude={"items", "subsidy_allocations"}, exclude_unset=True)
    # Phase 27.1.4: race-defence — если payload приходит с contractor_id=None,
    # а в БД он был установлен И contract_id не меняется → игнорируем stale null.
    # Это защищает от race в editFrameworkSeq: форма шлёт PUT до завершения async fetch контрагента.
    if (
        'contractor_id' in payload_dict
        and payload_dict['contractor_id'] is None
        and p.contractor_id is not None
        and payload_dict.get('contract_id', p.contract_id) == p.contract_id
    ):
        payload_dict.pop('contractor_id')

    # Владелец (2026-09-01): категория ФЭО после согласования — см.
    # _guard_feo_category_change_after_approval.
    _old_feo_category_id_put = p.feo_category_id
    if "feo_category_id" in payload_dict:
        await _guard_feo_category_change_after_approval(
            p, payload_dict["feo_category_id"], current_user, db
        )

    for k, v in payload_dict.items():
        # Don't overwrite frozen total_nmck
        if is_contracted and k in ("total_nmck", "planned_total_price"):
            continue
        setattr(p, k, v)
    # JSONB columns need explicit dirty-flag so SQLAlchemy detects mutations
    if "acceptance_docs" in data.model_fields_set:
        flag_modified(p, "acceptance_docs")

    # Владелец (2026-08-12, «закупка сама становится планом»): PUT — единственный
    # путь добавить/поменять позицию в УЖЕ СУЩЕСТВУЮЩЕЙ закупке напрямую (в обход
    # заявки — реальный случай с прода: категория 3716 «Приобретение брендированных
    # футболок» получила закупку на 149 282,50 ₽ без единой плановой позиции, ФЭО
    # автозаведения тогда не видело). Каждая позиция с категорией ФЭО (своей или
    # закупки целиком, items_data уже несёт её из payload'а — категория «применена»
    # раньше любых расчётных проверок ниже) без явной привязки находит/заводит
    # FeoPlannedItem — ДО assert_no_unapproved_excess/assert_tz_not_over_plan ниже,
    # иначе им не с чем сравнивать (тот же порядок, что в wishes.py._distribute_
    # wish_to_purchases). Работает на items_data (ещё pydantic, не персистентные
    # PurchaseItem) — auto_assign_planned_items требует только атрибуты
    # item_name/quantity/unit/total_price/feo_category_id/feo_planned_item_id/
    # over_plan, которые есть у обеих сторон; итоговый feo_planned_item_id/
    # over_plan, проставленные функцией на items_data, попадают в PurchaseItem
    # ниже через item_d.model_dump().
    await auto_assign_planned_items(
        items_data, p.feo_category_id, db,
        note=f"закупкой №{p.purchase_number or p.id} (правка вне заявки)",
    )

    # Задача владельца (2026-08-05) «блокировать пока не согласовано превышение плана
    # ФЭО», расширено 2026-08-10 (план zany-fluttering-mountain.md п.4) на ПЕР-ITEM
    # категории: изменение закупки, увеличивающее сумму В КОНКРЕТНОЙ категории ФЭО
    # (не только на уровне закупки целиком) — УВЕЛИЧИВАЮЩЕЕ план действие. Сравниваем
    # НОВЫЙ снимок по категориям (из items_data, только что распределённого PUT'ом,
    # тот же принцип, что и в create_purchase per-item) со СТАРЫМ (old_item_cat_amounts,
    # снят до удаления старых позиций выше) — категория, чья сумма ВЫРОСЛА (в т.ч. с
    # нуля — позиция перевешена в неё из другой категории), проходит гейт с дельтой
    # роста; категории, чья сумма НЕ выросла (уменьшилась/не изменилась), не трогаем —
    # это путь возврата в рамки плана, блокировать нельзя (см. assert_no_unapproved_excess
    # docstring).
    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # см. комментарий у create_purchase выше. Копится за весь PUT (обе точки
    # вызова ниже) и отдаётся в ответе как excess_warnings.
    _excess_warnings: list[dict] = []
    if not admin_override:
        _new_item_cat_amounts: dict[int, Decimal] = {}
        for _i in items_data:
            _ncid = _i.feo_category_id or p.feo_category_id
            if _ncid:
                _new_item_cat_amounts[_ncid] = _new_item_cat_amounts.get(_ncid, Decimal("0")) + (_i.total_price or Decimal("0"))
        if not _new_item_cat_amounts and p.feo_category_id:
            _new_item_cat_amounts[p.feo_category_id] = Decimal(str(_total_nmck_for_checks or 0))
        _touched_cat_ids = set(_new_item_cat_amounts) | set(old_item_cat_amounts)
        for _cid in _touched_cat_ids:
            _new_amt = _new_item_cat_amounts.get(_cid, Decimal("0"))
            _old_amt = old_item_cat_amounts.get(_cid, Decimal("0"))
            if _new_amt > _old_amt:
                _excess_warnings.extend(
                    await assert_no_unapproved_excess(db, _cid, adding_amount=_new_amt - _old_amt)
                )

    # Задача владельца «план ≠ факт» (шаг C, сессия 2026-08-06): переход закупки
    # в «Договор» — превентивная точка контроля. С этого момента итог закупки
    # (факт по договорным позициям/КП, см. FACT_PRICED_STATUSES в feo_plan.py)
    # уже мог сложиться дороже плана ещё на «Ведётся работа» — если превышение
    # факт-над-планом не согласовано, подписывать договор нельзя (иначе перерасход
    # закрывают постфактум поиском доп. финансирования — ровно то, что владелец
    # просил предотвратить). Проверяем по каждой категории ФЭО позиций закупки
    # (per-item feo_category_id, fallback — категория закупки целиком), как и
    # в create_purchase выше.
    _old_status_for_gate = _old_purchase_values.get("status")
    if not admin_override and p.status == "contracted" and _old_status_for_gate != "contracted":
        _gate_cat_ids: set[int] = set()
        for _i in items_data:
            _cid = _i.feo_category_id or p.feo_category_id
            if _cid:
                _gate_cat_ids.add(_cid)
        if not _gate_cat_ids and p.feo_category_id:
            _gate_cat_ids.add(p.feo_category_id)
        for _cid in _gate_cat_ids:
            _excess_warnings.extend(await assert_no_unapproved_excess(db, _cid))
        # Владелец (2026-09-02): тот же момент («Договор» — превентивная точка
        # контроля) обязан видеть и item-level превышение ТЗ над плановой позицией
        # (см. app.services.tz_excess_approval — assert_no_unapproved_excess из
        # feo_plan.py его не видит). Проверяем items_data — то, что РЕАЛЬНО будет
        # сохранено (PUT заменяет все позиции целиком, старый p.items не годится
        # для этой проверки — см. комментарий у assert_tz_batch_not_over_plan ниже).
        await assert_no_pending_tz_excess(db, items_data, fallback_category_id=p.feo_category_id)

    # ПРАВИЛО №6 (2026-09-05): единственный писатель денежных колонок — раньше
    # здесь `contract_price = items_sum` писалось В ЛЮБОМ статусе (даже до
    # договора, до единой строки ContractItem) — второе перо, конкурирующее с
    # Σ contract_items.total (см. _recalc_contract_price_from_contract_items).
    # Тем же вызовом пересчитываются total_nmck/planned_total_price/nmck по
    # АКТУАЛЬНОМУ (уже применённому setattr-циклом выше) статусу — см.
    # purchase_money_writer.py. items_sum выше посчитан с Python-truthy
    # фолбэком на data.nmck (используется для бюджетной проверки, не трогаем
    # его формулу) — сюда передаём чистую Σ purchase_items.total_price.
    from app.services.purchase_money_writer import recalc_purchase_money
    _items_total_put = (
        sum((i.total_price or Decimal("0")) for i in items_data) if items_data else None
    )
    await recalc_purchase_money(db, p, items_total=_items_total_put)
    if (p.contract_id != old_contract_id or p.purchase_contract_type != old_type) and data.framework_seq is None:
        p.framework_seq = None  # force re-assignment below
    # phase26-j-1 (fix: hotfix после регрессии): sync только при ИЗМЕНЕНИИ contract_id,
    # иначе ручные правки contract_number перетираются на каждом save (Vue v-model шлёт contract_id всегда).
    if p.contract_id and p.contract_id != old_contract_id:
        await _sync_purchase_from_contract(p, db)
    await _assign_framework_seq(p, db, exclude_id=pid)

    # Шаг 5 «цена ТЗ не выше плановой» (владелец, 2026-08-07): по каждой НОВОЙ позиции,
    # ДО удаления старых (PUT заменяет все позиции целиком — старые снимки плана
    # старых строк тут не помогут, проверяем именно то, что придёт в базу).
    # over_plan=true пропускаем — сознательно сверх плана, см. create_purchase выше.
    # Владелец (2026-08-17, прод-инцидент РЕЕ-2026-00887): накопление по общей
    # плановой позиции в пределах ЭТОЙ закупки (та же группировка, что у
    # assert_tz_batch_not_over_plan).
    # Владелец (2026-09-02): больше НЕ 409 здесь. Причина смены решения именно
    # здесь, а не только в create_purchase/wishes.py: PUT — ЕДИНСТВЕННЫЙ путь
    # сохранить закупку целиком (пересылает ВСЕ позиции при КАЖДОМ сохранении, в
    # т.ч. правку поля, никак не связанного с ТЗ) — оставь здесь жёсткий отказ, и
    # закупка, попавшая в План закупок с превышением ТЗ (заявка/аванс/СЗ выше),
    # стала бы НЕРЕДАКТИРУЕМОЙ вообще (кроме admin_override) до момента, пока
    # кто-то не решит превышение — то есть блокировка «дальше двигаться нельзя»
    # молча расползлась бы и на «сохранить дату доставки», а этого владелец не
    # просил. Собираем нарушения, регистрируем запрос ПОСЛЕ сохранения позиций
    # (см. _tz_violations_put ниже) — реальную блокировку ДВИЖЕНИЯ обеспечивает
    # assert_no_pending_tz_excess (см. выше, у входа в «Договор») и
    # purchase_transitions.py (см. её докстринг).
    _tz_violations_put: list[dict] = []
    if not admin_override:
        _tz_violations_put = await collect_tz_over_plan_violations(
            db, items_data, fallback_category_id=p.feo_category_id,
        )

    # Снимок старых плановых позиций ДО удаления (правка прод-инцидента,
    # сессия 2026-09-01, см. app/services/contract_item_link.py): PUT ниже
    # удаляет ВСЕ PurchaseItem и вставляет их заново под новыми id — это
    # рвёт ContractItem.source_item_id (FK ON DELETE SET NULL). Снимок
    # нужен, чтобы после вставки сопоставить старые/новые id и восстановить
    # связь через relink_contract_items(id_map=...) ниже.
    _old_items_snapshot = [
        (it.id, it.item_name, it.quantity, it.unit_price)
        for it in sorted(p.items, key=lambda x: x.id)
    ]

    # Replace items (auto-link to catalog via fuzzy match if product_id missing)
    await db.execute(delete(PurchaseItem).where(PurchaseItem.purchase_id == pid))
    for item_d in items_data:
        d = item_d.model_dump()
        if not d.get("product_id") and d.get("item_name"):
            org_id_for_match = get_single_org_id(current_user) or current_user.org_id
            existing = await find_matching_product(db, d["item_name"], org_id=org_id_for_match)
            if existing:
                d["product_id"] = existing.id
            else:
                new_prod = Product(
                    name=d["item_name"].strip(),
                    product_type=d.get("item_type"),
                    price=d.get("unit_price"),
                    org_id=org_id_for_match,
                )
                db.add(new_prod)
                await db.flush()
                d["product_id"] = new_prod.id
        item = PurchaseItem(purchase_id=pid, **d)
        # Снимок плана (Шаг 1 «план ≠ факт»): PUT удаляет и пересоздаёт ВСЕ позиции
        # (нет id для сопоставления со старым снимком), поэтому снимок фиксируем из
        # введённых значений только пока закупка ещё в статусе «План закупок» — так
        # же, как PATCH одной позиции ниже. Для более поздних статусов снимок НЕ
        # восстановить из уже удалённой строки — оставляем NULL, а не подставляем
        # текущую (возможно уже не плановую) цену как будто это план.
        if (
            p.status == "plan_schedule"
            and item.planned_quantity is None and item.planned_unit_price is None and item.planned_total is None
        ):
            item.planned_quantity = item.quantity
            item.planned_unit_price = item.unit_price
            item.planned_total = item.total_price
        db.add(item)

    # Phase 26-Z: при PUT — проставить contractor_id во все позиции без контрагента,
    # если на уровне закупки contractor_id установлен. Идемпотентно.
    if p.contractor_id:
        await db.flush()  # flush чтобы только что созданные items видны в SELECT
        _ctr_put = await db.get(Contractor, p.contractor_id)
        if _ctr_put:
            _null_items_put = (await db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == pid, PurchaseItem.contractor_id.is_(None))
            )).scalars().all()
            for _it in _null_items_put:
                _it.contractor_id = _ctr_put.id
                _it.contractor_inn = _ctr_put.inn
                _it.contractor_name = _ctr_put.name

    # 12-02: Auto-match FEO items for purchase items without feo_planned_item_id
    suggested_feo_matches = []
    await db.flush()  # ensure new items are visible
    _flushed_items = (await db.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == pid)
    )).scalars().all()

    # Владелец (2026-09-02): смена категории ФЭО шапки закупки — см.
    # _reset_incompatible_item_feo_links. ДО авто-подбора ниже, чтобы только
    # что сброшенные позиции сразу попали в suggested_feo_matches (новый
    # подбор по НОВОЙ категории), а не остались молча указывать на старую.
    _feo_links_reset = await _reset_incompatible_item_feo_links(
        _flushed_items, _old_feo_category_id_put, p.feo_category_id,
        bool(p.feo_per_item), db,
    )

    # Восстановление ContractItem.source_item_id (см. снимок выше и
    # app/services/contract_item_link.py): сопоставляем старые/новые id
    # плановых позиций, затем чиним договорные позиции этой закупки ДО
    # commit — одной транзакцией с самим сохранением закупки.
    _purchase_item_id_map = build_purchase_item_id_map(_old_items_snapshot, _flushed_items)
    _relinked_count = await relink_contract_items(db, pid, id_map=_purchase_item_id_map)
    if _relinked_count:
        import logging as _log
        _log.getLogger(__name__).info(
            "relink_contract_items: восстановлено %d связей source_item_id для закупки #%s (update_purchase)",
            _relinked_count, pid,
        )

    for idx, pi in enumerate(_flushed_items):
        if pi.feo_planned_item_id is not None:
            continue  # already linked
        match = await _auto_match_feo_item(
            pi.item_name,
            p.subsidy_id,
            p.feo_category_id,
            db,
        )
        if match:
            suggested_feo_matches.append({
                "item_index": idx,
                "purchase_item_id": pi.id,
                "item_name": pi.item_name,
                "suggested_item_id": match[0],
                "suggested_name": match[1],
                "confidence": match[2],
            })

    # Replace subsidy allocations
    await db.execute(delete(PurchaseSubsidyAllocation).where(PurchaseSubsidyAllocation.purchase_id == pid))
    if data.subsidy_allocations:
        for alloc in data.subsidy_allocations:
            db.add(PurchaseSubsidyAllocation(
                purchase_id=pid,
                subsidy_id=alloc.subsidy_id,
                amount=alloc.amount,
            ))

    # Auto-create/link contract record when contract_number is set
    await ensure_contract_linked(p, db)

    # Budget history write hook
    if p.subsidy_id:
        _old = float(old_planned_total_price or 0)
        _new = float(p.planned_total_price or 0)
        if _old != _new:
            from app.models.budget_history import BudgetHistory as _BH
            db.add(_BH(
                subsidy_id=p.subsidy_id,
                purchase_id=p.id,
                entity_type="purchase",
                old_value=_old,
                new_value=_new,
                changed_by_id=current_user.id,
                changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                reason=None,
            ))

    # Авансовый: синхронизировать связанную авто-заявку если она ещё не одобрена
    if p.purchase_method == 'advance' and p.wish_id:
        from app.models.wish import Wish
        from app.models.wish_item import WishItem as WishItemModel
        _wish = await db.get(Wish, p.wish_id)
        if _wish and getattr(_wish, 'source', None) == 'advance_report' and _wish.status in ('draft', 'submitted', 'rejected'):
            _wish.estimated_price = items_sum or p.planned_total_price
            _wish.justification = p.service_note_text
            _wish.title = f"Возмещение по авансовому отчёту {p.registry_number or f'#{p.id}'}"[:499]
            # Пересобрать WishItems из позиций закупки
            await db.execute(delete(WishItemModel).where(WishItemModel.wish_id == _wish.id))
            for item_d in items_data:
                d = item_d.model_dump()
                db.add(WishItemModel(
                    wish_id=_wish.id,
                    item_name=d.get('item_name', ''),
                    item_type=d.get('item_type'),
                    quantity=d.get('quantity'),
                    unit=d.get('unit'),
                    unit_price=d.get('unit_price'),
                    total_price=d.get('total_price'),
                    country_origin=d.get('country_origin'),
                    product_id=d.get('product_id'),
                    feo_category_id=d.get('feo_category_id'),
                ))

    # 12-03: Auto-create plan-graph version on status→fact or FEO-linked items
    _old_status = _old_purchase_values.get("status")
    _status_became_fact = (
        p.status in ("delivered", "paid")
        and _old_status not in ("delivered", "paid")
    )
    _has_feo_items = any(i.feo_planned_item_id for i in items_data if i.feo_planned_item_id)
    if p.subsidy_id and (_status_became_fact or _has_feo_items):
        if _status_became_fact:
            _st_label = "Оплачено" if p.status == "paid" else "Поставлено"
            _pgv_note = f"Авто-версия: закупка №{p.purchase_number or p.id} → {_st_label}"
        else:
            _pgv_note = f"Авто-версия при сохранении закупки #{p.purchase_number or p.id}"
        await _create_plan_graph_version(subsidy_id=p.subsidy_id, db=db, user=current_user, note=_pgv_note)

    # Владелец (2026-09-02): регистрируем запрос(ы) на согласование превышения ТЗ
    # над плановой позицией (собраны выше до мутаций, см. _tz_violations_put).
    if _tz_violations_put:
        await register_tz_excess_approvals(
            db, _tz_violations_put, subsidy_id=(data.subsidy_id or p.subsidy_id), current_user=current_user,
            context_label=f"сохранение закупки №{p.purchase_number or p.id}",
        )

    await db.commit()
    await db.refresh(p)

    # Phase 31: record EntityChange for each TRACKED_FIELD that changed (D-05..D-09)
    # Only record changes made by OTHER users (D-07: own changes are not highlighted)
    try:
        from app.models.entity_change import EntityChange as _EC
        _changes = []
        for _fname in PURCHASE_TRACKED_FIELDS:
            _old = _old_purchase_values.get(_fname)
            _new = getattr(p, _fname, None)
            _old_s = str(_old) if _old is not None else None
            _new_s = str(_new) if _new is not None else None
            if _old_s != _new_s:
                _changes.append(_EC(
                    entity_type='purchase',
                    entity_id=p.id,
                    field_name=_fname,
                    old_value=_old_s,
                    new_value=_new_s,
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                ))
        if _changes:
            for _c in _changes:
                db.add(_c)
            await db.commit()
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed: %s", _exc)

    # 12-02: Return suggestions if any + Владелец (2026-09-02): сообщить фронту,
    # сколько привязок feo_planned_item_id сброшено сменой категории шапки
    # (см. _reset_incompatible_item_feo_links) — чтобы показать предупреждение
    # "переопределите плановые позиции заново".
    # Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка» —
    # _excess_warnings (собраны выше у обеих точек assert_no_unapproved_excess
    # этого PUT) тоже требует явной сериализации через PurchaseOut, как и
    # suggested_feo_matches/_feo_links_reset — см. комментарий у create_purchase.
    if suggested_feo_matches or _feo_links_reset or _excess_warnings:
        from app.schemas.schemas import PurchaseOut as _POut
        base = _POut.model_validate(p).model_dump()
        if suggested_feo_matches:
            base["suggested_feo_matches"] = suggested_feo_matches
        base["feo_links_reset"] = _feo_links_reset
        if _excess_warnings:
            base["excess_warnings"] = _excess_warnings
        return base
    return p


async def _generate_temp_contract_number(p: Purchase, db: AsyncSession) -> str:
    """Технический номер договора для рамочной головы, у которой на момент
    формирования документа ещё не известны реальные номер/дата (владелец,
    2026-08-31): «Надо присваивать какой-то технический номер на данный
    момент времени и ставить примечание, что надо актуализировать номер».

    Формат: «ВРЕМ-{№закупки}», если у закупки есть purchase_number, иначе
    «ВРЕМ-{id закупки}». При коллизии с уже занятым contract_number другой
    закупки — добавляется числовой суффикс «-2», «-3», ... до первого
    свободного варианта.
    """
    base_num = p.purchase_number or p.id
    base = f"ВРЕМ-{base_num}"
    candidate = base
    suffix = 1
    while True:
        taken = (await db.execute(
            select(Purchase.id).where(
                Purchase.contract_number == candidate,
                Purchase.id != p.id,
            )
        )).scalar_one_or_none()
        if taken is None:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


# Phase 27.1 D-07: helper — авто-пересчёт purchase.contract_price = SUM(contract_items.total)
async def _recalc_contract_price_from_contract_items(purchase_id: int, db: AsyncSession) -> None:
    """Phase 27.1 D-07: авто-пересчёт purchase.contract_price = SUM(contract_items.total).

    Применимо: разовая (purchase_contract_type='single' или NULL), авансовая
    (purchase_method='advance'), дочерняя рамочного (parent_purchase_id IS NOT NULL).
    НЕ применимо для рамочного головного (framework_cumulative/framework_with_amount
    AND parent_purchase_id IS NULL) — manual entry сохраняется, см. is_framework_head().

    ПРАВИЛО №6 (2026-09-05): имя/сигнатура сохранены (внешние импорты —
    contract_items.py, тесты test_purchase_contract_price_recalc.py), тело —
    тонкая обёртка над единственным писателем денежных колонок,
    app.services.purchase_money_writer.recalc_purchase_money (та же логика
    рамочной головы там — FRAMEWORK_TYPES/is_head, зеркало is_framework_head()
    ниже в этом файле).
    """
    from app.services.purchase_money_writer import recalc_purchase_money
    p = await db.get(Purchase, purchase_id)
    if not p:
        return
    await recalc_purchase_money(db, p)
    await db.commit()


# Владелец (2026-09-01): «закупки после согласования есть возможность
# поменять категорию ФЭО, но это неправильно... остальным пользователям не
# должна предоставляться возможность менять после согласования» — с этого
# момента смена feo_category_id на закупке с approval_status='approved'
# запрещена обычным пользователям (422) и разрешена только суперадмину, но
# с уведомлением согласовавших + ответственного/назначенного по закупке.
# Вызывается и из PATCH (autosave — реальный вектор бага, фронт шлёт
# feo_category_id в serializeFormForAutosave), и из PUT (явный Save).
async def _guard_feo_category_change_after_approval(
    p: Purchase,
    new_feo_category_id,
    current_user,
    db: AsyncSession,
) -> None:
    if new_feo_category_id is None:
        return
    if new_feo_category_id == p.feo_category_id:
        return
    if p.approval_status != "approved":
        return

    if current_user.role != "superadmin":
        raise HTTPException(
            422,
            detail={
                "code": "FEO_CATEGORY_LOCKED_AFTER_APPROVAL",
                "message": (
                    "Закупка уже согласована — менять категорию ФЭО нельзя. "
                    "Если нужно — снимите согласование или обратитесь к администратору."
                ),
            },
        )

    # Суперадмин: смена разрешена, но согласовавшие и ответственный должны узнать.
    from app.notifications import notify_user, _esc, _purchase_url
    from app.models.purchase_approval import PurchaseApproval

    old_cat = await db.get(FeoCategory, p.feo_category_id) if p.feo_category_id else None
    new_cat = await db.get(FeoCategory, new_feo_category_id)
    old_name = old_cat.name if old_cat else "без категории"
    new_name = new_cat.name if new_cat else "—"
    actor_name = current_user.full_name or current_user.username
    when = datetime.now().strftime("%d.%m.%Y %H:%M")
    text = (
        f"⚠️ <b>Категория ФЭО изменена после согласования</b>\n\n"
        f"📌 Закупка №{p.purchase_number or p.id}\n"
        f"👤 {_esc(actor_name)} изменил(а) {when}:\n"
        f"«{_esc(old_name)}» → «{_esc(new_name)}»"
    )

    recipient_ids: set[int] = set()
    result = await db.execute(
        select(PurchaseApproval.user_id).where(
            PurchaseApproval.purchase_id == p.id,
            PurchaseApproval.status == "approved",
            PurchaseApproval.user_id.isnot(None),
        )
    )
    for uid in result.scalars().all():
        recipient_ids.add(uid)
    if p.assigned_user_id:
        recipient_ids.add(p.assigned_user_id)

    for uid in recipient_ids:
        u = await db.get(User, uid)
        if u:
            await notify_user(u, text, button_url=_purchase_url(p.id), button_label="Открыть закупку")




# Phase 26: автосохранение полей карточки закупки.
# Принимает произвольный частичный JSON; обновляет только переданные поля.
# Не пересчитывает items/НМЦК/contract_price (этим занимается PUT при явном Save).
PATCHABLE_FIELDS = {
    "subject", "description", "contractor_id", "feo_category_id",
    "purchase_method", "competitive_form", "purchase_contract_type",
    "contract_number", "contract_date", "contract_price", "contract_end_date",
    "contract_number_is_temporary",
    "nmck", "planned_total_price",
    "delivery_date", "delivery_location", "delivery_address",
    "delivery_region", "delivery_city", "delivery_street",
    "delivery_house", "delivery_building", "delivery_postcode",
    "submission_deadline", "service_term_mode", "service_start_date",
    "service_end_date", "service_term_days", "service_term_type",
    "service_deadline_date", "third_party_involved",
    "vat_applicable", "vat_rate", "vat_exemption_article", "vat_mode", "feo_per_item",
    "acceptance_doc_name", "acceptance_doc_date", "acceptance_doc_number",
    "acceptance_doc_amount",
    # Phase 24 D-08: JSONB-массив закрывающих документов (АКТ/УПД/СЧФ/ТТН/...)
    "acceptance_docs",
    "payment_doc_number", "payment_doc_date",
    "payment_amount", "country_origin", "purchase_basis",
    "responsible_person", "initiator_id", "subject_kind", "execution_term",
    "event_id", "delivery_location_kind", "region",
    # Phase 24: stages + financial plan
    "is_likely_needed", "is_prepayment", "prepayment_date", "stage_label",
    # Авансовый отчёт: кому возмещать
    "reimbursement_user_id",
    # Phase 28 B4: ответственный исполнитель
    "assigned_user_id",
    # Phase 26-K: доп. соглашение и дата заказа
    "agreement_number", "agreement_date", "order_date",
    # Phase 28: форма договора (выбор шаблона при генерации)
    "contract_form",
    # Методичка, приклеиваемая к договору (large / small / none)
    "methodology",
    # Phase 28: contract-specific поля (условия конкретного договора)
    'acceptance_term_days', 'penalty_rate', 'contractor_ogrnip_date',
    'repair_request_number',
    'commission_member_1_name', 'commission_member_2_name', 'commission_member_3_name',
    'advance_amount',
    # Phase 28: гарантия + ретроактивный договор (комментарии пользователя 2026-05-19)
    'warranty_period_days', 'is_retroactive',
    # Phase 29: связь закупки с ТС
    'vehicle_id',
    # SN-UX: адресат служебной записки
    'service_note_to_user_id',
    # ЭТП: ссылка на конкурсную процедуру
    'etp_url',
    # Fabrikant: срок оплаты и дата рассмотрения заявок
    'payment_term_days', 'applications_review_date',
    # Импорт/экспорт: квартал обязательств и планируемый месяц платежа
    "commitment_quarter", "planned_payment_month",
    # Phase 28 T6/T7: условные блоки шаблонов + протокол/приказ закупки
    "delivery_by_supplier", "has_stages",
    "procurement_protocol_number", "procurement_order_number",
}


# Имена полей с типом DATE/DATETIME — для коэрсии строк в date-объекты в PATCH.
# Фронт шлёт ISO-строки ('2026-05-08'), asyncpg ожидает date()/datetime().
# Полный список из backend/app/models/purchase.py — все Column(Date)/Column(DateTime).
_DATE_FIELDS = {
    "contract_date", "execution_term", "execution_term_changed",
    "delivery_date", "acceptance_doc_date", "payment_doc_date",
    "contract_end_date", "service_start_date", "service_end_date",
    "procurement_planned_date", "service_deadline_date", "prepayment_date",
    # Phase 26-K
    "agreement_date", "order_date",
    # Phase 28
    "contractor_ogrnip_date",
    # Fabrikant
    "applications_review_date",
    "planned_payment_month",
}
_DATETIME_FIELDS = {"submission_deadline", "service_note_at"}


def _coerce_patch_value(field: str, value):
    """Конвертирует ISO-строку в date/datetime для DATE-полей; пустые строки → None."""
    return coerce_patch_value(field, value, date_fields=_DATE_FIELDS, datetime_fields=_DATETIME_FIELDS)


@router.patch("/{pid}")
async def patch_purchase(
    pid: int,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Not found")
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")

    # Phase 28 B4: нельзя снять ответственного через PATCH
    if "assigned_user_id" in (body or {}):
        val = body["assigned_user_id"]
        if val is None or val == 0:
            raise HTTPException(422, "Нельзя снять ответственного исполнителя")
        target = await db.get(User, val)
        if target is None:
            raise HTTPException(422, f"Пользователь {val} не найден")

    # Opportunistic backfill: первый PATCH (autosave) от user'а закрепляет
    # за ним legacy-закупку без assigned_user_id — иначе после save она опять
    # пропадёт из его OrdersView.
    if p.assigned_user_id is None and "assigned_user_id" not in (body or {}):
        p.assigned_user_id = current_user.id

    # Владелец (2026-09-01): категория ФЭО после согласования — см.
    # _guard_feo_category_change_after_approval. autosave — реальный
    # вектор бага (форма шлёт feo_category_id в каждом PATCH).
    _old_feo_category_id_patch = p.feo_category_id
    if "feo_category_id" in (body or {}):
        _new_feo_cat = _coerce_patch_value("feo_category_id", body["feo_category_id"])
        await _guard_feo_category_change_after_approval(p, _new_feo_cat, current_user, db)

    # phase26-j-1 (fix): запоминаем contract_id ДО setattr, чтобы sync вызвался
    # только при реальном изменении FK, а не на каждый autosave с тем же contract_id.
    old_contract_id_patch = p.contract_id

    changed: list[str] = []
    for k, v in (body or {}).items():
        if k not in PATCHABLE_FIELDS:
            continue
        if not hasattr(p, k):
            continue
        v = _coerce_patch_value(k, v)
        if getattr(p, k) != v:
            setattr(p, k, v)
            changed.append(k)
            # JSONB колонки: SQLAlchemy не детектирует мутации без flag_modified
            if k == "acceptance_docs":
                flag_modified(p, "acceptance_docs")
    # phase26-j-1 (fix): sync только при ИЗМЕНЕНИИ contract_id, иначе ручные правки
    # contract_number перетираются на каждом autosave (Phase 26 patches шлют contract_id вместе с другими полями).
    if p.contract_id and p.contract_id != old_contract_id_patch:
        await _sync_purchase_from_contract(p, db)
        for f in ("contract_number", "contract_date", "purchase_contract_type"):
            if f not in changed:
                changed.append(f)
    # Phase 26-Z: при установке contractor_id на закупке — проставить во все
    # позиции без указанного контрагента (наследование одним подрядчиком).
    if p.contractor_id and "contractor_id" in changed:
        from app.models.purchase_item import PurchaseItem as _PI
        from app.models.contractor import Contractor as _Ctr
        c_row = await db.get(_Ctr, p.contractor_id)
        if c_row:
            upd_q = await db.execute(
                select(_PI).where(_PI.purchase_id == p.id, _PI.contractor_id.is_(None))
            )
            for it in upd_q.scalars().all():
                it.contractor_id = c_row.id
                it.contractor_inn = c_row.inn
                it.contractor_name = c_row.name

    # Владелец (2026-09-02): смена категории ФЭО шапки закупки — см.
    # _reset_incompatible_item_feo_links. autosave (этот PATCH) — основной
    # вектор бага, форма не шлёт items, поэтому чиним привязки уже
    # существующих PurchaseItem напрямую.
    _feo_links_reset = 0
    if "feo_category_id" in changed:
        from app.models.purchase_item import PurchaseItem as _PIFeo
        _items_for_feo_reset = (await db.execute(
            select(_PIFeo).where(_PIFeo.purchase_id == p.id)
        )).scalars().all()
        _feo_links_reset = await _reset_incompatible_item_feo_links(
            _items_for_feo_reset, _old_feo_category_id_patch, p.feo_category_id,
            bool(p.feo_per_item), db,
        )

    if changed:
        await db.commit()
        await db.refresh(p)
    return {"id": p.id, "changed": changed, "feo_links_reset": _feo_links_reset}


class _ActualizeContractNumberBody(BaseModel):
    # Не передан/None — подтвердить ТЕКУЩИЙ (технический) номер как окончательный.
    # Передан — записать его как новый номер договора.
    contract_number: Optional[str] = None
    contract_date: Optional[date] = None


@router.post("/{pid}/actualize-contract-number")
async def actualize_contract_number(
    pid: int,
    body: _ActualizeContractNumberBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Владелец (2026-08-31): актуализация технического номера договора
    рамочной головы — «подтвердить проставленный тобой или задать новый».

    body.contract_number передан → записывается как новый номер (+ дата, если
    передана). body.contract_number пуст/не передан → текущий номер (в т.ч.
    технический «ВРЕМ-...») подтверждается как окончательный без изменений.
    В обоих случаях флаг contract_number_is_temporary снимается.
    """
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")
    if body.contract_number:
        p.contract_number = body.contract_number.strip()
        if body.contract_date:
            p.contract_date = body.contract_date
    p.contract_number_is_temporary = False
    await db.commit()
    await db.refresh(p)
    return {
        "id": p.id,
        "contract_number": p.contract_number,
        "contract_date": p.contract_date,
        "contract_number_is_temporary": p.contract_number_is_temporary,
    }


# Шаг 2 «план ≠ факт»: с этих статусов закупка считается объявленной — количество/
# цена ТЗ позиции замораживаются (иначе правка «съедает» зафиксированный план,
# см. purchase_items.planned_* и compute_feo_plan_tree). Итоговую цену по факту
# закупки/КП вносят в подстроке «Договор» позиции (contract_items), не здесь.
TZ_FROZEN_STATUSES = {"work_in_progress", "contracted", "ordered", "delivered", "paid"}


async def _recalc_purchase_totals(p: Purchase, db: AsyncSession) -> None:
    """Пересчёт сумм закупки из позиций (та же логика, что в update_purchase).

    ПРАВИЛО №6 (2026-09-05): тонкая обёртка над app.services.purchase_money_
    writer.recalc_purchase_money — единственным писателем денежных колонок
    закупки. Раньше эта функция сама писала `contract_price = Σ purchase_items`
    в ЛЮБОМ статусе (в т.ч. до договора) — то самое «второе перо», конкурирующее
    с `_recalc_contract_price_from_contract_items` (источник истины —
    Σ contract_items.total). Новый писатель это устраняет: contract_price до
    договора (нет ContractItem) больше не трогается — см. докстринг
    purchase_money_writer.py.
    """
    from app.services.purchase_money_writer import recalc_purchase_money
    await recalc_purchase_money(db, p)


@router.delete("/{pid}")
async def delete_purchase(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Purchase).where(Purchase.id == pid))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")
    # 27.4-09: авансовый owner может удалить свой отчёт; остальным нужен tab 'purchases'
    from app.auth.permissions import can_manage_purchase
    if not await can_manage_purchase(current_user, p, db):
        raise HTTPException(403, "Нет прав на удаление: нужна вкладка «Закупки» (роль менеджер и выше) либо авторство своего авансового отчёта")
    await db.delete(p)
    await db.commit()
    return {"ok": True}




# Ленивый ре-экспорт (PEP 562 module __getattr__) символов, которые уехали в
# новые routers/purchase_*.py, но тесты и (в одном случае) другой роутер всё
# ещё обращаются к ним через app.routers.purchases / `pr.<имя>` (pr = import
# app.routers.purchases as pr). Модуль-ядро НЕ импортирует новые роутеры на
# уровне модуля — иначе цикл (эти роутеры сами импортируют is_framework_head/
# _has_purchase_write_access/_recalc_purchase_totals/TZ_FROZEN_STATUSES/
# _sync_purchase_from_contract ИЗ этого модуля при загрузке) — сам импорт
# происходит только по факту обращения к атрибуту, когда оба модуля уже
# полностью загружены.
#   _build_framework_chain_approvals, patch_purchase_item — тестами вызываются
#   напрямую как функции (asyncio.run(pr.patch_purchase_item(...))).
#   _ItemPatchBody — тестами конструируется напрямую (pr._ItemPatchBody(...))
#   как тело запроса для patch_purchase_item, минуя HTTP.
_LAZY_REEXPORTS = {
    "_build_framework_chain_approvals": "app.routers.purchase_ops",
    "patch_purchase_item": "app.routers.purchase_items_edit",
    "_ItemPatchBody": "app.routers.purchase_items_edit",
}


def __getattr__(name):
    module_path = _LAZY_REEXPORTS.get(name)
    if module_path is not None:
        import importlib
        return getattr(importlib.import_module(module_path), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
