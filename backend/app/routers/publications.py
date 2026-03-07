import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from typing import List

from app.database import get_db
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.contractor import Contractor
from app.models.subsidy import Subsidy
from app.schemas.schemas import PublishRequest, PublicationOut, PublicationStatusUpdate
from app.auth.jwt import get_current_user

router = APIRouter(prefix="/api/publications", tags=["publications"])

# n8n webhook URLs — заменить после настройки n8n workflow
N8N_WEBHOOKS = {
    "fabrikant":     "http://n8n:5678/webhook/fabrikant-publish",
    "roseltorg_rb":  "http://n8n:5678/webhook/roseltorg-publish",
}

PLATFORM_LABELS = {
    "fabrikant":    "Фабрикант",
    "roseltorg_rb": "Росэлторг.Бизнес",
}


async def _build_publish_payload(purchase_id: int, db: AsyncSession) -> dict:
    """Собирает все данные закупки для отправки в n8n."""
    res = await db.execute(select(Purchase).where(Purchase.id == purchase_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Закупка не найдена")

    items_res = await db.execute(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase_id))
    items = items_res.scalars().all()

    contractor = None
    if p.contractor_id:
        c_res = await db.execute(select(Contractor).where(Contractor.id == p.contractor_id))
        contractor = c_res.scalar_one_or_none()

    subsidy = None
    if p.subsidy_id:
        s_res = await db.execute(select(Subsidy).where(Subsidy.id == p.subsidy_id))
        subsidy = s_res.scalar_one_or_none()

    return {
        "purchase_id":      p.id,
        "registry_number":  p.registry_number,
        "subject":          p.subject,
        "nmck":             float(p.total_nmck or p.planned_total_price or 0),
        "purchase_method":  p.purchase_method,
        "contract_type":    p.purchase_contract_type,
        "execution_term":   str(p.execution_term) if p.execution_term else None,
        "feo_category_id":  p.feo_category_id,
        "contractor": {
            "name": contractor.name if contractor else None,
            "inn":  contractor.inn  if contractor else None,
            "ogrn": contractor.ogrn if contractor else None,
            "kpp":  getattr(contractor, "kpp", None) if contractor else None,
        } if contractor else None,
        "subsidy": {
            "id":   subsidy.id   if subsidy else None,
            "name": subsidy.name if subsidy else None,
        } if subsidy else None,
        "items": [
            {
                "item_name":  i.item_name,
                "item_type":  i.item_type,
                "quantity":   float(i.quantity or 0),
                "unit":       i.unit,
                "unit_price": float(i.unit_price or 0),
                "total_price": float(i.total_price or 0),
            }
            for i in items
        ],
    }


async def _call_n8n(pub_id: int, platform: str, payload: dict):
    """Фоновый вызов n8n webhook."""
    url = N8N_WEBHOOKS.get(platform)
    if not url:
        return
    payload["publication_id"] = pub_id
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(url, json=payload)
    except Exception:
        pass  # n8n сам вернёт статус через callback


@router.get("/purchases/{purchase_id}", response_model=List[PublicationOut])
async def get_publications(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    res = await db.execute(
        select(PlatformPublication)
        .where(PlatformPublication.purchase_id == purchase_id)
        .order_by(PlatformPublication.created_at.desc())
    )
    return res.scalars().all()


@router.post("/purchases/{purchase_id}", response_model=PublicationOut)
async def publish_purchase(
    purchase_id: int,
    body: PublishRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    if body.platform not in N8N_WEBHOOKS:
        raise HTTPException(400, f"Неизвестная площадка: {body.platform}")

    # Проверяем, нет ли уже активной публикации на эту площадку
    existing = await db.execute(
        select(PlatformPublication).where(
            PlatformPublication.purchase_id == purchase_id,
            PlatformPublication.platform == body.platform,
            PlatformPublication.status.in_(["pending", "publishing", "published"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Закупка уже опубликована или публикуется на {PLATFORM_LABELS.get(body.platform)}")

    payload = await _build_publish_payload(purchase_id, db)

    pub = PlatformPublication(
        purchase_id=purchase_id,
        platform=body.platform,
        status="publishing",
    )
    db.add(pub)
    await db.commit()
    await db.refresh(pub)

    background_tasks.add_task(_call_n8n, pub.id, body.platform, payload)
    return pub


@router.patch("/{pub_id}/status", response_model=PublicationOut)
async def update_publication_status(
    pub_id: int,
    body: PublicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Callback от n8n — обновляет статус публикации."""
    res = await db.execute(select(PlatformPublication).where(PlatformPublication.id == pub_id))
    pub = res.scalar_one_or_none()
    if not pub:
        raise HTTPException(404, "Публикация не найдена")

    pub.status = body.status
    if body.external_id:
        pub.external_id = body.external_id
    if body.external_url:
        pub.external_url = body.external_url
    if body.error_text:
        pub.error_text = body.error_text
    if body.status == "published":
        pub.published_at = datetime.now(timezone.utc)
    pub.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pub)
    return pub
