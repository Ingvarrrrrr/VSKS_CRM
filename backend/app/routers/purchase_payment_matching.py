"""Разнесение казначейских платежей по группам закупок (товары/услуги отдельно).

Вынесено из app/routers/purchases.py (Правило №5, модульность) без изменения
поведения (кроме удаления заведомо недостижимого `return stats` в конце
match_payments_endpoint — см. отчёт задачи, dead code после `return report`).

Сервисный слой — app/services/payment_target.py (группы + подозрительные
дубли) и app/services/payment_lookup.py (поиск кандидатов + attach). Права —
subsidy.edit конкретной субсидии, тот же гейт, что у мероприятий
(events.py::_get_subsidy_for_events) и импорта закупок.

GET /payment-groups и GET /payment-candidates зарегистрированы в
app/routes.py ДО purchases.router — иначе Starlette матчит их на catch-all
"/{pid}" (pid: int) и падает с 422, так и не доходя до нужного роута.
POST-версии (attach-payments, match-payments) этой проблемы не имеют —
совпадающего по методу и глубине пути "/{pid}" на POST нет.
"""
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.auth.jwt import get_current_user
from app.auth.permissions import has_org_key

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


async def _get_subsidy_for_payments(sid: int, db: AsyncSession, current_user) -> Subsidy:
    s = await db.get(Subsidy, sid)
    if not s:
        raise HTTPException(404, "Субсидия не найдена")
    if not await has_org_key(current_user, db, s.org_id, 'subsidy.edit', subsidy_id=sid):
        raise HTTPException(
            403,
            "Разнесение платежей доступно только тому, у кого есть право редактировать субсидию",
        )
    return s


def _payment_group_to_dict(g) -> dict:
    return {
        "group_key": g.group_key,
        "subsidy_id": g.subsidy_id,
        "registry_number": g.registry_number,
        "contract_number": g.contract_number,
        "is_framework": g.is_framework,
        "contractor_id": g.contractor_id,
        "contractor_inn": g.contractor_inn,
        "contractor_name": g.contractor_name,
        "goods_amount": float(g.goods_amount),
        "services_amount": float(g.services_amount),
        "unspecified_amount": float(g.unspecified_amount),
        "purchase_ids": g.purchase_ids,
        "payments": [
            {
                "id": p.id,
                "purchase_id": p.purchase_id,
                "amount": float(p.amount) if p.amount is not None else None,
                "document_number": p.document_number,
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                "basis_label": p.basis_label,
                "expense_code": p.expense_code,
            }
            for p in g.payments
        ],
    }


def _suspicious_group_to_dict(s) -> dict:
    return {
        "registry_number": s.registry_number,
        "purchase_ids": s.purchase_ids,
        "row_count": s.row_count,
        "shared_amount": float(s.shared_amount) if s.shared_amount is not None else None,
        "reason": s.reason,
    }


def _payment_candidate_to_dict(c) -> dict:
    return {
        "bank_payment_id": c.bank_payment_id,
        "amount": float(c.amount),
        "kind": c.kind,
        "checks": c.checks,
        "auto": c.auto,
        "free": c.free,
        "reason": c.reason,
        "basis_label": c.basis_label,
        "payment_number": c.payment_number,
        "payment_date": c.payment_date.isoformat() if c.payment_date else None,
    }


