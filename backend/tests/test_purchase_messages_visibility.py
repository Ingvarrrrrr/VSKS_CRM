# -*- coding: utf-8 -*-
"""Модульные тесты изоляции рабочих сообщений, комментариев и чатов
(закупки, задачи, ФЭО) — Правила №5, №6, №8.

Проверяют:
1) purchase_comments (list_purchase_comments, add_purchase_comment, delete_purchase_comment)
   вызывают ensure_purchase_visible и возвращают 404 при невидимой закупке,
   а @mention фильтрует пользователей по owner_scope_org_ids;
2) purchase_events и purchase_members (list_events, add_event, list_purchase_members,
   update_task_comment, list_members, add_member, remove_member, add_purchase_member,
   remove_purchase_member) вызывают ensure_purchase_visible;
3) chat.py (get_or_create_entity_room вызывает ensure_purchase_visible / ensure_task_visible,
   add_participant возвращает 403 для пользователя из другой org_id,
   _parse_mention_ids фильтрует по org_id и не падает при двух однофамильцах);
4) feo_comments (get_comments_visibility, get_comment_counts, list_comments)
   вызывают ensure_subsidy_visible;
5) task_comments.add_comment: @mention фильтрует пользователей через owner_scope_org_ids.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.routers.purchase_comments as purchase_comments_router
import app.routers.purchase_events as purchase_events_router
import app.routers.purchase_members as purchase_members_router
import app.routers.chat as chat_router
import app.routers.feo_comments as feo_comments_router
import app.routers.task_comments as task_comments_router
from app.schemas.tasks import TaskCommentCreate


# ---------------------------------------------------------------------------
# 1. purchase_comments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purchase_comments_list_raises_404_when_invisible(monkeypatch):
    """list_purchase_comments вызывает ensure_purchase_visible и отдаёт 404 при невидимой закупке."""
    called = {}

    async def fake_ensure(user, pid, db):
        called["args"] = (user.id, pid)
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10, role="employee", org_id=1, full_name="Тест")

    with pytest.raises(HTTPException) as exc_info:
        await purchase_comments_router.list_purchase_comments(pid=123, db=fake_db, current_user=user)
    assert exc_info.value.status_code == 404
    assert called["args"] == (10, 123)


@pytest.mark.asyncio
async def test_purchase_comments_add_raises_404_when_invisible(monkeypatch):
    """add_purchase_comment вызывает ensure_purchase_visible и отдаёт 404 при невидимой закупке."""
    async def fake_ensure(user, pid, db):
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10, role="employee", org_id=1, full_name="Тест", username="test")

    with pytest.raises(HTTPException) as exc_info:
        await purchase_comments_router.add_purchase_comment(
            pid=123, body={"text": "Привет"}, db=fake_db, current_user=user
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_purchase_comments_delete_raises_404_when_invisible(monkeypatch):
    """delete_purchase_comment вызывает ensure_purchase_visible и отдаёт 404 при невидимой закупке."""
    async def fake_ensure(user, pid, db):
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10, role="employee", org_id=1)

    with pytest.raises(HTTPException) as exc_info:
        await purchase_comments_router.delete_purchase_comment(
            pid=123, comment_id=456, db=fake_db, current_user=user
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_purchase_comments_add_mention_scoped_by_owner_contour(monkeypatch):
    """В add_purchase_comment выборка @mention ограничивается owner_scope_org_ids."""
    fake_purchase = SimpleNamespace(id=123, subject="Тестовая закупка")

    async def fake_ensure(user, pid, db):
        return fake_purchase

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    scope_called = {}

    async def fake_owner_scope(user, db):
        scope_called["user_id"] = user.id
        return {7, 8}

    monkeypatch.setattr("app.auth.visibility.owner_scope_org_ids", fake_owner_scope)

    captured_queries = []
    fake_db = AsyncMock()

    async def fake_execute(statement, *args, **kwargs):
        captured_queries.append(statement)
        m = MagicMock()
        m.scalars.return_value.all.return_value = [
            SimpleNamespace(id=20, username="ivan", full_name="Иван Иванов", org_id=7)
        ]
        return m

    fake_db.execute = fake_execute

    user = SimpleNamespace(id=10, role="employee", org_id=7, full_name="Петр", username="petr")

    await purchase_comments_router.add_purchase_comment(
        pid=123, body={"text": "Привет @ivan"}, db=fake_db, current_user=user
    )

    assert scope_called["user_id"] == 10
    # Проверяем, что в запросе к User применился фильтр по org_id IN (7, 8)
    user_queries = [str(q) for q in captured_queries if "users" in str(q).lower()]
    assert len(user_queries) >= 1
    assert "users.org_id" in user_queries[0]


# ---------------------------------------------------------------------------
# 2. purchase_events & purchase_members
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_purchase_events_list_events_raises_404_when_invisible(monkeypatch):
    """list_events вызывает ensure_purchase_visible."""
    called = {}

    async def fake_ensure(user, pid, db):
        called["checked"] = pid
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10)

    with pytest.raises(HTTPException) as exc_info:
        await purchase_events_router.list_events(pid=555, db=fake_db, current_user=user)
    assert exc_info.value.status_code == 404
    assert called["checked"] == 555


@pytest.mark.asyncio
async def test_purchase_events_add_event_raises_404_when_invisible(monkeypatch):
    """add_event вызывает ensure_purchase_visible."""
    async def fake_ensure(user, pid, db):
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10)
    body = purchase_events_router.AddEventBody(event_type="test_event")

    with pytest.raises(HTTPException) as exc_info:
        await purchase_events_router.add_event(pid=555, body=body, db=fake_db, current_user=user)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_purchase_events_members_endpoints_raise_404_when_invisible(monkeypatch):
    """list_members, add_member, remove_member вызывают ensure_purchase_visible."""
    async def fake_ensure(user, pid, db):
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10)

    with pytest.raises(HTTPException) as exc:
        await purchase_events_router.list_members(pid=777, db=fake_db, current_user=user)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await purchase_events_router.add_member(
            pid=777, body=purchase_events_router.AddMemberBody(user_id=20), db=fake_db, current_user=user
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await purchase_events_router.remove_member(pid=777, uid=20, db=fake_db, current_user=user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_purchase_members_router_raises_404_when_invisible(monkeypatch):
    """purchase_members: update_task_comment, list_purchase_members, add_purchase_member, remove_purchase_member."""
    called_pids = []

    async def fake_ensure(user, pid, db):
        called_pids.append(pid)
        raise HTTPException(404, "Закупка не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=10)

    with pytest.raises(HTTPException):
        await purchase_members_router.update_task_comment(pid=888, comment="c", db=fake_db, current_user=user)

    with pytest.raises(HTTPException):
        await purchase_members_router.list_purchase_members(pid=888, db=fake_db, current_user=user)

    with pytest.raises(HTTPException):
        await purchase_members_router.add_purchase_member(pid=888, body={"user_id": 2}, db=fake_db, current_user=user)

    with pytest.raises(HTTPException):
        await purchase_members_router.remove_purchase_member(pid=888, user_id=2, db=fake_db, current_user=user)

    assert called_pids == [888, 888, 888, 888]


# ---------------------------------------------------------------------------
# 3. chat.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_get_or_create_entity_room_checks_visibility(monkeypatch):
    """get_or_create_entity_room проверяет видимость закупки и задачи."""
    vis_calls = []

    async def fake_ensure_purchase(user, pid, db):
        vis_calls.append(("purchase", pid))
        if pid == 999:
            raise HTTPException(404, "Закупка не найдена")

    async def fake_ensure_task(user, tid, db):
        vis_calls.append(("task", tid))
        if tid == 888:
            raise HTTPException(404, "Задача не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure_purchase)
    monkeypatch.setattr("app.auth.object_visibility.ensure_task_visible", fake_ensure_task)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=1, org_id=10)

    # Невидимая закупка -> 404
    body_p = chat_router.ForEntityBody(entity_type="purchase", entity_id=999, name="Chat Purchase")
    with pytest.raises(HTTPException) as exc:
        await chat_router.get_or_create_entity_room(body=body_p, db=fake_db, current_user=user)
    assert exc.value.status_code == 404
    assert vis_calls[-1] == ("purchase", 999)

    # Невидимая задача -> 404
    body_t = chat_router.ForEntityBody(entity_type="task", entity_id=888, name="Chat Task")
    with pytest.raises(HTTPException) as exc:
        await chat_router.get_or_create_entity_room(body=body_t, db=fake_db, current_user=user)
    assert exc.value.status_code == 404
    assert vis_calls[-1] == ("task", 888)


@pytest.mark.asyncio
async def test_chat_add_participant_cross_org_forbidden(monkeypatch):
    """add_participant возвращает 403 для пользователя из чужой организации."""
    monkeypatch.setattr("app.routers.chat._check_room_participant", AsyncMock())

    fake_db = AsyncMock()
    # Целевой пользователь в org_id=99
    target_user = SimpleNamespace(id=25, org_id=99, full_name="Чужой")

    async def fake_execute(statement, *args, **kwargs):
        m = MagicMock()
        m.scalar_one_or_none.return_value = target_user
        return m

    fake_db.execute = fake_execute

    current_user = SimpleNamespace(id=10, org_id=1)

    with pytest.raises(HTTPException) as exc:
        await chat_router.add_participant(
            room_id=5, body={"user_id": 25}, db=fake_db, current_user=current_user
        )
    assert exc.value.status_code == 403
    assert "организации" in exc.value.detail


@pytest.mark.asyncio
async def test_chat_parse_mention_ids_org_scoping_and_homonyms():
    """_parse_mention_ids фильтрует по org_id и не падает при двух однофамильцах."""
    fake_db = AsyncMock()

    # Два однофамильца в одной организации
    user1 = SimpleNamespace(id=101, full_name="Иван Иванов", org_id=5)
    user2 = SimpleNamespace(id=102, full_name="Иван Иванов", org_id=5)

    executed_queries = []

    async def fake_execute(query):
        executed_queries.append(query)
        m = MagicMock()
        m.scalars.return_value.all.return_value = [user1, user2]
        return m

    fake_db.execute = fake_execute

    ids = await chat_router._parse_mention_ids("Сообщение для @Иван Иванов", fake_db, org_id=5)
    assert ids == [101, 102]

    # Проверяем, что запрос содержал условие org_id
    q_str = str(executed_queries[0])
    assert "users.org_id" in q_str


# ---------------------------------------------------------------------------
# 4. feo_comments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_feo_comments_get_visibility_raises_404_when_invisible(monkeypatch):
    """get_comments_visibility вызывает ensure_subsidy_visible."""
    called = {}

    async def fake_ensure(user, sub_id, db):
        called["sub_id"] = sub_id
        raise HTTPException(404, "Субсидия не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_subsidy_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=1)

    with pytest.raises(HTTPException) as exc:
        await feo_comments_router.get_comments_visibility(subsidy_id=42, db=fake_db, current_user=user)
    assert exc.value.status_code == 404
    assert called["sub_id"] == 42


@pytest.mark.asyncio
async def test_feo_comments_get_counts_raises_404_when_invisible(monkeypatch):
    """get_comment_counts вызывает ensure_subsidy_visible."""
    called = {}

    async def fake_ensure(user, sub_id, db):
        called["sub_id"] = sub_id
        raise HTTPException(404, "Субсидия не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_subsidy_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=1)

    with pytest.raises(HTTPException) as exc:
        await feo_comments_router.get_comment_counts(subsidy_id=42, db=fake_db, current_user=user)
    assert exc.value.status_code == 404
    assert called["sub_id"] == 42


@pytest.mark.asyncio
async def test_feo_comments_list_comments_raises_404_when_invisible(monkeypatch):
    """list_comments загружает категорию и вызывает ensure_subsidy_visible."""
    fake_cat = SimpleNamespace(id=10, subsidy_id=99)

    async def fake_load_cat(db, cat_id):
        return fake_cat

    monkeypatch.setattr("app.routers.feo_comments._load_category", fake_load_cat)

    called = {}

    async def fake_ensure(user, sub_id, db):
        called["sub_id"] = sub_id
        raise HTTPException(404, "Субсидия не найдена")

    monkeypatch.setattr("app.auth.object_visibility.ensure_subsidy_visible", fake_ensure)

    fake_db = AsyncMock()
    user = SimpleNamespace(id=1)

    with pytest.raises(HTTPException) as exc:
        await feo_comments_router.list_comments(
            feo_planned_item_id=None, feo_category_id=10, db=fake_db, current_user=user
        )
    assert exc.value.status_code == 404
    assert called["sub_id"] == 99


# ---------------------------------------------------------------------------
# 5. task_comments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_comments_add_mention_scoped_by_owner_contour(monkeypatch):
    """task_comments.add_comment фильтрует пользователей через owner_scope_org_ids."""
    async def fake_ensure_task(user, tid, db):
        return SimpleNamespace(id=tid)

    monkeypatch.setattr("app.auth.object_visibility.ensure_task_visible", fake_ensure_task)

    scope_called = {}

    async def fake_owner_scope(user, db):
        scope_called["user_id"] = user.id
        return {3, 4}

    monkeypatch.setattr("app.auth.visibility.owner_scope_org_ids", fake_owner_scope)

    captured_queries = []
    fake_db = AsyncMock()

    async def fake_execute(statement, *args, **kwargs):
        captured_queries.append(statement)
        m = MagicMock()
        m.scalar_one_or_none.return_value = SimpleNamespace(id=1, assignees=[])
        m.scalars.return_value.all.return_value = [
            SimpleNamespace(id=50, username="sergey", full_name="Сергей Сергеев", org_id=3)
        ]
        return m

    fake_db.execute = fake_execute

    user = SimpleNamespace(id=10, role="employee", org_id=3, full_name="Илья", username="ilya")
    body = TaskCommentCreate(text="Проверь @sergey задачу")

    await task_comments_router.add_comment(task_id=100, body=body, db=fake_db, current_user=user)

    assert scope_called["user_id"] == 10
    user_queries = [str(q) for q in captured_queries if "users" in str(q).lower()]
    assert len(user_queries) >= 1
    assert "users.org_id" in user_queries[0]
