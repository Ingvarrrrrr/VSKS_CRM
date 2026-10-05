"""«Где взять деньги» при превышении плана (владелец, план
.planning/quick/2026-10-05-funding-sources/PLAN.md + доп. контракт 05.10.2026
«фронт уже написан, два места не подключились»: цель = субсидия целиком, и
заголовок X-Funding-Hint на жёстком 409 «ТЗ/договор над плановой позицией»).

Фабрики субсидии/категории/плановой позиции переиспользуются из
tests/test_feo_plan_tree_scenarios.py и tests/test_money_committed.py
(ПРАВИЛО №6 — вторая копия тестовых фабрик не заводится). Сценарий
«заявка → согласование → закупка → блокировка движения» скопирован по образцу
tests/test_tz_over_plan_goes_to_approval.py (та же причина флейка: async-тесты
этого стиля гоняются по ОДНОМУ, см. её докстринг — здесь то же самое).
"""
import json
import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.entity_change import EntityChange
from app.models.feo_planned_item import FeoPlannedItem
from app.models.plan_excess_approval import PlanExcessApproval
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.auth.jwt import create_access_token
from app.services import plan_funding_sources as svc
from app.services.feo_plan_tz_checks import assert_tz_not_over_plan
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy
from tests.test_money_committed import _make_linked_purchase


async def _make_subsidy_org(db_session, org_id, budget=10_000_000):
    """Та же сущность, что _make_subsidy, но с реальным org_id — нужна ТОЛЬКО
    тесту гейта утверждённой субсидии (assert_direct_edit читает
    Subsidy.org_id). Остальные тесты файла используют org-свободный
    _make_subsidy (см. docstring модуля)."""
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"Funding-Subsidy-{uuid.uuid4().hex[:8]}", year=2026, budget=budget,
        org_id=org_id, require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _headers_for(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_group_order_and_cumulative_suggested_take(db_session, test_org):
    """Порядок групп: nice_to_have ПЕРЕД likely; «взять» нарастающим итогом
    через ОБЕ группы, cumulative_after растёт монотонно."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    nice = await _make_planned_item(db_session, cat.id, "Хотелось бы", 1, 5000)
    nice.need_level = "nice_to_have"
    likely = await _make_planned_item(db_session, cat.id, "Понадобится", 1, 3000)
    likely.need_level = "likely"
    await db_session.commit()

    result = await svc.find_funding_sources(db_session, subsidy.id, category_id=cat.id, amount=6000)

    assert [g["need_level"] for g in result["groups"]] == ["nice_to_have", "likely"]
    nice_items = result["groups"][0]["items"]
    likely_items = result["groups"][1]["items"]
    assert [it["planned_item_id"] for it in nice_items] == [nice.id]
    assert [it["planned_item_id"] for it in likely_items] == [likely.id]

    assert nice_items[0]["suggested_take"] == pytest.approx(5000.0)
    assert nice_items[0]["cumulative_after"] == pytest.approx(5000.0)
    assert likely_items[0]["suggested_take"] == pytest.approx(1000.0)
    assert likely_items[0]["cumulative_after"] == pytest.approx(6000.0)
    assert result["covered_amount"] == pytest.approx(6000.0)
    assert result["need_amount"] == pytest.approx(6000.0)
    assert result["target"]["kind"] == "category"
    assert result["target"]["id"] == cat.id


@pytest.mark.asyncio
async def test_scope_branch_when_ancestor_has_budget(db_session, test_org):
    """Область поиска — поддерево БЛИЖАЙШЕГО предка (или самого узла) с
    заданной суммой ФЭО (node['budget'] is not None)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id, budget=Decimal("50000"))
    leaf = await _make_category(db_session, subsidy.id, parent_id=root.id)

    result = await svc.find_funding_sources(db_session, subsidy.id, category_id=leaf.id, amount=1000)

    assert result["scope"]["kind"] == "branch"
    assert result["scope"]["category_id"] == root.id


