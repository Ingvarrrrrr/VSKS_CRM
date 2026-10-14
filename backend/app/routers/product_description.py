"""История описаний каталога + предложения правок (Этап В, план
item-tz-description.md, владелец 14.10.2026). Литеральные хвосты пути
("/description-history", "/description-proposals") — длиннее catch-all
"/{product_id}" products.router, по форме не конфликтуют, но
регистрируется ДО products.router в app/routes.py по тому же соглашению,
что и остальные products_* соседи (см. докстринг app/routers/products.py).

Эндпоинты:
  GET  /api/products/{id}/description-history           — видят все с доступом к каталогу
  POST /api/products/{id}/description-history/{hid}/revert — только с products.edit_catalog
  POST /api/products/{id}/description-proposals          — любой авторизованный
  GET  /api/products/description-proposals?status=pending — только с products.edit_catalog
  POST /api/products/description-proposals/{pid}/accept   — только с products.edit_catalog
  POST /api/products/description-proposals/{pid}/reject   — только с products.edit_catalog
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.product import Product
from app.models.product_description_history import ProductDescriptionHistory
from app.models.product_description_proposal import ProductDescriptionProposal
from app.models.user import User
from app.schemas.product_description import (
    ProductDescriptionHistoryOut,
    ProductDescriptionProposalAcceptOut,
    ProductDescriptionProposalCreate,
    ProductDescriptionProposalDecision,
    ProductDescriptionProposalOut,
)
from app.services.product_catalog_guard import assert_can_edit_catalog
from app.services.product_description_history import revert_product_description
from app.services.product_description_proposals import (
    accept_description_proposal,
    create_description_proposal,
    list_pending_proposals,
    reject_description_proposal,
)

router = APIRouter(prefix="/api/products", tags=["products"])


def _user_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    return user.full_name or user.username


async def _get_product_or_404(db: AsyncSession, product_id: int) -> Product:
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Товар не найден")
    return product


@router.get(
    "/description-proposals",
    response_model=list[ProductDescriptionProposalOut],
)
async def list_description_proposals(
    status: Optional[str] = Query("pending"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список предложений правок — видит только тот, кто может их решать
    (products.edit_catalog). Сортировка — свежие первыми."""
    await assert_can_edit_catalog(current_user, db)
    rows = await list_pending_proposals(db, status=status)
    product_ids = {r.product_id for r in rows}
    products_by_id = {}
    if product_ids:
        products = (await db.execute(
            select(Product).where(Product.id.in_(product_ids))
        )).scalars().all()
        products_by_id = {p.id: p for p in products}
    user_ids = {r.proposed_by for r in rows if r.proposed_by}
    users_by_id = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_by_id = {u.id: u for u in users}

    out = []
    for r in rows:
        product = products_by_id.get(r.product_id)
        author = users_by_id.get(r.proposed_by)
        out.append(ProductDescriptionProposalOut(
            id=r.id, product_id=r.product_id,
            product_name=product.name if product else None,
            field=r.field, proposed_value=r.proposed_value,
            current_value_at_proposal=r.current_value_at_proposal,
            wish_item_id=r.wish_item_id, purchase_item_id=r.purchase_item_id,
            proposed_by=r.proposed_by, proposed_by_name=_user_name(author),
            proposed_at=r.proposed_at, status=r.status,
            decided_by=r.decided_by, decided_at=r.decided_at,
            decision_comment=r.decision_comment,
        ))
    return out


@router.post(
    "/description-proposals/{proposal_id}/accept",
    response_model=ProductDescriptionProposalAcceptOut,
)
async def accept_proposal(
    proposal_id: int,
    body: ProductDescriptionProposalDecision = ProductDescriptionProposalDecision(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_can_edit_catalog(current_user, db)
    proposal, changed_since_proposal = await accept_description_proposal(
        db, proposal_id, current_user, comment=body.comment,
    )
    await db.commit()
    await db.refresh(proposal)
    return ProductDescriptionProposalAcceptOut(
        proposal=ProductDescriptionProposalOut.model_validate(proposal, from_attributes=True),
        changed_since_proposal=changed_since_proposal,
    )


@router.post(
    "/description-proposals/{proposal_id}/reject",
    response_model=ProductDescriptionProposalOut,
)
async def reject_proposal(
    proposal_id: int,
    body: ProductDescriptionProposalDecision = ProductDescriptionProposalDecision(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_can_edit_catalog(current_user, db)
    proposal = await reject_description_proposal(db, proposal_id, current_user, comment=body.comment)
    await db.commit()
    await db.refresh(proposal)
    return proposal


@router.get(
    "/{product_id}/description-history",
    response_model=list[ProductDescriptionHistoryOut],
)
async def get_description_history(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Видит история любой авторизованный с доступом к каталогу (вкладка
    products — та же видимость, что и у самой карточки товара), правка —
    отдельная, более узкая галочка (products.edit_catalog)."""
    await _get_product_or_404(db, product_id)
    rows = (await db.execute(
        select(ProductDescriptionHistory)
        .where(ProductDescriptionHistory.product_id == product_id)
        .order_by(ProductDescriptionHistory.changed_at.desc())
    )).scalars().all()
    user_ids = {r.user_id for r in rows if r.user_id}
    users_by_id = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_by_id = {u.id: u for u in users}
    return [
        ProductDescriptionHistoryOut(
            id=r.id, product_id=r.product_id, field=r.field,
            old_value=r.old_value, new_value=r.new_value,
            user_id=r.user_id, user_name=_user_name(users_by_id.get(r.user_id)),
            changed_at=r.changed_at, source=r.source, proposal_id=r.proposal_id,
        )
        for r in rows
    ]


@router.post(
    "/{product_id}/description-history/{history_id}/revert",
    response_model=ProductDescriptionHistoryOut,
)
async def revert_description_history(
    product_id: int,
    history_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assert_can_edit_catalog(current_user, db)
    product = await _get_product_or_404(db, product_id)
    try:
        created = await revert_product_description(db, product, history_id, current_user)
    except ValueError as e:
        raise HTTPException(404, str(e))
    await db.commit()
    await db.refresh(created)
    return ProductDescriptionHistoryOut(
        id=created.id, product_id=created.product_id, field=created.field,
        old_value=created.old_value, new_value=created.new_value,
        user_id=created.user_id, user_name=_user_name(current_user),
        changed_at=created.changed_at, source=created.source, proposal_id=created.proposal_id,
    )


@router.post(
    "/{product_id}/description-proposals",
    response_model=ProductDescriptionProposalOut,
)
async def propose_description(
    product_id: int,
    body: ProductDescriptionProposalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Любой авторизованный может предложить правку. Если у автора есть
    products.edit_catalog — применяется сразу (status вернётся 'accepted')."""
    product = await _get_product_or_404(db, product_id)
    try:
        proposal = await create_description_proposal(
            db, product, body.field, body.proposed_value, current_user,
            wish_item_id=body.wish_item_id, purchase_item_id=body.purchase_item_id,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    await db.commit()
    await db.refresh(proposal)
    return ProductDescriptionProposalOut(
        id=proposal.id, product_id=proposal.product_id, product_name=product.name,
        field=proposal.field, proposed_value=proposal.proposed_value,
        current_value_at_proposal=proposal.current_value_at_proposal,
        wish_item_id=proposal.wish_item_id, purchase_item_id=proposal.purchase_item_id,
        proposed_by=proposal.proposed_by, proposed_by_name=_user_name(current_user),
        proposed_at=proposal.proposed_at, status=proposal.status,
        decided_by=proposal.decided_by, decided_at=proposal.decided_at,
        decision_comment=proposal.decision_comment,
    )
