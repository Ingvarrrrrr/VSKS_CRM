"""Задача владельца (план ancient-prancing-music.md, раздел E, 2026-09-21;
РЕШЕНИЕ ВЛАДЕЛЬЦА от 21.09, повторное уточнение): контроль превышения ПО ТИПУ
(товары/услуги) на forward-переходах закупки — МЯГКИЙ, не 409. Переход
проходит (200), но (1) регистрирует запрос на согласование через
register_type_excess_approvals (тот же сервис, что и в routers/purchases.py
create/PUT, routers/wish_convert.py — ПРАВИЛО №6, второй копии нет) и
(2) отдаёт предупреждение в excess_warnings ответа перехода — тем же
механизмом, что и «план над ФЭО» (assert_no_unapproved_excess) с 2026-09-03.

Жёсткий контроль «ТЗ над плановой позицией» (assert_no_pending_tz_excess)
этим НЕ затронут (см. test_tz_over_plan_goes_to_approval.py — отдельный
файл, здесь не дублируется). Функция assert_no_pending_type_excess (жёсткая,
409) сохранена в app/services/type_excess_approval.py про запас — на
forward-переходах больше не вызывается (см. test_type_excess_approval.py —
прямые тесты самой функции/сервиса, здесь не дублируются, ПРАВИЛО №6).

Сценарий: категория ФЭО с типизированным ФЭО по услугам (30 000 ₽) и планом
услуг выше этого (60 000 ₽, за счёт позиции ВНЕ ФЭО-разбивки). Проверяем:
  (а) forward-переход проходит 200, несмотря на непогашенное превышение;
  (б) в ответе (excess_warnings) есть предупреждение вида plan_over_feo_services
      с видом (kind) и уровнем (level);
  (в) создана pending-запись PlanExcessApproval нужного kind (и на уровне
      категории, и на уровне субсидии целиком — оба независимы);
  (г) повторный forward-переход (следующий шаг того же перекоса) НЕ плодит
      дубль pending-записей — переиспользует уже созданные.

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ (pytest tests/test_purchase_transitions_type_gate.py::<name>).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.plan_excess_approval import PlanExcessApproval
from app.models.user_org_access import UserOrgAccess
from app.models.permission import UserOrgPermissionOverride
from app.services import plan_excess_kinds as PEK
from app.auth.jwt import create_access_token


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TypeGate-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=None):
    from app.models.feo_category import FeoCategory
    # budget УЗЛА намеренно НЕ задан (None) — явная FeoCategory.budget узла
    # была бы «нетипизированным бюджетом» (идёт целиком в feo_unspecified, см.
    # app.services.feo_plan_tree._feo_by_kind) и перекрыла бы типизированные
    # is_feo_breakdown-позиции ниже, из-за чего feo_services остался бы 0 и
    # excess_plan_over_feo_services никогда бы не поднялся — контроль по
    # определению требует именно типизированного ФЭО.
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name="Категория — превышение по услугам (тест)",
        budget=budget,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_ceiling_headroom_category(db_session, subsidy_id):
    """Соседняя категория с большим явным бюджетом — поднимает жёсткий
    потолок субсидии (calculate_budget_from_categories, PLAN_OVER_SUBSIDY_
    CEILING в assert_no_unapproved_excess, вызывается ПЕРЕД гейтом по типу в
    purchase_transitions.py) выше суммы плана тестовой категории, чтобы тест
    проверял ИМЕННО контроль по типу, а не жёсткий потолок субсидии (другой,
    уже покрытый вид, см. test_excess_total_not_per_branch.py)."""
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id, parent_id=None, level=1,
        name="Соседняя категория — запас потолка субсидии (тест)",
        budget=Decimal("5000000"),
    )
    db_session.add(cat)
    await db_session.commit()


async def _make_planned_items(db_session, feo_category_id):
    from app.models.feo_planned_item import FeoPlannedItem
    # Типизированное ФЭО по услугам — 30 000 ₽.
    db_session.add(FeoPlannedItem(
        feo_category_id=feo_category_id, name="Услуга (по ФЭО)",
        quantity=Decimal("1"), unit="усл", amount=Decimal("30000"),
        item_type="услуга", is_feo_breakdown=True, feo_amount=Decimal("30000"),
        is_active=True,
    ))
    # Ещё план услуг сверх ФЭО-разбивки — 30 000 ₽ (итого план услуг 60 000 ₽).
    db_session.add(FeoPlannedItem(
        feo_category_id=feo_category_id, name="Услуга сверх ФЭО-разбивки",
        quantity=Decimal("1"), unit="усл", amount=Decimal("30000"),
        item_type="услуга", is_active=True,
    ))
    await db_session.commit()


async def _make_purchase(db_session, subsidy_id, feo_category_id, amount=Decimal("30000"), status="wishes"):
    p = Purchase(
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
        item_name="Услуга (закупка, тест типового гейта)",
        status=status,
        planned_total_price=amount,
        total_nmck=amount,
        nmck=amount,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Услуга", quantity=Decimal("1"), unit="усл",
        unit_price=amount, total_price=amount,
        feo_category_id=feo_category_id, item_type="услуга", over_plan=False,
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _make_type_excess_approver(db_session, test_org, make_user):
    approver = await make_user(role="manager", org_id=test_org.id)
    uoa = UserOrgAccess(user_id=approver.id, org_id=test_org.id, role="manager")
    db_session.add(uoa)
    await db_session.commit()
    await db_session.refresh(uoa)
    db_session.add(UserOrgPermissionOverride(
        user_org_access_id=uoa.id, key="plan_excess.decide", granted=True,
    ))
    await db_session.commit()
    return approver


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


async def _pending_type_excess_rows(db_session, subsidy_id):
    rows = (await db_session.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.subsidy_id == subsidy_id,
            PlanExcessApproval.kind == PEK.PLAN_OVER_FEO_SERVICES,
            PlanExcessApproval.status == "pending",
        )
    )).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_forward_transition_soft_warns_registers_pending_no_dup(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """(а)+(б)+(в)+(г) в одном сценарии: forward-переход при непогашенном
    превышении по типу проходит 200, несёт предупреждение (kind/level),
    создаёт pending PlanExcessApproval нужного kind, а СЛЕДУЮЩИЙ forward-
    переход того же перекоса не плодит дубль (переиспользует pending)."""
    await _make_type_excess_approver(db_session, test_org, make_user)

    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    await _make_planned_items(db_session, cat.id)
    await _make_ceiling_headroom_category(db_session, subsidy.id)
    purchase = await _make_purchase(db_session, subsidy.id, cat.id, status="wishes")

    # Шаг 1: wishes -> plan_schedule (первый forward-переход, гейт по типу
    # срабатывает на КАЖДОМ forward-переходе, см. purchase_transitions.py).
    resp1 = await client.post(
        f"/api/purchases/{purchase.id}/transition?status=plan_schedule",
        headers=admin_headers,
    )
    assert resp1.status_code == 200, (
        f"Мягкий контроль — переход НЕ должен блокироваться превышением по типу: "
        f"{resp1.status_code} {resp1.text}"
    )
    body1 = resp1.json()
    warnings1 = body1.get("excess_warnings") or []
    services_warnings1 = [w for w in warnings1 if w.get("kind") == PEK.PLAN_OVER_FEO_SERVICES]
    assert services_warnings1, f"Ожидалось предупреждение plan_over_feo_services в ответе: {warnings1}"
    assert any(w.get("level") == PEK.LEVEL_CATEGORY for w in services_warnings1), services_warnings1
    assert any(w.get("level") == PEK.LEVEL_SUBSIDY for w in services_warnings1), services_warnings1

    rows_after_step1 = await _pending_type_excess_rows(db_session, subsidy.id)
    assert len(rows_after_step1) == 2, (
        f"Ожидались ДВЕ независимые pending-записи (категория + субсидия целиком), "
        f"получено {len(rows_after_step1)}"
    )
    ids_after_step1 = {r.id for r in rows_after_step1}

    purchase_after_step1 = await db_session.get(Purchase, purchase.id)
    assert purchase_after_step1.status == "plan_schedule"

    # Шаг 2: plan_schedule -> work_in_progress (второй forward-переход, тот же
    # непогашенный перекос по услугам) — переход ОБЯЗАН пройти, а pending-
    # записи НЕ должны задублироваться (register_type_excess_approvals находит
    # существующий pending той же пары (feo_category_id, kind) и переиспользует).
    resp2 = await client.post(
        f"/api/purchases/{purchase.id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert resp2.status_code == 200, (
        f"Мягкий контроль — второй forward-переход тоже НЕ должен блокироваться: "
        f"{resp2.status_code} {resp2.text}"
    )
    body2 = resp2.json()
    warnings2 = body2.get("excess_warnings") or []
    services_warnings2 = [w for w in warnings2 if w.get("kind") == PEK.PLAN_OVER_FEO_SERVICES]
    assert services_warnings2, f"Ожидалось предупреждение и на втором переходе: {warnings2}"

    rows_after_step2 = await _pending_type_excess_rows(db_session, subsidy.id)
    assert len(rows_after_step2) == 2, (
        f"Повторный переход НЕ должен плодить дубли pending-записей: "
        f"было {len(rows_after_step1)}, стало {len(rows_after_step2)}"
    )
    ids_after_step2 = {r.id for r in rows_after_step2}
    assert ids_after_step1 == ids_after_step2, (
        "Второй переход обязан переиспользовать ТЕ ЖЕ записи согласования, а не создавать новые"
    )

    purchase_final = await db_session.get(Purchase, purchase.id)
    assert purchase_final.status == "work_in_progress"


@pytest.mark.asyncio
async def test_no_approver_still_blocks_transition_not_silent_pass(
    client, db_session, test_org, test_admin_user, admin_headers,
):
    """Без единого уполномоченного ('plan_excess.decide') регистрация запроса
    на согласование невозможна — register_type_excess_approvals сама бросает
    409 (граница «превышение не проходит молча», см. docstring
    app/services/type_excess_approval.py), поэтому переход остаётся
    заблокирован — но ТЕПЕРЬ по ДРУГОЙ причине, чем раньше: не жёсткий гейт
    assert_no_pending_type_excess (он больше не вызывается на переходах), а
    невозможность создать сам запрос на согласование."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    await _make_planned_items(db_session, cat.id)
    await _make_ceiling_headroom_category(db_session, subsidy.id)
    purchase = await _make_purchase(db_session, subsidy.id, cat.id, status="plan_schedule")

    resp = await client.post(
        f"/api/purchases/{purchase.id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert resp.status_code == 409, (
        f"Без уполномоченного согласовать превышение по типу некому — переход "
        f"ОБЯЗАН остаться заблокированным: {resp.status_code} {resp.text}"
    )
    # Глобальный обработчик исключений оборачивает HTTPException(409, "<str>")
    # в {"code": "HTTP_409", "message": "<str>", ...} — не {"detail": ...}
    # (см. app/main.py exception handler); текст сообщения — из
    # register_type_excess_approvals (единственный источник, ПРАВИЛО №6).
    body = resp.json()
    message = body.get("message") or str(body.get("detail"))
    assert "Согласовать некому" in message, body

    purchase_after = await db_session.get(Purchase, purchase.id)
    assert purchase_after.status == "plan_schedule", "Статус не должен был сдвинуться при 409"

    rows = await _pending_type_excess_rows(db_session, subsidy.id)
    assert rows == [], "Без уполномоченного запись согласования не должна была создаться"
