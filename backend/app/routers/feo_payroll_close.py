"""«Закрыть ФОТ по статье» / «Отменить закрытие» — POST /api/feo-categories/
{cat_id}/payroll-close и /payroll-reopen (владелец, 22.10.2026, план
humble-stirring-emerson.md, шаг 1, вариант (в)).

Разрезано из feo_categories.py по тому же принципу, что feo_tree_ops.py
(Правило №5) — путь на сегмент длиннее catch-all "/{cat_id}" ядра, порядок
регистрации относительно feo_categories.router не важен.

ПРАВИЛО №8 (безопасность и связность):
  1) Закрыто по умолчанию — require_tab('feo_categories') + право
     редактировать ФЭО (_require_feo_category_write) И право «Видеть ФОТ»
     (subsidy.view_payroll) — обе проверки, как у остальных действий с ФОТ
     (update_category выше в этом же модуле).
  2) Личность — из токена (current_user), id категории проверяется запросом
     к БД ДО любой проверки прав (cat is None → 404 раньше любого 403).
  3) Статья, которая НЕ является ФОТ (is_effectively_payroll=False) —
     422, не 500/200 молча.
  4) Скрытая/чужая статья отвечает 404, как и остальные ручки feo_categories.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.permissions import require_tab
from app.models.feo_category import FeoCategory
from app.routers import feo_categories as fc
from app.services import feo_payroll_close

router = APIRouter(prefix="/api/feo-categories", tags=["feo_categories"])


async def _load_cat_for_payroll_close(
    cat_id: int, db: AsyncSession, current_user,
) -> FeoCategory:
    cat = (await db.execute(select(FeoCategory).where(FeoCategory.id == cat_id))).scalar_one_or_none()
    if cat is None or cat.subsidy_id is None:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    # Статья ФОТ скрытых субсидий отвечает как несуществующая (ПРАВИЛО №8 п.2,
    # тот же приём, что у get_category_subtree выше в feo_categories.py).
    from app.auth.object_visibility import ensure_subsidy_visible
    await ensure_subsidy_visible(current_user, cat.subsidy_id, db)
    from app.services.payroll_visibility import hidden_payroll_category_ids
    if cat_id in await hidden_payroll_category_ids(current_user, db, [cat.subsidy_id]):
        raise HTTPException(status_code=404, detail="Категория не найдена")

    await fc._require_feo_category_write(current_user, db, cat.subsidy_id)
    from app.services.subsidy_revision_guard import assert_direct_edit
    await assert_direct_edit(db, current_user, cat.subsidy_id)

    from app.services.payroll_visibility import can_view_subsidy_payroll
    if not await can_view_subsidy_payroll(current_user, db, cat.subsidy_id):
        raise HTTPException(status_code=403, detail="Нет права «Видеть ФОТ»")

    if not await feo_payroll_close.is_effectively_payroll(db, cat):
        raise HTTPException(status_code=422, detail="Эта статья не относится к ФОТ")
    return cat


async def _toggle(cat_id: int, closed: bool, db: AsyncSession, current_user) -> dict:
    cat = await _load_cat_for_payroll_close(cat_id, db, current_user)
    result = await feo_payroll_close.set_payroll_closed(db, current_user, cat, closed)
    await db.commit()
    await db.refresh(cat)
    return {
        "id": cat.id,
        "name": cat.name,
        "subsidy_id": cat.subsidy_id,
        "payroll_closed": cat.payroll_closed,
        "old_plan": round(result["old_plan"], 2),
        "new_plan": round(result["new_plan"], 2),
        "released_amount": round(result["delta"], 2),
    }


@router.post("/{cat_id}/payroll-close")
async def close_payroll_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """Нажали «Закрыть ФОТ по статье» — план статьи перестаёт быть защищён от
    замещения «заказ вместо плана» (fairness: это именно то поведение, что
    было ДО шага 1 этого плана), невыплаченный остаток уходит в «Свободно».
    released_amount — на сколько упал план статьи (та же разница, что видна
    на экране «Свободно» выросло/«Запланировано» упало)."""
    return await _toggle(cat_id, True, db, current_user)


@router.post("/{cat_id}/payroll-reopen")
async def reopen_payroll_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_tab('feo_categories')),
):
    """«Отменить закрытие» — защита возвращается, план статьи снова полный
    (невыплаченный остаток снова входит в «Запланировано»/строку «ФОТ»
    карточки «Можно перераспределить»). released_amount будет ОТРИЦАТЕЛЬНЫМ
    (план вырос, а не упал) — фронт показывает это как «вернулось в план»."""
    return await _toggle(cat_id, False, db, current_user)
