"""Роутер для работы с результатами процедур на ЭТП и итоговыми протоколами.

ПРАВИЛО №5: модульный файл (< 400 строк).
ПРАВИЛО №6: единый источник истины (состав комиссии из Субсидии, форматирование из documents.formatting).
ПРАВИЛО №8: проверка прав (get_current_user, ensure_purchase_visible), безопасные ответы 422/502.
"""
import io
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import get_current_user
from app.auth.object_visibility import ensure_purchase_visible
from app.database import get_db
from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.schemas.publication_results import (
    ApplyWinnerRequest, EnsurePubRequest, ResultsSyncRequest, SaveResultsRequest,
)
from app.services.documents.formatting import _fmt_date, _extract_city_from_address
from app.services.documents.protocol_vsks import build_vsks_protocol_docx
from app.services.documents.tkp_form_xlsx import render_standardized_tkp_xlsx
from app.services.documents.tkp_form_pdf import render_standardized_tkp_pdf
from app.services.publications_status import sync_purchase_on_platform_published
from app.services.roseltorg.analog_matcher import extract_item_structured_chars
from app.services.roseltorg.protocol_parser import parse_protocol_file
from app.services.roseltorg.results_builder import get_or_build_default_results
from app.services.roseltorg.results_import_service import (
    get_purchase_items_brief, import_multiple_protocol_files,
)
from app.services.roseltorg.results import (
    fetch_roseltorg_procedure_results, recalculate_places,
)
from app.services.roseltorg.winner_apply_service import (
    apply_winner_full, get_publication_file_path, save_publication_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/publications", tags=["publication_results"])


@router.get("/purchases/{purchase_id}/results")
async def get_purchase_results(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Возвращает результаты рассмотрения заявок по закупке (из активной публикации или дефолты)."""
    purchase = await ensure_purchase_visible(current_user, purchase_id, db)

    pub_res = await db.execute(
        select(PlatformPublication)
        .where(PlatformPublication.purchase_id == purchase_id)
        .order_by(PlatformPublication.created_at.desc())
    )
    pub = pub_res.scalars().first()

    results = await get_or_build_default_results(db, purchase, pub)

    return {
        "pub_id": pub.id if pub else None,
        "purchase_id": purchase_id,
        "platform": pub.platform if pub else "roseltorg_rb",
        "platform_number": pub.platform_number if pub else None,
        "results": results,
    }


@router.get("/purchases/{purchase_id}/tkp-template.xlsx")
async def download_tkp_template_xlsx(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отдаёт стандартизированный файл-бланк ТКП «Приложение № 2» в формате .xlsx."""
    await ensure_purchase_visible(current_user, purchase_id, db)
    xlsx_bytes, errors = await render_standardized_tkp_xlsx(db, purchase_id)
    if not xlsx_bytes:
        raise HTTPException(status_code=400, detail="; ".join(errors) or "Не удалось сформировать бланк ТКП")
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%D0%9F%D1%80%D0%B8%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5_2_%D0%A4%D0%BE%D1%80%D0%BC%D0%B0_%D0%A2%D0%9A%D0%9F.xlsx"},
    )


@router.get("/purchases/{purchase_id}/tkp-template.pdf")
async def download_tkp_template_pdf(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отдаёт стандартизированный интерактивный PDF-бланк ТКП «Приложение № 2»."""
    await ensure_purchase_visible(current_user, purchase_id, db)
    pdf_bytes, errors = await render_standardized_tkp_pdf(db, purchase_id)
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="; ".join(errors) or "Не удалось сформировать PDF-бланк ТКП")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%D0%9F%D1%80%D0%B8%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5_2_%D0%A4%D0%BE%D1%80%D0%BC%D0%B0_%D0%A2%D0%9A%D0%9F.pdf"},
    )


@router.post("/purchases/{purchase_id}/ensure-for-results")
async def ensure_publication_for_results(
    purchase_id: int,
    body: EnsurePubRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Гарантирует существование записи публикации для закупки (например, при ручном вводе извещения с ЭТП)."""
    purchase = await ensure_purchase_visible(current_user, purchase_id, db)

    pub_res = await db.execute(
        select(PlatformPublication)
        .where(PlatformPublication.purchase_id == purchase_id)
        .order_by(PlatformPublication.created_at.desc())
    )
    pub = pub_res.scalars().first()

    if not pub:
        pub = PlatformPublication(
            purchase_id=purchase_id,
            platform=body.platform or "roseltorg_rb",
            status="published",
            platform_number=body.platform_number or None,
            platform_state="published",
        )
        db.add(pub)
        await db.commit()
        await db.refresh(pub)
    elif body.platform_number and not pub.platform_number:
        pub.platform_number = body.platform_number
        await db.commit()
        await db.refresh(pub)

    sync_purchase_on_platform_published(purchase)
    await db.commit()

    results = await get_or_build_default_results(db, purchase, pub)
    return {
        "pub_id": pub.id,
        "purchase_id": purchase_id,
        "platform": pub.platform,
        "platform_number": pub.platform_number,
        "results": results,
    }


@router.post("/{pub_id}/results/sync")
async def sync_publication_results(
    pub_id: int,
    body: ResultsSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Синхронизирует результаты процедуры и заявки с Росэлторг.Бизнес API."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    await ensure_purchase_visible(current_user, pub.purchase_id, db)

    results = await fetch_roseltorg_procedure_results(
        pub,
        user_id=current_user.id,
        manual_reg_number=body.registration_number,
    )

    pub.results_data = json.dumps(results, ensure_ascii=False)
    if results.get("procedure_id"):
        pub.procedure_id = str(results["procedure_id"])
    if results.get("lot_id"):
        pub.lot_id = str(results["lot_id"])
    if results.get("registration_number"):
        pub.platform_number = str(results["registration_number"])
    if results.get("procedure_state"):
        pub.platform_state = str(results["procedure_state"])

    purchase = await db.get(Purchase, pub.purchase_id)
    sync_purchase_on_platform_published(purchase)

    await db.commit()
    await db.refresh(pub)

    return {
        "ok": True,
        "pub_id": pub.id,
        "results": results,
    }


@router.put("/{pub_id}/results")
async def save_publication_results(
    pub_id: int,
    body: SaveResultsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сохраняет отредактированные пользователем решения по заявкам и реквизиты протокола."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    await ensure_purchase_visible(current_user, pub.purchase_id, db)

    recalculated_apps = recalculate_places(body.applications)
    total_apps = len(recalculated_apps)
    admitted_count = sum(1 for a in recalculated_apps if a.get("admitted"))
    rejected_count = sum(1 for a in recalculated_apps if not a.get("admitted"))

    results_dict = body.dict()
    results_dict["applications"] = recalculated_apps
    results_dict["total_applications"] = total_apps
    results_dict["admitted_count"] = admitted_count
    results_dict["rejected_count"] = rejected_count

    pub.results_data = json.dumps(results_dict, ensure_ascii=False)
    if body.registration_number:
        pub.platform_number = body.registration_number

    await db.commit()
    await db.refresh(pub)

    return {
        "ok": True,
        "pub_id": pub.id,
        "results": results_dict,
    }


@router.get("/{pub_id}/results/files/{filename}")
async def get_publication_file(
    pub_id: int,
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Безопасное скачивание прикреплённого к заявке/публикации файла."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    await ensure_purchase_visible(current_user, pub.purchase_id, db)
    file_path = get_publication_file_path(pub_id, filename)
    return FileResponse(file_path, filename=filename)


@router.post("/{pub_id}/results/import-file")
async def import_protocol_file(
    pub_id: int,
    file: Optional[UploadFile] = File(default=None),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Импортирует результаты закупки и заявки из файла(ов) протокола/ТКП (.docx, .doc, .xlsx, .pdf, .zip)."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    purchase = await ensure_purchase_visible(current_user, pub.purchase_id, db)

    file_list: List[UploadFile] = []
    if isinstance(files, list):
        file_list.extend([f for f in files if hasattr(f, "read") and getattr(f, "filename", None)])
    if file is not None and hasattr(file, "read") and getattr(file, "filename", None) and file not in file_list:
        file_list.append(file)

    if not file_list:
        raise HTTPException(status_code=422, detail="Не выбраны файлы для загрузки")

    merged = await import_multiple_protocol_files(db, pub, purchase, file_list)

    sync_purchase_on_platform_published(purchase)
    await db.commit()

    return {
        "ok": True,
        "pub_id": pub.id,
        "results": merged,
    }


@router.post("/{pub_id}/results/applications/{app_idx}/upload-doc")
async def upload_application_document(
    pub_id: int,
    app_idx: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Прикрепляет и распознаёт файл ТКП/заявки для конкретного участника по индексу."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    purchase = await ensure_purchase_visible(current_user, pub.purchase_id, db)

    existing: Dict[str, Any] = {}
    if pub.results_data:
        try:
            existing = json.loads(pub.results_data)
        except Exception:
            existing = {}

    applications = existing.get("applications", [])
    if app_idx < 0 or app_idx >= len(applications):
        raise HTTPException(status_code=404, detail=f"Заявка с индексом {app_idx} не найдена")

    p_items = await get_purchase_items_brief(db, purchase.id)

    safe_name, file_url, content = await save_publication_file(pub.id, file)
    parsed = parse_protocol_file(file.filename or safe_name, content, purchase_items=p_items)

    target_app = applications[app_idx]
    doc_entry = {"name": file.filename or safe_name, "url": file_url, "size": len(content)}

    if parsed.get("is_single_application"):
        s_app = parsed["application"]
        if s_app.get("supplier_name") and (
            not target_app.get("supplier_name")
            or target_app.get("supplier_name", "").startswith("Заявка №")
            or target_app.get("supplier_name", "").startswith("Участник")
        ):
            target_app["supplier_name"] = s_app["supplier_name"]
        if s_app.get("inn") and not target_app.get("inn"):
            target_app["inn"] = s_app["inn"]
        if s_app.get("price_with_vat"):
            target_app["price_with_vat"] = s_app["price_with_vat"]
            target_app["price_without_vat"] = s_app["price_without_vat"]
        if s_app.get("positions"):
            target_app["positions"] = s_app["positions"]
        for _k in ("kpp", "vat_label", "compliance_status", "has_tz_correction", "tz_corrections_count", "tz_warning_notes", "analog_notes"):
            if _k in s_app and s_app[_k] is not None:
                target_app[_k] = s_app[_k]
    docs = target_app.get("documents", [])
    if not any(d.get("name") == doc_entry["name"] for d in docs):
        docs.append(doc_entry)
    target_app["documents"] = docs

    recalc = recalculate_places(applications)
    existing["applications"] = recalc
    pub.results_data = json.dumps(existing, ensure_ascii=False)
    await db.commit()
    await db.refresh(pub)

    return {
        "ok": True,
        "pub_id": pub.id,
        "results": existing,
    }


@router.post("/{pub_id}/results/init-positions")
async def init_purchase_positions(
    pub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Инициализирует попозиционный список товаров из закупки для всех заявок."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")

    purchase = await ensure_purchase_visible(current_user, pub.purchase_id, db)

    existing: Dict[str, Any] = {}
    if pub.results_data:
        try:
            existing = json.loads(pub.results_data)
        except Exception:
            existing = {}

    p_items_res = await db.execute(
        select(PurchaseItem)
        .where(PurchaseItem.purchase_id == purchase.id)
        .order_by(PurchaseItem.id)
    )
    p_items = p_items_res.scalars().all()

    default_positions = [
        {
            "item_num": idx,
            "purchase_item_id": pi.id,
            "requested_name": pi.item_name,
            "requested_specs": pi.tz_description or "",
            "offered_name": pi.item_name,
            "offered_specs": pi.tz_description or "",
            "unit": pi.unit or "шт.",
            "quantity": float(pi.quantity or 1),
            "unit_price": float(pi.unit_price or 0.0),
            "total_price": float(pi.total_price or 0.0),
            "is_alternative": False,
            "compliance_status": "compliant",
            "compliance_note": "",
            "characteristics": extract_item_structured_chars(pi, pi.tz_description or ""),
        }
        for idx, pi in enumerate(p_items, start=1)
    ]

    apps = existing.get("applications", [])
    for app in apps:
        if not app.get("positions"):
            app["positions"] = list(default_positions)

    existing["applications"] = apps
    pub.results_data = json.dumps(existing, ensure_ascii=False)
    await db.commit()
    await db.refresh(pub)

    return {
        "ok": True,
        "pub_id": pub.id,
        "results": existing,
    }


@router.post("/{pub_id}/results/apply-winner")
async def apply_winner_to_purchase(
    pub_id: int,
    body: Optional[ApplyWinnerRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Переносит реквизиты победителя в закупку."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")
    purchase = await ensure_purchase_visible(current_user, pub.purchase_id, db)
    if not pub.results_data:
        raise HTTPException(status_code=422, detail="Нет данных рассмотрения заявок")
    try:
        results = json.loads(pub.results_data)
    except Exception:
        raise HTTPException(status_code=422, detail="Некорректный формат результатов закупки")
    winner = next((a for a in results.get("applications", []) if a.get("admitted") and a.get("place") == 1), None)
    if not winner:
        raise HTTPException(status_code=422, detail="Среди допущенных заявок не определён победитель (1 место)")
    apply_cfg = body or ApplyWinnerRequest()
    return await apply_winner_full(
        db=db, purchase=purchase, winner=winner,
        protocol_number=results.get("protocol_number") or pub.platform_number,
        apply_positions_prices=apply_cfg.apply_positions_prices,
        apply_accepted_alternatives=apply_cfg.apply_accepted_alternatives,
    )


@router.get("/{pub_id}/results/protocol.docx")
async def download_protocol_docx(
    pub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Формирует и отдаёт итоговый протокол закупки в формате .docx."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")
    purchase = await ensure_purchase_visible(current_user, pub.purchase_id, db)
    subsidy = await db.get(Subsidy, purchase.subsidy_id) if purchase.subsidy_id else None
    from app.services.documents.stages_relations import load_customer
    customer_org, customer_ctr = await load_customer(db, subsidy)
    results = await get_or_build_default_results(db, purchase, pub)
    docx_bytes = build_vsks_protocol_docx(purchase, subsidy, customer_org, customer_ctr, results)
    reg_num = results.get("registration_number") or pub.platform_number or purchase.id
    filename = f"Протокол_{reg_num}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{pub_id}/results/comparison.xlsx")
async def download_comparison_matrix_xlsx(
    pub_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Формирует и отдаёт сводную таблицу сравнения предложений всех участников в формате .xlsx."""
    pub = await db.get(PlatformPublication, pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Публикация не найдена")
    await ensure_purchase_visible(current_user, pub.purchase_id, db)
    from app.services.roseltorg.comparison_xlsx_builder import build_comparison_matrix_for_publication
    xlsx_bytes, filename, errors = await build_comparison_matrix_for_publication(db, pub_id)
    if not xlsx_bytes:
        raise HTTPException(status_code=422, detail="; ".join(errors) or "Не удалось сформировать сводную таблицу")
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
