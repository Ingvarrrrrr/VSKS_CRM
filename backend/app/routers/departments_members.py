"""Участники отдела: список, добавление, правка должности, удаление
(вынесено из departments.py, Правило №5, сессия 2026-09-08 — см. докстринг
departments.py).

Регистрируется на том же префиксе ``/api/departments`` рядом с ядром;
коллизий путь+метод с catch-all ``/{dept_id}`` (только PATCH/DELETE в ядре)
у путей ``/{dept_id}/members`` и ``/{dept_id}/members/{user_id}`` нет
(другой набор методов и минимум на сегмент длиннее), порядок регистрации
относительно ядра значения не имеет.

Должность (Правило №6) — читается/пишется только через
``app.services.user_position`` (resolve_user_position/set_user_position);
создание НОВОЙ строки membership с ``position=...`` напрямую — установленный
паттерн (см. докстринг ``set_user_position``: создание membership не входит
в его ответственность).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.auth.permissions import require_tab
from app.database import get_db
from app.models.department import Department
from app.models.organization import Organization
from app.models.user import User
from app.models.user_organization import UserOrganization
from app.routers.departments import MemberAdd, MemberOut
from app.services.org_assignment_dates import (
    first_row_assignment_dates,
    dept_transfer_date,
    position_change_date,
)
from app.services.user_position import resolve_user_position, set_user_position

router = APIRouter(prefix="/api/departments", tags=["departments"])


# ── Members ──────────────────────────────────────────────────────────────────

@router.get("/{dept_id}/members", response_model=List[MemberOut])
async def list_members(
    dept_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # user_organizations is now the single source of truth for dept membership.
    uo_rows = (await db.execute(
        select(UserOrganization).where(UserOrganization.dept_id == dept_id)
    )).scalars().all()

    user_ids = {r.user_id for r in uo_rows}
    users_map: dict[int, User] = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():  # superadmin-bypass-ok: lookup by pre-computed IDs for department member enrichment
            users_map[u.id] = u

    out: list[MemberOut] = []
    seen_users: set[int] = set()
    for r in uo_rows:
        if r.user_id in seen_users:
            continue
        seen_users.add(r.user_id)
        u = users_map.get(r.user_id)
        out.append(MemberOut(
            id=r.id, department_id=dept_id, user_id=r.user_id,
            user_name=(u.full_name or u.username) if u else None,
            user_role=u.role if u else None,
            # Rule #6: единственный резолвер — эта строка уже задаёт org_id,
            # legacy User.position подмешивается только если членств нет вовсе.
            position=resolve_user_position(u, org_id=r.org_id, memberships=[r]),
            dept_assigned_at=r.dept_assigned_at,
            position_assigned_at=r.position_assigned_at,
        ))
    return out


@router.post("/{dept_id}/members", response_model=MemberOut)
async def add_member(
    dept_id: int,
    data: MemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    dept = await db.get(Department, dept_id)
    if not dept:
        raise HTTPException(404, "Отдел не найден")
    # Multi-dept-per-org разрешён: сотрудник может состоять одновременно в нескольких
    # отделах одной и той же организации (Цыганов в Бухгалтерии+Отделе МТО+«1»).
    # user_organizations is the single source of truth — look for an existing row
    # for this exact (user, org, dept) triple.
    user = await db.get(User, data.user_id)
    uo_exact = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == data.user_id,
            UserOrganization.org_id == dept.org_id,
            UserOrganization.dept_id == dept_id,
        )
    )).scalar_one_or_none()
    # Строка-заглушка «Без отдела» для этой же пары (user, org) — источник hired_at/
    # позиции/ставки для новой dept-строки, и то, что нужно удалить после успешного
    # назначения (иначе она продолжает висеть в карточке как «Без отдела», хотя
    # человек уже определён в отдел — баг owner 2026-09-01).
    null_row = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == data.user_id,
            UserOrganization.org_id == dept.org_id,
            UserOrganization.dept_id.is_(None),
        )
    )).scalar_one_or_none()
    if uo_exact:
        # Row already correct — just sync position if needed
        old_position = uo_exact.position
        position_changed = bool(data.position) and data.position != old_position
        if data.position:
            await set_user_position(db, data.position, membership=uo_exact)
        uo_exact.position_assigned_at = position_change_date(
            position_changed=position_changed,
            current=uo_exact.position_assigned_at,
            explicit=None,
        )
        if uo_exact.dept_assigned_at is None:
            uo_exact.dept_assigned_at = dept_transfer_date(data.dept_assigned_at)
        await db.commit()
        m = uo_exact
    else:
        # No row for this dept yet — insert a new one (multi-dept allowed).
        # hired_at (дата трудоустройства) ОБЩАЯ на пару (user, org) — переносим её
        # из заглушки/любой другой строки этой пары, а НЕ ставим now() (баг owner:
        # дата трудоустройства подменялась датой назначения в отдел).
        base_row = null_row or (await db.execute(
            select(UserOrganization)
            .where(
                UserOrganization.user_id == data.user_id,
                UserOrganization.org_id == dept.org_id,
            )
            .order_by(UserOrganization.id.asc())
            .limit(1)
        )).scalars().first()
        # Rule #6: единственный резолвер — если ввод пуст, наследуем должность
        # из другой строки этой же организации, иначе (нет вообще ни одной
        # записи по этой org) — из legacy User.position.
        new_pos = data.position or resolve_user_position(
            user, org_id=dept.org_id, memberships=[base_row] if base_row else []
        )
        kwargs = dict(user_id=data.user_id, org_id=dept.org_id, dept_id=dept_id, position=new_pos)
        if base_row is not None and base_row.hired_at is not None:
            kwargs["hired_at"] = base_row.hired_at
        if base_row is None:
            # Первая-ЕВЕР строка user_organizations для этой пары (user, org) —
            # это приём на работу, обе даты назначения = дате приёма (владелец,
            # 2026-09-01), а не «сегодня».
            kwargs.update(first_row_assignment_dates(
                kwargs.get("hired_at"),
                has_position=bool(new_pos),
                has_dept=True,
                explicit_dept_assigned_at=data.dept_assigned_at,
            ))
        else:
            # Перевод в другой отдел уже трудоустроенного человека — дата
            # перевода явная или сегодня; должность, если не менялась,
            # наследует прежнюю дату назначения (не обнуляем её).
            prior_position = base_row.position
            position_changed = bool(new_pos) and new_pos != prior_position
            kwargs["dept_assigned_at"] = dept_transfer_date(data.dept_assigned_at)
            pos_date = position_change_date(
                position_changed=position_changed,
                current=base_row.position_assigned_at,
                explicit=None,
            )
            if pos_date is not None:
                kwargs["position_assigned_at"] = pos_date
        if base_row is not None:
            if base_row.salary_amount is not None:
                kwargs["salary_amount"] = base_row.salary_amount
            if base_row.employment_percent is not None:
                kwargs["employment_percent"] = base_row.employment_percent
        m = UserOrganization(**kwargs)
        db.add(m)
        await db.commit()
        await db.refresh(m)
    # Заглушка «Без отдела» больше не нужна — человек определён в отдел.
    if null_row is not None and null_row.id != m.id:
        await db.delete(null_row)
        await db.commit()
    # Должность члена → head/deputy отдела (двусторонняя синхронизация)
    from app.services.dept_role_sync import sync_head_from_position
    await sync_head_from_position(db, dept, data.user_id, m.position)
    await db.commit()
    # Also update user.department string
    if user:
        user.department = dept.name
        await db.commit()
    # Auto-create hierarchy: new member becomes subordinate of dept head
    if dept.head_user_id and dept.head_user_id != data.user_id:
        from app.models.user_hierarchy import UserHierarchy
        existing_uh = (await db.execute(
            select(UserHierarchy).where(
                UserHierarchy.manager_id == dept.head_user_id,
                UserHierarchy.subordinate_id == data.user_id,
            )
        )).scalar_one_or_none()
        if not existing_uh:
            db.add(UserHierarchy(manager_id=dept.head_user_id, subordinate_id=data.user_id))
            await db.commit()
    u = await db.get(User, m.user_id)
    return MemberOut(
        id=m.id, department_id=dept_id, user_id=m.user_id,
        user_name=(u.full_name or u.username) if u else None,
        user_role=u.role if u else None,
        position=resolve_user_position(u, org_id=m.org_id, memberships=[m]),
        dept_assigned_at=m.dept_assigned_at,
        position_assigned_at=m.position_assigned_at,
    )


@router.patch("/{dept_id}/members/{user_id}")
async def update_member(
    dept_id: int,
    user_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    m = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.dept_id == dept_id,
            UserOrganization.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Сотрудник не найден в отделе")
    if "position" in data:
        await set_user_position(db, data["position"], membership=m)
        await db.commit()
        dept = await db.get(Department, dept_id)
        if dept is not None:
            from app.services.dept_role_sync import sync_head_from_position
            await sync_head_from_position(db, dept, user_id, m.position)
            await db.commit()
    else:
        await db.commit()
    return {"ok": True}


@router.delete("/{dept_id}/members/{user_id}")
async def remove_member(
    dept_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tab('staff')),
):
    uo_rows = (await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user_id,
            UserOrganization.dept_id == dept_id,
        )
    )).scalars().all()

    if not uo_rows:
        raise HTTPException(404, "Сотрудник не найден в отделе")

    # Phase 30 fix: учитываем закупки ТОЛЬКО в той же организации, что и отдел.
    # Раньше считались закупки глобально → удаление из АНО блокировалось задачами из ВСКС.
    from app.models.purchase import Purchase
    from app.models.subsidy import Subsidy
    dept = await db.get(Department, dept_id)
    dept_org_id = dept.org_id if dept else None
    active_count_q = (
        select(func.count()).select_from(Purchase)
        .join(Subsidy, Subsidy.id == Purchase.subsidy_id, isouter=True)
        .where(
            Purchase.assigned_user_id == user_id,
            Purchase.status.notin_(['paid', 'cancelled']),
        )
    )
    if dept_org_id is not None:
        active_count_q = active_count_q.where(Subsidy.org_id == dept_org_id)
    active_count = (await db.execute(active_count_q)).scalar() or 0
    # Суперадмин переносит/выводит сотрудника несмотря на активные закупки
    # (ссылки не блокируют операции суперадмина — модель Wave 1/3).
    if active_count > 0 and current_user.role != 'superadmin':
        org_name = (await db.execute(
            select(Organization.name).where(Organization.id == dept_org_id)
        )).scalar() if dept_org_id else 'этой организации'
        raise HTTPException(400, f"У сотрудника {active_count} активных задач (закупок) в «{org_name}». Сначала перераспределите задачи.")

    # Человек выведен из отдела → снять с него роль начальника/зама этого отдела
    # и очистить должность в снимаемых членствах (человек в разных отделах может
    # занимать разные должности — трогаем только это членство).
    if dept is not None:
        from app.services.dept_role_sync import clear_role_on_removal
        await clear_role_on_removal(db, dept, user_id)
    from app.services.dept_role_sync import POSITION_HEAD, POSITION_DEPUTY
    for uo in uo_rows:
        if uo.position in (POSITION_HEAD, POSITION_DEPUTY):
            await set_user_position(db, None, membership=uo)

    for uo in uo_rows:
        # Multi-dept: если у пары (user, org) остаётся ЕЩЁ хотя бы один отдел (не
        # считая текущей строки) — человек не выпадает из организации, эта строка
        # просто больше не нужна. Заглушку dept_id=NULL заводить НЕ надо — иначе
        # ровно тот же баг, который эта миграция/фича лечит (лишняя «Без отдела»).
        other_dept = (await db.execute(
            select(UserOrganization.id).where(
                UserOrganization.user_id == uo.user_id,
                UserOrganization.org_id == uo.org_id,
                UserOrganization.dept_id.isnot(None),
                UserOrganization.id != uo.id,
            )
        )).first()
        if other_dept is not None:
            await db.delete(uo)
            continue
        # Это был последний отдел пары (user, org) — превращаем строку в «Без
        # отдела», сохранив hired_at/должность/ставку (иначе человек выпадает
        # из организации целиком).
        conflict = (await db.execute(
            select(UserOrganization).where(
                UserOrganization.user_id == uo.user_id,
                UserOrganization.org_id == uo.org_id,
                UserOrganization.dept_id.is_(None),
                UserOrganization.id != uo.id,
            )
        )).scalar_one_or_none()
        if conflict is not None:
            # Заглушка уже существует (не должно происходить в норме, но на
            # всякий случай) — удаляем дубль, членство сохранено в заглушке.
            await db.delete(uo)
        else:
            uo.dept_id = None
            uo.dept_assigned_at = None
            uo.position_assigned_at = None

    await db.commit()
    # Синк карточки: если поле «Отдел» указывало на снимаемый отдел —
    # перенаправить на оставшееся членство (приоритет — родная орга карточки), иначе очистить.
    user = await db.get(User, user_id)
    if user is not None:
        removed_name = dept.name if dept is not None else None
        if user.department == removed_name:
            # Сначала ищем в «родной» орге карточки, затем в любой.
            remaining = None
            for org_filter in (
                [UserOrganization.org_id == user.org_id] if user.org_id else [],
                [],
            ):
                q = (
                    select(UserOrganization, Department)
                    .join(Department, Department.id == UserOrganization.dept_id)
                    .where(
                        UserOrganization.user_id == user_id,
                        UserOrganization.dept_id.isnot(None),
                        UserOrganization.dept_id != dept_id,
                        *org_filter,
                    )
                    .order_by(UserOrganization.id.asc())
                    .limit(1)
                )
                remaining = (await db.execute(q)).first()
                if remaining:
                    break
            user.department = remaining[1].name if remaining else None
            await db.commit()
    return {"ok": True}
