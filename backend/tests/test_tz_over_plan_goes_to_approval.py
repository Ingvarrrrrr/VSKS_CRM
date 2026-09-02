"""Владелец продукта (2026-09-02), дословно: «это же заявка согласуется, это
согласуется её необходимость, попасть должно в План-закупок, финансист (тот, у
кого есть право согласовывать превышение) видит, что люди просят, и решает —
пропускает её или нет. Но дальше двигаться нельзя по закупке без его
согласования».

Живой случай (прод): заявка №52, позиция «Логистические услуги», категория ФЭО
«Организационные расходы на содержание штаба» (id 125). Бюджет категории
330 100 ₽, свободно 318 830 ₽ — денег полно. Но единственная плановая позиция
внутри (id 1417) — всего 11 270,19 ₽ при количестве 1, а ТЗ 48 935,05 ₽.
app.services.feo_plan.assert_tz_batch_not_over_plan бросала жёсткий 409 без
единого обхода по правам — согласующий не мог пропустить заявку вообще никак.

Тест воспроизводит ровно этот сценарий (округлённые числа) через живой HTTP-путь
«заявка на согласование → approve → закупка в Плане закупок → попытка
продвинуть закупку дальше»:
  (а) ТЗ выше плановой позиции при согласовании заявки → 409 НЕ бросается,
      закупка создана (см. app.routers.wishes._distribute_wish_to_purchases,
      правка 2026-09-02);
  (б) после этого существует запрос на согласование превышения
      (PlanExcessApproval в статусе pending) — см.
      app.services.tz_excess_approval.register_tz_excess_approvals;
  (в) КЛЮЧЕВОЙ: пока превышение не согласовано, дальнейшее движение закупки
      (переход статуса «План закупок» → «Ведётся работа») заблокировано — см.
      app.services.tz_excess_approval.assert_no_pending_tz_excess, вызванную
      из app.routers.purchase_transitions.transition_status (это тот самый
      гейт, который feo_plan.assert_no_unapproved_excess закрыть НЕ может —
      см. докстринг tz_excess_approval.py, ПОЧЕМУ);
  (г) после одобрения превышения (POST /api/plan-excess/{id}/decide) то же
      движение разрешено.

Известный флейк (см. tests/conftest.py, НЕ чинить здесь): async-тесты падают
«attached to a different loop» при запуске пачкой — гонять файл по ОДНОМУ
тесту (pytest tests/test_tz_over_plan_goes_to_approval.py::<name>).
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.plan_excess_approval import PlanExcessApproval
from app.auth.jwt import create_access_token


async def _make_subsidy(db_session, org_id, budget=10_000_000):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TZ-Excess-Subsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=budget,
        org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, budget=Decimal("330100")):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name="Организационные расходы на содержание штаба (тест)",
        budget=budget,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, amount=Decimal("11270.19"), quantity=Decimal("1")):
    from app.models.feo_planned_item import FeoPlannedItem
    fpi = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name="Логистические услуги",
        quantity=quantity,
        unit="усл",
        amount=amount,
        is_active=True,
    )
    db_session.add(fpi)
    await db_session.commit()
    await db_session.refresh(fpi)
    return fpi


async def _make_wish_over_plan(db_session, org_id, user_id, subsidy_id, feo_category_id, feo_planned_item_id):
    """Заявка №52 (тестовый аналог): ТЗ 48 935,05 ₽ при плановой позиции 11 270,19 ₽."""
    qty = Decimal("1")
    unit_price = Decimal("48935.05")
    total = qty * unit_price
    w = Wish(
        org_id=org_id,
        title="Логистические услуги (тест превышения ТЗ над планом)",
        status="submitted",
        created_by=user_id,
        subsidy_id=subsidy_id,
        feo_category_id=feo_category_id,
    )
    db_session.add(w)
    await db_session.flush()
    wi = WishItem(
        wish_id=w.id,
        item_name="Логистические услуги",
        quantity=qty,
        unit="усл",
        unit_price=unit_price,
        total_price=total,
        feo_category_id=feo_category_id,
        feo_planned_item_id=feo_planned_item_id,
        over_plan=False,
    )
    db_session.add(wi)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _make_plan_excess_approver(db_session, test_org, make_user):
    """Пользователь с реальным правом 'plan_excess.decide' в test_org — та же
    роль владелец описывал как «финансист»: право выдано ТОЧЕЧНО этому
    конкретному пользователю (UserOrgPermissionOverride), а не всей роли —
    ровно так, как задача требует («право выдаётся точечно, никому не
    полагается по умолчанию», см. app/routers/plan_excess.py). Точечный грант,
    а не общая RolePermission(role='manager', ...): дев-БД, на которой гоняются
    тесты, УЖЕ содержит реальную строку RolePermission('manager',
    'plan_excess.decide', granted=False) — вставка второй строки той же роли
    упала бы в unique-constraint (role_name, key).

    UserOrgAccess — членство/роль в org (один из четырёх источников кандидатов
    в _authorized_plan_excess_approvers, см. её докстринг) И носитель
    override'а (UserOrgPermissionOverride.user_org_access_id → UserOrgAccess)."""
    from app.models.user_org_access import UserOrgAccess
    from app.models.permission import UserOrgPermissionOverride

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


