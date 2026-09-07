"""generate_document: subsidy/customer/event/approvers/initiator/FEO-path/responsible.

Split out of app/routers/documents.py::generate_document (wave 3f refactor).
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.models.subsidy_approver import SubsidyApprover
from app.models.feo_category import FeoCategory
from app.models.event import Event
from app.routers.purchases import is_framework_head
from app.services.documents.formatting import _format_initials
from app.services.documents.contexts import (
    _build_contract_item_feo_paths,
    _resolve_user_position,
)


async def load_subsidy(db: AsyncSession, p: Purchase) -> Optional[Subsidy]:
    subsidy_r = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
    return subsidy_r.scalar_one_or_none()


async def load_customer(db: AsyncSession, subsidy: Optional[Subsidy]):
    # Phase 23: Customer = Organization owning the subsidy. Loads linked Contractor (FK)
    # for banking details (r/s, bank_name, BIK, k/s).
    customer_org = None
    customer_ctr = None  # Contractor linked to org via FK
    if subsidy and subsidy.org_id:
        from app.models.organization import Organization
        org_r = await db.execute(select(Organization).where(Organization.id == subsidy.org_id))
        customer_org = org_r.scalar_one_or_none()
        if customer_org and customer_org.contractor_id:
            from app.models.contractor import Contractor as _CtrCust
            ctr_r = await db.execute(select(_CtrCust).where(_CtrCust.id == customer_org.contractor_id))
            customer_ctr = ctr_r.scalar_one_or_none()
    return customer_org, customer_ctr


async def load_event(db: AsyncSession, p: Purchase) -> Optional[Event]:
    event = None
    if p.event_id:
        ev_r = await db.execute(select(Event).where(Event.id == p.event_id))
        event = ev_r.scalar_one_or_none()
    return event


async def resolve_approvers(db: AsyncSession, p: Purchase, pid: int, doc_type: str, approver_ids: Optional[str]):
    """Selected approvers: explicit ?approver_ids → subsidy defaults → framework-head
    approval_sheet override (real necessity chain, not money-approval chain).
    Returns (selected_approvers, fh_pa_by_synth_id).
    """
    # Load approvers if requested
    selected_approvers = []
    if approver_ids:
        ids = [int(x.strip()) for x in approver_ids.split(",") if x.strip().isdigit()]
        if ids:
            res = await db.execute(
                select(SubsidyApprover)
                .where(SubsidyApprover.id.in_(ids))
                .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
            )
            selected_approvers = res.scalars().all()

    # If no approvers specified — load defaults for this subsidy
    if not selected_approvers and p.subsidy_id:
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.subsidy_id == p.subsidy_id, SubsidyApprover.is_default == True)
            .order_by(SubsidyApprover.order_num, SubsidyApprover.id)
        )
        selected_approvers = res.scalars().all()

    # Владелец (2026-09-03): «у рамочного договора тоже должен быть лист
    # согласования» — с реальными согласующими. Диагноз: до этой правки лист
    # для рамочной ГОЛОВЫ печатал selected_approvers из SubsidyApprover (выше)
    # — конфигурацию ДЕНЕЖНОГО согласования субсидии, никак не связанную с
    # цепочкой согласования НЕОБХОДИМОСТИ договора (PurchaseApproval-строки,
    # которые строит purchases.py::_build_framework_chain_approvals или
    # добавляет вручную purchase_approvals.py::add_approver — у них
    # subsidy_approver_id всегда NULL, поэтому approval_map по нему их вообще
    # не находил). Печатаем именно эту, реальную цепочку — approver_ids
    # (пикер по субсидии) и default-согласующие субсидии для рамочной головы
    # смысла не имеют.
    _fh_approval_rows: list = []
    _fh_pa_by_synth_id: dict = {}
    if doc_type == "approval_sheet" and is_framework_head(p):
        from app.models.purchase_approval import PurchaseApproval as _FhPA
        from types import SimpleNamespace as _FhNS
        fh_res = await db.execute(
            select(_FhPA).where(_FhPA.purchase_id == pid).order_by(_FhPA.order_num)
        )
        _fh_approval_rows = fh_res.scalars().all()
        selected_approvers = [
            _FhNS(
                id=f"fh-{row.id}",
                full_name=row.approver_full_name,
                role_name=row.role_name,
                show_feo_path=False,
            )
            for row in _fh_approval_rows
        ]
        _fh_pa_by_synth_id = {f"fh-{row.id}": row for row in _fh_approval_rows}

    return selected_approvers, _fh_pa_by_synth_id


async def resolve_initiator(db: AsyncSession, current_user, initiator_id: Optional[int],
                             subsidy: Optional[Subsidy], customer_org):
    # Load initiator if requested (frontend always sends User.id, not SubsidyApprover.id).
    # Бизнес-правило: за другого человека делать СЗ может только тот, кому
    # подчинён этот человек (видим через _get_visible_user_ids — тот же scope,
    # что для постановки задач). Самого себя — всегда можно.
    initiator = None
    if initiator_id and initiator_id != getattr(current_user, "id", None):
        from app.routers.task_visibility import _get_visible_user_ids
        visible = await _get_visible_user_ids(current_user, db)
        if visible is not None and initiator_id not in visible:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "INITIATOR_FORBIDDEN",
                    "message": (
                        "Указанный инициатор вам не подчинён. Сделать служебную "
                        "записку за другого человека может только его руководитель."
                    ),
                },
            )
    # Стратегия резолва:
    #   1) SubsidyApprover.user_id == initiator_id (привязанный approver субсидии) →
    #      берём full_name/role_name из карточки approver'а
    #   2) Иначе SimpleNamespace из User (full_name/position/department)
    if initiator_id:
        # 1. Привязанный approver субсидии (если есть)
        res = await db.execute(
            select(SubsidyApprover)
            .where(SubsidyApprover.user_id == initiator_id)
            .options(selectinload(SubsidyApprover.user))
            .order_by(SubsidyApprover.id)
            .limit(1)
        )
        initiator = res.scalar_one_or_none()
        # 2. Виртуальный approver из User
        if initiator is None:
            from app.models.user import User as UserModel
            from types import SimpleNamespace
            u = (
                await db.execute(select(UserModel).where(UserModel.id == initiator_id))
            ).scalar_one_or_none()
            if u:
                # Rule #6: не читаем u.position напрямую — единственный резолвер
                # должности (org-aware, с legacy fallback внутри) уже здесь.
                initiator = SimpleNamespace(
                    full_name=u.full_name or u.username,
                    role_name=await _resolve_user_position(
                        u, db, getattr(subsidy, "org_id", None) if subsidy else None
                    ),
                    user=u,
                )

        # Membership-check: инициатор должен состоять в организации, к которой
        # привязана субсидия закупки. Без этого должность/отдел не определены,
        # СЗ от имени постороннего сотрудника недопустима.
        subsidy_org_id = getattr(subsidy, "org_id", None) if subsidy else None
        init_user = initiator.user if (initiator and getattr(initiator, "user", None)) else None
        if subsidy_org_id and init_user:
            from app.models.user_organization import UserOrganization
            mem = (await db.execute(
                select(UserOrganization.id).where(
                    UserOrganization.user_id == init_user.id,
                    UserOrganization.org_id == subsidy_org_id,
                ).limit(1)
            )).first()
            # Legacy fallback — User.org_id (primary)
            if not mem and getattr(init_user, "org_id", None) != subsidy_org_id:
                org_name = getattr(customer_org, "name", "") if customer_org else ""
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "INITIATOR_NOT_IN_ORG",
                        "message": (
                            f"Инициатор не состоит в организации"
                            + (f" «{org_name}»" if org_name else "")
                            + ", к которой привязана субсидия закупки. Выберите "
                            "сотрудника этой организации."
                        ),
                    },
                )
    return initiator


async def build_feo_path(db: AsyncSession, p: Purchase, doc_type: str):
    """Build FEO category path (root → ... → selected) + individual levels."""
    feo_path = ""
    feo_level_1 = ""
    feo_level_2 = ""
    feo_level_3 = ""
    item_feo_paths: list = []  # [(path_str, Decimal total)] по позициям со своей категорией ФЭО

    # Требование владельца (2026-08-30): «В "Путь ФЭО" должны прописываться
    # договорные категории, они должны совпадать с Плановыми». Лист
    # согласования и остальные CONTRACT_FAMILY_DOC_TYPES визируют ДОГОВОРНЫЕ
    # позиции (ContractItem) — цены там уже договорные, поэтому путь ФЭО
    # тоже обязан идти от договорных позиций, иначе строки «цена / категория»
    # расходятся. См. _build_contract_item_feo_paths().
    from app.services.documents.doc_types import CONTRACT_FAMILY_DOC_TYPES
    _is_contract_family = doc_type in CONTRACT_FAMILY_DOC_TYPES
    if _is_contract_family:
        _plan_feo_by_id = {it.id: it.feo_category_id for it in (p.items or []) if it.feo_category_id}
        item_feo_ids = list(dict.fromkeys(
            _plan_feo_by_id[ci.source_item_id]
            for ci in (p.contract_items or [])
            if ci.source_item_id and ci.source_item_id in _plan_feo_by_id
        ))
    else:
        item_feo_ids = list(dict.fromkeys(it.feo_category_id for it in (p.items or []) if it.feo_category_id))

    if p.feo_category_id or item_feo_ids or (_is_contract_family and (p.contract_items or [])):
        feo_res = await db.execute(select(FeoCategory))
        all_feo = {f.id: f for f in feo_res.scalars().all()}

        def _feo_path_nodes(node_id):
            path_nodes: list = []
            visited: set = set()
            while node_id and node_id not in visited:
                visited.add(node_id)
                cat = all_feo.get(node_id)
                if not cat:
                    break
                path_nodes.append(cat)
                node_id = cat.parent_id
            path_nodes.reverse()  # root → leaf
            return path_nodes

        if p.feo_category_id:
            path_nodes = _feo_path_nodes(p.feo_category_id)
            feo_path = " → ".join(n.name.strip() for n in path_nodes)
            if len(path_nodes) >= 1: feo_level_1 = path_nodes[0].name.strip()
            if len(path_nodes) >= 2: feo_level_2 = path_nodes[1].name.strip()
            if len(path_nodes) >= 3: feo_level_3 = path_nodes[2].name.strip()

        if _is_contract_family:
            item_feo_paths = _build_contract_item_feo_paths(
                p.contract_items or [], p.items or [], _feo_path_nodes,
            )
        elif item_feo_ids:
            cat_sums: dict = {cid: Decimal("0") for cid in item_feo_ids}
            for it in (p.items or []):
                if it.feo_category_id and it.total_price is not None:
                    cat_sums[it.feo_category_id] += Decimal(str(it.total_price))
            for cid in item_feo_ids:
                cat_path = " → ".join(n.name.strip() for n in _feo_path_nodes(cid))
                if cat_path:
                    item_feo_paths.append((cat_path, cat_sums[cid]))

    return feo_path, feo_level_1, feo_level_2, feo_level_3, item_feo_paths


def resolve_responsible_person(p: Purchase, responsible_name: Optional[str]):
    # Resolved responsible person: priority = ?responsible_name → assigned_user.full_name
    # → p.responsible_person → автор служебной записки (последний фолбэк, чтобы клетка
    # «Ответственный исполнитель» никогда не оставалась привязанной к фиксированному
    # человеку из настроек субсидии — см. app/services/responsible_role.py)
    assigned_full = (getattr(p.assigned_user, "full_name", None) or "") if getattr(p, "assigned_user", None) else ""
    service_note_author_full = (
        (getattr(p.service_note_author, "full_name", None) or "")
        if getattr(p, "service_note_author", None) else ""
    )
    raw_responsible = responsible_name or assigned_full or p.responsible_person or service_note_author_full or ""
    resolved_responsible = _format_initials(raw_responsible) if raw_responsible else ""
    resolved_responsible_full = raw_responsible  # для шаблонов которым нужно полное ФИО
    return resolved_responsible, resolved_responsible_full
