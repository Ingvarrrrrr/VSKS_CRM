"""Предложения правок описания каталога (Этап В, план item-tz-description.md,
владелец 14.10.2026). Единая точка создания/принятия/отклонения (ПРАВИЛО
№6) — эндпоинты в app/routers/product_description.py только парсят вход и
зовут эти функции, повторной бизнес-логики там нет.

create_description_proposal: если у автора уже есть право
products.edit_catalog — применяется СРАЗУ (через
app.services.product_description_history.set_product_description,
source='proposal', status='accepted'), как и решил владелец: «с галочкой —
сразу применяется, тоже с историей». Без галочки — создаётся pending-запись,
ждёт человека с галочкой.
"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_description_proposal import ProductDescriptionProposal
from app.models.user import User
from app.services.product_catalog_guard import can_edit_catalog
from app.services.product_description_history import DESCRIPTION_FIELDS, set_product_description


async def create_description_proposal(
    db: AsyncSession,
    product: Product,
    field: str,
    proposed_value: Optional[str],
    user: User,
    wish_item_id: Optional[int] = None,
    purchase_item_id: Optional[int] = None,
) -> ProductDescriptionProposal:
    if field not in DESCRIPTION_FIELDS:
        raise ValueError(f"Неизвестное поле описания: {field}")

    proposal = ProductDescriptionProposal(
        product_id=product.id,
        field=field,
        proposed_value=proposed_value,
        current_value_at_proposal=getattr(product, field),
        wish_item_id=wish_item_id,
        purchase_item_id=purchase_item_id,
        proposed_by=user.id,
        proposed_at=datetime.utcnow(),
        status="pending",
    )
    db.add(proposal)
    await db.flush()

    if await can_edit_catalog(user, db):
        await set_product_description(
            db, product, field, proposed_value, user,
            source="proposal", proposal_id=proposal.id,
        )
        proposal.status = "accepted"
        proposal.decided_by = user.id
        proposal.decided_at = datetime.utcnow()
        proposal.decision_comment = "Применено автоматически — у автора есть право «Редактировать каталог товаров»"
        await db.flush()
    return proposal


async def _load_pending_or_404(db: AsyncSession, proposal_id: int) -> ProductDescriptionProposal:
    proposal = await db.get(ProductDescriptionProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Предложение не найдено")
    return proposal


async def accept_description_proposal(
    db: AsyncSession, proposal_id: int, user: User, comment: Optional[str] = None,
) -> tuple[ProductDescriptionProposal, bool]:
    """Принимает предложение — применяет значение к товару через
    set_product_description, даже если описание товара успело измениться
    после подачи (владелец: «всё равно применяем»). Возвращает
    (proposal, changed_since_proposal)."""
    proposal = await _load_pending_or_404(db, proposal_id)
    if proposal.status != "pending":
        raise HTTPException(409, "Предложение уже рассмотрено")

    product = await db.get(Product, proposal.product_id)
    if product is None:
        raise HTTPException(404, "Товар не найден")

    current_value = getattr(product, proposal.field)
    changed_since_proposal = (
        (current_value or "").strip() != (proposal.current_value_at_proposal or "").strip()
    )

    await set_product_description(
        db, product, proposal.field, proposal.proposed_value, user,
        source="proposal", proposal_id=proposal.id,
    )
    proposal.status = "accepted"
    proposal.decided_by = user.id
    proposal.decided_at = datetime.utcnow()
    proposal.decision_comment = comment
    await db.flush()
    return proposal, changed_since_proposal


async def reject_description_proposal(
    db: AsyncSession, proposal_id: int, user: User, comment: Optional[str] = None,
) -> ProductDescriptionProposal:
    proposal = await _load_pending_or_404(db, proposal_id)
    if proposal.status != "pending":
        raise HTTPException(409, "Предложение уже рассмотрено")
    proposal.status = "rejected"
    proposal.decided_by = user.id
    proposal.decided_at = datetime.utcnow()
    proposal.decision_comment = comment
    await db.flush()
    return proposal


async def list_pending_proposals(db: AsyncSession, status: Optional[str] = "pending") -> list:
    q = select(ProductDescriptionProposal)
    if status:
        q = q.where(ProductDescriptionProposal.status == status)
    q = q.order_by(ProductDescriptionProposal.proposed_at.desc())
    return (await db.execute(q)).scalars().all()
