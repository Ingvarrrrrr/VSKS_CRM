"""Purchase-receipts import endpoints: FNS JSON export, QR scan, QR fetch.

Split out of app/routers/purchase_receipts.py (Правило №5, сессия 2026-09-08).
"""
import json
import os
from typing import List

import httpx
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.purchase import Purchase
from app.models.purchase_receipt import PurchaseReceipt
from app.models.user import User
from app.schemas.schemas import ReceiptOut
from app.services.receipts_creation import _create_receipt_with_items, _raise_receipt_duplicate_detail
from app.services.receipts_parsing import _parse_fns_json_receipt, _parse_qr_string

router = APIRouter(prefix="/api/purchases", tags=["receipts"])


@router.post("/{purchase_id}/receipts/import-json", response_model=List[ReceiptOut])
async def import_receipt_json(
    purchase_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Import one or more receipts from FNS mobile-app JSON export."""
    if not (file.filename or "").lower().endswith('.json'):
        raise HTTPException(400, "Поддерживается только .json")

    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    content = await file.read()
    try:
        payload = json.loads(content)
    except Exception:
        raise HTTPException(400, "Не удалось распарсить JSON")

    if not isinstance(payload, list):
        payload = [payload]

    results: List[PurchaseReceipt] = []
    conflicts: List = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            data = _parse_fns_json_receipt(entry)
            r = await _create_receipt_with_items(
                purchase_id, data, 'json_import', entry, db
            )
            results.append(r)
        except HTTPException as he:
            # Conflict (409) = receipt linked to another purchase — surface to user.
            # detail — структурированный dict (code RECEIPT_DUPLICATE, is_advance, ...),
            # его нельзя str()-ить: фронт ждёт объект, а не Python repr словаря.
            if he.status_code == 409:
                conflicts.append(he.detail)
            # Other HTTP errors and malformed entries are skipped.
            continue
        except Exception:
            continue
    if not results and conflicts:
        # All entries conflicted — bubble first message up so the user sees it.
        raise HTTPException(409, detail=conflicts[0])
    return results


@router.post("/{purchase_id}/receipts/from-qr", response_model=ReceiptOut)
async def import_receipt_qr(
    purchase_id: int,
    qr: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Create a receipt from a QR-string. No items (admin adds them later)."""
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    data = _parse_qr_string(qr)
    if not data.get('fiscal_drive_number'):
        raise HTTPException(400, "QR не содержит фискальных данных")

    return await _create_receipt_with_items(
        purchase_id, data, 'qr_scan', {'qr': qr}, db,
    )


@router.post("/{purchase_id}/receipts/from-qr-fetch", response_model=ReceiptOut)
async def import_receipt_qr_fetch(
    purchase_id: int,
    qr: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Fetch full receipt (with items) from proverkacheka.com API by QR string.

    Requires PROVERKACHEKA_TOKEN in env. Returns the same shape as JSON-import:
    fiscal data + items auto-matched against the catalog (match_confirmed=False).
    """
    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(404, "Закупка не найдена")

    qr = (qr or '').strip()
    if not qr:
        raise HTTPException(400, "Пустая QR-строка")

    # Phase 24: pre-check duplicate by fiscal triple BEFORE hitting FNS API.
    # ФНС режет повторные обращения по тому же чеку → лучше отдать осмысленную
    # ошибку «уже заведён» чем «Превышено количество обращений».
    qr_data = _parse_qr_string(qr)
    fn = qr_data.get('fiscal_drive_number')
    fd = qr_data.get('fiscal_document_number')
    fp = qr_data.get('fiscal_sign')

    async def _find_existing_by_qr():
        """Найти существующий чек по любым доступным полям из QR.
        Чем больше совпало — тем выше уверенность."""
        # 1) Точная фискальная тройка
        if fn and fd and fp:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn,
                    PurchaseReceipt.fiscal_document_number == fd,
                    PurchaseReceipt.fiscal_sign == fp,
                )
            )).scalar_one_or_none()
            if row:
                return row
        # 2) Пара fn+fd (старые записи могли сохраниться без fp)
        if fn and fd:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn,
                    PurchaseReceipt.fiscal_document_number == fd,
                )
            )).scalar_one_or_none()
            if row:
                return row
        # 3) fn + дата + сумма из QR (для очень старых записей без fd/fp)
        dt = qr_data.get('receipt_datetime')
        total = qr_data.get('total_sum')
        if fn and dt and total is not None:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn,
                    PurchaseReceipt.receipt_datetime == dt,
                    PurchaseReceipt.total_sum == total,
                )
            )).scalar_one_or_none()
            if row:
                return row
        return None

    async def _find_existing_loose():
        """Loose поиск: только fn+fd (без fp), затем dt+inn+sum."""
        parsed = _parse_qr_string(qr) or {}
        fn2 = parsed.get('fiscal_drive_number')
        fd2 = parsed.get('fiscal_document_number')
        if fn2 and fd2:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.fiscal_drive_number == fn2,
                    PurchaseReceipt.fiscal_document_number == fd2,
                ).limit(1)
            )).scalar_one_or_none()
            if row:
                return row
        # Fallback: dt+inn+sum
        dt2 = parsed.get('receipt_datetime')
        inn2 = parsed.get('seller_inn')
        total2 = parsed.get('total_sum')
        if dt2 and inn2 and total2 is not None:
            row = (await db.execute(
                select(PurchaseReceipt).where(
                    PurchaseReceipt.seller_inn == inn2,
                    PurchaseReceipt.receipt_datetime == dt2,
                    PurchaseReceipt.total_sum == total2,
                ).limit(1)
            )).scalar_one_or_none()
            if row:
                return row
        return None

    async def _raise_receipt_duplicate(existing_row):
        """Поднять structured 409 со ссылкой на документ (закупку/авансовый отчёт),
        где этот чек уже есть. Формулировка — в общем хелпере
        _raise_receipt_duplicate_detail, чтобы все точки входа (QR, JSON-импорт,
        ручной ввод) говорили одно и то же."""
        await _raise_receipt_duplicate_detail(existing_row.purchase_id, purchase_id, existing_row.id, db)

    pre_existing = await _find_existing_by_qr() or await _find_existing_loose()
    if pre_existing:
        await _raise_receipt_duplicate(pre_existing)

    token = os.getenv("PROVERKACHEKA_TOKEN", "").strip()
    if not token:
        raise HTTPException(503, "PROVERKACHEKA_TOKEN не настроен на сервере")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://proverkacheka.com/api/v1/check/get",
                data={"qrraw": qr, "token": token},
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Ошибка запроса к proverkacheka.com: {e}")
    except ValueError:
        raise HTTPException(502, "Не удалось распарсить ответ proverkacheka.com")

    if not isinstance(payload, dict) or payload.get("code") != 1:
        msg = (payload or {}).get("data") if isinstance(payload, dict) else None
        msg_str = msg if isinstance(msg, str) else ""
        # Если ФНС режет по rate-limit — это сильный сигнал что чек уже импортировали
        # сегодня. Пробуем ещё раз поискать в БД (loose поиск тоже).
        if "Превышено" in msg_str or "превышен" in msg_str.lower() or "уже" in msg_str.lower():
            again = await _find_existing_by_qr() or await _find_existing_loose()
            if again:
                await _raise_receipt_duplicate(again)
            raise HTTPException(429, detail={
                "code": "FNS_RATE_LIMIT",
                "message": "ФНС временно ограничила запросы. В базе CRM этот чек не найден — попробуйте через 1–2 минуты.",
                "hint": msg_str or None,
            })
        if msg_str:
            raise HTTPException(400, f"Чек не найден: {msg_str}")
        raise HTTPException(400, "Чек не найден в ФНС (proverkacheka.com)")

    body = payload.get("data") or {}
    receipt_obj = body.get("json") if isinstance(body, dict) else None
    if not isinstance(receipt_obj, dict):
        raise HTTPException(502, "Ответ proverkacheka.com без данных чека")

    data = _parse_fns_json_receipt(receipt_obj)
    if not data.get("fiscal_drive_number"):
        # fall back to QR fields if proverkacheka returned partial data
        qr_data = _parse_qr_string(qr)
        for k, v in qr_data.items():
            if v and not data.get(k):
                data[k] = v

    return await _create_receipt_with_items(
        purchase_id, data, 'qr_scan', {"qr": qr, "proverkacheka": payload}, db,
    )