@router.get("/payment-groups")
async def list_payment_groups(
    subsidy_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Группы оплаты по закупкам субсидии (Этап 4) + отчёт «подозрительные
    дубли», которые в группировку не попали — их надо разобрать вручную сначала."""
    await _get_subsidy_for_payments(subsidy_id, db, current_user)
    from app.services.payment_target import build_groups, suspicious_groups

    groups = await build_groups(db, subsidy_id)
    susp = await suspicious_groups(db, subsidy_id=subsidy_id)
    return {
        "groups": [_payment_group_to_dict(g) for g in groups],
        "suspicious": [_suspicious_group_to_dict(s) for s in susp],
    }


@router.get("/payment-candidates")
async def list_payment_candidates(
    subsidy_id: int = Query(...),
    group_key: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Кандидаты-платежи для одной группы (Этап 5), раздельно по товарной и
    сервисной сумме — см. app/services/payment_lookup.py::find_candidates."""
    await _get_subsidy_for_payments(subsidy_id, db, current_user)
    from app.services.payment_target import find_group
    from app.services.payment_lookup import find_candidates

    group = await find_group(db, subsidy_id, group_key)
    if not group:
        raise HTTPException(404, "Группа не найдена — пересчитайте /api/purchases/payment-groups")

    cands = await find_candidates(db, group)
    return {
        "goods": [_payment_candidate_to_dict(c) for c in cands["goods"]],
        "services": [_payment_candidate_to_dict(c) for c in cands["services"]],
    }


@router.get("/{pid}/payment-candidates")
async def list_purchase_payment_candidates(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Тонкая обёртка над /payment-candidates (Этап 7б) для карточки закупки —
    кнопка «Найти платежи в реестре» в PaymentsBlock.vue: находит группу
    (см. app/services/payment_target.py::build_groups), содержащую ЭТУ закупку,
    без явного group_key, и отдаёт кандидатов, как и общий эндпоинт."""
    p = await db.get(Purchase, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if not p.subsidy_id:
        return {"group": None, "goods": [], "services": [], "reason": "у закупки не указана субсидия"}
    await _get_subsidy_for_payments(p.subsidy_id, db, current_user)
    from app.services.payment_target import build_groups
    from app.services.payment_lookup import find_candidates

    groups = await build_groups(db, p.subsidy_id)
    group = next((g for g in groups if pid in g.purchase_ids), None)
    if not group:
        return {
            "group": None, "goods": [], "services": [],
            "reason": "закупка не входит ни в одну группу оплаты — либо у неё нет "
                      "реестрового номера, либо она попала в «подозрительные дубли» "
                      "(см. /api/purchases/payment-groups) и требует ручного разбора",
        }
    cands = await find_candidates(db, group)
    return {
        "group": _payment_group_to_dict(group),
        "goods": [_payment_candidate_to_dict(c) for c in cands["goods"]],
        "services": [_payment_candidate_to_dict(c) for c in cands["services"]],
    }


class AttachPaymentsRequest(BaseModel):
    subsidy_id: int
    group_key: str
    bank_payment_ids: List[int]
    allocations: Optional[dict] = None   # {purchase_id: amount}, только для одного bank_payment_id


@router.post("/attach-payments")
async def attach_payments_endpoint(
    data: AttachPaymentsRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Явная загрузка платежей в группу — Этап 5. bank_payment_ids обычно один
    элемент (кандидат, выбранный вручную или auto-предложенный), но можно
    передать несколько сразу (каждый станет отдельной Payment-записью)."""
    await _get_subsidy_for_payments(data.subsidy_id, db, current_user)
    from app.services.payment_target import find_group
    from app.services.payment_lookup import attach, PaymentAttachError

    group = await find_group(db, data.subsidy_id, data.group_key)
    if not group:
        raise HTTPException(404, "Группа не найдена — пересчитайте /api/purchases/payment-groups")

    allocations = None
    if data.allocations:
        allocations = {int(k): Decimal(str(v)) for k, v in data.allocations.items()}

    try:
        created = await attach(db, group, data.bank_payment_ids, allocations=allocations)
    except PaymentAttachError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc))

    await db.commit()
    return {
        "created": [
            {
                "id": p.id,
                "purchase_id": p.purchase_id,
                "amount": float(p.amount) if p.amount is not None else None,
                "bank_payment_id": p.bank_payment_id,
                "basis_label": p.basis_label,
            }
            for p in created
        ]
    }


@router.post("/match-payments")
async def match_payments_endpoint(
    subsidy_id: int = Query(...),
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Прогон по субсидии (Этап 5): для каждой группы и каждой её суммы
    (товары/услуги) авто-разносит РОВНО ОДНОГО свободного кандидата, если он
    единственный (см. find_candidates — auto=True); неоднозначные и ненайденные
    остаются в отчёте без изменений. dry_run=true (умолчание) — ничего не
    пишет, только считает, что было бы сделано."""
    await _get_subsidy_for_payments(subsidy_id, db, current_user)
    from app.services.payment_target import build_groups, suspicious_groups
    from app.services.payment_lookup import find_candidates, attach, PaymentAttachError

    groups = await build_groups(db, subsidy_id)
    susp = await suspicious_groups(db, subsidy_id=subsidy_id)

    report = {
        "subsidy_id": subsidy_id,
        "dry_run": dry_run,
        "groups_total": len(groups),
        "attached": [],
        "ambiguous": [],
        "not_found": [],
        "suspicious": [_suspicious_group_to_dict(s) for s in susp],
    }

    for g in groups:
        cands = await find_candidates(db, g)
        group_attached: list[dict] = []
        group_ambiguous: list[dict] = []
        group_had_target = False

        for kind in ("goods", "services"):
            kind_amount = g.goods_amount if kind == "goods" else g.services_amount
            if not kind_amount:
                continue
            group_had_target = True
            kind_cands = cands.get(kind, [])
            auto_cand = next((c for c in kind_cands if c.auto), None)

            if auto_cand:
                if dry_run:
                    group_attached.append({
                        "kind": kind, "bank_payment_id": auto_cand.bank_payment_id,
                        "amount": float(auto_cand.amount), "basis_label": auto_cand.basis_label,
                    })
                else:
                    try:
                        created = await attach(db, g, [auto_cand.bank_payment_id])
                        group_attached.append({
                            "kind": kind, "bank_payment_id": auto_cand.bank_payment_id,
                            "amount": float(auto_cand.amount), "basis_label": auto_cand.basis_label,
                            "payment_ids": [p.id for p in created],
                        })
                    except PaymentAttachError as exc:
                        await db.rollback()
                        group_ambiguous.append({"kind": kind, "reason": str(exc)})
            elif kind_cands:
                reasons = sorted({c.reason for c in kind_cands if c.reason} or {"нет свободного кандидата"})
                group_ambiguous.append({"kind": kind, "reason": "; ".join(reasons)})

        if group_attached:
            report["attached"].append({
                "group_key": g.group_key, "registry_number": g.registry_number, "items": group_attached,
            })
        if group_ambiguous:
            report["ambiguous"].append({
                "group_key": g.group_key, "registry_number": g.registry_number, "items": group_ambiguous,
            })
        if group_had_target and not group_attached and not group_ambiguous:
            report["not_found"].append({"group_key": g.group_key, "registry_number": g.registry_number})

    if not dry_run:
        await db.commit()

    return report
