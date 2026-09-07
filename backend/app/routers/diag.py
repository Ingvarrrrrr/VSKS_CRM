"""Диагностические эндпоинты /api/diag/* (Phase 26-BB/DD/FF).

Перенесено из app/__init__.py при разрезании монолитного файла на модули
(Правило №5). Пути и логика не менялись:
  GET  /api/diag/version
  POST /api/diag/run-backfills
  GET  /api/diag/advance-overview
  POST /api/diag/recompute/{pid}
  GET  /api/diag/purchase/{pid}
"""
from fastapi import APIRouter, Depends, HTTPException

from app.auth.jwt import get_current_user
from app.database import async_session

router = APIRouter(prefix="/api/diag", tags=["diag"])


@router.get("/version")
async def diag_version():
    """Phase 26-BB: маркер фазы + git sha + runtime checks (колонка, backfill)."""
    import os as _os, subprocess as _sp
    from sqlalchemy import text as _text
    git_sha = "unknown"
    try:
        git_sha = _sp.check_output(
            ['git', '-C', _os.path.dirname(__file__) + '/../../..', 'rev-parse', '--short', 'HEAD'],
            stderr=_sp.DEVNULL,
            timeout=2,
        ).decode().strip()
    except Exception:
        pass

    # Runtime DB checks
    schema_status = {"purchase_items.receipt_id": "unknown", "linked_count": 0, "advance_purchases": 0, "advance_null_contractor_items": 0}
    try:
        async with async_session() as db:
            col_q = await db.execute(_text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='purchase_items' AND column_name='receipt_id'
                LIMIT 1
            """))
            schema_status["purchase_items.receipt_id"] = "present" if col_q.scalar() else "MISSING"
            if schema_status["purchase_items.receipt_id"] == "present":
                cnt_q = await db.execute(_text("SELECT COUNT(*) FROM purchase_items WHERE receipt_id IS NOT NULL"))
                schema_status["linked_count"] = int(cnt_q.scalar() or 0)
            advances_q = await db.execute(_text("""
                SELECT COUNT(*) FROM purchases WHERE purchase_method='advance'
            """))
            schema_status["advance_purchases"] = int(advances_q.scalar() or 0)
            null_c_q = await db.execute(_text("""
                SELECT COUNT(*) FROM purchase_items pi
                JOIN purchases p ON p.id = pi.purchase_id
                WHERE p.purchase_method='advance' AND pi.contractor_id IS NULL
            """))
            schema_status["advance_null_contractor_items"] = int(null_c_q.scalar() or 0)
    except Exception as e:
        schema_status["error"] = str(e)[:200]

    return {
        "phase": "26-DD",
        "git_sha": git_sha,
        "schema": schema_status,
        "features": [
            "auto-recompute-on-get-advance",
            "structured-document-errors",
            "receipt-as-file-in-acceptance-docs",
            "contractor-inheritance-purchase-to-items",
            "per-receipt-contractor-mapping",
            "fuzzy-match-legacy-items",
            "propagate-purchase-contractor-to-items",
            "force-backfill-endpoint",
            "diag-purchase-endpoint",
        ],
    }


@router.post("/run-backfills")
async def diag_run_backfills(current_user=Depends(get_current_user)):
    """Принудительный запуск всех backfill'ов (admin/superadmin only).
    Returns per-stage counts."""
    if current_user.role not in ('admin', 'superadmin'):
        raise HTTPException(403, "Только admin/superadmin")

    from sqlalchemy import select as _sel
    from app.models.purchase import Purchase as _Purchase
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase_receipt import PurchaseReceipt as _PR
    from app.models.contractor import Contractor as _Ctr
    from app.routers.purchase_receipts import _items_match_score as _fuzzy, _extract_items as _ext
    from app.services.item_contractor import set_item_contractor

    result = {"propagated_from_purchase": 0, "linked_by_fuzzy": 0, "filled_first_receipt": 0, "errors": []}

    async with async_session() as db:
        # Stage A: propagate purchase.contractor_id → items
        try:
            advances_with_c = (await db.execute(
                _sel(_Purchase).where(
                    _Purchase.purchase_method == 'advance',
                    _Purchase.contractor_id.is_not(None),
                )
            )).scalars().all()
            for p in advances_with_c:
                c_row = await db.get(_Ctr, p.contractor_id)
                if not c_row:
                    continue
                null_items = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == p.id, _PI.contractor_id.is_(None))
                )).scalars().all()
                for it in null_items:
                    # ПРАВИЛО №6 (группа D5): единственный писатель — тот же
                    # item_contractor.set_item_contractor, что и в startup/backfills.py
                    # (_phase26_cc_propagate_contractor_to_items) — код не копируем.
                    set_item_contractor(it, contractor=c_row)
                    result["propagated_from_purchase"] += 1
            await db.commit()
        except Exception as e:
            result["errors"].append(f"stage_A: {str(e)[:200]}")

        # Stage B: fuzzy match unlinked items с raw_json
        try:
            advances_ids = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            for (pid,) in advances_ids:
                unlinked = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == pid, _PI.receipt_id.is_(None))
                )).scalars().all()
                if not unlinked:
                    continue
                receipts = (await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid)
                )).scalars().all()
                if not receipts:
                    continue
                for it in unlinked:
                    best_r = None
                    best_score = 0
                    for r in receipts:
                        for ri in _ext(r.raw_json):
                            s = _fuzzy(it, ri)
                            if s >= 2 and s > best_score:
                                best_score = s
                                best_r = r
                    if best_r:
                        it.receipt_id = best_r.id
                        if best_r.seller_inn:
                            c_row = (await db.execute(
                                _sel(_Ctr).where(_Ctr.inn == best_r.seller_inn)
                            )).scalar_one_or_none()
                            if not c_row:
                                c_row = _Ctr(inn=best_r.seller_inn, name=best_r.seller_name or f"ИНН {best_r.seller_inn}")
                                db.add(c_row)
                                await db.flush()
                            # ПРАВИЛО №6 (группа D5): тот же set_item_contractor,
                            # что и в startup/backfills.py (_phase26_bb_fuzzy_link_items_to_receipts).
                            set_item_contractor(it, contractor=c_row)
                        result["linked_by_fuzzy"] += 1
            await db.commit()
        except Exception as e:
            result["errors"].append(f"stage_B: {str(e)[:200]}")

        # Stage C: fallback — для NULL items с одним чеком в закупке, заполнить от него
        try:
            advances_ids = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            for (pid,) in advances_ids:
                null_items = (await db.execute(
                    _sel(_PI).where(_PI.purchase_id == pid, _PI.contractor_id.is_(None))
                )).scalars().all()
                if not null_items:
                    continue
                receipts = (await db.execute(
                    _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc())
                )).scalars().all()
                if not receipts:
                    continue
                # Стратегия: если 1 чек — все NULL ← него; если несколько — НЕ трогать
                if len(receipts) == 1:
                    r = receipts[0]
                    if not r.seller_inn:
                        continue
                    c_row = (await db.execute(
                        _sel(_Ctr).where(_Ctr.inn == r.seller_inn)
                    )).scalar_one_or_none()
                    if not c_row:
                        c_row = _Ctr(inn=r.seller_inn, name=r.seller_name or f"ИНН {r.seller_inn}")
                        db.add(c_row)
                        await db.flush()
                    for it in null_items:
                        # ПРАВИЛО №6 (группа D5): единственный писатель —
                        # item_contractor.set_item_contractor (см. startup/backfills.py).
                        set_item_contractor(it, contractor=c_row)
                        result["filled_first_receipt"] += 1
            await db.commit()
        except Exception as e:
            result["errors"].append(f"stage_C: {str(e)[:200]}")

        # Stage D: для каждой advance закупки прогнать _recompute_from_receipts_core —
        # создаёт PurchaseItem из raw_json если items отсутствуют, плюс per-receipt mapping.
        try:
            from app.routers.purchase_receipts import _recompute_from_receipts_core
            advances_ids = (await db.execute(
                _sel(_Purchase.id).where(_Purchase.purchase_method == 'advance')
            )).all()
            d_autocreated = 0
            for (pid_,) in advances_ids:
                res = await _recompute_from_receipts_core(pid_, db)
                d_autocreated += int(res.get("items_autocreated") or 0)
            result["items_autocreated_from_raw_json"] = d_autocreated
        except Exception as e:
            result["errors"].append(f"stage_D: {str(e)[:200]}")

    return result


@router.get("/advance-overview")
async def diag_advance_overview(current_user=Depends(get_current_user)):
    """Overview всех advance закупок: pid, registry_number, items в purchase_items vs contract_items,
    receipts_count, contractor. Чтобы найти где реально лежат данные."""
    from sqlalchemy import select as _sel, func as _func, text as _text
    from app.models.purchase import Purchase as _Purchase
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase_receipt import PurchaseReceipt as _PR

    async with async_session() as db:
        advances = (await db.execute(
            _sel(_Purchase).where(_Purchase.purchase_method == 'advance').order_by(_Purchase.id.desc())
        )).scalars().all()
        rows = []
        for p in advances:
            pi_count = (await db.execute(
                _sel(_func.count(_PI.id)).where(_PI.purchase_id == p.id)
            )).scalar() or 0
            r_count = (await db.execute(
                _sel(_func.count(_PR.id)).where(_PR.purchase_id == p.id)
            )).scalar() or 0
            # contract_items count через raw SQL — модель может быть в другом месте
            try:
                ci_count = (await db.execute(
                    _text("SELECT COUNT(*) FROM contract_items WHERE purchase_id = :pid"),
                    {"pid": p.id}
                )).scalar() or 0
            except Exception:
                ci_count = -1  # таблицы нет
            rows.append({
                "id": p.id,
                "registry_number": p.registry_number,
                "purchase_number": p.purchase_number,
                "purchase_method": p.purchase_method,
                "contractor_id": p.contractor_id,
                "purchase_items_count": pi_count,
                "contract_items_count": ci_count,
                "receipts_count": r_count,
            })
        # Также — все PurchaseReceipt и их purchase_id (где реально лежат чеки)
        all_receipts = (await db.execute(
            _sel(_PR.id, _PR.purchase_id, _PR.seller_inn, _PR.seller_name, _PR.total_sum)
            .order_by(_PR.id.desc()).limit(30)
        )).all()
        receipts_summary = [
            {"id": r.id, "purchase_id": r.purchase_id, "seller_inn": r.seller_inn,
             "seller_name": (r.seller_name or "")[:60], "total": float(r.total_sum or 0)}
            for r in all_receipts
        ]
        return {"advances": rows, "recent_receipts": receipts_summary}


@router.post("/recompute/{pid}")
async def diag_recompute_single(pid: int, current_user=Depends(get_current_user)):
    """Phase 26-DD: ручной recompute одной закупки доступен ЛЮБОЙ авторизованной роли,
    с подробным отчётом включая sample raw_json. Для отладки 575/582 без admin токена."""
    from sqlalchemy import select as _sel
    from app.models.purchase import Purchase as _Purchase
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase_receipt import PurchaseReceipt as _PR
    from app.routers.purchase_receipts import (
        _recompute_from_receipts_core, _extract_items
    )
    import json as _json

    async with async_session() as db:
        p = await db.get(_Purchase, pid)
        if not p:
            raise HTTPException(404, "Закупка не найдена")
        # Snapshot ДО
        items_before = (await db.execute(
            _sel(_PI).where(_PI.purchase_id == pid)
        )).scalars().all()
        receipts = (await db.execute(
            _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc())
        )).scalars().all()
        before = {
            "items_count": len(items_before),
            "items_with_contractor": sum(1 for i in items_before if i.contractor_id),
            "items_with_receipt_id": sum(1 for i in items_before if i.receipt_id),
            "receipts_count": len(receipts),
            "receipts_raw_items_count": [len(_extract_items(r.raw_json or {})) for r in receipts],
            "purchase_contractor_id": p.contractor_id,
        }
        # Sample raw_json первого чека (truncated)
        sample = None
        if receipts:
            r0 = receipts[0]
            raw_str = _json.dumps(r0.raw_json or {}, ensure_ascii=False)[:1500]
            sample = {
                "receipt_id": r0.id,
                "seller_inn": r0.seller_inn,
                "seller_name": r0.seller_name,
                "raw_json_truncated": raw_str,
                "extracted_items": _extract_items(r0.raw_json or {})[:5],
            }
        # Запуск
        result = await _recompute_from_receipts_core(pid, db)
        # Snapshot ПОСЛЕ
        items_after = (await db.execute(
            _sel(_PI).where(_PI.purchase_id == pid)
        )).scalars().all()
        # Phase 26-FF: per-item info + contractor resolvability
        from app.models.contractor import Contractor as _Ctr
        items_detail = []
        for it in items_after:
            c_resolvable = False
            c_inn = None
            c_name = None
            if it.contractor_id:
                c_row = await db.get(_Ctr, it.contractor_id)
                if c_row:
                    c_resolvable = True
                    c_inn = c_row.inn
                    c_name = c_row.name
            items_detail.append({
                "item_id": it.id,
                "name": (it.item_name or "")[:60],
                "contractor_id": it.contractor_id,
                "contractor_inn_in_item": it.contractor_inn,
                "contractor_name_in_item": (it.contractor_name or "")[:60] if it.contractor_name else None,
                "receipt_id": it.receipt_id,
                "contractor_resolvable_in_db": c_resolvable,
                "contractor_inn_resolved": c_inn,
                "contractor_name_resolved": (c_name or "")[:60] if c_name else None,
            })
        after = {
            "items_count": len(items_after),
            "items_with_contractor": sum(1 for i in items_after if i.contractor_id),
            "items_with_receipt_id": sum(1 for i in items_after if i.receipt_id),
            "items_detail": items_detail,
        }
        return {
            "ok": True,
            "before": before,
            "recompute_result": result,
            "after": after,
            "sample_receipt": sample,
        }


@router.get("/purchase/{pid}")
async def diag_purchase(pid: int, current_user=Depends(get_current_user)):
    """Sample данных о закупке для диагностики backfills (admin/superadmin only)."""
    if current_user.role not in ('admin', 'superadmin'):
        raise HTTPException(403, "Только admin/superadmin")

    from sqlalchemy import select as _sel
    from app.models.purchase import Purchase as _Purchase
    from app.models.purchase_item import PurchaseItem as _PI
    from app.models.purchase_receipt import PurchaseReceipt as _PR
    from app.models.contractor import Contractor as _Ctr
    import json as _json

    async with async_session() as db:
        p = await db.get(_Purchase, pid)
        if not p:
            raise HTTPException(404, "Закупка не найдена")
        items = (await db.execute(
            _sel(_PI).where(_PI.purchase_id == pid).order_by(_PI.id.asc())
        )).scalars().all()
        receipts = (await db.execute(
            _sel(_PR).where(_PR.purchase_id == pid).order_by(_PR.id.asc())
        )).scalars().all()

        # Resolve contractor inn for purchase
        purchase_contractor_inn = None
        if p.contractor_id:
            c = await db.get(_Ctr, p.contractor_id)
            if c:
                purchase_contractor_inn = c.inn

        items_out = [{
            "id": it.id,
            "item_name": it.item_name,
            "qty": float(it.quantity or 0),
            "unit_price": float(it.unit_price or 0),
            "total_price": float(it.total_price or 0),
            "contractor_id": it.contractor_id,
            "contractor_inn": it.contractor_inn,
            "receipt_id": it.receipt_id,
        } for it in items]

        receipts_out = []
        for r in receipts:
            raw_str = _json.dumps(r.raw_json or {}, ensure_ascii=False)[:2000] if r.raw_json else None
            receipts_out.append({
                "id": r.id,
                "seller_inn": r.seller_inn,
                "seller_name": r.seller_name,
                "total_sum": float(r.total_sum or 0),
                "raw_json_truncated": raw_str,
            })

        return {
            "purchase_id": pid,
            "purchase_contractor_id": p.contractor_id,
            "purchase_contractor_inn": purchase_contractor_inn,
            "items": items_out,
            "receipts": receipts_out,
        }
