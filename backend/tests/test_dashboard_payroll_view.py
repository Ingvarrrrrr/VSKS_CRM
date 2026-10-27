"""test_dashboard_payroll_view.py — переключатель карточек «Всё / Только
закупки / Только ФОТ» (?payroll_view=all|exclude|only, план владельца
23.10.2026, часть 1 — бэк).

ПРАВИЛО №6 — "exclude" НЕ вторая формула: тот же scrub_payroll_from_
dashboard_charts (app.services.payroll_visibility), что уже прячет ФОТ от
пользователя без права subsidy.view_payroll, просто с force_hide_all=True —
поэтому (а) ниже сверяет ответ managerа (exclude, право ЕСТЬ) буква-в-букву
с ответом пользователя без права (payroll_view=all по умолчанию).
"only" ничего не считает заново — лишь форсирует ту же разбивку по видам,
что ?type_split=true (budget_payroll/planned_payroll/*_by_kind уже покрыты
test_payroll_visibility.py и test_payroll_kind_cards.py, здесь — что они
появляются и без явного ?type_split=true).
"""
import uuid
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.permission import UserOrgPermissionOverride
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess
from tests.test_feo_plan_tree_scenarios import _make_planned_item


async def _make_subsidy(db_session, org_id):
    s = Subsidy(
        name=f"PayrollView-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, is_payroll=False, name=None, budget=None):
    cat = FeoCategory(
        subsidy_id=subsidy_id, level=1, parent_id=None, is_payroll=is_payroll, budget=budget,
        name=name or (f"ФОТ-{uuid.uuid4().hex[:6]}" if is_payroll else f"Товары-{uuid.uuid4().hex[:6]}"),
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_purchase(db_session, subsidy_id, category_id, amount: Decimal, item_type=None, name="Закупка"):
    p = Purchase(
        subsidy_id=subsidy_id, status="paid", item_name=f"{name}-{uuid.uuid4().hex[:6]}",
        feo_category_id=category_id,
        planned_total_price=amount, payment_amount_declared=amount,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Строка", item_type=item_type,
        quantity=Decimal("1"), unit_price=amount, total_price=amount,
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _manager_with_access(db_session, test_org, make_user, *, can_view_payroll=None):
    user = await make_user(role="manager", org_id=test_org.id)
    uoa = UserOrgAccess(user_id=user.id, org_id=test_org.id, role="manager")
    db_session.add(uoa)
    await db_session.commit()
    await db_session.refresh(uoa)
    for tab in ("subsidies", "dashboard", "purchases"):
        db_session.add(UserOrgPermissionOverride(user_org_access_id=uoa.id, key=tab, granted=True))
    if can_view_payroll is not None:
        db_session.add(UserOrgPermissionOverride(
            user_org_access_id=uoa.id, key="subsidy.view_payroll", granted=can_view_payroll,
        ))
    await db_session.commit()
    return user, uoa


def _headers(user):
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


def _find_subsidy_row(payload, subsidy_id):
    for row in payload["subsidy_stats"]:
        if row["id"] == subsidy_id:
            return row
    raise AssertionError(f"subsidy {subsidy_id} not found in subsidy_stats")


@pytest.mark.asyncio
class TestDashboardPayrollView:
    async def test_invalid_payroll_view_is_rejected(self, client, superadmin_headers):
        resp = await client.get(
            "/api/dashboard/charts",
            params={"scope": "dashboard", "payroll_view": "something_else"},
            headers=superadmin_headers,
        )
        # Query(regex=...) — та же конвенция, что scope/kind/metric в этом файле
        # (см. dashboard_contracts_drill.py и соседей) — FastAPI отвечает 422,
        # не вторая, своя проверка с другим кодом.
        assert resp.status_code == 422

    async def test_exclude_matches_user_without_right(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """(а) payroll_view=exclude у пользователя С правом «Видеть ФОТ» даёт
        ТЕ ЖЕ числа, что payroll_view=all (умолчание) у пользователя БЕЗ права —
        одна субсидия, закупка ФОТ + закупка товара."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True)
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False)
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП")
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        manager_with_right, _ = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=True)
        manager_without_right, _ = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_exclude = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "payroll_view": "exclude"},
            headers=_headers(manager_with_right),
        )
        resp_without_right = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"},
            headers=_headers(manager_without_right),
        )
        assert resp_exclude.status_code == 200 and resp_without_right.status_code == 200

        row_exclude = _find_subsidy_row(resp_exclude.json(), subsidy.id)
        row_plain = _find_subsidy_row(resp_without_right.json(), subsidy.id)

        assert row_exclude["paid_declared"] == pytest.approx(row_plain["paid_declared"], abs=0.01)
        assert row_exclude["paid_declared"] == pytest.approx(40000.0, abs=0.01)
        assert row_exclude["paid_declared_by_kind"]["payroll"] == pytest.approx(0.0, abs=0.01)
        assert row_exclude["widget"]["paid"]["amount"] == pytest.approx(row_plain["widget"]["paid"]["amount"], abs=0.01)

        # Без exclude (payroll_view=all, умолчание) тот же пользователь с
        # правом видит ФОТ целиком — убеждаемся, что exclude это реально
        # что-то меняло, а не совпало случайно.
        resp_all = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"},
            headers=_headers(manager_with_right),
        )
        row_all = _find_subsidy_row(resp_all.json(), subsidy.id)
        assert row_all["paid_declared_by_kind"]["payroll"] == pytest.approx(90000.0, abs=0.01)

    async def test_payroll_visible_flag(
        self, client, db_session, test_org, make_user,
    ):
        """(б) payroll_visible=true у пользователя с правом/на субсидии с ФОТ,
        false — у пользователя без права и у пользователя, где ФОТ-статей нет
        вовсе (нечего показывать переключателем)."""
        subsidy_payroll = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy_payroll.id, is_payroll=True)
        await _make_purchase(db_session, subsidy_payroll.id, payroll_cat.id, Decimal("10000"), name="ЗП")

        subsidy_no_payroll = await _make_subsidy(db_session, test_org.id)
        goods_cat = await _make_category(db_session, subsidy_no_payroll.id, is_payroll=False)
        await _make_purchase(db_session, subsidy_no_payroll.id, goods_cat.id, Decimal("5000"), item_type="товар")

        manager_with_right, _ = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=True)
        manager_without_right, _ = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_with = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager_with_right),
        )
        assert resp_with.json()["payroll_visible"] is True

        resp_without = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager_without_right),
        )
        assert resp_without.json()["payroll_visible"] is False

    async def test_only_forces_type_split_payload(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """(в) payroll_view=only отдаёт разбивку по видам (budget_payroll/
        planned_payroll/*_by_kind) даже без ?type_split=true — то же, что
        type_split=true возвращает без payroll_view."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True, budget=Decimal("90000"))
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False, budget=Decimal("40000"))
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП")
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        resp_only = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "payroll_view": "only"},
            headers=superadmin_headers,
        )
        resp_plain = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"},
            headers=superadmin_headers,
        )
        assert resp_only.status_code == 200 and resp_plain.status_code == 200
        row_only = _find_subsidy_row(resp_only.json(), subsidy.id)
        row_plain = _find_subsidy_row(resp_plain.json(), subsidy.id)

        # Без payroll_view — type_split-поля вовсе не считаются.
        assert "budget_payroll" not in row_plain

        # payroll_view=only — та же разбивка, что ?type_split=true дал бы.
        resp_type_split = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=superadmin_headers,
        )
        row_type_split = _find_subsidy_row(resp_type_split.json(), subsidy.id)
        assert row_only["budget_payroll"] == pytest.approx(row_type_split["budget_payroll"], abs=0.01)
        assert row_only["budget_payroll"] == pytest.approx(90000.0, abs=0.01)
        assert row_only["paid_declared_by_kind"]["payroll"] == pytest.approx(90000.0, abs=0.01)

    async def test_exclude_strips_planned_full(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """НАЙДЕНО владельцем 27.10.2026 (ДНР_Актуальная, payroll_view=exclude):
        карточка «Запланировано» = planned_full (Σ ВСЕХ плановых позиций, БЕЗ
        урезания до ФЭО, см. docstring subsidy_money_summary.py) раньше
        НЕ вычищалась в режиме «Только по закупкам» — ФОТ оставался внутри,
        хотя planned_tree/budget_payroll уже вычищались. planned_full —
        ОТДЕЛЬНОЕ поле (другой источник: full_display_<kind> vs plan_<kind>),
        его нужно вычищать своей payroll-долей (planned_full_payroll), а не
        подставлять урезанную planned_payroll."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = FeoCategory(
            subsidy_id=subsidy.id, level=1, parent_id=None, is_payroll=True,
            budget=Decimal("90000"), name=f"ФОТ-{uuid.uuid4().hex[:6]}",
        )
        goods_cat = FeoCategory(
            subsidy_id=subsidy.id, level=1, parent_id=None, is_payroll=False,
            budget=Decimal("40000"), name=f"Товары-{uuid.uuid4().hex[:6]}",
        )
        db_session.add_all([payroll_cat, goods_cat])
        await db_session.commit()
        await db_session.refresh(payroll_cat)
        await db_session.refresh(goods_cat)

        await _make_planned_item(db_session, payroll_cat.id, "ЗП — план на год", 1, 90_000)
        item_goods = await _make_planned_item(db_session, goods_cat.id, "Товар", 1, 40_000)
        item_goods.item_type = "товар"
        db_session.add(item_goods)
        await db_session.commit()

        manager_with_right, _ = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=True)

        # (а) без ?type_split=true — planned_full_payroll считается on-demand
        # (_on_demand_budget_planned_payroll), ключ в ответе не появляется
        # (та же конвенция, что и у budget_payroll, см. test_only_forces_
        # type_split_payload выше), но planned_full всё равно без ФОТ.
        resp_exclude = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "payroll_view": "exclude"},
            headers=_headers(manager_with_right),
        )
        assert resp_exclude.status_code == 200
        row_exclude = _find_subsidy_row(resp_exclude.json(), subsidy.id)
        assert "planned_full_payroll" not in row_exclude
        assert row_exclude["planned_full"] == pytest.approx(40000.0, abs=0.01)

        # (б) с ?type_split=true — planned_full_payroll обнулён явно, и
        # planned_full по-прежнему без ФОТ.
        resp_exclude_split = await client.get(
            "/api/dashboard/charts",
            params={"scope": "dashboard", "payroll_view": "exclude", "type_split": "true"},
            headers=_headers(manager_with_right),
        )
        row_exclude_split = _find_subsidy_row(resp_exclude_split.json(), subsidy.id)
        assert row_exclude_split["planned_full"] == pytest.approx(40000.0, abs=0.01)
        assert row_exclude_split["planned_full_payroll"] == pytest.approx(0.0, abs=0.01)
        assert row_exclude_split["planned_full_goods"] == pytest.approx(40000.0, abs=0.01)

        # (в) без exclude (payroll_view=all, умолчание) — то же дерево даёт
        # planned_full ПОЛНЫМ (130000 = 90000 ФОТ + 40000 товар), убеждаемся,
        # что exclude реально что-то меняло.
        resp_all_split = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard", "type_split": "true"},
            headers=_headers(manager_with_right),
        )
        row_all_split = _find_subsidy_row(resp_all_split.json(), subsidy.id)
        assert row_all_split["planned_full"] == pytest.approx(130000.0, abs=0.01)
        assert row_all_split["planned_full_payroll"] == pytest.approx(90000.0, abs=0.01)
