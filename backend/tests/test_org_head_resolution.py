# -*- coding: utf-8 -*-
"""app/services/org_head.py::resolve_org_head_user_id — единственный источник
истины для «руководителя организации» в цепочках согласования (владелец,
2026-09-29): «подписант может быть по доверенности, руководитель — это
руководитель по ЕГРЮЛ». Organization.head_user_id и signatory_* НЕ источник.

Покрытие:
  1. director_* уже заполнены вручную → сопоставление по ФИО сотрудника, без
     похода в ЕГРЮЛ.
  2. director_* пусты, но у организации есть ИНН → lookup_inn (мок) вызывается
     ОДИН раз, director_* сохраняются на Organization, сотрудник находится.
  3. Ни director_*, ни ИНН — resolve возвращает None, describe объясняет, что
     нет ИНН.
  4. director_* (или ЕГРЮЛ) есть, но такого сотрудника нет — describe называет
     конкретное ФИО и просит добавить сотрудником.
  5. Организация без ИНН и подписант (signatory_*) НЕ используется как
     источник — заполненный только signatory не даёт руководителя.
"""
import pytest
from unittest.mock import AsyncMock

from app.models.user import User
from app.auth.jwt import hash_password
from app.services.org_head import (
    resolve_org_head_user_id,
    describe_org_head_missing_reason,
    get_org_director_full_name,
)


@pytest.mark.asyncio
async def test_resolve_uses_director_fields_already_set(db_session, test_org, make_user):
    manager = await make_user(
        role="manager", last_name="Козеев", first_name="Евгений", middle_name="Викторович",
    )
    test_org.director_last_name = "Козеев"
    test_org.director_first_name = "Евгений"
    test_org.director_middle_name = "Викторович"
    await db_session.commit()

    uid = await resolve_org_head_user_id(db_session, test_org)
    assert uid == manager.id


@pytest.mark.asyncio
async def test_resolve_normalizes_case_and_yo(db_session, test_org, make_user):
    """Регистр и ё/е не должны мешать совпадению (владелец: нормализация)."""
    manager = await make_user(
        role="manager", last_name="Пугачёв", first_name="Пётр", middle_name="Ильич",
    )
    test_org.director_last_name = "ПУГАЧЕВ"
    test_org.director_first_name = "петр"
    test_org.director_middle_name = "ИЛЬИЧ"
    await db_session.commit()

    uid = await resolve_org_head_user_id(db_session, test_org)
    assert uid == manager.id


@pytest.mark.asyncio
async def test_resolve_fetches_from_egrul_when_director_empty_but_inn_present(
    db_session, test_org, make_user, monkeypatch,
):
    """director_* пусты, ИНН есть — lookup_inn (тот же сервис, что у карточки
    контрагента) запрашивается ОДИН раз, найденный руководитель сохраняется
    на Organization.director_* и используется для сопоставления."""
    employee = await make_user(
        role="employee", last_name="Козеев", first_name="Евгений", middle_name="Викторович",
    )
    test_org.inn = "7701234567"
    assert test_org.director_last_name is None
    await db_session.commit()

    fake_lookup = AsyncMock(return_value={
        "director_last_name": "Козеев",
        "director_first_name": "Евгений",
        "director_middle_name": "Викторович",
        "director_position": "Председатель",
        # signatory_* деliberately different — не должно влиять
        "signatory_last_name": "Доверенный",
        "signatory_first_name": "Пред",
        "signatory_middle_name": "Ставитель",
    })
    monkeypatch.setattr("app.routers.contractors_lookup.lookup_inn", fake_lookup)

    uid = await resolve_org_head_user_id(db_session, test_org)
    await db_session.commit()

    assert uid == employee.id
    fake_lookup.assert_awaited_once()
    assert fake_lookup.await_args.kwargs.get("force_egrul") is True
    await db_session.refresh(test_org)
    assert test_org.director_last_name == "Козеев"
    assert test_org.director_position == "Председатель"


@pytest.mark.asyncio
async def test_resolve_none_without_director_and_without_inn(db_session, test_org):
    assert await resolve_org_head_user_id(db_session, test_org) is None
    reason = await describe_org_head_missing_reason(db_session, test_org)
    assert "инн" in reason.lower()
    assert "не заполнен" in reason.lower()


@pytest.mark.asyncio
async def test_describe_names_director_when_no_matching_employee(db_session, test_org):
    test_org.director_last_name = "Козеев"
    test_org.director_first_name = "Евгений"
    test_org.director_middle_name = "Викторович"
    await db_session.commit()

    assert await resolve_org_head_user_id(db_session, test_org) is None
    reason = await describe_org_head_missing_reason(db_session, test_org)
    assert "Козеев" in reason
    assert "добавьте" in reason.lower()


@pytest.mark.asyncio
async def test_signatory_alone_is_not_a_source(db_session, test_org, make_user):
    """signatory_* (подписант, может быть доверенным лицом) НЕ используется
    для определения руководителя — только director_*."""
    await make_user(
        role="manager", last_name="Доверенный", first_name="Пред", middle_name="Ставитель",
    )
    test_org.signatory_last_name = "Доверенный"
    test_org.signatory_first_name = "Пред"
    test_org.signatory_middle_name = "Ставитель"
    await db_session.commit()

    assert await resolve_org_head_user_id(db_session, test_org) is None
    assert get_org_director_full_name(test_org) is None
