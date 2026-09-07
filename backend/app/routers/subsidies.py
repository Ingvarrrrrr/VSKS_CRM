import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from app.utils.http import content_disposition

_content_disposition = content_disposition

logger = logging.getLogger(__name__)
from sqlalchemy import select, delete, func, text, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, ProgrammingError
from app.database import get_db
from app.models.subsidy import Subsidy
from app.models.subsidy_member import SubsidyMember
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.subsidy_contractor_override import SubsidyContractorOverride
from app.models.contractor import Contractor
from app.schemas.schemas import (
    SubsidyCreate, SubsidyOut,
    SubsidyContractorOverrideCreate, SubsidyContractorOverrideOut,
)
from app.auth.jwt import get_current_user, get_org_filter, get_single_org_id
from app.auth.permissions import require_tab
from app.models.user import User
from app.services.fio import compose_fio
from app.services.feo_plan import calculate_ceiling_forecasts_bulk, calculate_ceiling_forecast
from typing import List, Optional

# Re-exports (Правило №5, рефакторинг 2026-09-07 — разрезание subsidies.py):
# другие модули продолжают импортировать эти имена из app.routers.subsidies,
# сами функции теперь живут в отдельных файлах-соседях (см. их докстринги).
from app.services.org_dedup import _materialize_org_from_contractor, _merge_duplicate_orgs_by_inn
from app.routers.subsidy_templates import _normalize_docx_template

router = APIRouter(prefix="/api/subsidies", tags=["subsidies"])

@router.get("/diag/columns")
async def diag_columns(db: AsyncSession = Depends(get_db)):
    """Diagnostic endpoint — возвращает реальные колонки таблицы subsidies из information_schema."""
    result = await db.execute(text(
        "SELECT column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_name = 'subsidies' "
        "ORDER BY ordinal_position"
    ))
    rows = result.fetchall()
    columns = [{"column_name": r[0], "data_type": r[1], "is_nullable": r[2]} for r in rows]
    logger.info("diag_columns: subsidies has %d columns: %s", len(columns), [c["column_name"] for c in columns])
    return {"table": "subsidies", "columns": columns}


# Правило №6 (волна C1/C2, 2026-09-07): рекурсия «бюджет узла = собственный
# budget, иначе сумма детей» и фолбэк «дерево пустое → ручной subsidy.budget»
# теперь живут в app.services.subsidy_budget (там же перечислены ВСЕ места,
# где формула раньше дублировалась). Здесь — тонкие обёртки: имена оставлены
# без изменений, их продолжают импортировать app.routers.dashboard,
# app.routers.feo_tree_ops, app.routers.purchase_budget, app.services.feo_plan,
# и монкипатчить тесты (test_subsidy_draft.py делает
# monkeypatch.setattr(subsidies, "calculate_budget_from_categories", ...)).
from app.services.subsidy_budget import (
    effective_subsidy_budget,
    calculate_budget_from_categories,
    calculate_budgets_bulk,
)


# Статусы, исключаемые из подсчёта потраченного (отменённые закупки не занимают бюджет)
_EXCLUDED_FROM_SPENT: tuple = ("cancelled",)


async def _calculate_spent(
    db: AsyncSession,
    subsidy_id: int,
    exclude_purchase_id: Optional[int] = None,
) -> float:
    """Σ effective (по стадии закупки) по активным закупкам субсидии (кроме
    cancelled) — используется как «сколько уже занято» для бюджетного гейта
    при создании/правке закупки (CreateOrderView.vue::budgetInfo, не выводится
    пользователю отдельной подписью «Освоено» — только через remaining/over/
    exceeded). ПРАВИЛО №6 (2026-09-05): раньше — Σ planned_total_price, что
    не учитывало закупки, ушедшие дальше плана (Договор/Поставка/Оплата) —
    единый расчёт суммы закупки, см. app/services/purchase_amounts.py.

    Владелец (2026-09-06) — решение по рамочным договорам в итогах: голова с
    предельной суммой несёт «законтрактовано» целиком (её effective уже =
    Contract.max_amount), «заказано» — ТОЛЬКО по её детям; накопительная
    голова (без предела) сама не несёт суммы. Чтобы Σ не задваивала голову
    и детей — доп. фильтр aggregate_scope_expr() (см. её докстринг, тот же
    предикат применён в dashboard.py::subsidy_q и feo_categories.py::
    get_purchase_totals)."""
    from app.services.purchase_amounts import effective_amount_expr, aggregate_scope_expr
    q = select(func.coalesce(func.sum(effective_amount_expr()), 0)).where(
        Purchase.subsidy_id == subsidy_id,
        Purchase.status.notin_(_EXCLUDED_FROM_SPENT),
        aggregate_scope_expr(),
    )
    if exclude_purchase_id:
        q = q.where(Purchase.id != exclude_purchase_id)
    result = await db.execute(q)
    return float(result.scalar() or 0)


