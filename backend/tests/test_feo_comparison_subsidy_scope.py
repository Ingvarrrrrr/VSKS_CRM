"""GET /feo-planned-items/comparison?subsidy_id= — «вся субсидия по категориям
товара» (задача владельца, 28.10.2026, SubsidyCategoryPanel.vue): feo_category_id
опущен, subsidy_id становится селектором и собирает плановые/фактические позиции
ВСЕХ статей ФЭО субсидии одним списком — та же строка-построитель (cat_map/
cat_plan_fallback_map в get_comparison, feo_planned_items_reports.py), что и у
режима одной категории (ПРАВИЛО №6, второй расчёт не заводится).

Покрывает:
  - subsidy_id без feo_category_id отдаёт позиции из ≥2 статей ФЭО одним списком;
  - строка subsidy-wide ответа совпадает с ответом ?feo_category_id= для её статьи
    (один источник, не вторая формула);
  - 400, если НЕ передан ни один из двух параметров;
  - 404 (НЕ 403 — тот же canonical read-access гейт, что и GET /api/subsidies/{id}
    и GET /api/subsidies/{id}/card-drill, см. app.auth.visibility.
    ensure_subsidy_visible: политика «не раскрывать существование чужой субсидии»
    этих двух мест-образцов, не вторая копия 403) на субсидию вне доступа пользователя.

⚠️ Доступ к feo_category_id-режиму (без subsidy_id) гейт НЕ проверяет — он уже
годами отдавался без него (см. докстринг get_comparison), эта задача трогает
только НОВУЮ subsidy_wide-поверхность, старую не меняет."""
import uuid
from decimal import Decimal

import pytest

from app.auth.jwt import create_access_token
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.permission import RolePermission
from app.models.subsidy import Subsidy


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _headers(user):
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def grant_subsidies_tab(db_session):
    """auth_headers (test_user, role=employee) видит вкладку «Субсидии» своей
    орги — иначе новый гейт ensure_subsidy_visible (ПРАВИЛО №6, тот же код, что
    у GET /api/subsidies/{id}) отказывает employee без единой закупки в субсидии,
    как и настоящему непривилегированному сотруднику без доступа."""
    db_session.add(RolePermission(role_name="employee", key="subsidies", granted=True))
    await db_session.commit()


@pytest.fixture
async def subsidy_with_two_categories(db_session, test_org):
    """Субсидия с ДВУМЯ статьями ФЭО, в каждой — плановая позиция одного и того
    же товара каталога (чтобы они встретились в ОДНОЙ группе категории товара на
    фронте), плюс позиция без совпадения в каталоге (идёт в «Без категории»)."""
    subsidy = Subsidy(name=f"SubsidyWide-{_uid()}", year=2026, org_id=test_org.id)
    db_session.add(subsidy)
    await db_session.flush()
    cat_a = FeoCategory(subsidy_id=subsidy.id, level=3, name="Статья А")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=3, name="Статья Б")
    db_session.add_all([cat_a, cat_b])
    await db_session.flush()

    uniq = f"ТестВсяСубсидия_{_uid()}"
    item_a = FeoPlannedItem(feo_category_id=cat_a.id, name=f"{uniq} Бензопила", amount=Decimal("1000"), quantity=Decimal("1"), is_active=True)
    item_b = FeoPlannedItem(feo_category_id=cat_b.id, name=f"{uniq} Бензопила цепная", amount=Decimal("2000"), quantity=Decimal("2"), is_active=True)
    item_other = FeoPlannedItem(feo_category_id=cat_b.id, name=f"{uniq} Без каталога вовсе", amount=Decimal("300"), is_active=True)
    db_session.add_all([item_a, item_b, item_other])
    await db_session.commit()
    return subsidy, cat_a, cat_b, item_a, item_b, item_other


@pytest.mark.asyncio
async def test_subsidy_wide_returns_items_from_multiple_feo_categories(
    client, auth_headers, db_session, subsidy_with_two_categories, grant_subsidies_tab,
):
    subsidy, cat_a, cat_b, item_a, item_b, item_other = subsidy_with_two_categories

    resp = await client.get(
        f"/api/feo-planned-items/comparison?subsidy_id={subsidy.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    planned = {row["id"]: row for row in resp.json()["planned"]}

    assert item_a.id in planned and item_b.id in planned and item_other.id in planned
    assert planned[item_a.id]["feo_category_name"] == "Статья А"
    assert planned[item_b.id]["feo_category_name"] == "Статья Б"
    assert planned[item_other.id]["feo_category_name"] == "Статья Б"
    # Позиции из ДВУХ разных статей действительно присутствуют одним списком.
    cat_names = {row["feo_category_name"] for row in planned.values()}
    assert cat_names == {"Статья А", "Статья Б"}


@pytest.mark.asyncio
async def test_subsidy_wide_row_matches_single_category_response(
    client, auth_headers, db_session, subsidy_with_two_categories, grant_subsidies_tab,
):
    """Строка subsidy-wide ответа для позиции статьи Б совпадает с ответом
    ?feo_category_id=<Б> для этой же позиции — один источник (ПРАВИЛО №6),
    не вторая формула с другим результатом."""
    subsidy, cat_a, cat_b, item_a, item_b, item_other = subsidy_with_two_categories

    resp_wide = await client.get(
        f"/api/feo-planned-items/comparison?subsidy_id={subsidy.id}",
        headers=auth_headers,
    )
    resp_single = await client.get(
        f"/api/feo-planned-items/comparison?feo_category_id={cat_b.id}",
        headers=auth_headers,
    )
    assert resp_wide.status_code == 200, resp_wide.text
    assert resp_single.status_code == 200, resp_single.text

    wide_row = next(r for r in resp_wide.json()["planned"] if r["id"] == item_b.id)
    single_row = next(r for r in resp_single.json()["planned"] if r["id"] == item_b.id)

    for field in ("name", "amount", "quantity", "catalog_category", "catalog_product_type", "item_type_effective"):
        assert wide_row[field] == single_row[field], f"{field} разошёлся между режимами"


@pytest.mark.asyncio
async def test_comparison_requires_one_of_the_two_params(client, auth_headers):
    resp = await client.get("/api/feo-planned-items/comparison", headers=auth_headers)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_subsidy_wide_foreign_subsidy_is_404_not_leaked(
    client, db_session, make_user, test_org, subsidy_with_two_categories,
):
    """Пользователь без доступа к этой субсидии (другая орга, никаких грантов) —
    404, как и у GET /api/subsidies/{id} (та же политика «не раскрывать
    существование», не 403 — см. докстринг модуля/ensure_subsidy_visible)."""
    subsidy, *_ = subsidy_with_two_categories

    import uuid as _uuid
    from app.models.contractor import Contractor
    from app.models.organization import Organization
    contractor = Contractor(name=f"ForeignOrg-{_uuid.uuid4().hex[:8]}")
    db_session.add(contractor)
    await db_session.flush()
    foreign_org = Organization(contractor_id=contractor.id)
    db_session.add(foreign_org)
    await db_session.commit()
    await db_session.refresh(foreign_org)

    outsider = await make_user(role="employee", org_id=foreign_org.id)

    resp = await client.get(
        f"/api/feo-planned-items/comparison?subsidy_id={subsidy.id}",
        headers=_headers(outsider),
    )
    assert resp.status_code == 404, resp.text
