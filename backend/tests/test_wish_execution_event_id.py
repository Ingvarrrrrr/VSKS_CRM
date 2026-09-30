"""Жалоба владельца (30.09): согласующий (account_owner, заявка №92, submitted)
поставил «Мероприятие» в форме заявки, но оно не сохранилось. Причина —
фронтовая: поле event_id в карточке «Дополнительно» не имело НИКАКОГО пути
сохранения для согласующего, который не является assigned_to/admin (см.
frontend/src/components/wishes/WishFormDialog.vue — readonly не учитывал
canEditWishFeo, и не было автосохранения при смене значения; главная кнопка
«Сохранить» скрыта, т.к. isWishEditable=false на статусе submitted).

Бэкендовый гейт PATCH /wishes/{id}/execution (wish_transitions.py::
patch_wish_execution) для event_id уже был корректен ДО этой правки — тест
фиксирует именно это правило (ПРАВИЛО №6, тот же канал, что и у ФЭО):

  manager+ (MANAGER_ROLES) ИЛИ assigned_to ИЛИ участник цепочки согласования
  (wish_approvals) — пропускается для event_id (право wish.edit_feo тут ни при
  чём — оно гейтит только feo_category_id/items, см. комментарий в
  patch_wish_execution); любой другой (employee не из цепочки, не автор, не
  назначенный) — 403.
"""
import pytest
from app.models.event import Event
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.wish_approval import WishApproval


async def _seed_submitted_wish_with_events(db_session, test_org, author):
    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()

    event = Event(subsidy_id=subsidy.id, name="Мероприятие 1", org_id=test_org.id)
    db_session.add(event)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id,
        title="Заявка на согласовании",
        status="submitted",
        created_by=author.id,
        subsidy_id=subsidy.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w, event


@pytest.mark.asyncio
async def test_chain_approver_can_set_event_id_on_submitted_wish(client, db_session, test_org, test_user, make_user):
    """Согласующий из цепочки WishApproval (не автор, не assigned_to, не
    manager+) вправе поставить «Мероприятие» заявке на этапе submitted."""
    from app.auth.jwt import create_access_token

    w, event = await _seed_submitted_wish_with_events(db_session, test_org, test_user)

    approver = await make_user(role="employee", org_id=test_org.id)
    db_session.add(WishApproval(wish_id=w.id, user_id=approver.id, order_num=0, status="pending"))
    await db_session.commit()

    approver_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': approver.username, 'org_id': approver.org_id})}"
    }

    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"event_id": event.id},
        headers=approver_headers,
    )

    assert resp.status_code == 200, resp.text
    await db_session.refresh(w)
    assert w.event_id == event.id


@pytest.mark.asyncio
async def test_outsider_employee_cannot_set_event_id(client, db_session, test_org, test_user, make_user):
    """Сотрудник вне цепочки согласования, не автор, не assigned_to — 403,
    event_id заявки не меняется."""
    from app.auth.jwt import create_access_token

    w, event = await _seed_submitted_wish_with_events(db_session, test_org, test_user)

    outsider = await make_user(role="employee", org_id=test_org.id)
    outsider_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': outsider.username, 'org_id': outsider.org_id})}"
    }

    resp = await client.patch(
        f"/api/wishes/{w.id}/execution",
        json={"event_id": event.id},
        headers=outsider_headers,
    )

    assert resp.status_code == 403, resp.text
    await db_session.refresh(w)
    assert w.event_id != event.id
