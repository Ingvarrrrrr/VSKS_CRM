"""Backfill: части разбиения закупки (parent_purchase_id) — wish_id/feo_per_item/
feo_category_id/status легаси 'planned' (задача 29.10.2026, прод, заявка 226).

Контекст (проверено на проде): заявку (wish 226) разбили кнопкой «Разбить на
закупки» → POST /purchases/{pid}/split → split_purchase_core (app/services/
purchase_split.py). Исходная закупка 4482 получила status='split', 0 позиций,
wish_id=226. 15 частей (4483-4497), созданные ДО правки этой задачи в
purchase_split.py, получили: wish_id=NULL (GET /wishes/226/purchases-board
открывал пустой канбан), status='planned' (легаси-значение вне STATUS_ORDER —
см. app/services/purchase_amounts.py:59-63), feo_per_item=False у 14 из 15 при
том, что позиции внутри части — РАЗНЫХ категорий ФЭО (унаследованных от разных
плановых позиций), feo_category_id шапки NULL — комбинация давала баннер
«РАСХОЖДЕНИЕ КАТЕГОРИИ ФЭО» (purchase_feo_checks.py::_item_feo_mismatch).

Эта миграция — ТОЛЬКО backfill существующих частей (без изменения схемы), той
же формулой, что теперь и app/services/purchase_split.py::resolve_part_feo_header
для НОВЫХ разбиений (ПРАВИЛО №6 — не второй механизм, тот же набор правил,
переписанный на SQL, т.к. alembic-миграция не тянет ORM-сервисы приложения):

  (a) wish_id: у частей (parent_purchase_id IS NOT NULL), чей родитель уже
      status='split' (т.е. родитель действительно прошёл разбиение, а не
      произвольный Purchase с FK на другую запись) — wish_id части := wish_id
      родителя, ТОЛЬКО если у части wish_id сейчас NULL (не трогаем часть,
      которую уже привязали к другой заявке руками).

  (b) feo_per_item: := TRUE для частей, у позиций которых >1 РАЗЛИЧНОЙ
      feo_category_id (NULL игнорируется при подсчёте различных) — "разные
      категории для каждого товара", раньше терялось при разбиении.

  (c) feo_category_id шапки: := единственная категория позиций части, ТОЛЬКО
      если шапка сейчас NULL и у всех позиций части РОВНО ОДНА (не NULL)
      категория — несовпадение шапки/позиций устраняется без выдумывания
      категории, когда она не определена однозначно.

  (d) status: 'planned' (легаси, не в STATUS_ORDER) → 'plan_schedule'
      (актуальный пред-договорный статус в STATUS_ORDER, app/routers/
      purchases.py::STATUS_ORDER) — ТОЛЬКО для частей (parent_purchase_id IS
      NOT NULL чей родитель status='split'); закупки-НЕ-части со статусом
      'planned' (если где-то на проде такие тоже есть) этой миграцией не
      трогаются — задача касается конкретно последствий разбиения.

Идемпотентна: каждый шаг отсекается WHERE-условием на несовпадение/отсутствие
значения — повторный прогон на уже исправленных строках ничего не меняет
(проверено: второй upgrade head rowcount=0 на всех четырёх UPDATE).

Downgrade: намеренно no-op — откат означал бы снятие уже верной связи
part↔wish и возврат легаси-статуса/потерю категории — небезопасно и не нужно
(тот же принцип, что у w6y8a0c2e4g6).

Revision ID: c7d9e1f3g5h7
Revises: d4f6h8j0k2m4
Create Date: 2026-10-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c7d9e1f3g5h7"
down_revision = "d4f6h8j0k2m4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # (a) wish_id части := wish_id родителя (родитель status='split'), только
    # если у части wish_id сейчас NULL.
    result_a = conn.execute(sa.text(
        """
        UPDATE purchases AS part
        SET wish_id = parent.wish_id
        FROM purchases AS parent
        WHERE part.parent_purchase_id = parent.id
          AND parent.status = 'split'
          AND part.wish_id IS NULL
          AND parent.wish_id IS NOT NULL
        """
    ))
    print(f"[c7d9e1f3g5h7] (a) wish_id проставлен частям: {result_a.rowcount}")

    # (b) feo_per_item := TRUE у частей, где >1 различной feo_category_id среди
    # позиций (NULL не считается отдельной категорией).
    result_b = conn.execute(sa.text(
        """
        UPDATE purchases AS part
        SET feo_per_item = TRUE
        FROM (
            SELECT purchase_id, COUNT(DISTINCT feo_category_id) AS n_cats
            FROM purchase_items
            WHERE feo_category_id IS NOT NULL
            GROUP BY purchase_id
        ) AS cats
        WHERE cats.purchase_id = part.id
          AND cats.n_cats > 1
          AND part.parent_purchase_id IS NOT NULL
          AND part.feo_per_item = FALSE
          AND EXISTS (
              SELECT 1 FROM purchases AS parent
              WHERE parent.id = part.parent_purchase_id AND parent.status = 'split'
          )
        """
    ))
    print(f"[c7d9e1f3g5h7] (b) feo_per_item включён у частей с разными категориями: {result_b.rowcount}")

    # (c) feo_category_id шапки := единственная категория позиций, когда шапка
    # NULL и у ВСЕХ позиций части ровно одна (не NULL) категория.
    result_c = conn.execute(sa.text(
        """
        UPDATE purchases AS part
        SET feo_category_id = cats.only_cat
        FROM (
            SELECT purchase_id, MIN(feo_category_id) AS only_cat, COUNT(DISTINCT feo_category_id) AS n_cats
            FROM purchase_items
            WHERE feo_category_id IS NOT NULL
            GROUP BY purchase_id
        ) AS cats
        WHERE cats.purchase_id = part.id
          AND cats.n_cats = 1
          AND part.feo_category_id IS NULL
          AND part.parent_purchase_id IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM purchases AS parent
              WHERE parent.id = part.parent_purchase_id AND parent.status = 'split'
          )
        """
    ))
    print(f"[c7d9e1f3g5h7] (c) feo_category_id шапки проставлена частям: {result_c.rowcount}")

    # (d) status 'planned' → 'plan_schedule' для частей (не для произвольной
    # закупки со статусом 'planned', не являющейся частью разбиения).
    result_d = conn.execute(sa.text(
        """
        UPDATE purchases AS part
        SET status = 'plan_schedule'
        FROM purchases AS parent
        WHERE part.parent_purchase_id = parent.id
          AND parent.status = 'split'
          AND part.status = 'planned'
        """
    ))
    print(f"[c7d9e1f3g5h7] (d) status 'planned' -> 'plan_schedule' у частей: {result_d.rowcount}")


def downgrade() -> None:
    pass