@pytest.mark.asyncio
async def test_scope_subsidy_when_no_ancestor_has_budget(db_session, test_org):
    """Нет ни у узла, ни у предков суммы ФЭО — область поиска вся субсидия."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    root = await _make_category(db_session, subsidy.id)  # budget не задан
    leaf = await _make_category(db_session, subsidy.id, parent_id=root.id)

    result = await svc.find_funding_sources(db_session, subsidy.id, category_id=leaf.id, amount=1000)

    assert result["scope"]["kind"] == "subsidy"
    assert result["scope"]["category_id"] is None


@pytest.mark.asyncio
async def test_funding_sources_subsidy_wide_target(db_session, test_org, monkeypatch):
    """Доп. контракт владельца 05.10.2026: GET /funding-sources БЕЗ
    category_id И БЕЗ planned_item_id -> target.kind='subsidy', excess_amount =
    превышение плана субсидии над бюджетом (= «Можно перераспределить» в
    минусе, app.services.subsidy_money_summary.subsidy_money_summary,
    ПРАВИЛО №6 — переиспользуется как есть, не считается заново здесь).
    Подменяем subsidy_money_summary, т.к. воспроизводить реальный перебор
    бюджета субсидии через полное дерево ФЭО не нужно для этой проверки —
    достаточно убедиться, что _resolve_target читает redistributable ровно
    ОТТУДА и переворачивает знак."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id, "Остаток", 1, 4000)

    async def _fake_summary(db, subsidy_ids):
        return {sid: {"redistributable": -2500.0} for sid in subsidy_ids}

    monkeypatch.setattr(
        "app.services.subsidy_money_summary.subsidy_money_summary", _fake_summary,
    )

    result = await svc.find_funding_sources(db_session, subsidy.id)

    assert result["target"]["kind"] == "subsidy"
    assert result["target"]["id"] == subsidy.id
    assert result["target"]["excess_amount"] == pytest.approx(2500.0)
    assert result["scope"]["kind"] == "subsidy"
    assert result["need_amount"] == pytest.approx(2500.0)
    # Позиция всё ещё попадает в кандидаты (субсидия целиком — вся база).
    all_ids = [it["planned_item_id"] for g in result["groups"] for it in g["items"]]
    assert item.id in all_ids


@pytest.mark.asyncio
async def test_reduce_not_below_committed(db_session, test_org, test_admin_user):
    """Уменьшение не ниже уже законтрактованного — 422 с причиной; ровно до
    законтрактованного — проходит."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id, "С договором", 1, 10000)
    await _make_linked_purchase(
        db_session, subsidy.id, cat.id, item.id, quantity=1, contract_price=4000, status="contracted",
    )

    with pytest.raises(Exception) as exc_info:
        await svc.reduce_planned_item_amount(db_session, test_admin_user, item, Decimal("8000"))
    detail = exc_info.value.detail
    assert isinstance(detail, dict) and detail.get("code") == "PLANNED_ITEM_REDUCE_BELOW_COMMITTED"
    assert detail["committed"] == pytest.approx(4000.0)

    await db_session.refresh(item)
    assert float(item.amount) == pytest.approx(10000.0), "Отказ не должен был менять сумму"

    result = await svc.reduce_planned_item_amount(db_session, test_admin_user, item, Decimal("5000"))
    assert result["ok"] is True
    assert result["item"]["amount"] == pytest.approx(5000.0)
    await db_session.refresh(item)
    assert float(item.amount) == pytest.approx(5000.0)


@pytest.mark.asyncio
async def test_reduce_transfer_clears_tz_excess_over_position(db_session, test_org, test_admin_user):
    """Перенос в целевую позицию снимает «ТЗ/договор над плановой позицией»:
    target — план 2 шт × ед, законтрактовано 1 шт на 15 000 (больше плана
    10 000) -> перенос 5000 с другой позиции закрывает превышение целиком."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat_target = await _make_category(db_session, subsidy.id)
    target = await _make_planned_item(db_session, cat_target.id, "Цель (превышена)", 2, 10000)
    await _make_linked_purchase(
        db_session, subsidy.id, cat_target.id, target.id, quantity=1, contract_price=15000, status="contracted",
    )

    cat_source = await _make_category(db_session, subsidy.id)
    source = await _make_planned_item(db_session, cat_source.id, "Источник (остаток)", 1, 6000)

    excess_before = await svc._planned_item_excess(db_session, target)
    assert excess_before == pytest.approx(5000.0), "Контрольная сумма сценария (15000-10000)"

    result = await svc.reduce_planned_item_amount(
        db_session, test_admin_user, source, Decimal("5000"), target_planned_item_id=target.id,
    )
    assert result["ok"] is True
    assert result["target_remaining_excess"] == pytest.approx(0.0)

    await db_session.refresh(source)
    await db_session.refresh(target)
    assert float(source.amount) == pytest.approx(1000.0)
    assert float(target.amount) == pytest.approx(15000.0)
    excess_after = await svc._planned_item_excess(db_session, target)
    assert excess_after == pytest.approx(0.0)

    # История ФЭО — записана у ОБЕИХ позиций (поле 'redistribution').
    changes = (await db_session.execute(
        select(EntityChange).where(
            EntityChange.entity_type == "feo_item",
            EntityChange.entity_id.in_([source.id, target.id]),
            EntityChange.field_name == "redistribution",
        )
    )).scalars().all()
    by_entity = {c.entity_id for c in changes}
    assert source.id in by_entity and target.id in by_entity
    source_note = next(c for c in changes if c.entity_id == source.id)
    target_note = next(c for c in changes if c.entity_id == target.id)
    assert "перераспределение" in source_note.new_value
    assert "за счёт" in target_note.new_value


