# -*- coding: utf-8 -*-
"""Страж Правила №6 (миграция w6x7y8z9a0b1, 16.10.2026): организация больше НЕ
хранит своё название/реквизиты — единственный источник — привязанный
Contractor (app/models/organization.py: name/full_name/inn/kpp/ogrn/address/
signatory* — column_property, вычисляются из Contractor по contractor_id).

Этот тест ловит ровно тот класс регрессии, который чинила эта волна:
- новый код снова передаёт name/full_name/inn/... в конструктор Organization(...)
  (молча не персистируется — создаёт organizations без реального имени);
- новый код снова пишет org.<реквизит> = ... (присвоение column_property
  молча теряется при следующем refresh/expire — тот же баг, другая форма);
- `_legacy_*` используется где-то кроме app/models/organization.py и
  alembic-миграций (единственные легитимные потребители, см. докстринг
  Organization).

Grep-проверки приблизительны (ищут текстовые паттерны по backend/app), а не
парсят AST — умышленно: быстро, без рантайма, ловит тот же класс ошибки,
который уже случился. Ложные срабатывания разбирать по месту, не понижать
регекс до пропуска реальных случаев.

Плюс поведенческие тесты (API + ORM): создание/правка организации и
контрагента не расходятся — один источник, что и требует Правило №6.
"""
import os
import re

import pytest

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")

# Реквизитные поля, которые НЕ должны передаваться в конструктор Organization(...)
# и НЕ должны присваиваться org.<field> = ... где-либо кроме модели.
_REQUISITE_FIELDS = (
    "name", "full_name", "inn", "kpp", "ogrn", "address",
    "signatory", "signatory_position", "signatory_last_name",
    "signatory_first_name", "signatory_middle_name",
)

# Файлы, которым разрешено упоминать паттерны ниже (сама модель — объявляет
# column_property с тем же именем слева от `=`, это не "присвоение"; alembic-
# миграции работают с живой БД через raw SQL/op.*, не через ORM-модель).
_EXEMPT_PATH_PARTS = (
    os.path.join("app", "models", "organization.py"),
)


def _iter_app_py_files():
    for root, _dirs, files in os.walk(APP_DIR):
        if "alembic" in root.split(os.sep):
            continue
        for fname in files:
            if fname.endswith(".py"):
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, os.path.dirname(APP_DIR))
                yield path, rel


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_no_organization_constructor_kwargs_with_requisite_fields():
    """`Organization(name=..., inn=..., ...)` в app/ (кроме модели) — молча не
    персистируется (column_property), это ровно баг, который чинила эта волна."""
    pattern = re.compile(
        r"Organization\s*\([^)]*?\b(" + "|".join(_REQUISITE_FIELDS) + r")\s*=",
        re.DOTALL,
    )
    offenders = []
    for path, rel in _iter_app_py_files():
        if any(part in path for part in _EXEMPT_PATH_PARTS):
            continue
        text = _read(path)
        for m in pattern.finditer(text):
            # org.contractor_id= и прочие НЕ-реквизитные kwargs разрешены —
            # паттерн уже ограничен списком реквизитных полей выше.
            offenders.append(f"{rel}: Organization(...{m.group(1)}=...)")
    assert not offenders, (
        "Найден конструктор Organization(...) с реквизитным полем — "
        "column_property не персистирует присвоение (Правило №6). "
        "Пиши в привязанный Contractor. Места:\n" + "\n".join(offenders)
    )


def test_no_assignment_to_organization_requisite_attributes():
    """`org.name = ...` / `org.inn = ...` и т.п. где-либо в app/ (кроме модели) —
    присвоение column_property молча теряется (не персистируется)."""
    # org/organization/filial/_org — типичные имена переменных Organization
    # в этом кодовом базе; `contractor`/`c`/`ctr` исключены явно ниже отдельным
    # паттерном, т.к. это легитимная запись в Contractor.
    var_pat = r"(?:org|organization|filial|_org|root_org|other_org|child_org)"
    pattern = re.compile(
        rf"\b{var_pat}\.(" + "|".join(_REQUISITE_FIELDS) + r")\s*=(?!=)"
    )
    offenders = []
    for path, rel in _iter_app_py_files():
        if any(part in path for part in _EXEMPT_PATH_PARTS):
            continue
        text = _read(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            m = pattern.search(line)
            if m:
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Найдено присвоение org.<реквизит> = ... — column_property не "
        "персистирует (Правило №6). Пиши в привязанный Contractor. Места:\n"
        + "\n".join(offenders)
    )


