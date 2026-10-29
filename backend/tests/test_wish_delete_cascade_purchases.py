"""Тесты задачи владельца (29.10.2026): DELETE /api/wishes/{wish_id} удаляет
связанные закупки заявки, а не оставляет их осиротевшими.

До исправления: delete_wish звал _withdraw_wish_from_plan (прячет закупки
'plan_schedule' в статус 'wishes'), а саму заявку всё равно удалял —
purchases.wish_id обнулялся каскадом (ON DELETE SET NULL), закупки
'wishes'/'cancelled' оставались в базе осиротевшими и невидимыми.

После исправления (app/routers/wishes.py::delete_wish):
  - блокировка «закупка ушла дальше Плана закупок» СОХРАНЕНА — проверяется ДО
    любых мутаций (wish_purchase_delete_blockers, app/services/wish_access.py,
    тот же источник, что и у _withdraw_wish_from_plan, ПРАВИЛО №6);
  - если блокировки нет — ВСЕ связанные закупки (любого статуса, не только
    plan_schedule) удаляются через delete_purchase_core
    (app/routers/purchases.py), та же реализация, что у DELETE /api/purchases/{id}
    и у сброса разбивки (wish_distribution_reset.py)."""
import pytest
from sqlalchemy import select
from app.models.wish import Wish
from app.models.purchase import Purchase


async def _make_draft_wish(db_session, test_org, test_user, title="Тестовая заявка"):
    w = Wish(
        org_id=test_org.id,
        title=title,
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


async def _make_purchase(db_session, wish_id, status, item_name="Товар"):
    p = Purchase(
        wish_id=wish_id,
        status=status,
        item_name=item_name,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _purchases_of(db_session, wish_id):
    res = await db_session.execute(select(Purchase).where(Purchase.wish_id == wish_id))
    return res.scalars().all()


@pytest.mark.asyncio
async def test_delete_wish_deletes_unblocked_purchases(
    client, db_session, auth_headers, test_org, test_user,
):
    """(а) Заявка с закупками в plan_schedule/wishes/cancelled — ни одна не
    блокирует удаление (все статусы ДО «Плана закупок» включительно либо
    отменены). Удаление заявки удаляет и все эти закупки."""
    w = await _make_draft_wish(db_session, test_org, test_user)
    p_plan = await _make_purchase(db_session, w.id, "plan_schedule")
    p_wishes = await _make_purchase(db_session, w.id, "wishes")
    p_cancelled = await _make_purchase(db_session, w.id, "cancelled")

    resp = await client.delete(f"/api/wishes/{w.id}", headers=auth_headers)
    assert resp.status_code == 204, resp.text

    # Заявка удалена.
    res = await db_session.execute(select(Wish).where(Wish.id == w.id))
    assert res.scalar_one_or_none() is None

    # Все три закупки удалены — не осиротели, не остались скрытыми.
    for pid in (p_plan.id, p_wishes.id, p_cancelled.id):
        res = await db_session.execute(select(Purchase).where(Purchase.id == pid))
        assert res.scalar_one_or_none() is None, f"purchase {pid} should be deleted"


@pytest.mark.asyncio
async def test_delete_wish_blocked_by_contracted_purchase_deletes_nothing(
    client, db_session, auth_headers, test_org, test_user,
):
    """(б) Закупка ушла дальше «Плана закупок» (contracted) — удаление
    заявки запрещено (409 с перечнем закупок-стадий), заявка и ВСЕ её
    закупки (включая не блокирующие) остаются нетронутыми — проверка идёт
    до любых мутаций, частичного удаления не бывает."""
    w = await _make_draft_wish(db_session, test_org, test_user)
    p_ok = await _make_purchase(db_session, w.id, "wishes")
    p_blocking = await _make_purchase(db_session, w.id, "contracted")

    resp = await client.delete(f"/api/wishes/{w.id}", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    body = resp.json()
    detail = body.get("detail") or body.get("message") or ""
    assert "отмените её в реестре закупок" in detail, body

    # Заявка жива.
    res = await db_session.execute(select(Wish).where(Wish.id == w.id))
    assert res.scalar_one_or_none() is not None

    # Обе закупки живы — частичного удаления не было.
    remaining_ids = {p.id for p in await _purchases_of(db_session, w.id)}
    assert remaining_ids == {p_ok.id, p_blocking.id}


@pytest.mark.asyncio
async def test_delete_wish_without_purchases_still_works(
    client, db_session, auth_headers, test_org, test_user,
):
    """Заявка без единой закупки — удаляется как раньше (регресс-проверка:
    новая логика не требует наличия закупок)."""
    w = await _make_draft_wish(db_session, test_org, test_user)

    resp = await client.delete(f"/api/wishes/{w.id}", headers=auth_headers)
    assert resp.status_code == 204, resp.text

    res = await db_session.execute(select(Wish).where(Wish.id == w.id))
    assert res.scalar_one_or_none() is None
