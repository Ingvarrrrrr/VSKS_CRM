"""Пакетная публикация и проверка закупок для отправки на площадки (ЭТП).

Вынесено из app/routers/publications.py в отдельный модуль (< 350 строк, Правило №5).
Подключается через router.include_router(...) в publications.py.
"""
from typing import List, Optional
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.purchase import Purchase
from app.models.platform_publication import PlatformPublication
from app.auth.jwt import get_current_user
from app.auth.permissions import require_action
from app.auth.object_visibility import ensure_purchase_visible
from app.services.tz_items import tz_required, items_without_tz
from app.services.publications_payload import _build_publish_payload
from app.services.publications_fabrikant_client import _call_fabrikant
from app.services.publications_roseltorg_client import _call_roseltorg
from app.services.etp_credentials import (
    resolve_purchase_etp_credentials,
    extract_organizer_inn_from_jwt,
    verify_organizer_inn,
)

router = APIRouter()


class BatchCheckRequest(BaseModel):
    purchase_ids: List[int]
    platform: str


class BatchCheckItemOut(BaseModel):
    purchase_id: int
    number: Optional[str] = None
    subject: Optional[str] = None
    ready: bool
    issues: List[str]


class BatchPublishRequest(BaseModel):
    purchase_ids: List[int]
    platform: str
    as_draft: bool = True
    procedure_type: Optional[str] = "request_quotations"
    proposal_start: Optional[str] = None
    proposal_end: Optional[str] = None
    summing_up_date: Optional[str] = None
    attach_documents: bool = True
    no_nmcd: Optional[bool] = None


class BatchPublishItemResult(BaseModel):
    purchase_id: int
    number: Optional[str] = None
    pub_id: Optional[int] = None
    status: str
    error: Optional[str] = None


async def _check_single_purchase(
    pid: int,
    platform: str,
    current_user,
    db: AsyncSession,
) -> BatchCheckItemOut:
    """Проверяет одну закупку на готовность к публикации."""
    # 1. Проверка видимости закупки
    try:
        p = await ensure_purchase_visible(current_user, pid, db)
    except HTTPException:
        return BatchCheckItemOut(
            purchase_id=pid,
            number=str(pid),
            subject="Нет доступа или закупка не найдена",
            ready=False,
            issues=["Закупка не найдена или нет доступа"],
        )

    # Догружаем связи для проверки
    res = await db.execute(
        select(Purchase)
        .options(selectinload(Purchase.items))
        .where(Purchase.id == pid)
    )
    p = res.scalar_one_or_none() or p

    num_str = p.registry_number or (f"№{p.purchase_number}" if p.purchase_number else str(p.id))
    subj_str = p.subject or "Без темы"
    issues: List[str] = []

    # 2. Проверка существующей публикации
    existing_pub = (await db.execute(
        select(PlatformPublication).where(
            PlatformPublication.purchase_id == pid,
            PlatformPublication.platform == platform,
            PlatformPublication.status.in_(["pending", "publishing", "draft", "published"]),
        )
    )).scalar_one_or_none()
    if existing_pub:
        if existing_pub.status == "draft":
            issues.append(f"Уже создан черновик процедуры (№{existing_pub.platform_number or existing_pub.external_id or '—'})")
        else:
            issues.append("Закупка уже опубликована или публикуется на площадке")

    # 3. Наличие позиций и дубли
    if not p.items:
        issues.append("В закупке нет позиций")
    else:
        names = [it.item_name.strip().lower() for it in p.items if it.item_name and it.item_name.strip()]
        counts = Counter(names)
        dups = [name for name, count in counts.items() if count > 1]
        if dups:
            issues.append(f"Обнаружены повторяющиеся позиции: {', '.join(dups[:3])}")

    # 4. Проверка ТЗ
    if p.items and tz_required(p):
        missing_tz = items_without_tz(p.items)
        if missing_tz:
            issues.append(f"Нет ТЗ у {len(missing_tz)} позиций")

    # 5. Адрес поставки и регион
    delivery_addr = (p.delivery_address or p.delivery_location or "").strip()
    if not delivery_addr and not p.region and not p.delivery_region:
        issues.append("Не указан адрес или регион поставки")

    # 6. Проверка единиц ОКЕИ (для Росэлторга)
    if platform == "roseltorg_rb" and p.items:
        from app.services.roseltorg.items import load_purchase_item_rows, find_items_with_unknown_unit
        try:
            _, rows = await load_purchase_item_rows(db, pid)
            bad_units = find_items_with_unknown_unit(rows)
            if bad_units:
                issues.append(f"Единицы измерения не из ОКЕИ: {', '.join(bad_units)}")
        except Exception:
            pass

    # 7. Проверка ключей площадки от имени организации субсидии
    creds_res = await resolve_purchase_etp_credentials(db, pid, platform)
    if not creds_res.get("ok"):
        issues.append(creds_res.get("error") or "Не задан ключ площадки для организации субсидии")
    elif platform == "roseltorg_rb" and creds_res.get("token"):
        # Проверяем авторизацию и ИНН организатора
        try:
            from app.services.roseltorg.auth import get_roseltorg_jwt
            jwt = await get_roseltorg_jwt(creds_res["token"])
            organizer_inn = extract_organizer_inn_from_jwt(jwt)
            org_inn = creds_res.get("org_inn")
            if organizer_inn and org_inn and organizer_inn.strip() != org_inn.strip():
                issues.append(
                    f"ИНН ключа площадки ({organizer_inn}) не совпадает с ИНН организации субсидии «{creds_res.get('org_name')}» ({org_inn})"
                )
        except Exception as e:
            issues.append(f"Сбой проверки ключа Росэлторг: {str(e)[:100]}")

    return BatchCheckItemOut(
        purchase_id=pid,
        number=num_str,
        subject=subj_str,
        ready=len(issues) == 0,
        issues=issues,
    )