_ORG_LEGACY_ATTRS = tuple(f"_legacy_{f}" for f in (
    "name", "full_name", "inn", "kpp", "ogrn", "address",
    "signatory", "signatory_position", "signatory_last_name",
    "signatory_first_name", "signatory_middle_name",
))


def test_legacy_columns_only_used_in_model_and_migrations():
    """`_legacy_<реквизит>` (имена из app/models/organization.py) —
    единственные легитимные потребители: сама модель Organization и
    alembic-миграции (они читают физические колонки при backfill/откате).
    Новый прикладной код не должен их трогать. Не ловит НЕСВЯЗАННЫЕ
    `_legacy_*` имена в других подсистемах (напр. app/services/
    items_import_parsing.py::_legacy_extract_tables) — те не про
    организацию/реквизиты вовсе, это другой словарь имён."""
    offenders = []
    for path, rel in _iter_app_py_files():
        if any(part in path for part in _EXEMPT_PATH_PARTS):
            continue
        text = _read(path)
        if not any(attr in text for attr in _ORG_LEGACY_ATTRS):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(attr in line for attr in _ORG_LEGACY_ATTRS):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "`_legacy_<реквизит>` организации использован вне "
        "app/models/organization.py — единственные легитимные потребители. "
        "Места:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# Поведенческие тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_organization_via_api_has_contractor_and_name(
    client, superadmin_headers,
):
    r = await client.post(
        "/api/organizations/",
        json={"name": "Org_Single_Source_Guard_Create"},
        headers=superadmin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Org_Single_Source_Guard_Create"
    assert body.get("contractor_id") is not None


@pytest.mark.asyncio
async def test_put_organization_updates_contractor_name_and_is_visible_in_get(
    client, superadmin_headers, db_session,
):
    r = await client.post(
        "/api/organizations/",
        json={"name": "Org_Single_Source_Guard_Before"},
        headers=superadmin_headers,
    )
    assert r.status_code == 201, r.text
    org_id = r.json()["id"]
    contractor_id = r.json()["contractor_id"]

    r2 = await client.put(
        f"/api/organizations/{org_id}",
        json={"name": "Org_Single_Source_Guard_After"},
        headers=superadmin_headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["name"] == "Org_Single_Source_Guard_After"

    from app.models.contractor import Contractor
    contractor = await db_session.get(Contractor, contractor_id)
    assert contractor.name == "Org_Single_Source_Guard_After"

    r3 = await client.get("/api/organizations/", headers=superadmin_headers)
    assert r3.status_code == 200, r3.text
    names = {o["id"]: o["name"] for o in r3.json()}
    assert names.get(org_id) == "Org_Single_Source_Guard_After"


@pytest.mark.asyncio
async def test_editing_contractor_card_updates_organization_name(
    client, superadmin_headers,
):
    r = await client.post(
        "/api/organizations/",
        json={"name": "Org_Single_Source_Guard_Via_Contractor"},
        headers=superadmin_headers,
    )
    assert r.status_code == 201, r.text
    org_id = r.json()["id"]
    contractor_id = r.json()["contractor_id"]

    r2 = await client.put(
        f"/api/contractors/{contractor_id}",
        json={"name": "Org_Single_Source_Guard_Renamed_From_Contractor"},
        headers=superadmin_headers,
    )
    assert r2.status_code == 200, r2.text

    r3 = await client.get(f"/api/organizations/{org_id}", headers=superadmin_headers)
    assert r3.status_code == 200, r3.text
    assert r3.json()["name"] == "Org_Single_Source_Guard_Renamed_From_Contractor"
