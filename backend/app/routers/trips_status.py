"""
Trips — workflow-переходы статусов путевого листа (Phase 30-PR3).

Сосед app/routers/trips.py (Правило №5, резка монолита, сессия 2026-09-08).
ПЕРЕНЕСЕНО без изменений. Тот же префикс /api/trips. Все пути здесь
трёхсегментные (/{trip_id}/...) — конфликта с catch-all ядра GET /{trip_id}
нет (методы POST), порядок регистрации в app/routes.py относительно ядра
не важен.

Использует _load_trip_or_404 / _trip_to_dict из ядра (app.routers.trips) —
не дублирует их (Правило №6).

Endpoints:
  POST /api/trips/{trip_id}/tech-inspect       — created/draft → med_inspect
  POST /api/trips/{trip_id}/med-inspect        — med_inspect → in_progress
  POST /api/trips/{trip_id}/post-trip-mechanic — фиксация, статус не меняется
  POST /api/trips/{trip_id}/post-trip-doctor   — фиксация, статус не меняется
  POST /api/trips/{trip_id}/driver-sign        — in_progress → on_review
  POST /api/trips/{trip_id}/close              — on_review → closed
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab, require_action
from app.models.user import User
from app.schemas.waybill_workflow import (
    TechInspectIn, MedInspectIn, PostTripMechanicIn, PostTripDoctorIn, DriverSignIn,
)
from app.routers.trips import _load_trip_or_404, _trip_to_dict

router = APIRouter(prefix="/api/trips", tags=["vehicles"])

# Allowed status transitions map
_ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "created":      ["tech_inspect"],
    "draft":        ["tech_inspect"],  # legacy alias
    "tech_inspect": ["med_inspect"],
    "med_inspect":  ["in_progress"],
    "in_progress":  ["on_review"],    # via driver-sign
    "on_review":    ["closed"],
    # Terminal states — no outgoing transitions
    "closing":      [],
    "closed":       [],
    "overdue":      [],
    "rendered":     [],               # legacy
}


def _assert_status_transition(current: str, target: str) -> None:
    """Raise 422 if the transition from current → target is not allowed."""
    allowed = _ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_STATUS_TRANSITION",
                "message": f"Нельзя перевести из «{current}» в «{target}». "
                           f"Разрешённые переходы из «{current}»: {allowed or 'нет (конечный статус)'}",
            },
        )


# ─────────────────────── POST /{trip_id}/tech-inspect ───────────────────────

@router.post("/{trip_id}/tech-inspect")
async def tech_inspect(
    trip_id: int,
    body: TechInspectIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Механик подтверждает тех. осмотр (pre-trip). Status: created → med_inspect."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "tech_inspect")

    mechanic = await db.get(User, body.mechanic_id)
    if not mechanic:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Механик не найден"})

    trip.pre_trip_mechanic_id = body.mechanic_id
    trip.pre_trip_mechanic_inspected_at = body.inspected_at
    trip.pre_trip_mechanic_result = body.result
    trip.status = "med_inspect"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/med-inspect ────────────────────────

@router.post("/{trip_id}/med-inspect")
async def med_inspect(
    trip_id: int,
    body: MedInspectIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Медик подтверждает медосмотр (pre-trip). Status: med_inspect → in_progress."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "med_inspect")

    doctor = await db.get(User, body.doctor_id)
    if not doctor:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Медик не найден"})

    trip.pre_trip_doctor_id = body.doctor_id
    trip.pre_trip_doctor_inspected_at = body.inspected_at
    trip.pre_trip_doctor_result = body.result
    trip.status = "in_progress"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/post-trip-mechanic ─────────────────

@router.post("/{trip_id}/post-trip-mechanic")
async def post_trip_mechanic(
    trip_id: int,
    body: PostTripMechanicIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Послерейсовый механик. Фиксирует осмотр, статус НЕ меняется."""
    trip = await _load_trip_or_404(trip_id, db)

    mechanic = await db.get(User, body.mechanic_id)
    if not mechanic:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Механик не найден"})

    trip.post_trip_mechanic_id = body.mechanic_id
    trip.post_trip_mechanic_inspected_at = body.inspected_at
    trip.post_trip_mechanic_result = body.result

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/post-trip-doctor ───────────────────

@router.post("/{trip_id}/post-trip-doctor")
async def post_trip_doctor(
    trip_id: int,
    body: PostTripDoctorIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Послерейсовый медик. Фиксирует осмотр, статус НЕ меняется."""
    trip = await _load_trip_or_404(trip_id, db)

    doctor = await db.get(User, body.doctor_id)
    if not doctor:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Медик не найден"})

    trip.post_trip_doctor_id = body.doctor_id
    trip.post_trip_doctor_inspected_at = body.inspected_at
    trip.post_trip_doctor_result = body.result

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/driver-sign ────────────────────────

@router.post("/{trip_id}/driver-sign")
async def driver_sign(
    trip_id: int,
    body: DriverSignIn,
    current_user: User = Depends(require_tab("vehicles")),
    db: AsyncSession = Depends(get_db),
):
    """Водитель ставит электронную подпись. Status: in_progress → on_review."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "on_review")

    if not body.signature:
        raise HTTPException(422, detail={"code": "SIGNATURE_REQUIRED", "message": "Подпись обязательна"})

    trip.driver_signature = body.signature
    trip.driver_signed_at = body.signed_at
    trip.status = "on_review"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)


# ─────────────────────── POST /{trip_id}/close ──────────────────────────────

@router.post("/{trip_id}/close")
async def close_waybill(
    trip_id: int,
    current_user: User = Depends(require_action("vehicle.trip.create")),
    db: AsyncSession = Depends(get_db),
):
    """Диспетчер закрывает путевой лист. Status: on_review → closed."""
    trip = await _load_trip_or_404(trip_id, db)
    _assert_status_transition(trip.status, "closed")

    trip.status = "closed"

    await db.commit()
    await db.refresh(trip)
    return _trip_to_dict(trip)