async def _calculate_planned_amount(db: AsyncSession, subsidy_id: int) -> float:
    """Σ FeoPlannedItem.amount для субсидии (ФЭО плановая сумма)."""
    q = select(func.coalesce(func.sum(FeoPlannedItem.amount), 0)).join(
        FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id
    ).where(
        FeoCategory.subsidy_id == subsidy_id,
        FeoPlannedItem.is_active == True,
    )
    result = await db.execute(q)
    return float(result.scalar() or 0)


async def _calculate_planned_amounts_bulk(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, float]:
    """Batch Σ FeoPlannedItem.amount для набора субсидий."""
    if not subsidy_ids:
        return {}
    q = (
        select(FeoCategory.subsidy_id, func.coalesce(func.sum(FeoPlannedItem.amount), 0).label("total"))
        .join(FeoPlannedItem, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(
            FeoCategory.subsidy_id.in_(subsidy_ids),
            FeoPlannedItem.is_active == True,
        )
        .group_by(FeoCategory.subsidy_id)
    )
    rows = (await db.execute(q)).all()
    result = {sid: 0.0 for sid in subsidy_ids}
    for r in rows:
        result[r.subsidy_id] = float(r.total)
    return result


async def _calculate_spent_bulk(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, float]:
    """Batch-версия _calculate_spent (см. её докстринг, включая решение
    владельца про рамочные договоры и aggregate_scope_expr()) — Σ effective
    для набора субсидий (кроме cancelled). ПРАВИЛО №6 (2026-09-05): та же
    формула, не вторая копия — app/services/purchase_amounts.py::
    effective_amount_expr."""
    if not subsidy_ids:
        return {}
    from app.services.purchase_amounts import effective_amount_expr, aggregate_scope_expr
    q = (
        select(Purchase.subsidy_id, func.coalesce(func.sum(effective_amount_expr()), 0).label("spent"))
        .where(
            Purchase.subsidy_id.in_(subsidy_ids),
            Purchase.status.notin_(_EXCLUDED_FROM_SPENT),
            aggregate_scope_expr(),
        )
        .group_by(Purchase.subsidy_id)
    )
    rows = (await db.execute(q)).all()
    result = {sid: 0.0 for sid in subsidy_ids}
    for r in rows:
        result[r.subsidy_id] = float(r.spent)
    return result


async def _calculate_feo_planned_tree_bulk(
    db: AsyncSession, subsidy_ids: list[int]
) -> dict[int, float]:
    """Плановая сумма дерева ФЭО для набора субсидий (единый источник для «Запланировано»).

    Тонкая обёртка над app.services.feo_plan.feo_plan_subsidy_totals — Σ display
    корневых узлов дерева ФЭО, где для каждого узла (листа и группы):
      display = MAX(план, выбрано) + сверх_плана
    План/выбрано/сверх план считаются рекурсивно по поддереву (см. подробный
    docstring compute_feo_plan_tree в app/services/feo_plan.py). Формула вынесена
    в общий сервис, чтобы:
      1) устранить задвоение, когда позиция закупки лежит ОДНОВРЕМЕННО на группе
         и на её дочернем листе (раньше их суммы складывались напрямую — группа
         «Внедорожник повышенной проходимости» показывала 16 380 000 = план листа
         8 380 000 + позиция заявки на самой группе 8 000 000, вместо MAX = 8 380 000);
      2) не расходиться с _create_plan_graph_version (purchases.py) — снапшот
         истории версий плана закупок использует ту же compute_feo_plan_tree.

    Совпадает с тем, что показывает панель ФЭО вкладки «Субсидии»
    (feoPlannedDisplayFor(root) в SubsidiesView.vue, режим 'all' — реализует ту же
    формулу MAX(план, выбрано)+сверх_план на фронте, см. docstring там).
    """
    if not subsidy_ids:
        return {}
    from app.services.feo_plan import feo_plan_subsidy_totals
    return await feo_plan_subsidy_totals(db, subsidy_ids)


@router.get("/", response_model=List[SubsidyOut])
async def list_subsidies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scope: Optional[str] = Query(None, description="strict|wishes — строгий скоуп пикера: прямое членство + управляемые орги + гранты, БЕЗ контура-детей"),
):
    # GET list is intentionally open to all authenticated users (incl. employee) so
    # that WishesView can populate the subsidy selector. Org-filter below already
    # limits visible subsidies to the user's own organisations. Write operations
    # (POST/PUT/DELETE/templates) remain gated by require_tab('subsidies').
    q = select(Subsidy).order_by(Subsidy.year.desc(), Subsidy.name)
    # Shared picker endpoint (orders/wishes/etc): member-union scope, NOT role-scoped.
    # Сужение до орг-админ-орг ломало бы выбор субсидии у сотрудника в /orders.
    org_ids = get_org_filter(current_user)
    # scope="wishes"/"strict" — строгий скоуп пикера заявки: пользователь видит
    # субсидии ТОЛЬКО тех орг, где реально состоит (членство/primary/UOA) или которыми
    # управляет, + личные гранты. Контур аккаунта (root+дети) НЕ применяется: менеджер
    # ВСКС не должен видеть субсидии дочернего Центрпоиска только из-за дерева орг —
    # наследование по дереву признано неверным (видимость даёт членство/управление).
    if scope in ("wishes", "strict") and current_user.role not in ('superadmin', 'account_owner'):
        from app.models.user_organization import UserOrganization
        from app.models.user_org_access import UserOrgAccess
        from app.models.manager_organization import ManagerOrganization
        strict: set[int] = set()
        if current_user.org_id:
            strict.add(int(current_user.org_id))
        strict |= {int(r[0]) for r in (await db.execute(
            select(UserOrganization.org_id).where(UserOrganization.user_id == current_user.id)
        )).all() if r[0]}
        strict |= {int(r[0]) for r in (await db.execute(
            select(UserOrgAccess.org_id).where(UserOrgAccess.user_id == current_user.id)
        )).all() if r[0]}
        strict |= {int(r[0]) for r in (await db.execute(
            select(ManagerOrganization.org_id).where(ManagerOrganization.manager_user_id == current_user.id)
        )).all() if r[0]}
        org_ids = list(strict)
    # 27.4-06: hard fallback для не-SaaS-ролей. Если JWT не содержит org_id/org_ids
    # И users.org_id = NULL — get_org_filter вернёт None → раньше employee видел ВСЕ
    # субсидии. Подтягиваем memberships из user_organizations.
    if org_ids is None and current_user.role not in ('superadmin', 'account_owner'):
        from app.models.user_organization import UserOrganization
        uo_rows = (await db.execute(
            select(UserOrganization.org_id).where(UserOrganization.user_id == current_user.id)
        )).all()
        org_ids = list({r[0] for r in uo_rows if r[0]})
        if not org_ids and current_user.org_id:
            org_ids = [current_user.org_id]
    # Per-user explicit subsidy grants (expand visibility regardless of org)
    from app.models.user_subsidy_access import UserSubsidyAccess
    granted_ids = set((await db.execute(
        select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == current_user.id)
    )).scalars().all())
    # Пикер (orders/wishes): пермиссивный member-union scope + кросс-орг гранты.
    # Управление ВИДИМОСТЬЮ субсидий (страница «Субсидии») — отдельно, в dashboard
    # charts через get_visible_subsidy_ids. Здесь НЕ сужаем до грантов, иначе ломается
    # выбор субсидии у рядового сотрудника.
    if org_ids is not None:
        if not org_ids and not granted_ids:
            return []
        q = q.where(or_(Subsidy.org_id.in_(org_ids), Subsidy.id.in_(granted_ids)))
    result = await db.execute(q)
    subsidies = result.scalars().all()

    # Batch-загрузка вместо N+1: бюджеты/контрагенты/орги одним IN-запросом каждый
    from app.models.organization import Organization
    sid_list = [s.id for s in subsidies]
    budgets = await calculate_budgets_bulk(db, sid_list)
    spent_map = await _calculate_spent_bulk(db, sid_list)
    planned_amounts = await _calculate_planned_amounts_bulk(db, sid_list)
    # Владелец (2026-08-30): предупреждение «сумма заказанного приближается к
    # потолку субсидии» — считаем батчем на список, не по одной (см. docstring
    # calculate_ceiling_forecasts_bulk в app/services/feo_plan.py).
    ceiling_forecasts = await calculate_ceiling_forecasts_bulk(db, sid_list)
    contractor_ids = {s.contractor_id for s in subsidies if s.contractor_id}
    contractors = {}
    if contractor_ids:
        rows = (await db.execute(
            select(Contractor).where(Contractor.id.in_(contractor_ids))
        )).scalars().all()
        contractors = {c.id: c for c in rows}
    subsidy_org_ids = {s.org_id for s in subsidies if s.org_id}
    orgs = {}
    if subsidy_org_ids:
        rows = (await db.execute(
            select(Organization).where(Organization.id.in_(subsidy_org_ids))
        )).scalars().all()
        orgs = {o.id: o for o in rows}

    out = []
    for s in subsidies:
        calc = budgets.get(s.id, 0.0)
        # calculated_budget — deprecated колонка, БОЛЬШЕ НЕ пишется на GET
        # (Правило №6): считается на чтении через effective_subsidy_budget,
        # единственный источник — app.services.subsidy_budget.
        effective_budget = effective_subsidy_budget(calc, s.budget)
        # Решение 14.07: budget — ручное значение, деревом ФЭО НЕ перезаписывается
        spent = spent_map.get(s.id, 0.0)
        planned_amt = planned_amounts.get(s.id, 0.0)
        remaining = effective_budget - spent
        discrepancy = (effective_budget - planned_amt) if abs(effective_budget - planned_amt) > 0.01 else None

        d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
        d["calculated_budget"] = effective_budget
        d["feo_filled"] = calc > 0
        d["feo_budget_total"] = effective_budget
        d["remaining"] = remaining
        d["planned_amount"] = planned_amt
        d["budget_discrepancy"] = discrepancy
        contractor = contractors.get(s.contractor_id) if s.contractor_id else None
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
        org = orgs.get(s.org_id) if s.org_id else None
        d["org_inn"] = org.inn if org else None
        d.update(ceiling_forecasts.get(s.id, {}))
        out.append(d)

    return out

