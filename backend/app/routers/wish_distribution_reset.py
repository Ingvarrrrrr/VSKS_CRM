"""«Сбросить разбивку» заявки — задача B (владелец, лист 2 №3, 2026-09-20).

Заявка, распределённая канбаном на НЕСКОЛЬКО закупок (approve-distribution,
split=True), потом отправленная на повторное согласование — уходит через
`_withdraw_wish_from_plan` (app/services/wish_distribution.py): её закупки НЕ
удаляются, а прячутся в статус 'wishes' (сохраняется история/файлы/чаты).
Если владелец хочет заново разбить заявку на группы ИНАЧЕ (не просто поправить
состав внутри уже сложившихся групп через wish_multi_sync — см. задачу A), эти
скрытые закупки-«пустышки» нужно СНЕСТИ целиком, чтобы следующее согласование
создало закупки заново по актуальным `target_column_key`
(`_distribute_wish_to_purchases`, group-by в wish_distribution.py).

DELETE /api/wishes/{wish_id}/distribution — подключён под-роутером в конце
app/routers/wish_items.py (`wish_items.router.include_router(router)`), тот же
приём, что plan_to_wish.py → feo_planned_items_matching.py: ЭТОТ router БЕЗ
собственного prefix — итоговый путь складывается из префикса РОДИТЕЛЯ
("/api/wishes", уже зарегистрирован в routes.py) + полного пути декоратора
ниже (см. докстринг plan_to_wish.py про double-prefix — у include_router
self.prefix применяется ПОВТОРНО, поэтому дублировать "/api/wishes" в prefix=
этого router нельзя, иначе получится "/api/wishes/api/wishes/...").

Условие: ВСЕ закупки заявки должны быть в статусе 'wishes' (то есть уже
откачены из плана — ни одна не в plan_schedule и тем более не дальше). Если
хоть одна не 'wishes' — 409 с перечислением блокирующих (номер, стадия
по-русски, тот же словарь STATUS_LABELS, что использует _withdraw_wish_from_plan/
_sync_purchase_from_wish).

ПРАВИЛО №6: удаление закупки — `app.routers.purchases.delete_purchase_core`
(та же реализация, что у DELETE /api/purchases/{pid}), каскады НЕ копируются
здесь.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import get_current_user
from app.models.user import User

router = APIRouter(tags=["wishes"])


@router.delete("/{wish_id}/distribution")
async def reset_wish_distribution(
    wish_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.routers.wishes import _load_wish
    from app.services.wish_access import _wish_linked_purchases
    from app.services.dictionaries import STATUS_LABELS as _STATUS_LABELS
    from app.routers.purchases import delete_purchase_core

    wish = await _load_wish(wish_id, db)

    purchases = await _wish_linked_purchases(wish.id, db)
    if not purchases:
        raise HTTPException(status_code=404, detail="У заявки нет закупок — сбрасывать нечего")

    blockers: list[str] = []
    for p in purchases:
        if p.status != "wishes":
            label = _STATUS_LABELS.get(p.status, p.status)
            blockers.append(f"№{p.purchase_number or p.id} «{p.item_name or ''}» на стадии «{label}»")
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=(
                "Разбивку нельзя сбросить: закупка " + "; ".join(blockers)
                + ". Сначала верните заявку на повторное согласование (закупки скрываются из плана автоматически) "
                "или отмените их в реестре закупок."
            ),
        )

    deleted_ids = [p.id for p in purchases]
    for p in purchases:
        await delete_purchase_core(p, db)
    # wish.purchase_id указывал на первую созданную закупку — если она среди
    # удалённых, обнуляем (ON DELETE SET NULL на FK сделал бы то же самое на
    # уровне БД, но объект `wish` уже в памяти сессии — явная правка нужна,
    # чтобы _enrich/последующий ответ не читали устаревшее значение).
    if wish.purchase_id in deleted_ids:
        wish.purchase_id = None
    await db.commit()

    return {"deleted_purchase_ids": deleted_ids, "wish_id": wish.id}