@pytest.mark.asyncio
async def test_a_tz_over_plan_approve_does_not_409_purchase_created(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """(а) ТЗ выше плановой позиции при согласовании заявки -> 409 НЕ бросается,
    закупка создана в «Плане закупок».

    ГРАНИЦА задачи (проверена ОТДЕЛЬНО, см. test_e ниже): без ХОТЬ ОДНОГО
    уполномоченного на согласование в организации регистрация не может
    состояться, и код обязан отказать (не пропускать молча) — поэтому здесь
    approver создаётся заранее, как и в реальной организации, где право
    «Согласование превышения плана ФЭО» выдано финансисту."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id)
    w = await _make_wish_over_plan(
        db_session, test_org.id, test_admin_user.id, subsidy.id, cat.id, fpi.id,
    )

    resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)

    assert resp.status_code == 200, (
        f"Ожидался 200 (согласование НЕ блокируется превышением ТЗ над плановой "
        f"позицией), получили {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("status") == "converted", body
    purchase_ids = body.get("purchase_ids") or []
    assert purchase_ids, f"Закупка не создана: {body}"

    purchase = await db_session.get(Purchase, purchase_ids[0])
    assert purchase is not None
    assert purchase.status == "plan_schedule", (
        f"Закупка обязана попасть в «План закупок», получили статус {purchase.status!r}"
    )


@pytest.mark.asyncio
async def test_b_pending_plan_excess_approval_registered(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """(б) После согласования заявки существует запрос PlanExcessApproval в
    статусе pending по затронутой категории ФЭО."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id)
    w = await _make_wish_over_plan(
        db_session, test_org.id, test_admin_user.id, subsidy.id, cat.id, fpi.id,
    )

    resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    approvals = (await db_session.execute(
        select(PlanExcessApproval).where(PlanExcessApproval.feo_category_id == cat.id)
    )).scalars().all()
    assert approvals, "Запрос на согласование превышения ТЗ над плановой позицией не создан"
    assert any(a.status == "pending" for a in approvals), (
        f"Ожидался pending-запрос, получили статусы: {[a.status for a in approvals]}"
    )
    pending = next(a for a in approvals if a.status == "pending")
    assert pending.subsidy_id == subsidy.id
    assert float(pending.excess_amount) > 0


@pytest.mark.asyncio
async def test_c_further_movement_blocked_without_approval(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """(в) КЛЮЧЕВОЙ: пока превышение не согласовано, переход закупки «План
    закупок» -> «Ведётся работа» заблокирован 409."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id)
    w = await _make_wish_over_plan(
        db_session, test_org.id, test_admin_user.id, subsidy.id, cat.id, fpi.id,
    )

    resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    purchase_id = resp.json()["purchase_ids"][0]

    transition_resp = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert transition_resp.status_code == 409, (
        f"Движение закупки дальше «Плана закупок» ОБЯЗАНО быть заблокировано, пока "
        f"превышение ТЗ над плановой позицией не согласовано. Получили "
        f"{transition_resp.status_code}: {transition_resp.text}"
    )
    # Глобальный обработчик HTTPException (app/__init__.py::http_exception_handler)
    # разворачивает dict-detail в {"code","message","details","correlation_id"} —
    # не {"detail": ...}, как голый FastAPI по умолчанию.
    body = transition_resp.json()
    detail_text = body.get("message", "")
    assert "плановую позицию" in detail_text or "согласован" in detail_text.lower(), (
        f"Текст отказа должен объяснять причину (превышение ТЗ над плановой позицией), "
        f"получили: {body}"
    )
    assert body.get("code") == "TZ_EXCESS_OVER_PLANNED_ITEM_PENDING", body

    await db_session.refresh(await db_session.get(Purchase, purchase_id))
    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase.status == "plan_schedule", "Статус не должен был сдвинуться при 409"


@pytest.mark.asyncio
async def test_d_movement_allowed_after_approval(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """(г) После одобрения превышения уполномоченным движение закупки разрешено."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id)
    w = await _make_wish_over_plan(
        db_session, test_org.id, test_admin_user.id, subsidy.id, cat.id, fpi.id,
    )
    approver = await _make_plan_excess_approver(db_session, test_org, make_user)
    approver_headers = _headers_for(approver)

    resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    purchase_id = resp.json()["purchase_ids"][0]

    # Подтверждаем сначала, что БЕЗ решения движение действительно закрыто —
    # тот же гейт, что и в тесте (в), для полноты сценария "до/после".
    blocked = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert blocked.status_code == 409, blocked.text

    approval = (await db_session.execute(
        select(PlanExcessApproval).where(
            PlanExcessApproval.feo_category_id == cat.id,
            PlanExcessApproval.status == "pending",
        )
    )).scalar_one_or_none()
    assert approval is not None, "Запрос на согласование не найден"

    decide_resp = await client.post(
        f"/api/plan-excess/{approval.id}/decide",
        json={"decision": "approved"},
        headers=approver_headers,
    )
    assert decide_resp.status_code == 200, (
        f"Уполномоченный (право plan_excess.decide) обязан быть способен одобрить "
        f"запрос: {decide_resp.status_code} {decide_resp.text}"
    )
    assert decide_resp.json()["status"] == "approved"

    allowed = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=work_in_progress",
        headers=admin_headers,
    )
    assert allowed.status_code == 200, (
        f"После одобрения превышения движение закупки обязано быть разрешено: "
        f"{allowed.status_code} {allowed.text}"
    )
    purchase = await db_session.get(Purchase, purchase_id)
    assert purchase.status == "work_in_progress"


@pytest.mark.asyncio
async def test_e_no_approver_available_falls_back_to_hard_block_not_silent_pass(
    client, db_session, test_org, test_admin_user, admin_headers,
):
    """ГРАНИЦА задачи (владелец): «нельзя, чтобы превышение молча проходило».
    Если по организации НЕТ ни одного пользователя с правом
    'plan_excess.decide' — регистрация запроса невозможна (некому решать), и
    согласование заявки ОБЯЗАНО остаться жёстким отказом (409), а НЕ тихо
    пропустить превышение. Никакого approver в этом тесте не создаётся —
    ключевое отличие от теста (а)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id)
    w = await _make_wish_over_plan(
        db_session, test_org.id, test_admin_user.id, subsidy.id, cat.id, fpi.id,
    )

    resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)

    assert resp.status_code == 409, (
        f"Без единого уполномоченного согласовать превышение некому — заявка ОБЯЗАНА "
        f"получить отказ, а не пройти молча. Получили {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    # См. app/__init__.py::http_exception_handler — envelope {"code","message",...}.
    detail_text = body.get("message", "") if isinstance(body, dict) else str(body)
    assert "plan_excess.decide" in detail_text or "некому" in detail_text.lower(), body

    # Не проверяем здесь, что Purchase-строка, УСПЕВШАЯ flush()-нуться до
    # исключения, физически исчезла — попытка явного db_session.rollback() в
    # ЭТОМ тесте вызывает несвязанный конфликт гринлетов SQLAlchemy (общий
    # db_session, отдельный event loop httpx-ASGI-транспорта, см. docstring
    # модуля про флейк pytest-asyncio). В проде это неопасно: get_db() —
    # per-request AsyncSession, закрывается (close()) при выходе из
    # обработчика БЕЗ предшествующего commit() (approve_wish коммитит только
    # ПОСЛЕ успешного _distribute_wish_to_purchases, а тут дошло до исключения
    # раньше) — SQLAlchemy откатывает незакоммиченный flush() сам. Здесь
    # проверяем главное, требуемое границей задачи: превышение НЕ проходит
    # молча (409 выше), а не полную атомарность конкретно этого теста.