@router.get("/{subsidy_id}", response_model=SubsidyOut)
async def get_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    subsidy = result.scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    calc = await calculate_budget_from_categories(db, subsidy.id)
    # calculated_budget — deprecated колонка, БОЛЬШЕ НЕ пишется на GET (Правило №6).
    effective_budget = effective_subsidy_budget(calc, subsidy.budget)
    # Решение 14.07: budget — ручное значение, деревом ФЭО НЕ перезаписывается

    spent = await _calculate_spent(db, subsidy.id)
    planned_amt = await _calculate_planned_amount(db, subsidy.id)
    remaining = effective_budget - spent
    discrepancy = (effective_budget - planned_amt) if abs(effective_budget - planned_amt) > 0.01 else None

    d = {c.name: getattr(subsidy, c.name) for c in subsidy.__table__.columns}
    d["calculated_budget"] = effective_budget
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = effective_budget
    d["remaining"] = remaining
    d["planned_amount"] = planned_amt
    d["budget_discrepancy"] = discrepancy
    if subsidy.contractor_id:
        contractor = await db.get(Contractor, subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    d.update(await calculate_ceiling_forecast(db, subsidy.id))
    return d


@router.get("/{subsidy_id}/budget-check")
async def budget_check(
    subsidy_id: int,
    exclude_purchase_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Canonical budget-check endpoint (D-17).

    Returns limit (ФЭО-tree budget), spent (Σ active purchases), remaining, discrepancy.
    T-31-05-01: read-access validated — only subsidies visible to user.
    """
    from app.auth.visibility import get_visible_subsidy_ids, build_visibility_clause
    # Security: ensure user has read-access to this subsidy
    visible = await get_visible_subsidy_ids(current_user, db)
    if visible is not None and subsidy_id not in visible:
        # Пользователь может не иметь вкладки «Субсидии» в орге субсидии, но видеть
        # закупку по ней (назначен/участник/в чате/задача) — тогда бюджет субсидии
        # ему доступен для контекста закупки. Иначе открытие чужой (по орг) закупки
        # падало 404 «Subsidy not found» у исполнителя.
        clause = await build_visibility_clause(current_user, db, "purchase")
        allowed = clause is None
        if clause is not None:
            cnt = (await db.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.subsidy_id == subsidy_id, clause
                )
            )).scalar() or 0
            allowed = cnt > 0
        if not allowed:
            raise HTTPException(status_code=404, detail="Subsidy not found")

    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    limit = await calculate_budget_from_categories(db, subsidy_id)
    spent = await _calculate_spent(db, subsidy_id, exclude_purchase_id=exclude_purchase_id)
    planned_amt = await _calculate_planned_amount(db, subsidy_id)
    remaining = limit - spent
    discrepancy = (limit - planned_amt) if abs(limit - planned_amt) > 0.01 else 0.0

    return {
        "limit": limit,
        "spent": spent,
        "remaining": remaining,
        "planned_amount": planned_amt,
        "discrepancy": discrepancy,
    }



# ── Черновые субсидии (план C1/C2) ──────────────────────────────────────────
# «Должна быть возможность у любого сотрудника создавать субсидию и вносить в
# неё корректировки, так же подключать к этой субсидии других людей для
# совместной работы... Но это будет черновая субсидия, которую надо будет
# утвердить у администратора, чтобы она могла пойти в работу.» Один флаг
# состояния (Subsidy.status), без цепочек согласования.

async def _is_subsidy_member(subsidy_id: int, user_id: int, db: AsyncSession) -> bool:
    return (await db.execute(
        select(SubsidyMember.id).where(
            SubsidyMember.subsidy_id == subsidy_id,
            SubsidyMember.user_id == user_id,
        ).limit(1)
    )).scalar_one_or_none() is not None


async def _can_edit_draft_subsidy(subsidy: Subsidy, user: User, db: AsyncSession) -> bool:
    """Пока субсидия в черновике, её содержимое правят автор и участники
    совместной работы (subsidy_members) — без выданного права subsidy.edit."""
    if user.role in ("superadmin", "account_owner"):
        return True
    if subsidy.created_by is not None and subsidy.created_by == user.id:
        return True
    return await _is_subsidy_member(subsidy.id, user.id, db)


@router.post("/", response_model=SubsidyOut)
async def create_subsidy(
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('subsidies')),
):
    data = subsidy.dict()
    # Новая субсидия всегда рождается черновиком — «в работу» она идёт только
    # после явного утверждения администратором (POST /{id}/approve).
    data['status'] = 'draft'
    data['created_by'] = current_user.id
    # org_id субсидии = организация-грантополучатель (из контрагента), НЕ активная орг
    # из свитчера: иначе субсидия «уезжает» под чужую орг (кейс ДНР_2026 → ЦЕНТРПОИСК).
    _contractor = None
    _grantee_org = None
    if data.get('contractor_id'):
        _contractor = await db.get(Contractor, data['contractor_id'])
        _grantee_org = await _materialize_org_from_contractor(db, _contractor, current_user.org_id)
    if _grantee_org is not None:
        data['org_id'] = _grantee_org.id
    else:
        data['org_id'] = get_single_org_id(current_user) or current_user.org_id
    _new_name = (data.get('name') or '').strip()
    if _new_name:
        _dup = (await db.execute(
            select(Subsidy.id).where(func.lower(func.trim(Subsidy.name)) == _new_name.lower())
        )).first()
        if _dup:
            raise HTTPException(status_code=409, detail=f"Субсидия с названием «{_new_name}» уже существует")
    db_subsidy = Subsidy(**data)
    db.add(db_subsidy)
    await db.commit()
    await db.refresh(db_subsidy)

    # Новая субсидия — дерево ФЭО ещё пустое (calc=0), effective = ручной budget
    # (та же формула, что list/detail/dashboard — Правило №6, раньше здесь было
    # захардкожено 0.0 независимо от заданного при создании budget).
    _new_effective = effective_subsidy_budget(0.0, db_subsidy.budget)
    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = _new_effective
    d["feo_filled"] = False
    d["feo_budget_total"] = _new_effective
    if _contractor is not None:
        d["contractor_name"] = _contractor.name
        d["contractor_inn"] = _contractor.inn
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    d.update(await calculate_ceiling_forecast(db, db_subsidy.id))
    return d


@router.post("/{subsidy_id}/approve", response_model=SubsidyOut)
async def approve_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Утверждение черновой субсидии — «руководитель уполномоченный проверит и
    запустит всё в работу». Требует subsidy.edit в орге ЭТОЙ субсидии (как и
    обычная правка утверждённой субсидии — утверждение не слабее правки).
    Повторное утверждение — не ошибка, просто ничего не меняет (идемпотентно)."""
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    from app.auth.permissions import has_org_key
    if not await has_org_key(current_user, db, db_subsidy.org_id, 'subsidy.edit', subsidy_id=subsidy_id):
        raise HTTPException(
            status_code=403,
            detail="Нет права утвердить субсидию: право «Редактирование субсидий» не выдано для организации-грантополучателя",
        )

    if db_subsidy.status != 'approved':
        from datetime import datetime, timezone
        db_subsidy.status = 'approved'
        db_subsidy.approved_by = current_user.id
        db_subsidy.approved_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(db_subsidy)

    calc = await calculate_budget_from_categories(db, subsidy_id)
    # Правило №6: раньше здесь НЕ применялся фолбэк на ручной budget (в отличие
    # от list/detail/dashboard) — субсидия с budget=1 000 000, но ещё без дерева
    # ФЭО, после /approve показывала calculated_budget=0 вместо budget.
    effective_budget = effective_subsidy_budget(calc, db_subsidy.budget)
    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = effective_budget
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = effective_budget
    if db_subsidy.contractor_id:
        contractor = await db.get(Contractor, db_subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    d.update(await calculate_ceiling_forecast(db, db_subsidy.id))
    return d


@router.put("/{subsidy_id}", response_model=SubsidyOut)
async def update_subsidy(
    subsidy_id: int,
    subsidy: SubsidyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # Черновые субсидии (план C1/C2): в черновике правит автор/участник, без
    # выданного subsidy.edit — «любой сотрудник» может вносить корректировки.
    # После утверждения — прежний строгий орг-осознанный гейт subsidy.edit.
    if db_subsidy.status == 'draft':
        if not await _can_edit_draft_subsidy(db_subsidy, current_user, db):
            raise HTTPException(
                status_code=403,
                detail="Черновик субсидии редактируют автор и участники совместной работы — попросите автора добавить вас участником",
            )
    else:
        # Wave 3: орг-осознанная проверка — право subsidy.edit должно действовать
        # именно в орге ЭТОЙ субсидии (орг-роль не даёт власти в чужих оргах).
        from app.auth.permissions import has_org_key
        if not await has_org_key(current_user, db, db_subsidy.org_id, 'subsidy.edit', subsidy_id=subsidy_id):
            raise HTTPException(
                status_code=403,
                detail="Нет права редактировать субсидии этой организации: право «Редактирование субсидий» не выдано для организации-грантополучателя",
            )

    old_budget = db_subsidy.budget  # capture BEFORE setattr loop

    # Step 1: log incoming payload
    payload = subsidy.model_dump() if hasattr(subsidy, 'model_dump') else subsidy.dict()
    logger.info("update_subsidy id=%s incoming payload: %s", subsidy_id, payload)

    calc = await calculate_budget_from_categories(db, subsidy_id)

    # Step 2: try normal setattr → commit
    _upd_name = (payload.get('name') or '').strip()
    if _upd_name:
        _dup = (await db.execute(
            select(Subsidy.id).where(
                func.lower(func.trim(Subsidy.name)) == _upd_name.lower(),
                Subsidy.id != subsidy_id,
            )
        )).first()
        if _dup:
            raise HTTPException(status_code=409, detail=f"Субсидия с названием «{_upd_name}» уже существует")
    for key, value in payload.items():
        setattr(db_subsidy, key, value)
    # calculated_budget — deprecated колонка (Правило №6), БОЛЬШЕ НЕ пишется —
    # см. app.services.subsidy_budget, считается на чтении.

    # Budget history write hook — track subsidy limit changes only (NOT calculated_budget)
    if old_budget != db_subsidy.budget:
        from app.models.budget_history import BudgetHistory as _BH
        db.add(_BH(
            subsidy_id=subsidy_id,
            purchase_id=None,
            entity_type="subsidy",
            old_value=float(old_budget) if old_budget is not None else None,
            new_value=float(db_subsidy.budget) if db_subsidy.budget is not None else None,
            changed_by_id=current_user.id,
            changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
            reason=None,
        ))

    logger.info(
        "update_subsidy id=%s db_subsidy state before commit: name=%r year=%r budget=%r "
        "basis_doc_number=%r basis_doc_date=%r",
        subsidy_id,
        db_subsidy.name, db_subsidy.year, db_subsidy.budget,
        getattr(db_subsidy, 'basis_doc_number', '<attr_missing>'),
        getattr(db_subsidy, 'basis_doc_date', '<attr_missing>'),
    )

    try:
        await db.commit()
        await db.refresh(db_subsidy)
    except (ProgrammingError, IntegrityError) as exc:
        logger.warning(
            "update_subsidy id=%s commit failed (%s: %s), attempting ALTER fallback",
            subsidy_id, type(exc).__name__, exc,
        )
        await db.rollback()

        # ALTER fallback — отдельная транзакция вне текущей сессии
        from app.database import ensure_phase22_columns as _ensure_p22
        await _ensure_p22()

        # Перезагружаем объект и повторяем setattr
        result2 = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
        db_subsidy = result2.scalar_one_or_none()
        if not db_subsidy:
            raise HTTPException(status_code=404, detail="Subsidy not found after ALTER fallback")
        db.expire_all()

        for key, value in payload.items():
            setattr(db_subsidy, key, value)
        # calculated_budget — deprecated, не пишется (см. выше).

        if old_budget != db_subsidy.budget:
            from app.models.budget_history import BudgetHistory as _BH2
            db.add(_BH2(
                subsidy_id=subsidy_id,
                purchase_id=None,
                entity_type="subsidy",
                old_value=float(old_budget) if old_budget is not None else None,
                new_value=float(db_subsidy.budget) if db_subsidy.budget is not None else None,
                changed_by_id=current_user.id,
                changed_by_name=getattr(current_user, 'full_name', None) or current_user.username,
                reason=None,
            ))

        await db.commit()
        await db.refresh(db_subsidy)
        logger.info("update_subsidy id=%s ALTER fallback commit succeeded", subsidy_id)

    # Step 4: raw SELECT to verify final DB state
    raw = await db.execute(
        text("SELECT id, name, year, budget, basis_doc_number, basis_doc_date FROM subsidies WHERE id = :id"),
        {"id": subsidy_id},
    )
    raw_row = raw.fetchone()
    logger.info("update_subsidy id=%s post-commit raw SELECT: %s", subsidy_id, raw_row)

    # Правило №6: тот же фолбэк-на-ручной-budget, что list/detail/create/approve
    # (calc посчитан ДО setattr — budget в payload мог измениться, effective
    # пересчитывается по актуальному db_subsidy.budget после него).
    effective_budget = effective_subsidy_budget(calc, db_subsidy.budget)
    d = {c.name: getattr(db_subsidy, c.name) for c in db_subsidy.__table__.columns}
    d["calculated_budget"] = effective_budget
    d["feo_filled"] = calc > 0
    d["feo_budget_total"] = effective_budget
    if db_subsidy.contractor_id:
        contractor = await db.get(Contractor, db_subsidy.contractor_id)
        d["contractor_name"] = contractor.name if contractor else None
        d["contractor_inn"] = contractor.inn if contractor else None
        grantee_org = await _materialize_org_from_contractor(db, contractor, current_user.org_id)
        # Субсидия принадлежит организации-грантополучателю — перепривязываем
        # владельца при смене контрагента (expire_on_commit=False, доступ безопасен).
        if grantee_org is not None and db_subsidy.org_id != grantee_org.id:
            db_subsidy.org_id = grantee_org.id
            await db.commit()
            d["org_id"] = grantee_org.id
    else:
        d["contractor_name"] = None
        d["contractor_inn"] = None
    d.update(await calculate_ceiling_forecast(db, db_subsidy.id))
    return d

@router.get("/{subsidy_id}/delete-impact")
async def subsidy_delete_impact(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('subsidies')),
):
    """Counts of dependent rows so the UI can warn before deleting a subsidy."""
    from app.models.purchase import Purchase
    from app.models.contract import Contract
    from app.models.feo_planned_item import FeoPlannedItem
    feo_count = await db.scalar(
        select(func.count()).select_from(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
    )
    planned_count = await db.scalar(
        select(func.count()).select_from(FeoPlannedItem)
        .join(FeoCategory, FeoPlannedItem.feo_category_id == FeoCategory.id)
        .where(FeoCategory.subsidy_id == subsidy_id)
    )
    p_count = await db.scalar(
        select(func.count()).select_from(Purchase).where(Purchase.subsidy_id == subsidy_id)
    )
    c_count = await db.scalar(
        select(func.count()).select_from(Contract).where(Contract.subsidy_id == subsidy_id)
    )
    return {
        "feo_categories": feo_count or 0,
        "planned_items": planned_count or 0,
        "purchases": p_count or 0,
        "contracts": c_count or 0,
    }

@router.delete("/{subsidy_id}")
async def delete_subsidy(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))
    db_subsidy = result.scalar_one_or_none()
    if not db_subsidy:
        raise HTTPException(status_code=404, detail="Subsidy not found")

    # Черновые субсидии (план C1/C2): то же расщепление, что и в PUT — раньше
    # DELETE был гейтован слабее (просто 'subsidies' tab), чем правка
    # ('subsidy.edit') — исправлено заодно.
    if db_subsidy.status == 'draft':
        if not await _can_edit_draft_subsidy(db_subsidy, current_user, db):
            raise HTTPException(
                status_code=403,
                detail="Черновик субсидии удаляют автор и участники совместной работы",
            )
    else:
        # Wave 3: удалять субсидию можно только при праве subsidy.edit
        # в орге ЭТОЙ субсидии (орг-роль не даёт власти в чужих оргах).
        from app.auth.permissions import has_org_key
        if not await has_org_key(current_user, db, db_subsidy.org_id, 'subsidy.edit', subsidy_id=subsidy_id):
            raise HTTPException(
                status_code=403,
                detail="Нет права удалить субсидию: право «Редактирование субсидий» не выдано для организации-грантополучателя",
            )

    # Pre-check FK references to avoid 500 ForeignKeyViolationError
    # Superadmin bypasses this check — DB will SET NULL automatically (b7e1 migration).
    if current_user.role != 'superadmin':
        from app.models.purchase import Purchase
        from app.models.contract import Contract

        blocking_purchases = (await db.execute(
            select(Purchase.id, Purchase.status).where(Purchase.subsidy_id == subsidy_id)
        )).all()
        blocking_contracts = (await db.execute(
            select(Contract.id).where(Contract.subsidy_id == subsidy_id)
        )).all()
    else:
        blocking_purchases = []
        blocking_contracts = []
    if blocking_purchases or blocking_contracts:
        parts = []
        if blocking_purchases:
            ids = ", ".join(f"#{p.id}" for p in blocking_purchases[:20])
            more = f" и ещё {len(blocking_purchases) - 20}" if len(blocking_purchases) > 20 else ""
            parts.append(f"{len(blocking_purchases)} закупок (ID: {ids}{more})")
        if blocking_contracts:
            ids = ", ".join(f"#{c.id}" for c in blocking_contracts[:20])
            more = f" и ещё {len(blocking_contracts) - 20}" if len(blocking_contracts) > 20 else ""
            parts.append(f"{len(blocking_contracts)} договоров (ID: {ids}{more})")
        raise HTTPException(
            status_code=409,
            detail=(
                f"Нельзя удалить субсидию «{db_subsidy.name}»: связано "
                f"{' и '.join(parts)}. Часть закупок может быть скрыта фильтрами в списке "
                f"(например, разделённые закупки со статусом «split»). Сначала удалите или перепривяжите их."
            ),
        )

    # Bulk-delete dependents via SQL (not ORM cascade): feo_planned_items.feo_category_id
    # is NOT NULL, and ORM-level cascade would try to NULL it on parent delete -> IntegrityError.
    # Direct DELETE relies on the DB and avoids the autoflush nullify path entirely.
    from app.models.feo_planned_item import FeoPlannedItem
    try:
        cat_ids_subq = select(FeoCategory.id).where(FeoCategory.subsidy_id == subsidy_id)
        await db.execute(
            delete(FeoPlannedItem).where(FeoPlannedItem.feo_category_id.in_(cat_ids_subq))
        )
        await db.execute(
            delete(FeoCategory).where(FeoCategory.subsidy_id == subsidy_id)
        )
        await db.delete(db_subsidy)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.warning("delete_subsidy %s blocked by FK: %s", subsidy_id, e)
        raise HTTPException(
            status_code=409,
            detail=(
                "Не удалось удалить субсидию: на неё ссылаются другие записи "
                "(закупки, договоры или плановые позиции). Сначала удалите или "
                "перепривяжите связанные данные, затем повторите."
            ),
        )
    return {"message": "Субсидия удалена"}


# ── Per-subsidy contractor override endpoints ──

@router.get("/{subsidy_id}/contractor-override", response_model=SubsidyContractorOverrideOut)
async def get_contractor_override(
    subsidy_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get contractor detail overrides for a subsidy."""
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy or not subsidy.contractor_id:
        raise HTTPException(404, "Субсидия или контрагент не найден")

    override = (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == subsidy.contractor_id,
        )
    )).scalar_one_or_none()

    if not override:
        # Return base contractor data as initial override
        contractor = await db.get(Contractor, subsidy.contractor_id)
        if not contractor:
            raise HTTPException(404, "Контрагент не найден")
        return {
            "id": 0,
            "subsidy_id": subsidy_id,
            "contractor_id": subsidy.contractor_id,
            "org_type": contractor.org_type,
            "inn": contractor.inn,
            "kpp": contractor.kpp,
            "ogrn": contractor.ogrn,
            "signatory": contractor.signatory,
            "signatory_basis": contractor.signatory_basis,
            "address": contractor.address,
            "postal_address": contractor.postal_address,
            "bank_details": contractor.bank_details,
            "settlement_account": contractor.settlement_account,
            "bank_name": contractor.bank_name,
            "bik": contractor.bik,
            "correspondent_account": contractor.correspondent_account,
            "contact_person": contractor.contact_person,
            "phone": contractor.phone,
            "email": contractor.email,
        }
    return override


@router.put("/{subsidy_id}/contractor-override", response_model=SubsidyContractorOverrideOut)
async def upsert_contractor_override(
    subsidy_id: int,
    data: SubsidyContractorOverrideCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update contractor detail overrides for a subsidy."""
    subsidy = (await db.execute(select(Subsidy).where(Subsidy.id == subsidy_id))).scalar_one_or_none()
    if not subsidy or not subsidy.contractor_id:
        raise HTTPException(404, "Субсидия или контрагент не найден")

    override = (await db.execute(
        select(SubsidyContractorOverride).where(
            SubsidyContractorOverride.subsidy_id == subsidy_id,
            SubsidyContractorOverride.contractor_id == subsidy.contractor_id,
        )
    )).scalar_one_or_none()

    d = data.dict(exclude_unset=True) if override else data.dict()
    # Пересобираем signatory из структурированных частей (только ФИО)
    _fio_parts = (
        d.get('signatory_last_name') or (override.signatory_last_name if override else None),
        d.get('signatory_first_name') or (override.signatory_first_name if override else None),
        d.get('signatory_middle_name') or (override.signatory_middle_name if override else None),
    )
    if any(_fio_parts):
        d['signatory'] = compose_fio(*_fio_parts) or d.get('signatory')

    if override:
        for key, value in d.items():
            setattr(override, key, value)
    else:
        override = SubsidyContractorOverride(
            subsidy_id=subsidy_id,
            contractor_id=subsidy.contractor_id,
            **d
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    return override


@router.get("/{subsidy_id}/history")
async def get_budget_history(
    subsidy_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('subsidies')),
):
    from app.models.budget_history import BudgetHistory as BudgetHistoryModel
    from sqlalchemy import func as safunc

    base_q = (
        select(BudgetHistoryModel)
        .where(BudgetHistoryModel.subsidy_id == subsidy_id)
        .order_by(BudgetHistoryModel.changed_at.desc())
    )

    total = (
        await db.execute(select(safunc.count()).select_from(base_q.subquery()))
    ).scalar() or 0

    rows = (await db.execute(base_q.offset(offset).limit(limit))).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "purchase_id": r.purchase_id,
                "old_value": float(r.old_value) if r.old_value is not None else None,
                "new_value": float(r.new_value) if r.new_value is not None else None,
                "changed_by_name": r.changed_by_name,
                "reason": r.reason,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ],
    }
