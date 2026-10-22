"""test_payroll_visibility.py — право «Видеть ФОТ» (subsidy.view_payroll,
план владельца 21.10.2026): пользователь БЕЗ права не видит суммы/закупки
ФОТ ни на карточках дашборда, ни в реестре закупок, ни по прямому id;
account_owner/superadmin и пользователь С индивидуальным override — видят.

ПРАВИЛО №6 — проверка видимости везде ОДНА (app.services.payroll_visibility),
этот тест бьёт по трём потребителям: GET /api/dashboard/charts (часть 2),
GET /api/purchases/ + GET /api/purchases/{id} (часть 3)."""
import uuid
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.permission import UserOrgPermissionOverride
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user_org_access import UserOrgAccess


async def _make_subsidy(db_session, org_id):
    s = Subsidy(
        name=f"PayrollVis-{uuid.uuid4().hex[:8]}", year=2026, org_id=org_id,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, is_payroll=False, name=None, budget=None, parent_id=None, level=1):
    cat = FeoCategory(
        subsidy_id=subsidy_id, level=level, parent_id=parent_id, is_payroll=is_payroll, budget=budget,
        name=name or (f"ФОТ-{uuid.uuid4().hex[:6]}" if is_payroll else f"Товары-{uuid.uuid4().hex[:6]}"),
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_purchase(db_session, subsidy_id, category_id, amount: Decimal, item_type=None, name="Закупка",
                          assigned_user_id=None):
    p = Purchase(
        subsidy_id=subsidy_id, status="paid", item_name=f"{name}-{uuid.uuid4().hex[:6]}",
        feo_category_id=category_id, assigned_user_id=assigned_user_id,
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
    """Manager с доступом к test_org (subsidies/dashboard/purchases — иначе
    видимость субсидии сама по себе блокирует тест раньше права ФОТ) и,
    опционально, персональным override subsidy.view_payroll."""
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
class TestPayrollVisibility:
    async def test_manager_without_right_sees_no_payroll_on_charts(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True)
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False)
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП")
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_manager = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager),
        )
        assert resp_manager.status_code == 200
        row = _find_subsidy_row(resp_manager.json(), subsidy.id)
        assert row["paid_declared"] == pytest.approx(40000.0, abs=0.01)
        assert row["paid_declared_by_kind"]["payroll"] == pytest.approx(0.0, abs=0.01)

        resp_super = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row_super = _find_subsidy_row(resp_super.json(), subsidy.id)
        assert row_super["paid_declared"] == pytest.approx(130000.0, abs=0.01)
        assert row_super["paid_declared_by_kind"]["payroll"] == pytest.approx(90000.0, abs=0.01)

    async def test_manager_with_override_sees_payroll(
        self, client, db_session, test_org, make_user,
    ):
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True)
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("50000"), name="ЗП")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=True)

        resp = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager),
        )
        row = _find_subsidy_row(resp.json(), subsidy.id)
        assert row["paid_declared_by_kind"]["payroll"] == pytest.approx(50000.0, abs=0.01)

    async def test_purchase_list_hides_payroll_purchase_without_right(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True)
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False)
        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)
        # assigned_user_id=manager — иначе видимость отвалится по общей причине
        # (нет назначения/оргвидимости), тест должен проверять ИМЕННО правило
        # ФОТ, а не случайную невидимость закупки вообще.
        payroll_purchase = await _make_purchase(
            db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП", assigned_user_id=manager.id,
        )
        goods_purchase = await _make_purchase(
            db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар",
            assigned_user_id=manager.id,
        )

        resp_manager = await client.get(
            "/api/purchases/", params={"subsidy_id": subsidy.id, "scope": "purchases"}, headers=_headers(manager),
        )
        assert resp_manager.status_code == 200
        ids_manager = {row["id"] for row in resp_manager.json()}
        assert payroll_purchase.id not in ids_manager
        assert goods_purchase.id in ids_manager

        resp_super = await client.get(
            "/api/purchases/", params={"subsidy_id": subsidy.id, "scope": "purchases"}, headers=superadmin_headers,
        )
        ids_super = {row["id"] for row in resp_super.json()}
        assert payroll_purchase.id in ids_super
        assert goods_purchase.id in ids_super

    async def test_get_payroll_purchase_by_id_is_404_without_right(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True)
        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)
        payroll_purchase = await _make_purchase(
            db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП", assigned_user_id=manager.id,
        )

        resp_manager = await client.get(f"/api/purchases/{payroll_purchase.id}", headers=_headers(manager))
        assert resp_manager.status_code == 404

        resp_super = await client.get(f"/api/purchases/{payroll_purchase.id}", headers=superadmin_headers)
        assert resp_super.status_code == 200

    async def test_charts_without_type_split_scrubs_stage_widgets_and_budget(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """Координатор, 21.10.2026, часть 2: БЕЗ ?type_split=true — widget[stage]
        ["amount"] (здесь "paid") и feo_budget_total обязаны быть вычищены от
        ФОТ так же, как by_kind-поля (уже покрыто другим тестом выше)."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True, budget=Decimal("90000"))
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False)
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП")
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_manager = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager),
        )
        resp_super = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row_m = _find_subsidy_row(resp_manager.json(), subsidy.id)
        row_s = _find_subsidy_row(resp_super.json(), subsidy.id)

        # Стадия "paid" (status='paid' обеих закупок) — без ФОТ у manager.
        assert row_m["widget"]["paid"]["amount"] == pytest.approx(40000.0, abs=0.01)
        assert row_s["widget"]["paid"]["amount"] == pytest.approx(130000.0, abs=0.01)
        # "*_payroll" ключ НЕ появляется в ответе без ?type_split=true (контракт
        # не меняется для клиентов, которые его не просили).
        assert "paid_payroll" not in row_m["widget"]["paid"]
        # Бюджет ФЭО — категория с собственным budget=90000 (ФОТ) входит в
        # корневой узел дерева; у manager он должен быть меньше, чем у superadmin,
        # ровно на эту сумму (если feo_entered — дерево построено).
        if row_s.get("feo_budget_total") is not None and row_m.get("feo_budget_total") is not None:
            assert row_s["feo_budget_total"] - row_m["feo_budget_total"] == pytest.approx(90000.0, abs=0.01)

    async def test_metric_drill_hides_payroll_rows(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """Часть 2/3: /dashboard/metric-drill?metric=paid_declared — строка
        закупки ФОТ убирается из rows, total уменьшается на её сумму."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True)
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False)
        payroll_purchase = await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП")
        goods_purchase = await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp = await client.get(
            "/api/dashboard/metric-drill",
            params={"metric": "paid_declared", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=_headers(manager),
        )
        assert resp.status_code == 200
        data = resp.json()
        pids = {r.get("purchase_id") for r in data["rows"]}
        assert payroll_purchase.id not in pids
        assert goods_purchase.id in pids
        assert data["total"] == pytest.approx(40000.0, abs=0.01)

        resp_super = await client.get(
            "/api/dashboard/metric-drill",
            params={"metric": "paid_declared", "scope": "dashboard", "subsidy_ids": str(subsidy.id)},
            headers=superadmin_headers,
        )
        data_super = resp_super.json()
        assert payroll_purchase.id in {r.get("purchase_id") for r in data_super["rows"]}
        assert data_super["total"] == pytest.approx(130000.0, abs=0.01)

    async def test_feo_categories_list_and_tree_hide_payroll(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """Часть 4: GET /feo-categories/ и /feo-categories/tree не отдают статью
        ФОТ (и её поддерево) без права."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True, name="ФОТ родитель")
        payroll_child = await _make_category(
            db_session, subsidy.id, is_payroll=False, name="ФОТ потомок",
            parent_id=payroll_cat.id, level=2,
        )
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False, name="Товары")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_list = await client.get(
            "/api/feo-categories/", params={"subsidy_id": subsidy.id}, headers=_headers(manager),
        )
        assert resp_list.status_code == 200
        ids_list = {c["id"] for c in resp_list.json()}
        assert payroll_cat.id not in ids_list
        assert payroll_child.id not in ids_list
        assert goods_cat.id in ids_list

        resp_tree = await client.get(
            "/api/feo-categories/tree", params={"subsidy_id": subsidy.id}, headers=_headers(manager),
        )
        assert resp_tree.status_code == 200

        def _collect_ids(nodes):
            out = set()
            for n in nodes:
                out.add(n["id"])
                out |= _collect_ids(n.get("children") or [])
            return out

        tree_ids = _collect_ids(resp_tree.json())
        assert payroll_cat.id not in tree_ids
        assert payroll_child.id not in tree_ids
        assert goods_cat.id in tree_ids

        resp_list_super = await client.get(
            "/api/feo-categories/", params={"subsidy_id": subsidy.id}, headers=superadmin_headers,
        )
        ids_list_super = {c["id"] for c in resp_list_super.json()}
        assert payroll_cat.id in ids_list_super
        assert payroll_child.id in ids_list_super

    async def test_charts_scrubs_contracts_widget_and_calculated_budget_planned_tree(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """Находки живой приёмки 21.10.2026 (ДНР id 61/ХРО_2026 id 55):
        D1 — widget["contracts"]["amount"] («Заключено договоров») не входил
        в список стадий, которые чистит payroll_visibility (единственная
        стадия, пропущенная локальным _STAGE_KEYS) — у manager он оставался
        владельческим числом целиком. D3/D6 — "calculated_budget" и
        "planned_tree" — те же величины, что "feo_budget_total"/
        "total_feo_planned" (dashboard_charts.py кладёт budget_basis/
        planned_tree в оба поля отдельными строками), но чистились только
        вторые — фронт (useFeoTreeAmounts.selectedBudget читает
        calculated_budget ПЕРВЫМ; SubsidiesView.vue: `planned: s.planned_tree
        ?? s.total_planned`) показывал невычищенные суммы."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True, budget=Decimal("90000"))
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False, budget=Decimal("40000"))
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="ЗП")
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_m = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager),
        )
        resp_s = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row_m = _find_subsidy_row(resp_m.json(), subsidy.id)
        row_s = _find_subsidy_row(resp_s.json(), subsidy.id)

        # D1 — «Заключено договоров» (обе закупки status='paid' — накопительно
        # входят в "contracted") без ФОТ у manager, с ФОТ у superadmin.
        assert row_m["widget"]["contracts"]["amount"] == pytest.approx(40000.0, abs=0.01)
        assert row_s["widget"]["contracts"]["amount"] == pytest.approx(130000.0, abs=0.01)
        assert "contracts_payroll" not in row_m["widget"]["contracts"]

        # D3 — "calculated_budget" синхронен с "feo_budget_total" (одно и то же
        # число по построению dashboard_charts.py) и вычищен от ФОТ-бюджета.
        assert row_m["calculated_budget"] == pytest.approx(row_m["feo_budget_total"], abs=0.01)
        assert row_m["calculated_budget"] == pytest.approx(row_s["calculated_budget"] - 90000.0, abs=0.01)
        # D6 — "planned_tree" («план дерева ФЭО», источник «Запланировано» для
        # сводной таблицы субсидий — SubsidiesView.vue: `s.planned_tree ?? ...`)
        # — закрытая ФОТ-закупка без своей плановой позиции учитывается деревом
        # через «пол плана» (plan_floor_added, см. feo_plan_tree.py), поэтому
        # у superadmin planned_tree = 130000 (обе закупки), а у manager он
        # обязан быть МЕНЬШЕ ровно на payroll-часть (90000) — раньше оставался
        # невычищенным (= 130000 у обоих), поэтому «Запланировано»/«Свободно» в
        # сводной таблице у сотрудника были с ФОТ внутри.
        if row_m.get("planned_tree") is not None and row_s.get("planned_tree") is not None:
            assert row_s["planned_tree"] - row_m["planned_tree"] == pytest.approx(90000.0, abs=0.01)

        # D4 — «Свободно» (бюджет − план, формула фронта и бэка одна и та же)
        # обязана совпасть у manager, когда считается ИЗ ВЫЧИЩЕННЫХ budget_basis/
        # planned_tree — то, что фронт делает сам (useFeoTreeAmounts.freeDiffRounded).
        if row_m.get("remaining") is not None and row_m.get("planned_tree") is not None:
            assert row_m["remaining"] == pytest.approx(
                row_m["calculated_budget"] - row_m["planned_tree"], abs=0.01,
            )

    async def test_balance_scrubbed_for_payroll_budget_without_payroll_purchases(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """D5 (живая приёмка 21.10.2026, ДНР id 61): субсидия со статьёй ФОТ
        (бюджет введён), но БЕЗ единой оплаченной закупки ФОТ — раньше
        balance_by_marks/balance_by_statement («Остаток субсидии») у manager
        оставались НЕВЫЧИЩЕННЫМИ (payroll_visibility пропускал всю строку,
        когда у субсидии не было payroll-ОПЛАТ, хотя payroll-БЮДЖЕТ есть)."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        await _make_category(db_session, subsidy.id, is_payroll=True, budget=Decimal("90000"))
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False, budget=Decimal("40000"))
        # Единственная оплаченная закупка — товар, НЕ ФОТ (ФОТ-статья без закупок).
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("10000"), item_type="товар", name="Товар")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_m = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager),
        )
        resp_s = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row_m = _find_subsidy_row(resp_m.json(), subsidy.id)
        row_s = _find_subsidy_row(resp_s.json(), subsidy.id)

        if row_s.get("balance_by_marks") is not None and row_m.get("balance_by_marks") is not None:
            assert row_s["balance_by_marks"] - row_m["balance_by_marks"] == pytest.approx(90000.0, abs=0.01)
        if row_s.get("balance_by_statement") is not None and row_m.get("balance_by_statement") is not None:
            assert row_s["balance_by_statement"] - row_m["balance_by_statement"] == pytest.approx(90000.0, abs=0.01)

    async def test_redistributable_by_kind_puts_free_budget_under_payroll(
        self, db_session, test_org,
    ):
        """Находка владельца 21.10.2026 (ХРО_2026): непланированный остаток
        бюджета статьи ФОТ («Свободно» → «ФОТ: свободно») раньше лумился в
        «без типа» карточки «Можно перераспределить» — см. правку
        backend/app/services/subsidy_money_summary.py. ФОТ-категория с
        budget=90000 и без плановых позиций (plan_payroll=0) → весь remainder
        должен попасть в redistributable_by_kind.payroll, НЕ unspecified."""
        from app.services.subsidy_money_summary import subsidy_money_summary

        subsidy = await _make_subsidy(db_session, test_org.id)
        await _make_category(db_session, subsidy.id, is_payroll=True, budget=Decimal("90000"))
        await _make_category(db_session, subsidy.id, is_payroll=False, budget=Decimal("40000"))

        result = await subsidy_money_summary(db_session, [subsidy.id])
        row = result[subsidy.id]
        by_kind = row["redistributable_by_kind"]
        assert by_kind is not None
        # Остаток бюджета статьи ФОТ — под «payroll», не задвоен и не ушёл
        # целиком в «без типа» (budget второй категории, 40000, сама не
        # помечена payroll — она и должна остаться «без типа», это НЕ её
        # бюджет мы проверяем, а то, что 90000 ФОТ его туда не утащили).
        assert by_kind["payroll"] == pytest.approx(90000.0, abs=0.01)
        assert by_kind["unspecified"] == pytest.approx(40000.0, abs=0.01)
        assert by_kind["payroll"] + by_kind["unspecified"] == pytest.approx(row["redistributable_unplanned"], abs=0.01)

    async def test_plan_tree_without_right_subtracts_payroll_from_ancestors(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """Часть 3 (владелец 21.10.2026): узлы ФОТ убраны из ответа ЦЕЛИКОМ
        (уже было), но итоги ПРЕДКОВ/корня обязаны уменьшиться на их вклад —
        раньше оставались «с ФОТ внутри», хотя сами ФОТ-строки не отдавались
        (Σ видимых строк расходилась с итогом дерева)."""
        subsidy = await _make_subsidy(db_session, test_org.id)
        root = await _make_category(db_session, subsidy.id, is_payroll=False, name="Направление", level=1)
        goods_child = await _make_category(
            db_session, subsidy.id, is_payroll=False, name="Товары", parent_id=root.id, level=2,
        )
        payroll_child = await _make_category(
            db_session, subsidy.id, is_payroll=True, name="ФОТ", parent_id=root.id, level=2,
        )
        from app.models.feo_category import FeoCategory as _FC
        for cat, amt in ((goods_child, Decimal("40000")), (payroll_child, Decimal("90000"))):
            await db_session.execute(
                _FC.__table__.update().where(_FC.id == cat.id).values(
                    plan_source="manual_sum", manual_plan_amount=amt,
                )
            )
        await db_session.commit()

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_manager = await client.get(
            "/api/feo-categories/plan-tree", params={"subsidy_id": subsidy.id}, headers=_headers(manager),
        )
        resp_super = await client.get(
            "/api/feo-categories/plan-tree", params={"subsidy_id": subsidy.id}, headers=superadmin_headers,
        )
        assert resp_manager.status_code == 200 and resp_super.status_code == 200
        data_m = resp_manager.json()
        data_s = resp_super.json()

        assert str(payroll_child.id) not in data_m and payroll_child.id not in data_m
        root_m = data_m[str(root.id)]
        root_s = data_s[str(root.id)]
        payroll_s = data_s[str(payroll_child.id)]
        # Итог предка без права == итог предка с правом минус вклад скрытой
        # ветки ФОТ (не второй источник числа — прямая сверка с тем, что
        # superadmin реально видит у скрытого узла).
        assert root_m["display"] == pytest.approx(root_s["display"] - payroll_s["display"], abs=0.01)
        assert root_m["plan"] == pytest.approx(root_s["plan"] - payroll_s["plan"], abs=0.01)
        # subsidy_type_totals.*_payroll зануляется целиком без права (манер
        # manual_sum-категории в этом фикстурном дереве не несёт payroll-
        # классификацию без линкованной FeoPlannedItem — это свойство
        # compute_subsidy_type_summary/kind_of, не предмет этой правки;
        # здесь достаточно проверить, что зануление не падает и не портит
        # остальные виды).
        assert data_m["subsidy_type_totals"]["plan_payroll"] == pytest.approx(0.0, abs=0.01)
        assert data_m["subsidy_type_totals"]["plan_goods"] == pytest.approx(data_s["subsidy_type_totals"]["plan_goods"], abs=0.01)

    async def test_redistributable_substrings_scrub_payroll_without_right(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """D7 (живая приёмка 21.10.2026, ДНР id 61): подстроки карточки «Можно
        перераспределить» (not_committed_nice/likely, redistributable_unplanned,
        monthly_future_not_started) обязаны вычищаться от ФОТ у пользователя
        без права ТОЧНО НА ТУ ЖЕ сумму, что уже вычтена из redistributable_by_
        kind['payroll'] (итог карточки) — находка владельца: «не запланировано»/
        «скорее всего понадобится» у ДНР не совпадали со «Свободно»/
        «Запланировано» без ФОТ (payroll_visibility.py не трогал эти 4 поля
        вовсе)."""
        from app.models.feo_planned_item import FeoPlannedItem

        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True, budget=Decimal("90000"))
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False, budget=Decimal("40000"))
        # Плановая позиция ФОТ 50000 (nice_to_have, без закупок) — бюджет
        # статьи 90000 оставляет 40000 payroll-«свободно» (redistributable_
        # unplanned) + 50000 payroll-«хотелось бы» (not_committed_nice).
        db_session.add(FeoPlannedItem(
            feo_category_id=payroll_cat.id, name="Резерв ФОТ", quantity=Decimal("1"),
            amount=Decimal("50000"), need_level="nice_to_have", is_active=True,
        ))
        await db_session.commit()

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp_m = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=_headers(manager),
        )
        resp_s = await client.get(
            "/api/dashboard/charts", params={"scope": "dashboard"}, headers=superadmin_headers,
        )
        row_m = _find_subsidy_row(resp_m.json(), subsidy.id)
        row_s = _find_subsidy_row(resp_s.json(), subsidy.id)

        if row_s.get("not_committed_nice") is not None and row_m.get("not_committed_nice") is not None:
            # У superadmin «хотелось бы» несёт весь резерв ФОТ (50000); у
            # manager — ровно без payroll-доли (0).
            assert row_s["not_committed_nice"] == pytest.approx(50000.0, abs=0.01)
            assert row_m["not_committed_nice"] == pytest.approx(0.0, abs=0.01)
        if row_s.get("redistributable_unplanned") is not None and row_m.get("redistributable_unplanned") is not None:
            # «Не запланировано» — payroll-доля (40000, остаток бюджета статьи
            # ФОТ сверх её плана) вычтена у manager, goods-доля (40000) остаётся.
            assert row_s["redistributable_unplanned"] - row_m["redistributable_unplanned"] == pytest.approx(40000.0, abs=0.01)
            assert row_m["redistributable_unplanned"] == pytest.approx(40000.0, abs=0.01)
        # Инвариант подстрок карточки держится И у manager (не только у
        # superadmin) — Σ подстрок == итогу «Можно перераспределить» без ФОТ.
        if row_m.get("redistributable") is not None:
            assert (
                row_m["redistributable_unplanned"] + row_m["not_committed_nice"]
                + row_m["not_committed_likely"] + row_m["monthly_future_not_started"]
            ) == pytest.approx(row_m["redistributable"], abs=0.01)

    async def test_plan_graph_export_excludes_payroll_without_right(
        self, client, db_session, test_org, make_user, superadmin_headers,
    ):
        """Часть 4 (владелец 21.10.2026): выгрузка плана-графика без права
        не несёт статью/закупку ФОТ (ни в лист «Сводная», ни в «План закупок» —
        категория/позиция отсутствуют во всей книге)."""
        import io
        import openpyxl

        subsidy = await _make_subsidy(db_session, test_org.id)
        payroll_cat = await _make_category(db_session, subsidy.id, is_payroll=True, name="ФОТ-статья")
        goods_cat = await _make_category(db_session, subsidy.id, is_payroll=False, name="Товары-статья")
        await _make_purchase(db_session, subsidy.id, payroll_cat.id, Decimal("90000"), name="Зарплата")
        await _make_purchase(db_session, subsidy.id, goods_cat.id, Decimal("40000"), item_type="товар", name="Товар")

        manager, _uoa = await _manager_with_access(db_session, test_org, make_user, can_view_payroll=False)

        resp = await client.get(
            f"/api/subsidies/{subsidy.id}/plan-graph/export", headers=_headers(manager),
        )
        assert resp.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        found_payroll = False
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if isinstance(cell, str) and ("ФОТ" in cell or "Зарплата" in cell or "90000" in cell or "90 000" in cell):
                        found_payroll = True
        assert not found_payroll, "ФОТ-статья/закупка просочилась в выгрузку без права"

        resp_super = await client.get(
            f"/api/subsidies/{subsidy.id}/plan-graph/export", headers=superadmin_headers,
        )
        assert resp_super.status_code == 200
        wb_super = openpyxl.load_workbook(io.BytesIO(resp_super.content))
        found_super = False
        for ws in wb_super.worksheets:
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if isinstance(cell, str) and "Зарплата" in cell:
                        found_super = True
        assert found_super, "superadmin обязан видеть ФОТ в выгрузке"
