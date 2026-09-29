"""GET/POST /api/organizations/{id}/director — руководитель по ЕГРЮЛ,
отдельно от подписанта (app/services/org_head.py, app/routers/organization_director.py).

Единственный сервис похода в ЕГРЮЛ — contractors_lookup.lookup_inn, здесь
мокается через monkeypatch на модуле app.services.org_head (где он
импортируется лениво внутри refresh_director_from_egrul), чтобы тест не
дёргал реальную налоговую.
"""
import pytest


def _mock_lookup_inn(director_last, director_first, director_middle, director_position="Директор"):
    async def _fake(inn, force_egrul=True, db=None):
        return {
            "director_last_name": director_last,
            "director_first_name": director_first,
            "director_middle_name": director_middle,
            "director_position": director_position,
        }
    return _fake


@pytest.mark.asyncio
async def test_refresh_writes_director_and_keeps_signatory_untouched(
    client, db_session, superadmin_headers, test_org, monkeypatch,
):
    test_org.inn = "7700000010"
    test_org.signatory_last_name = "Доверенный"
    test_org.signatory_first_name = "Иван"
    test_org.signatory_middle_name = "Иванович"
    db_session.add(test_org)
    await db_session.commit()

    # lookup_inn импортируется лениво внутри refresh_director_from_egrul из
    # app.routers.contractors_lookup — патчим именно там, откуда реально читается.
    import app.routers.contractors_lookup as lookup_module
    monkeypatch.setattr(lookup_module, "lookup_inn", _mock_lookup_inn("Директоров", "Пётр", "Петрович"))

    r = await client.post(f"/api/organizations/{test_org.id}/director/refresh", headers=superadmin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["last_name"] == "Директоров"
    assert body["first_name"] == "Пётр"
    assert body["middle_name"] == "Петрович"
    assert body["position"] == "Директор"
    assert body["source"] == "egrul"

    await db_session.refresh(test_org)
    assert test_org.director_last_name == "Директоров"
    # Подписант — отдельная сущность, refresh руководителя его не трогает.
    assert test_org.signatory_last_name == "Доверенный"
    assert test_org.signatory_first_name == "Иван"


@pytest.mark.asyncio
async def test_get_director_returns_matching_employee(
    client, db_session, superadmin_headers, test_org, make_user,
):
    test_org.director_last_name = "Директоров"
    test_org.director_first_name = "Пётр"
    test_org.director_middle_name = "Петрович"
    test_org.director_position = "Генеральный директор"
    db_session.add(test_org)
    await db_session.commit()

    employee = await make_user(
        role="employee", org_id=test_org.id,
        last_name="Директоров", first_name="Пётр", middle_name="Петрович",
        full_name="Директоров Пётр Петрович",
    )

    r = await client.get(f"/api/organizations/{test_org.id}/director", headers=superadmin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["last_name"] == "Директоров"
    assert body["fio_short"] == "Директоров П.П."
    assert body["employee"] is not None
    assert body["employee"]["id"] == employee.id


@pytest.mark.asyncio
async def test_get_director_no_matching_employee_returns_null(
    client, db_session, superadmin_headers, test_org,
):
    test_org.director_last_name = "Безсотрудников"
    test_org.director_first_name = "Некто"
    db_session.add(test_org)
    await db_session.commit()

    r = await client.get(f"/api/organizations/{test_org.id}/director", headers=superadmin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["employee"] is None