@pytest.mark.asyncio
async def test_reduce_denied_for_approved_subsidy_without_right(db_session, test_org, make_user, monkeypatch):
    """Утверждённая субсидия: пользователь без subsidy.edit/subsidy.correct
    не может уменьшить плановую позицию напрямую (assert_direct_edit)."""
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")
    subsidy = await _make_subsidy_org(db_session, test_org.id)
    subsidy.status = "approved"
    await db_session.commit()
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id, "Позиция утверждённой субсидии", 1, 5000)

    plain_user = await make_user(role="employee", org_id=test_org.id)

    with pytest.raises(Exception) as exc_info:
        await svc.reduce_planned_item_amount(db_session, plain_user, item, Decimal("1000"))
    assert exc_info.value.status_code in (403, 409)


@pytest.mark.asyncio
async def test_purchase_funding_hint_tz_excess(db_session, test_org):
    """GET /purchases/{id}/funding-hint — по закупке с ТЗ выше плановой
    позиции отдаёт planned_item_id/category_id/amount (сухая проверка, без
    записи в БД)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id, "ТЗ выше плана", 1, 10000)

    purchase = Purchase(
        subsidy_id=subsidy.id, feo_category_id=cat.id, item_name="ТЗ выше плана",
        status="plan_schedule", total_nmck=Decimal("15000"), nmck=Decimal("15000"),
    )
    db_session.add(purchase)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=purchase.id, item_name="ТЗ выше плана", quantity=Decimal("1"), unit="шт",
        unit_price=Decimal("15000"), total_price=Decimal("15000"),
        feo_category_id=cat.id, feo_planned_item_id=item.id, over_plan=False,
    )
    db_session.add(pi)
    await db_session.commit()
    await db_session.refresh(purchase)

    hint = await svc.purchase_funding_hint(db_session, purchase.id)
    assert hint is not None
    assert hint["planned_item_id"] == item.id
    assert hint["category_id"] == cat.id
    assert hint["amount"] == pytest.approx(5000.0)


@pytest.mark.asyncio
async def test_funding_hint_header_on_direct_tz_check(db_session, test_org):
    """assert_tz_not_over_plan (feo_plan_tz_checks.py) — 409 несёт заголовок
    X-Funding-Hint с суммой ПРЕВЫШЕНИЯ (не самой суммой ТЗ)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id, planned_quantity=Decimal("1"), planned_amount=Decimal("1000"))

    with pytest.raises(Exception) as exc_info:
        await assert_tz_not_over_plan(
            db_session, feo_planned_item_id=None, feo_category_id=cat.id,
            quantity=Decimal("1"), unit_price=Decimal("1500"), total_price=Decimal("1500"),
            item_name="Позиция сверх плана",
        )
    headers = exc_info.value.headers or {}
    assert "X-Funding-Hint" in headers
    payload = json.loads(headers["X-Funding-Hint"])
    assert payload["planned_item_id"] is None
    assert payload["category_id"] == cat.id
    assert payload["amount"] == pytest.approx(500.0)


async def _make_plan_excess_approver(db_session, test_org, make_user):
    """Копия хелпера test_tz_over_plan_goes_to_approval.py (ПРАВИЛО №6 — тот
    же приём: право 'plan_excess.decide' выдаётся точечным оверрайдом)."""
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


@pytest.mark.asyncio
async def test_funding_hint_header_propagates_through_http(
    client, db_session, test_org, test_admin_user, admin_headers, make_user,
):
    """X-Funding-Hint на РЕАЛЬНОМ HTTP-409 assert_no_pending_tz_excess (через
    app/errors.py::http_exception_handler — до правки заголовки
    HTTPException.headers терялись молча, т.к. JSONResponse строился без
    headers=exc.headers)."""
    await _make_plan_excess_approver(db_session, test_org, make_user)
    subsidy = await _make_subsidy_org(db_session, test_org.id)
    cat = await _make_category(db_session, subsidy.id)
    fpi = await _make_planned_item(db_session, cat.id, "Логистические услуги", 1, Decimal("11270.19"))

    w = Wish(
        org_id=test_org.id, title="Логистика (тест funding-hint)", status="submitted",
        created_by=test_admin_user.id, subsidy_id=subsidy.id, feo_category_id=cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    wi = WishItem(
        wish_id=w.id, item_name="Логистические услуги", quantity=Decimal("1"), unit="усл",
        unit_price=Decimal("48935.05"), total_price=Decimal("48935.05"),
        feo_category_id=cat.id, feo_planned_item_id=fpi.id, over_plan=False,
    )
    db_session.add(wi)
    await db_session.commit()

    approve_resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)
    assert approve_resp.status_code == 200, approve_resp.text
    purchase_id = approve_resp.json()["purchase_ids"][0]

    resp = await client.post(
        f"/api/purchases/{purchase_id}/transition?status=work_in_progress", headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text
    hint_header = resp.headers.get("x-funding-hint") or resp.headers.get("X-Funding-Hint")
    assert hint_header, f"Заголовок X-Funding-Hint отсутствует: {dict(resp.headers)}"
    payload = json.loads(hint_header)
    assert payload["planned_item_id"] == fpi.id
    assert payload["category_id"] == cat.id
    assert payload["amount"] == pytest.approx(float(Decimal("48935.05") - Decimal("11270.19")))
