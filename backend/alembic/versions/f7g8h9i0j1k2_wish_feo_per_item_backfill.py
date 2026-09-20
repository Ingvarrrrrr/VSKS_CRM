"""Backfill: Wish.feo_per_item=True для заявок из плана до правки сервиса
(владелец, 2026-09-20, блокер): app/services/plan_to_wish.py::create_wish_from_plan
раньше при позициях из НЕСКОЛЬКИХ категорий ФЭО обнулял feo_category_id заявки,
но НЕ включал feo_per_item — фронт показывал заявку без категории и без
режима «своя категория у каждого товара», хотя у самих позиций (wish_items)
feo_category_id уже был проставлен правильно (по их плановой позиции). Код
исправлен отдельно (та же сессия); эта миграция — только backfill уже
созданных до фикса заявок.

Условие ровно повторяет симптом: feo_category_id заявки пуст (создатель не
смог выбрать одну общую категорию) И feo_per_item ещё не включён И среди
позиций заявки реально есть хоть одна с проставленной feo_category_id — то
есть заявка была заведена по этому же пути (plan-to-wish), а не через ручное
создание без категорий вовсе.

Идемпотентна (WHERE feo_per_item = false — повторный прогон ничего не меняет).
Downgrade — намеренно no-op (откат стирал бы уже верный режим показа).

Revision ID: f7g8h9i0j1k2
Revises: y1z2a3b4c5d6
Create Date: 2026-09-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f7g8h9i0j1k2"
down_revision = "y1z2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text(
        """
        UPDATE wishes
        SET feo_per_item = true
        WHERE feo_category_id IS NULL
          AND feo_per_item = false
          AND EXISTS (
              SELECT 1 FROM wish_items wi
              WHERE wi.wish_id = wishes.id
                AND wi.feo_category_id IS NOT NULL
          )
        """
    ))
    print(f"[f7g8h9i0j1k2] wishes.feo_per_item включён для заявок из плана с разными категориями позиций: {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — см. докстринг модуля.
    pass