@router.post("/batch-check", response_model=List[BatchCheckItemOut])
async def batch_check_purchases(
    body: BatchCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("publication.create")),
):
    """Массовая проверка готовности выбранных закупок к отправке на площадку."""
    results: List[BatchCheckItemOut] = []
    for pid in body.purchase_ids:
        item_check = await _check_single_purchase(pid, body.platform, current_user, db)
        results.append(item_check)
    return results


@router.post("/batch-publish", response_model=List[BatchPublishItemResult])
async def batch_publish_purchases(
    body: BatchPublishRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_action("publication.create")),
):
    """Массовая отправка готовых закупок на площадку (по умолчанию черновиком)."""
    results: List[BatchPublishItemResult] = []

    for pid in body.purchase_ids:
        # Повторно проверяем готовность перед отправкой
        check = await _check_single_purchase(pid, body.platform, current_user, db)
        if not check.ready:
            results.append(BatchPublishItemResult(
                purchase_id=pid,
                number=check.number,
                status="failed",
                error="; ".join(check.issues),
            ))
            continue

        try:
            payload = await _build_publish_payload(pid, db)
            p = await db.get(Purchase, pid)
            if not p:
                continue

            if body.no_nmcd is not None and bool(body.no_nmcd) != bool(p.fabrikant_no_nmcd):
                p.fabrikant_no_nmcd = bool(body.no_nmcd)
                await db.commit()

            payload.update({
                "procedure_type": body.procedure_type or "request_quotations",
                "proposal_start": body.proposal_start,
                "proposal_end": body.proposal_end,
                "summing_up_date": body.summing_up_date,
                "no_nmcd": bool(p.fabrikant_no_nmcd),
            })

            pub = PlatformPublication(
                purchase_id=pid,
                platform=body.platform,
                status="publishing",
            )
            db.add(pub)
            await db.commit()
            await db.refresh(pub)

            # as_draft=True: publish_immediately=False (черновик)
            publish_immediately = not body.as_draft

            if body.platform == "fabrikant":
                background_tasks.add_task(
                    _call_fabrikant, pub.id, payload, current_user.id,
                    body.attach_documents,
                )
            elif body.platform == "roseltorg_rb":
                background_tasks.add_task(
                    _call_roseltorg, pub.id, payload, current_user.id,
                    body.attach_documents, publish_immediately,
                )

            results.append(BatchPublishItemResult(
                purchase_id=pid,
                number=check.number,
                pub_id=pub.id,
                status="publishing",
                error=None,
            ))
        except Exception as e:
            results.append(BatchPublishItemResult(
                purchase_id=pid,
                number=check.number,
                status="failed",
                error=str(e)[:250],
            ))

    return results
