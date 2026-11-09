"""Сервис импорта и слияния файлов результатов закупок с ЭТП.

ПРАВИЛО №5: компактный модульный файл (< 200 строк).
ПРАВИЛО №6: единый пересчет мест recalculate_places.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.roseltorg.analog_matcher import extract_item_structured_chars
from app.services.roseltorg.protocol_parser import parse_protocol_file
from app.services.roseltorg.results import recalculate_places
from app.services.roseltorg.winner_apply_service import save_publication_file


async def get_purchase_items_brief(db: AsyncSession, purchase_id: int) -> List[Dict[str, Any]]:
    """Возвращает краткий список позиций закупки для сопоставления при парсинге."""
    try:
        p_items_res = await db.execute(
            select(PurchaseItem)
            .where(PurchaseItem.purchase_id == purchase_id)
            .order_by(PurchaseItem.id)
        )
        if hasattr(p_items_res, "scalars"):
            sc = p_items_res.scalars()
            items = sc.all() if hasattr(sc, "all") and callable(sc.all) else []
            return [
                {
                    "id": getattr(pi, "id", None),
                    "name": getattr(pi, "item_name", ""),
                    "item_name": getattr(pi, "item_name", ""),
                    "description": getattr(pi, "tz_description", "") or "",
                    "quantity": float(getattr(pi, "quantity", 1) or 1),
                    "unit": getattr(pi, "unit", "шт.") or "шт.",
                    "characteristics": extract_item_structured_chars(pi, getattr(pi, "tz_description", "") or ""),
                }
                for pi in items if hasattr(pi, "item_name")
            ]
    except Exception:
        pass
    return []


async def import_multiple_protocol_files(
    db: AsyncSession,
    pub: PlatformPublication,
    purchase: Purchase,
    files: List[UploadFile],
) -> Dict[str, Any]:
    """Импортирует и сливает список файлов результатов в publication.results_data."""
    p_items = await get_purchase_items_brief(db, purchase.id)

    existing: Dict[str, Any] = {}
    if pub.results_data:
        try:
            existing = json.loads(pub.results_data)
        except Exception:
            existing = {}

    merged = dict(existing)
    merged_apps: List[Dict[str, Any]] = list(merged.get("applications", []))

    for up_file in files:
        safe_name, file_url, content = await save_publication_file(pub.id, up_file)
        parsed = parse_protocol_file(up_file.filename or safe_name, content, purchase_items=p_items)

        doc_entry = {"name": up_file.filename or safe_name, "url": file_url, "size": len(content)}

        if parsed.get("is_single_application"):
            single_app = parsed.get("application") or (parsed.get("applications")[0] if parsed.get("applications") else {})
            single_app["documents"] = [doc_entry]
            matched_app = None
            for ex_app in merged_apps:
                if single_app.get("inn") and ex_app.get("inn") == single_app["inn"]:
                    matched_app = ex_app
                    break
                if single_app.get("supplier_name") and ex_app.get("supplier_name", "").lower() == single_app["supplier_name"].lower():
                    matched_app = ex_app
                    break
            if matched_app:
                matched_app["positions"] = single_app.get("positions", [])
                p_val = single_app.get("price_with_vat") or single_app.get("price")
                if p_val:
                    matched_app["price_with_vat"] = p_val
                    matched_app["price_without_vat"] = p_val
                for fld in ("kpp", "contacts", "validity_days", "outgoing_ref", "vat_label"):
                    if single_app.get(fld):
                        matched_app[fld] = single_app[fld]
                if "admitted" in single_app:
                    matched_app["admitted"] = bool(single_app["admitted"])
                    matched_app["rejection_reason"] = single_app.get("rejection_reason", "")
                    if not single_app["admitted"]:
                        matched_app["decision_text"] = f"Не соответствует. {single_app.get('rejection_reason', '')}"
                docs = matched_app.get("documents", [])
                if not any(d.get("name") == doc_entry["name"] for d in docs):
                    docs.append(doc_entry)
                matched_app["documents"] = docs
            else:
                single_app["app_id"] = str(len(merged_apps) + 1)
                single_app["application_number"] = str(len(merged_apps) + 1)
                if not single_app.get("price_with_vat") and single_app.get("price"):
                    single_app["price_with_vat"] = single_app["price"]
                    single_app["price_without_vat"] = single_app["price"]
                if not single_app.get("decision_text"):
                    single_app["decision_text"] = (
                        "Признать соответствующей требованиям закупочной документации."
                        if single_app.get("admitted")
                        else f"Не соответствует. {single_app.get('rejection_reason', '')}"
                    )
                merged_apps.append(single_app)
        else:
            for k in ("registration_number", "notice_date", "protocol_number", "protocol_date", "submission_deadline", "meeting_address", "meeting_time", "commission_order_number", "commission_order_date", "commission_members"):
                if parsed.get(k):
                    merged[k] = parsed[k]
            if parsed.get("applications"):
                for p_app in parsed["applications"]:
                    p_app["documents"] = [doc_entry]
                    merged_apps.append(p_app)

    for k in ("commission_order_number", "commission_order_date", "commission_members", "meeting_address"):
        if not merged.get(k) and existing.get(k):
            merged[k] = existing[k]

    recalculated = recalculate_places(merged_apps)
    merged["applications"] = recalculated
    merged["total_applications"] = len(recalculated)
    merged["admitted_count"] = sum(1 for a in recalculated if a.get("admitted"))
    merged["rejected_count"] = sum(1 for a in recalculated if not a.get("admitted"))

    pub.results_data = json.dumps(merged, ensure_ascii=False)
    if merged.get("registration_number"):
        pub.platform_number = merged["registration_number"]

    await db.commit()
    await db.refresh(pub)
    return merged
