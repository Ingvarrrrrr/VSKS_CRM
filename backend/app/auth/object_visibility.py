"""Единый гейт «видимость объекта по id = видимость в списке» (К2, 19.10.2026).

Поведенческое тестирование (tests/behavior/REPORT.md, К2) нашло, что открытие
закупки/файла/задачи/заявки ПО ID не проверяло видимость вовсе — сотрудник
другой организации, не видящий субсидию в списке (404), получал 200 на её
закупку, файлы, ТЗ-документ, задачу и переписку.

ПРАВИЛО №6: ни одна функция здесь не считает видимость заново — все
переиспользуют те же построители, что уже фильтруют списки:
  - purchases: app.auth.visibility.build_visibility_clause(..., 'purchase')
    + get_visible_subsidy_ids (как в routers/purchases.py::list_purchases)
    + user_subsidy_access grants.
  - tasks: app.auth.visibility.build_visibility_clause(..., 'task')
    (как в routers/tasks.py::list_tasks).
  - wishes: app.services.wish_access.ensure_wish_read_access — уже
    единственный источник («Правила: та же проверка, что и .../tz-rows»),
    здесь не дублируется, а напрямую вызывается.
  - subsidies: тот же гейт, что и routers/subsidies.py::get_subsidy
    (get_visible_subsidy_ids + fallback по видимой закупке субсидии).

Невидимо → 404 (не 403) — не раскрываем сам факт существования объекта,
кроме wishes, где уже устоявшийся конвенш 403 (routers/wishes.py) —
при повторном использовании ensure_wish_read_access код ошибки не меняем,
чтобы не плодить второй несовместимый источник для заявок.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase import Purchase
from app.models.task import Task
from app.models.user import User


async def _purchase_visibility_subsidy_ids(user: User, db: AsyncSession) -> set[int] | None:
    """Множество subsidy_id, закупки которых видны пользователю через
    двухуровневую видимость субсидий (orgs/tabs), ИЛИ None если фильтр не нужен
    (superadmin). Объединяет все вкладки, с которых закупка может быть видна
    в списке — purchases/advance_reports/service_notes (routers/purchases.py
    ::list_purchases использует get_visible_subsidy_ids(scope) по активной
    вкладке; здесь — объединение, т.к. у by-id ручки нет понятия «вкладка»)."""
    from app.auth.visibility import get_visible_subsidy_ids

    if user.role == "superadmin":
        return None

    result: set[int] = set()
    saw_none = False
    for scope in ("purchases", "advance_reports", "service_notes"):
        vis = await get_visible_subsidy_ids(user, db, scope)
        if vis is None:
            saw_none = True
        else:
            result |= vis
    if saw_none:
        return None
    return result


async def ensure_purchase_visible(user: User, purchase_id: int, db: AsyncSession) -> Purchase:
    """Возвращает Purchase, если видна пользователю, иначе 404.

    Два НЕЗАВИСИМЫХ (OR) пути:
      (1) именная причастность — ты лично назначен на эту закупку (ответственный,
          возмещение, участник, согласующий закупки/заявки, исполнитель связанной
          задачи) — та же _purchase_participation_clauses, что и в списке, НО
          проверяется сама по себе, без требования видеть вкладку субсидии: имя
          в листе согласования само по себе — причина видеть объект, который
          просят согласовать, даже если у согласующего нет вкладки/доступа к
          самой субсидии (QA-итерация 2, регрессия, 19.10.2026 — иначе
          согласующий получал 404 при попытке скачать файл закупки).
      (2) субсидия видна ПО ВКЛАДКЕ (get_visible_subsidy_ids) ИЛИ точечный грант,
          И ОТДЕЛЬНО — org-lead/view_all_in_org ветка build_visibility_clause
          (широкая видимость «вся орга»). Оба условия здесь ОБЯЗАТЕЛЬНЫ (AND) —
          список применяет их последовательными .where() (SQL AND), а не как
          альтернативы; без этого AND сотрудник другой орги того же аккаунта
          проходил бы по голой тАб-видимости (get_visible_subsidy_ids
          расширяется на весь контур аккаунта) — найдено прогоном
          l1_cross_account.py."""
    from app.auth.visibility import (
        build_visibility_clause, get_visible_user_ids, _purchase_participation_clauses,
    )
    from app.auth.jwt import ADMIN_ROLES
    from app.models.user_subsidy_access import UserSubsidyAccess
    from sqlalchemy import or_ as _or

    p = await db.get(Purchase, purchase_id)
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    if user.role == "superadmin":
        return p

    async def _payroll_gate(purchase: Purchase) -> Purchase:
        # Право «Видеть ФОТ» (владелец, 21.10.2026, часть 3): закупка ФОТ
        # (feo_payroll.purchase_payroll_map — ЕДИНСТВЕННАЯ формула «закупка —
        # ФОТ») субсидии без subsidy.view_payroll отдаётся как несуществующая
        # (ПРАВИЛО №8 п.2 — скрытая сущность = 404, не раскрываем сам факт
        # существования закупки ЗП/отчислений тому, кому её не положено видеть).
        if purchase.subsidy_id is None:
            return purchase
        from app.services.feo_payroll import purchase_payroll_map, subsidy_ids_with_payroll
        from app.services.payroll_visibility import can_view_subsidy_payroll
        # Перф (координатор, 21.10.2026): короткий выход ДО purchase_payroll_map
        # (3 запроса — purchase/items/plan items) — если в субсидии вообще
        # нет ни одной ФОТ-статьи, закупка заведомо не ФОТ.
        if not await subsidy_ids_with_payroll(db, [purchase.subsidy_id]):
            return purchase
        pmap = await purchase_payroll_map(db, [purchase.id])
        if pmap.get(purchase.id) and not await can_view_subsidy_payroll(user, db, purchase.subsidy_id):
            raise HTTPException(404, "Закупка не найдена")
        return purchase

    # Путь 1: именная причастность (всегда достаточно, независимо от вкладки).
    named_match = (await db.execute(
        select(Purchase.id).where(
            Purchase.id == purchase_id,
            _or(
                Purchase.assigned_user_id == user.id,
                Purchase.reimbursement_user_id == user.id,
                *_purchase_participation_clauses(user.id),
            ),
        )
    )).scalar_one_or_none()
    if named_match is not None:
        return await _payroll_gate(p)

    # Путь 2: субсидия видна по вкладке ИЛИ точечный грант.
    sub_ids = await _purchase_visibility_subsidy_ids(user, db)
    subsidy_ok = sub_ids is None  # None = SaaS, уже отработано выше (defensive)
    if not subsidy_ok and p.subsidy_id is not None:
        subsidy_ok = p.subsidy_id in sub_ids
    if not subsidy_ok and p.subsidy_id is not None:
        granted_ids = set((await db.execute(
            select(UserSubsidyAccess.subsidy_id).where(UserSubsidyAccess.user_id == user.id)
        )).scalars().all())
        subsidy_ok = p.subsidy_id in granted_ids
    if not subsidy_ok:
        raise HTTPException(404, "Закупка не найдена")

    # Условие 2 (AND): build_visibility_clause — org-lead/view_all_in_org ветка,
    # тот же порядок, что list_purchases (именную причастность уже проверили выше).
    clause = await build_visibility_clause(user, db, "purchase")
    if clause is None:
        return await _payroll_gate(p)  # SaaS-роль — фильтр не нужен (сюда не дойдёт для superadmin, defensive)

    vuids = await get_visible_user_ids(user, db)
    is_org_lead = user.role in ADMIN_ROLES or (vuids is not None and len(vuids) > 1)
    if is_org_lead:
        clause = _or(clause, Purchase.assigned_user_id.is_(None))

    match = (await db.execute(
        select(Purchase.id).where(Purchase.id == purchase_id, clause)
    )).scalar_one_or_none()
    if match is not None:
        return await _payroll_gate(p)

    raise HTTPException(404, "Закупка не найдена")


async def ensure_task_visible(user: User, task_id: int, db: AsyncSession) -> Task:
    """Возвращает Task, если видна пользователю, иначе 404.

    Переиспользует build_visibility_clause('task') — тот же источник, что
    routers/tasks.py::list_tasks (назначен/создал/участник чата/комментатор/
    view_all_in_org)."""
    from app.auth.visibility import build_visibility_clause

    t = await db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Задача не найдена")

    if user.role == "superadmin":
        return t

    clause = await build_visibility_clause(user, db, "task")
    if clause is None:
        return t

    match = (await db.execute(
        select(Task.id).where(Task.id == task_id, clause)
    )).scalar_one_or_none()
    if match is None:
        raise HTTPException(404, "Задача не найдена")
    return t


async def ensure_subsidy_visible(user: User, subsidy_id: int, db: AsyncSession):
    """Возвращает Subsidy, если видна пользователю, иначе 404.

    ТОТ ЖЕ гейт, что routers/subsidies.py::get_subsidy (единственный
    источник — видимые субсидии ∪ фолбэк по видимой закупке этой субсидии)."""
    from app.auth.visibility import get_visible_subsidy_ids, build_visibility_clause
    from app.models.subsidy import Subsidy

    subsidy = await db.get(Subsidy, subsidy_id)
    if not subsidy:
        raise HTTPException(404, "Субсидия не найдена")

    if user.role == "superadmin":
        return subsidy

    visible = await get_visible_subsidy_ids(user, db)
    if visible is not None and subsidy_id not in visible:
        clause = await build_visibility_clause(user, db, "purchase")
        allowed = clause is None
        if clause is not None:
            from sqlalchemy import func
            cnt = (await db.execute(
                select(func.count()).select_from(Purchase).where(
                    Purchase.subsidy_id == subsidy_id, clause
                )
            )).scalar() or 0
            allowed = cnt > 0
        if not allowed:
            raise HTTPException(status_code=404, detail="Субсидия не найдена")

    return subsidy


async def ensure_wish_visible(user: User, wish_id: int, db: AsyncSession):
    """Возвращает Wish, если видна пользователю, иначе 403 (НЕ 404 — см.
    модульный docstring: переиспользует устоявшийся
    services.wish_access.ensure_wish_read_access, который уже используется
    в GET /api/wishes/{id} и GET /api/wishes/{id}/tz-rows; код ошибки там
    исторически 403 и менять его здесь означало бы завести второй источник
    с другим контрактом."""
    from app.services.wish_access import ensure_wish_read_access
    from app.routers.wishes import _load_wish

    wish = await _load_wish(wish_id, db)
    await ensure_wish_read_access(wish, user, db)
    return wish
