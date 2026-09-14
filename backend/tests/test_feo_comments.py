"""Волна 4, п.16 владельца (2026-09-13): «Должна быть возможность оставлять
комментарии... отображается, кто оставил комментарий и когда, и текст
комментария, и на него должна быть возможность ответить» — плановые позиции
ФЭО (FeoPlannedItem) и узлы дерева ФЭО (FeoCategory), см. app/models/
feo_comment.py и app/routers/feo_comments.py.

Узлы:
  - добавление комментария к плановой позиции;
  - ответ на комментарий (ветка связывается через parent_id);
  - комментарий к категории;
  - чужой пользователь без доступа не может добавить (403);
  - удаление плановой позиции не оставляет висячих комментариев (ON DELETE
    CASCADE на feo_comments.feo_planned_item_id — проверяем реальным DELETE
    через HTTP, не просто читая схему миграции);
  - переключатель видимости комментариев субсидии (GET/PUT /settings).

HTTP-интеграционные тесты (client + db_session, реальная БД — см. docstring
conftest.py про транзакционную изоляцию). superadmin_headers используется там,
где интересует сама функциональность (superadmin проходит
_check_planned_item_write_access/_can_edit_feo_origin без завязки на
конкретные сиды прав в БД-копии прода) — тест доступа НАРОЧНО не полагается на
то, что у роли employee реально нет вкладок wishes/purchases в этой БД (сиды
могли измениться), а монkeyпатчит has_org_key/_has_key_in_any_org НА САМОМ
МОДУЛЕ app.routers.feo_planned_items — там, где _check_planned_item_write_access
их реально вызывает (импорт верхнего уровня, не локальный `from ... import`
внутри функции, поэтому патчить нужно именно этот модуль, а не
app.auth.permissions — см. по контрасту test_feo_category_write_gate.py).

Флейк pytest-asyncio «different loop» (см. tests/conftest.py) — гонять КАЖДЫЙ
тест ПО ОТДЕЛЬНОСТИ: pytest tests/test_feo_comments.py::<name>.
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.feo_comment import FeoComment
from app.routers import feo_planned_items as fpi_module


async def _make_subsidy(db_session):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidy-{uuid.uuid4().hex[:8]}",
        year=2026,
        budget=1_000_000,
        require_planned_dates=False,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_category(db_session, subsidy_id, **kwargs):
    from app.models.feo_category import FeoCategory
    cat = FeoCategory(
        subsidy_id=subsidy_id,
        parent_id=None,
        level=1,
        name=kwargs.pop("name", f"Cat-{uuid.uuid4().hex[:8]}"),
        **kwargs,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return cat


async def _make_planned_item(db_session, feo_category_id, name="Позиция теста"):
    from decimal import Decimal
    from app.models.feo_planned_item import FeoPlannedItem
    item = FeoPlannedItem(
        feo_category_id=feo_category_id,
        name=name,
        quantity=Decimal("1"),
        unit="шт",
        amount=Decimal("1000"),
        is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def _deny_all_permissions(monkeypatch):
    """«Чужой пользователь без доступа» — гарантированно без права, независимо
    от того, что реально насеяно в role_permissions копии прода (см. докстринг
    файла): монkeyпатчим ИМЕННО на app.routers.feo_planned_items, где
    _check_planned_item_write_access их вызывает по импортированному верхнеуровнево
    имени."""
    async def _fake_has_org_key(*args, **kwargs):
        return False

    async def _fake_has_key_in_any_org(*args, **kwargs):
        return False

    monkeypatch.setattr(fpi_module, "has_org_key", _fake_has_org_key)
    monkeypatch.setattr(fpi_module, "_has_key_in_any_org", _fake_has_key_in_any_org)


@pytest.mark.asyncio
async def test_add_comment_to_planned_item(client, db_session, superadmin_headers):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id)

    resp = await client.post(
        "/api/feo-comments/",
        json={"feo_planned_item_id": item.id, "text": "Проверьте, пожалуйста, эту позицию"},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["feo_planned_item_id"] == item.id
    assert body["feo_category_id"] is None
    assert body["parent_id"] is None
    assert body["text"] == "Проверьте, пожалуйста, эту позицию"
    assert body["author_name"]

    listed = await client.get(
        f"/api/feo-comments/?feo_planned_item_id={item.id}", headers=superadmin_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_reply_links_to_parent(client, db_session, superadmin_headers):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id)

    root = await client.post(
        "/api/feo-comments/",
        json={"feo_planned_item_id": item.id, "text": "Исходный комментарий"},
        headers=superadmin_headers,
    )
    assert root.status_code == 200, root.text
    root_id = root.json()["id"]

    reply = await client.post(
        f"/api/feo-comments/{root_id}/reply",
        json={"text": "Ответ на комментарий"},
        headers=superadmin_headers,
    )
    assert reply.status_code == 200, reply.text
    reply_body = reply.json()
    assert reply_body["parent_id"] == root_id
    # Ответ наследует привязку к сущности от родителя, а не из тела запроса.
    assert reply_body["feo_planned_item_id"] == item.id
    assert reply_body["feo_category_id"] is None

    thread = (await client.get(
        f"/api/feo-comments/?feo_planned_item_id={item.id}", headers=superadmin_headers,
    )).json()
    assert len(thread) == 2
    ids = {c["id"] for c in thread}
    assert root_id in ids and reply_body["id"] in ids


@pytest.mark.asyncio
async def test_add_comment_to_category(client, db_session, superadmin_headers):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)

    resp = await client.post(
        "/api/feo-comments/",
        json={"feo_category_id": cat.id, "text": "Комментарий на уровне категории"},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["feo_category_id"] == cat.id
    assert body["feo_planned_item_id"] is None

    listed = await client.get(
        f"/api/feo-comments/?feo_category_id={cat.id}", headers=superadmin_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_add_comment_denied_without_access(client, db_session, test_user, auth_headers, monkeypatch):
    _deny_all_permissions(monkeypatch)
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id)

    resp = await client.post(
        "/api/feo-comments/",
        json={"feo_planned_item_id": item.id, "text": "Попытка постороннего"},
        headers=auth_headers,
    )
    assert resp.status_code == 403, resp.text

    # В БД ничего не осело.
    rows = (await db_session.execute(
        select(FeoComment).where(FeoComment.feo_planned_item_id == item.id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_planned_item_removes_comments(client, db_session, superadmin_headers):
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)
    item = await _make_planned_item(db_session, cat.id)

    add_resp = await client.post(
        "/api/feo-comments/",
        json={"feo_planned_item_id": item.id, "text": "Комментарий перед удалением позиции"},
        headers=superadmin_headers,
    )
    assert add_resp.status_code == 200, add_resp.text
    comment_id = add_resp.json()["id"]

    del_resp = await client.delete(f"/api/feo-planned-items/{item.id}", headers=superadmin_headers)
    assert del_resp.status_code == 200, del_resp.text

    # ON DELETE CASCADE на feo_comments.feo_planned_item_id — комментарий не
    # остался висячей ссылкой на удалённую позицию.
    remaining = (await db_session.execute(
        select(FeoComment).where(FeoComment.id == comment_id)
    )).scalar_one_or_none()
    assert remaining is None


@pytest.mark.asyncio
async def test_comment_counts_by_subsidy(client, db_session, superadmin_headers):
    """Один запрос на субсидию (см. докстринг get_comment_counts в
    routers/feo_comments.py) — счётчик у категории с комментарием и у
    плановой позиции с комментарием, по каждому entity-типу отдельно."""
    subsidy = await _make_subsidy(db_session)
    cat_with_comment = await _make_category(db_session, subsidy.id, name="С комментарием")
    cat_empty = await _make_category(db_session, subsidy.id, name="Без комментариев")
    item_with_comment = await _make_planned_item(db_session, cat_empty.id, name="Позиция с комментарием")
    item_empty = await _make_planned_item(db_session, cat_empty.id, name="Позиция без комментариев")

    root = await client.post(
        "/api/feo-comments/",
        json={"feo_category_id": cat_with_comment.id, "text": "Комментарий к направлению"},
        headers=superadmin_headers,
    )
    assert root.status_code == 200, root.text
    root_id = root.json()["id"]
    reply = await client.post(
        f"/api/feo-comments/{root_id}/reply",
        json={"text": "Ответ на комментарий к направлению"},
        headers=superadmin_headers,
    )
    assert reply.status_code == 200, reply.text

    item_resp = await client.post(
        "/api/feo-comments/",
        json={"feo_planned_item_id": item_with_comment.id, "text": "Комментарий к позиции"},
        headers=superadmin_headers,
    )
    assert item_resp.status_code == 200, item_resp.text

    counts_resp = await client.get(
        f"/api/feo-comments/counts?subsidy_id={subsidy.id}", headers=superadmin_headers,
    )
    assert counts_resp.status_code == 200, counts_resp.text
    body = counts_resp.json()

    # Категория с комментарием+ответом — счётчик 2 (корневой + ответ, то же
    # множество строк, что вернул бы GET /?feo_category_id=...).
    assert body["category_counts"][str(cat_with_comment.id)] == 2
    # Плановая позиция с одним комментарием — счётчик 1.
    assert body["planned_item_counts"][str(item_with_comment.id)] == 1

    # Сущность без комментариев — её нет в ответе ИЛИ счётчик 0 (оба варианта
    # допустимы по контракту, см. докстринг FeoCommentCountsOut).
    assert body["category_counts"].get(str(cat_empty.id), 0) == 0
    assert body["planned_item_counts"].get(str(item_empty.id), 0) == 0


@pytest.mark.asyncio
async def test_comment_counts_update_after_add(client, db_session, superadmin_headers):
    """Добавление комментария сразу меняет счётчик — без этого владелец
    увидел бы «0» там, где только что написал (жалоба, см. задачу)."""
    subsidy = await _make_subsidy(db_session)
    cat = await _make_category(db_session, subsidy.id)

    before = (await client.get(
        f"/api/feo-comments/counts?subsidy_id={subsidy.id}", headers=superadmin_headers,
    )).json()
    assert before["category_counts"].get(str(cat.id), 0) == 0

    add_resp = await client.post(
        "/api/feo-comments/",
        json={"feo_category_id": cat.id, "text": "Новый комментарий"},
        headers=superadmin_headers,
    )
    assert add_resp.status_code == 200, add_resp.text

    after = (await client.get(
        f"/api/feo-comments/counts?subsidy_id={subsidy.id}", headers=superadmin_headers,
    )).json()
    assert after["category_counts"][str(cat.id)] == 1


@pytest.mark.asyncio
async def test_comment_counts_denied_without_auth(client, db_session, superadmin_headers):
    """«Чужой пользователь без доступа получает отказ» — счётчики читаются
    ТЕМ ЖЕ гейтом, что и list_comments/get_comments_visibility (только
    get_current_user, см. докстринг get_comment_counts), поэтому здесь нет
    отдельной орг-проверки для авторизованного пользователя другой орги —
    единственный реальный отказ этого гейта — отсутствие/невалидность токена.
    Не изобретаем более строгий гейт только ради этого теста (ПРАВИЛО №6:
    не заводить второй механизм проверки прав чтения)."""
    subsidy = await _make_subsidy(db_session)
    await _make_category(db_session, subsidy.id)

    resp = await client.get(f"/api/feo-comments/counts?subsidy_id={subsidy.id}")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_comments_visibility_toggle(client, db_session, superadmin_headers):
    subsidy = await _make_subsidy(db_session)

    # По умолчанию (строки настройки ещё нет) — видимость включена.
    default_resp = await client.get(
        f"/api/feo-comments/settings?subsidy_id={subsidy.id}", headers=superadmin_headers,
    )
    assert default_resp.status_code == 200
    assert default_resp.json()["comments_visible"] is True

    off_resp = await client.put(
        "/api/feo-comments/settings",
        json={"subsidy_id": subsidy.id, "comments_visible": False},
        headers=superadmin_headers,
    )
    assert off_resp.status_code == 200
    assert off_resp.json()["comments_visible"] is False

    check_resp = await client.get(
        f"/api/feo-comments/settings?subsidy_id={subsidy.id}", headers=superadmin_headers,
    )
    assert check_resp.json()["comments_visible"] is False

    on_resp = await client.put(
        "/api/feo-comments/settings",
        json={"subsidy_id": subsidy.id, "comments_visible": True},
        headers=superadmin_headers,
    )
    assert on_resp.json()["comments_visible"] is True
