"""Лидерборды мини-игр окна ожидания — app/routers/games.py, app/models/game_score.py.

Проверяет: закрыто по умолчанию (401 без логина), upsert держит максимум,
глобальный список не содержит fio, аккаунтный список — только своего
аккаунта, невалидный id игры -> 400/422, валидация ника.
"""
import asyncio

import pytest

# Роутер игнорирует повторный POST score того же пользователя быстрее 2с
# (простая защита от спама, см. app/routers/games.py::_RATE_LIMIT_SECONDS) —
# тесты на последовательные сабмиты одного игрока ждут дольше этого окна.
_RATE_LIMIT_GAP = 2.1


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client):
    r = await client.post("/api/games/duck/score", json={"score": 10})
    assert r.status_code == 401

    r = await client.get("/api/games/duck/leaderboard")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bad_game_id_rejected(client, auth_headers):
    r = await client.post("/api/games/not-a-game/score", json={"score": 10}, headers=auth_headers)
    assert r.status_code in (400, 422)

    r = await client.get("/api/games/not-a-game/leaderboard", headers=auth_headers)
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_score_upsert_keeps_max(client, auth_headers):
    r = await client.post("/api/games/duck/score", json={"score": 50}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["best"] == 50

    await asyncio.sleep(_RATE_LIMIT_GAP)
    r = await client.post("/api/games/duck/score", json={"score": 10}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["best"] == 50  # меньший результат не понижает best

    await asyncio.sleep(_RATE_LIMIT_GAP)
    r = await client.post("/api/games/duck/score", json={"score": 90}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["best"] == 90


@pytest.mark.asyncio
async def test_score_out_of_range_rejected(client, auth_headers):
    r = await client.post("/api/games/duck/score", json={"score": -1}, headers=auth_headers)
    assert r.status_code == 422

    r = await client.post("/api/games/duck/score", json={"score": 99_999_999}, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_global_leaderboard_has_no_fio(client, auth_headers, test_user):
    await client.post("/api/games/brick/score", json={"score": 42}, headers=auth_headers)

    r = await client.get("/api/games/brick/leaderboard", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "global" in body
    for entry in body["global"]:
        assert set(entry.keys()) == {"nickname", "score", "is_me"}
        for v in entry.values():
            assert test_user.full_name != v
            assert str(test_user.id) != str(v)
    # По умолчанию (без заданного ника) — «Игрок»
    assert any(e["nickname"] == "Игрок" for e in body["global"])


@pytest.mark.asyncio
async def test_account_leaderboard_shows_fio_and_only_own_account(
    client, auth_headers, test_user, make_user, db_session,
):
    await client.post("/api/games/tank/score", json={"score": 77}, headers=auth_headers)

    # Пользователь другой организации с результатом — не должен попасть в
    # аккаунтный список test_user.
    from app.models.contractor import Contractor
    from app.models.organization import Organization
    from app.auth.jwt import create_access_token
    import uuid

    other_contractor = Contractor(name=f"OtherOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(other_contractor)
    await db_session.flush()
    other_org = Organization(contractor_id=other_contractor.id)
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    other_user = await make_user(role="employee", org_id=other_org.id)
    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': other_user.username, 'org_id': other_user.org_id})}"
    }
    await client.post("/api/games/tank/score", json={"score": 999}, headers=other_headers)

    r = await client.get("/api/games/tank/leaderboard", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    account_fios = [e["fio"] for e in body["account"]]
    assert any("Test" in f or test_user.full_name.split()[0] in f for f in account_fios)
    assert len(account_fios) == 1  # только свой аккаунт, не other_user (999)
    for entry in body["account"]:
        assert "score" in entry and "fio" in entry and "is_me" in entry


@pytest.mark.asyncio
async def test_nickname_validation(client, auth_headers):
    r = await client.put("/api/games/nickname", json={"nickname": "a"}, headers=auth_headers)
    assert r.status_code == 422  # меньше 2 символов

    r = await client.put("/api/games/nickname", json={"nickname": "x" * 25}, headers=auth_headers)
    assert r.status_code == 422  # больше 24 символов

    r = await client.put("/api/games/nickname", json={"nickname": "<script>"}, headers=auth_headers)
    assert r.status_code == 422  # недопустимые символы

    r = await client.put("/api/games/nickname", json={"nickname": "Снайпер_99"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["nickname"] == "Снайпер_99"

    r = await client.get("/api/games/nickname", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["nickname"] == "Снайпер_99"

    # null — сброс на дефолт
    r = await client.put("/api/games/nickname", json={"nickname": None}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["nickname"] == "Игрок"
