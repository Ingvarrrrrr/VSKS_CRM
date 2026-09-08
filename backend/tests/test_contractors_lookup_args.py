"""Регресс на дефект (сессия 2026-09-08): enrich_contractor_from_fns и
enrich_all_contractors_from_fns вызывали lookup_inn() напрямую (в обход
FastAPI DI — второго механизма ЕГРЮЛ/ФНС-поиска не заводим, см. докстринг
app/routers/contractors_lookup.py), передавая объект пользователя ВТОРЫМ
ПОЗИЦИОННЫМ аргументом — тот приземлялся на `force_egrul: bool`.

Проверяем: 1) сигнатура lookup_inn не съехала (force_egrul всё ещё второй
параметр, типа bool) — иначе именованный fix ниже перестанет что-либо значить;
2) реальные вызовы из обеих функций передают force_egrul=True (bool) и
db = реальная AsyncSession, а не Depends(...)-заглушку/объект пользователя.
Внешний вызов ЕГРЮЛ подменяется — сеть не трогаем.
"""
import inspect

import pytest

import app.routers.contractors_lookup as lookup_mod
from app.routers.contractors_lookup import (
    lookup_inn,
    enrich_contractor_from_fns,
    enrich_all_contractors_from_fns,
)


def test_lookup_inn_signature_force_egrul_is_second_bool_param():
    params = list(inspect.signature(lookup_inn).parameters.values())
    assert params[0].name == "inn"
    assert params[1].name == "force_egrul"
    assert params[1].annotation is bool


@pytest.mark.asyncio
async def test_enrich_from_fns_passes_bool_force_egrul_not_user_object(db_session, monkeypatch):
    from app.models.contractor import Contractor

    captured = {}

    async def fake_lookup_inn(inn, *args, **kwargs):
        bound = inspect.signature(lookup_inn).bind_partial(inn, *args, **kwargs)
        captured.update(bound.arguments)
        return {}

    monkeypatch.setattr(lookup_mod, "lookup_inn", fake_lookup_inn)

    contractor = Contractor(name="ООО Дефект ФНС", inn="7700000031")
    db_session.add(contractor)
    await db_session.commit()
    await db_session.refresh(contractor)

    fake_gate_result = object()  # ровно то, что раньше просачивалось в force_egrul
    result = await enrich_contractor_from_fns(
        contractor_id=contractor.id, db=db_session, _=fake_gate_result,
    )
    assert result["updated_fields"] == []

    assert "force_egrul" in captured
    assert isinstance(captured["force_egrul"], bool)
    assert captured["force_egrul"] is True
    assert captured["db"] is db_session
    # current_user не используется внутри lookup_inn — вызывающий код не обязан
    # (и не должен) его туда прокидывать.
    assert "current_user" not in captured


@pytest.mark.asyncio
async def test_enrich_all_from_fns_passes_bool_force_egrul_not_user_object(db_session, test_user, monkeypatch):
    from app.models.contractor import Contractor

    captured_calls = []

    async def fake_lookup_inn(inn, *args, **kwargs):
        bound = inspect.signature(lookup_inn).bind_partial(inn, *args, **kwargs)
        captured_calls.append(bound.arguments)
        return {}

    monkeypatch.setattr(lookup_mod, "lookup_inn", fake_lookup_inn)

    contractor = Contractor(name="ООО Дефект ФНС Bulk", inn="7700000032")
    db_session.add(contractor)
    await db_session.commit()

    await enrich_all_contractors_from_fns(db=db_session, current_user=test_user)

    assert captured_calls, "lookup_inn должен был быть вызван хотя бы раз"
    for call in captured_calls:
        assert isinstance(call["force_egrul"], bool)
        assert call["force_egrul"] is True
        assert call["db"] is db_session
        assert "current_user" not in call
