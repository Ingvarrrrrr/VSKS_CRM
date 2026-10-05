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

# ---------------------------------------------------------------------------
# НДС по выгрузке платежей (владелец, 2026-09-26): «если в платежах НДС
# указан другой, то об этом надо сообщать, давать ссылки на закупки, где не
# соответствует НДС, и предлагать приравнять НДС тому, что в выгрузках
# платежей». Вся логика сверки — app/services/purchase_vat_check.py (ПРАВИЛО
# №6, единственное место). Роутер здесь только потому, что этот файл уже
# зарегистрирован в routes.py ДО catch-all purchases.router (см. докстринг
# файла) — не заводим третий payments-роутер.
#
# "/vat-payment-mismatches" — статический одно-сегментный путь, коллизии с
# "/{pid}/payment-candidates" (двухсегментным) в этом же роутере нет; ставим
# его раньше "/{pid}/..." путей на всякий случай (порядок регистрации внутри
# одного APIRouter имеет значение при совпадении числа сегментов, здесь не
# совпадает, но так нагляднее).
# ---------------------------------------------------------------------------


@router.get("/vat-payment-mismatches")
async def list_vat_payment_mismatches(
    subsidy_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.services.purchase_vat_check import find_vat_mismatches
    return await find_vat_mismatches(db, current_user, subsidy_id=subsidy_id)


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
        "service_period": c.service_period,
        "service_period_conflict": c.service_period_conflict,
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
    # Задача 04.10.2026 («Помесячные платежи — разные месяцы»): необязательный
    # явный выбор месяца оказания человеком — {purchase_id: "YYYY-MM-DD"}, нужен,
    # когда app/services/payment_service_period.py не смог определить месяц сам
    # (409 от attach с текстом про месяц) — см. ServicePeriodConflict-паттерн.
    service_periods: Optional[dict] = None


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
    from app.services.payment_lookup import attach, PaymentAttachError, ServicePeriodAttachConflict
    from app.services.payment_service_period import service_period_conflict_detail

    group = await find_group(db, data.subsidy_id, data.group_key)
    if not group:
        raise HTTPException(404, "Группа не найдена — пересчитайте /api/purchases/payment-groups")

    allocations = None
    if data.allocations:
        allocations = {int(k): Decimal(str(v)) for k, v in data.allocations.items()}

    service_periods = None
    if data.service_periods:
        from datetime import date as _dt_date
        service_periods = {
            int(k): (v if isinstance(v, _dt_date) else _dt_date.fromisoformat(str(v)))
            for k, v in data.service_periods.items()
        }

    # Доработка плана 2026-10-04-fadm-statement: ручная привязка пары, отклонённой
    # ранее при подтверждении «Оплачено», разрешена — attach() дописывает сюда
    # предупреждение, не блокирует запись (см. app/services/payment_lookup.py).
    warnings: list[str] = []
    try:
        created = await attach(
            db, group, data.bank_payment_ids, allocations=allocations, service_periods=service_periods,
            warnings_out=warnings,
        )
    except ServicePeriodAttachConflict as exc:
        await db.rollback()
        raise HTTPException(409, service_period_conflict_detail(str(exc), exc.purchase_id, exc.occupied_period))
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
        ],
        "warnings": warnings,
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

    # Задача 05.10.2026 («три расширения штатного сопоставления»): группы,
    # которые простой пасс выше не закрыл (not_found/ambiguous — обычный
    # find_candidates ищет РОВНО ОДИН платёж на ВСЮ сумму группы), донабираются
    # помесячным/рамочным/авансовым поиском — см.
    # app/services/payment_lookup_multi.py (ПРАВИЛО №6: пишет туда же, через
    # тот же attach()).
    from app.services.payment_lookup_multi import match_monthly, match_framework, match_advance

    handled_keys = {a["group_key"] for a in report["attached"]}
    pending_groups = [g for g in groups if g.group_key not in handled_keys]

    purchase_ids_all = [pid for g in pending_groups for pid in g.purchase_ids]
    purchases_by_id = {}
    if purchase_ids_all:
        purchase_rows = (await db.execute(
            select(Purchase).where(Purchase.id.in_(purchase_ids_all))
        )).scalars().all()
        purchases_by_id = {p.id: p for p in purchase_rows}

    multi_report = {
        "monthly": {"attached": [], "ambiguous": []},
        "framework": {"attached": [], "ambiguous": []},
        "advance": {"attached": [], "ambiguous": []},
    }

    for g in pending_groups:
        monthly_purchase = next(
            (purchases_by_id[pid] for pid in g.purchase_ids if purchases_by_id.get(pid) and purchases_by_id[pid].is_monthly_payment),
            None,
        )
        if monthly_purchase is not None:
            r = await match_monthly(db, g, monthly_purchase, dry_run=dry_run)
            multi_report["monthly"]["attached"].extend(
                {**item, "group_key": g.group_key} for item in r["attached"]
            )
            multi_report["monthly"]["ambiguous"].extend(
                {**item, "group_key": g.group_key} for item in r["ambiguous"]
            )

    framework_groups = [g for g in pending_groups if g.is_framework]
    if framework_groups:
        r = await match_framework(db, framework_groups, dry_run=dry_run)
        multi_report["framework"]["attached"].extend(r["attached"])
        multi_report["framework"]["ambiguous"].extend(r["ambiguous"])

    advance_pairs = []
    for g in pending_groups:
        adv_purchase = next(
            (
                purchases_by_id[pid] for pid in g.purchase_ids
                if purchases_by_id.get(pid)
                and purchases_by_id[pid].purchase_method == "advance"
                and purchases_by_id[pid].reimbursement_user_id
            ),
            None,
        )
        if adv_purchase is not None:
            advance_pairs.append((g, adv_purchase))
    if advance_pairs:
        r = await match_advance(db, advance_pairs, dry_run=dry_run)
        multi_report["advance"]["attached"].extend(r["attached"])
        multi_report["advance"]["ambiguous"].extend(r["ambiguous"])

    report["multi"] = multi_report

    if not dry_run:
        await db.commit()

    return report


