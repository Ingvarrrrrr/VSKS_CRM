"""Доступ к ПДн контрагента-физлица (ГПХ): паспорт/СНИЛС/адрес регистрации/
дата рождения — должны видеть и писать ТОЛЬКО пользователи с правом на
раздел «Договоры» (tab_key `contracts`). Баг (решение владельца, 2026-10-08):
GET /api/contractors/ и GET /api/contractors/{id} отдавали эти поля любому
вошедшему, т.к. tab_key `contracts` на эндпоинтах вообще не проверялся (tab
`contractors`, которым был гейтован список/карточка, выдан employee тоже —
см. alembic/versions/perm_seed_hotfix.sql).

Единственное место, которое решает видимость/запись этих полей —
app/services/contractor_pii.py (ПРАВИЛО №6). Этот файл проверяет периметр:
- employee (есть `contractors`, НЕТ `contracts`) — ПДн не видит в списке и
  карточке, PATCH/PUT с ПДн-полями их не затирает;
- org_admin (есть и `contractors`, и `contracts`, см. тот же seed) — видит
  и может записать.

Паттерн fixtures — как в test_admin_legal_docs.py / test_require_tab.py
(client, auth_headers=employee/test_user, make_user для произвольной роли).
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.contractor import Contractor

PII_FIELDS = (
    "passport_series",
    "passport_number",
    "passport_issuer",
    "passport_issued_date",
    "snils",
    "registration_address",
    "birth_date",
)


def _headers_for(user):
    from app.auth.jwt import create_access_token
    token = create_access_token({"sub": user.username, "org_id": user.org_id})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def gph_contractor(db_session, test_org):
    """Контрагент-физлицо с заполненными ПДн (ГПХ), напрямую в БД."""
    c = Contractor(
        name="Иванов Иван Иванович",
        org_type="Физ.лицо",
        org_id=test_org.id,
        passport_series="1234",
        passport_number="567890",
        passport_issuer="ОВД Центрального района г. Москвы",
        snils="123-456-789 00",
        registration_address="г. Москва, ул. Тестовая, д. 1",
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


# ---------------------------------------------------------------------------
# Чтение: список
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_hides_pii_without_contracts_tab(client, auth_headers, gph_contractor):
    # search= чтобы найти нашего контрагента независимо от размера общей
    # таблицы contractors (тесты идут на реальной dev БД, см. conftest.py).
    r = await client.get(
        "/api/contractors/", params={"search": gph_contractor.name}, headers=auth_headers
    )
    assert r.status_code == 200
    rows = {row["id"]: row for row in r.json()}
    assert gph_contractor.id in rows
    row = rows[gph_contractor.id]
    for f in PII_FIELDS:
        assert not row.get(f), f"поле {f} не должно быть видно без права 'contracts'"
    # Неперсональные поля остаются видимыми как и раньше
    assert row["name"] == gph_contractor.name
    assert row["org_type"] == "Физ.лицо"


@pytest.mark.asyncio
async def test_list_shows_pii_with_contracts_tab(client, db_session, test_org, make_user, gph_contractor):
    org_admin = await make_user(role="org_admin", org_id=test_org.id)
    r = await client.get(
        "/api/contractors/", params={"search": gph_contractor.name}, headers=_headers_for(org_admin)
    )
    assert r.status_code == 200
    rows = {row["id"]: row for row in r.json()}
    row = rows[gph_contractor.id]
    assert row["passport_series"] == "1234"
    assert row["passport_number"] == "567890"
    assert row["snils"] == "123-456-789 00"
    assert row["registration_address"] == "г. Москва, ул. Тестовая, д. 1"


# ---------------------------------------------------------------------------
# Чтение: карточка
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detail_hides_pii_without_contracts_tab(client, auth_headers, gph_contractor):
    r = await client.get(f"/api/contractors/{gph_contractor.id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    for f in PII_FIELDS:
        assert not body.get(f)
    assert body["name"] == gph_contractor.name


@pytest.mark.asyncio
async def test_detail_shows_pii_with_contracts_tab(client, db_session, test_org, make_user, gph_contractor):
    org_admin = await make_user(role="org_admin", org_id=test_org.id)
    r = await client.get(f"/api/contractors/{gph_contractor.id}", headers=_headers_for(org_admin))
    assert r.status_code == 200
    body = r.json()
    assert body["passport_series"] == "1234"
    assert body["snils"] == "123-456-789 00"


# ---------------------------------------------------------------------------
# Запись: PUT /api/contractors/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_without_contracts_tab_does_not_overwrite_passport(
    client, db_session, auth_headers, gph_contractor
):
    """employee has 'contractors' (может редактировать карточку), но не
    'contracts' — паспорт/СНИЛС/адрес/дата рождения в payload должны быть
    ИГНОРИРОВАНЫ, а не затёрты и не записаны новым значением."""
    payload = {
        "name": gph_contractor.name,
        "org_type": "Физ.лицо",
        "phone": "+7 999 000-00-00",
        "passport_series": "9999",
        "passport_number": "000000",
        "snils": "000-000-000 00",
        "registration_address": "подменённый адрес",
        "birth_date": "1990-01-01",
    }
    r = await client.put(f"/api/contractors/{gph_contractor.id}", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Ответ без ПДн (нет права смотреть)
    for f in PII_FIELDS:
        assert not body.get(f)
    # Неперсональное поле обновилось
    assert body["phone"] == "+7 999 000-00-00"

    # В БД паспорт/СНИЛС/адрес НЕ изменились
    row = (await db_session.execute(
        select(Contractor).where(Contractor.id == gph_contractor.id)
    )).scalar_one()
    assert row.passport_series == "1234"
    assert row.passport_number == "567890"
    assert row.snils == "123-456-789 00"
    assert row.registration_address == "г. Москва, ул. Тестовая, д. 1"
    assert row.phone == "+7 999 000-00-00"


@pytest.mark.asyncio
async def test_patch_with_contracts_tab_can_write_passport(
    client, db_session, test_org, make_user, gph_contractor
):
    org_admin = await make_user(role="org_admin", org_id=test_org.id)
    payload = {
        "name": gph_contractor.name,
        "org_type": "Физ.лицо",
        "passport_series": "4321",
        "passport_number": "098765",
        "snils": "987-654-321 00",
        "registration_address": "г. Москва, новый адрес",
        "birth_date": "1985-05-05",
    }
    r = await client.put(
        f"/api/contractors/{gph_contractor.id}", json=payload, headers=_headers_for(org_admin)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["passport_series"] == "4321"
    assert body["snils"] == "987-654-321 00"

    row = (await db_session.execute(
        select(Contractor).where(Contractor.id == gph_contractor.id)
    )).scalar_one()
    assert row.passport_series == "4321"
    assert row.passport_number == "098765"
    assert row.snils == "987-654-321 00"


@pytest.mark.asyncio
async def test_create_contractor_without_contracts_tab_ignores_passport_fields(
    client, db_session, auth_headers
):
    """POST /api/contractors/ требует только 'contractors' (у employee есть) —
    но без 'contracts' паспортные поля в payload должны игнорироваться при
    создании новой карточки, а не сохраняться."""
    payload = {
        "name": "Петров Пётр Петрович",
        "org_type": "Физ.лицо",
        "passport_series": "1111",
        "passport_number": "222222",
    }
    r = await client.post("/api/contractors/", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert not body.get("passport_series")
    assert not body.get("passport_number")

    row = (await db_session.execute(
        select(Contractor).where(Contractor.id == body["id"])
    )).scalar_one()
    assert row.passport_series is None
    assert row.passport_number is None
