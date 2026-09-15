"""Остановка/возобновление ЗАКУПКИ напрямую (владелец, 2026-09-15).

Отдельный модуль (Правило №5 — purchases.py и так огромный). Дополняет уже
существующую остановку ЗАЯВКИ (POST /api/wishes/{wish_id}/stop,
app/routers/wish_transitions.py) — та каскадом останавливает закупки, ещё не
дошедшие до договора; здесь тот же результат (Purchase.stopped_at/
stopped_by/stopped_reason), но действие целиком на самой закупке, доступное
и из списка «Закупки», и с карточки закупки, плюс обратная операция
(возобновить), которой у заявки нет.

Права: «останавливать могут все, кто видит закупку» — тот же принцип, что и
у заявки. GET /api/purchases/{id} у этого проекта не гейтится org_filter
(см. докстринг _has_purchase_write_access в purchases.py: «GET /{pid} вообще
без auth — кто смог прочесть, тот может и сохранить»); PUT/PATCH закупки
проверяют доступ через ту же _has_purchase_write_access — реиспользуем её
здесь, а не заводим вторую проверку (ПРАВИЛО №6).

Граница «на какой стадии уже нельзя остановить» — ОДНА функция
app.services.purchase_stop.can_stop_purchase, общая с каскадом из
wish_transitions.py::stop_wish (ПРАВИЛО №6 — не копировать формулу).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User
from app.routers.purchases import _has_purchase_write_access, load_purchase_for_out
from app.schemas.purchases import PurchaseStop
from app.schemas.schemas import PurchaseOutFull
from app.services.purchase_stop import can_stop_purchase

router = APIRouter(prefix="/api/purchases", tags=["purchase-stop"])


async def _load_full_purchase_out(pid: int, db: AsyncSession) -> PurchaseOutFull:
    """Единый сериализатор ответа — тот же путь, что и GET /api/purchases/{pid}
    (ПРАВИЛО №6), но БЕЗ побочных silent-recompute/unseen_fields блоков GET —
    здесь достаточно карточки данных с обновлёнными stopped_* полями."""
    from app.services.purchase_serializers import _purchase_to_full
    from app.models.contractor import Contractor
    from app.models.subsidy import Subsidy
    from sqlalchemy import select

    p = await load_purchase_for_out(db, pid)
    subsidies_r = await db.execute(select(Subsidy))
    subsidies = {s.id: s.name for s in subsidies_r.scalars().all()}
    contractors_r = await db.execute(select(Contractor))
    contractors_list = contractors_r.scalars().all()
    contractors = {c.id: c.name for c in contractors_list}
    contractor_inns = {c.id: c.inn for c in contractors_list}
    su_map: dict = {}
    if p.stopped_by and p.stopped_by_user:
        su_map = {p.stopped_by: (p.stopped_by_user.full_name or p.stopped_by_user.username)}
    from app.services.purchase_amounts import load_purchase_amounts
    amounts_map = await load_purchase_amounts(db, [p.id])
    return _purchase_to_full(
        p, contractors, subsidies, contractor_inns=contractor_inns,
        su_map=su_map, amounts_map=amounts_map, contract=p.contract,
    )


@router.post("/{pid}/stop", response_model=PurchaseOutFull)
async def stop_purchase(
    pid: int,
    body: PurchaseStop,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Остановить закупку напрямую (не через заявку). Не удаляет данные —
    только stopped_at/stopped_by/stopped_reason (stopped_wish_id НЕ трогаем —
    это поле только для остановки каскадом от заявки, см. модель)."""
    p = await load_purchase_for_out(db, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Закупка не найдена")

    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(status_code=403, detail="Нет доступа к этой закупке")

    can_stop, reason = can_stop_purchase(p)
    if not can_stop:
        raise HTTPException(status_code=409, detail=reason)

    p.stopped_at = datetime.now(timezone.utc)
    p.stopped_by = current_user.id
    p.stopped_reason = (body.reason if body else None) or None
    await db.commit()

    return await _load_full_purchase_out(pid, db)


@router.post("/{pid}/resume", response_model=PurchaseOutFull)
async def resume_purchase(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Снять остановку закупки (обратная операция — у заявки такой нет,
    владелец просил именно для закупки)."""
    p = await load_purchase_for_out(db, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Закупка не найдена")

    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(status_code=403, detail="Нет доступа к этой закупке")

    if p.stopped_at is None:
        raise HTTPException(status_code=409, detail="Закупка не остановлена")

    p.stopped_at = None
    p.stopped_by = None
    p.stopped_reason = None
    p.stopped_wish_id = None
    await db.commit()

    return await _load_full_purchase_out(pid, db)