@router.get("/{pid}/vat-payment-check")
async def get_purchase_vat_payment_check(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from app.routers.purchases import load_purchase_for_out
    from app.services.purchase_vat_check import check_purchase_vat, _purchase_payment_sources

    p = await load_purchase_for_out(db, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    payments = await _purchase_payment_sources(db, pid)
    return check_purchase_vat(p, payments)


class _AlignVatBody(BaseModel):
    # Явное подтверждение с фронта — что именно приравниваем (защита от гонки,
    # если платежи изменились между GET vat-payment-check и этим POST).
    vat_applicable: bool
    vat_rate: Optional[float] = None


@router.post("/{pid}/align-vat-to-payments")
async def align_purchase_vat_to_payments(
    pid: int,
    body: _AlignVatBody,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Приравнять НДС закупки к тому, что распознано в её подтверждённых платежах.

    Гейт прав — тот же, что у PATCH/PUT закупки (_has_purchase_write_access,
    app/routers/purchases.py) — не заводим отдельную проверку прав. Меняет
    ТОЛЬКО шапку закупки (vat_mode='uniform', vat_applicable, vat_rate):
    при vat_mode='uniform' построчная PurchaseItem.vat_rate генератором
    документов не читается (см. app/services/documents/stages_amounts.py::
    compute_amounts_and_vat, ветка vat_mode != 'per_item') — трогать позиции
    не нужно и рискованно (они могут нести реальные построчные ставки другого
    смысла, если закупку потом вернут в per_item).
    """
    from app.routers.purchases import load_purchase_for_out, _has_purchase_write_access
    from app.services.purchase_vat_check import check_purchase_vat, _purchase_payment_sources

    p = await load_purchase_for_out(db, pid)
    if not p:
        raise HTTPException(404, "Закупка не найдена")
    if not await _has_purchase_write_access(current_user, db):
        raise HTTPException(403, "Нет прав на редактирование этой закупки. Обратитесь к администратору организации.")

    payments = await _purchase_payment_sources(db, pid)
    check = check_purchase_vat(p, payments)
    if check["status"] not in ("mismatch", "unknown_purchase_vat") or not check["suggested"]:
        raise HTTPException(409, "Нет подтверждённого расхождения НДС с платежами для этой закупки — приравнивать нечего")

    old_vals = {
        "vat_mode": p.vat_mode, "vat_applicable": p.vat_applicable, "vat_rate": p.vat_rate,
    }
    p.vat_mode = "uniform"
    p.vat_applicable = body.vat_applicable
    p.vat_rate = int(body.vat_rate) if body.vat_rate is not None else None
    await db.commit()
    await db.refresh(p)

    try:
        from app.models.entity_change import EntityChange
        changes = []
        for field in ("vat_mode", "vat_applicable", "vat_rate"):
            old_s = str(old_vals[field]) if old_vals[field] is not None else None
            new_s = str(getattr(p, field)) if getattr(p, field) is not None else None
            if old_s != new_s:
                changes.append(EntityChange(
                    entity_type="purchase", entity_id=p.id, field_name=field,
                    old_value=old_s, new_value=new_s,
                    changed_by_id=current_user.id,
                    changed_by_name=getattr(current_user, "full_name", None) or current_user.username,
                ))
        if changes:
            for c in changes:
                db.add(c)
            await db.commit()
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("entity_change record failed (align-vat-to-payments): %s", _exc)

    return {
        "id": p.id, "vat_mode": p.vat_mode, "vat_applicable": p.vat_applicable, "vat_rate": p.vat_rate,
    }
