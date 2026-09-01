"""contract_items.source_item_id — разовый backfill побитых связей (прод-инцидент)

Диагноз (сессия 2026-09-01, полный текст — см. docstring
app/services/contract_item_link.py): PUT закупки удаляет и пересоздаёт ВСЕ
её purchase_items под новыми id; FK contract_items.source_item_id объявлен
ON DELETE SET NULL — Postgres тут же обнуляет ссылку у договорных позиций,
скопированных из плана раньше. Фронт следом присылает договорные позиции со
СТАРЫМИ id, роутер их не находит и молча выбрасывает поле — связь теряется
навсегда. На проде так побиты 26 позиций в закупках 767, 785, 802, 807, 808,
841, 886, 902 (столько же NULL, сколько плановых позиций в каждой закупке).

Код (app/routers/purchases.py::update_purchase,
app/routers/contract_items.py::replace_all_contract_items) теперь чинит это
на лету через app.services.contract_item_link.relink_contract_items — но эта
миграция нужна ОТДЕЛЬНО, разовым backfill'ом, чтобы вылечить уже осевшие в
БД NULL: там старый purchase_item.id физически утрачен (обнулён раньше, чем
код узнал о новых id), relink с id_map тут не поможет — восстанавливаем
эвристикой по данным, которые СЕЙЧАС есть в обеих таблицах.

ЧТО ДЕЛАЕТ (весь UPDATE идемпотентен — трогает только
contract_items.source_item_id IS NULL; безопасен на пустой БД):

  Шаг 1 — по уникальному совпадению lower(btrim(name)) в пределах одной
    purchase_id: связывает, если СО СТОРОНЫ ПЛАНА однозначно — ровно один
    кандидат-purchase_item с этим именем в закупке, и он ещё не занят другой
    договорной позицией. Со стороны contract_items уникальность НЕ
    требуется: N договорных позиций с одинаковым NULL-именем и единственной
    подходящей плановой позицией — это разбитая позиция (D-05,
    splitContractRow в PurchaseItemsEditor.vue), легальный случай, когда
    несколько договорных строк намеренно делят одного родителя. Единственный
    возможный родитель у них у всех один — гадания тут нет, в отличие от
    стороны плана (там несколько кандидатов с одинаковым именем — это
    настоящая неоднозначность).

  Шаг 2 — по совпадению (quantity, unit_price) одновременно, с требованием
    однозначности с ОБЕИХ сторон, среди того, что осталось NULL/свободным
    после шага 1. Тут послаблять нельзя: у разбитых позиций количества и
    цены как раз РАЗНЫЕ, повтор здесь означал бы реальную ошибку сопоставления.

  Шаг 3 — позиционный 1↔1: row_number() OVER (PARTITION BY purchase_id ORDER
    BY id) отдельно по оставшимся NULL договорным и оставшимся свободным
    плановым позициям, СОПОСТАВЛЯЕТСЯ ТОЛЬКО для тех purchase_id, где число
    оставшихся NULL договорных позиций РОВНО равно числу оставшихся свободных
    плановых — иначе порядок id ничего не гарантирует.

  Неоднозначность на любом шаге → source_item_id остаётся NULL. Это прямое
  требование владельца (см. FEO_PATH_UNRESOLVED_LABEL в app/routers/
  documents.py): честная «категория не определена» лучше подставленной
  чужой категории.

Revision ID: k3m5p7r9t1v3
Revises: h8j2k4m6n8p0
Create Date: 2026-09-01 00:00:00.000000

down_revision привязан к ФАКТИЧЕСКОЙ закоммиченной голове на момент правки.
Пока писался этот фикс, параллельная сессия дважды достраивала цепочку
(f25e7fa19cbc → 2b00d0245ba5 → c4d5e6f7a8b9 → z9a8b7c6d5e4 → h8j2k4m6n8p0),
и миграция дважды оказывалась второй головой. Две миграции с одним родителем
= две головы = alembic upgrade head падает на старте бэкенда и прод отдаёт
502. ПЕРЕД push сверить голову ещё раз: `git ls-files backend/alembic/versions`
и убедиться, что ни у одной закоммиченной миграции нет down_revision,
равного нашему.
"""
import sqlalchemy as sa
from alembic import op

revision = 'k3m5p7r9t1v3'
down_revision = 'h8j2k4m6n8p0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if 'contract_items' not in tables or 'purchase_items' not in tables:
        return

    # Step 1: unique normalized-name match within one purchase.
    # Uniqueness is required on the PLAN side only — see module docstring
    # (several contract rows may legitimately share one plan row: D-05 split).
    op.execute(sa.text("""
        WITH plan_candidates AS (
            SELECT id AS pi_id, purchase_id, lower(btrim(item_name)) AS norm_name,
                   count(*) OVER (PARTITION BY purchase_id, lower(btrim(item_name))) AS cnt
            FROM purchase_items
        ),
        unique_plan AS (
            SELECT pi_id, purchase_id, norm_name FROM plan_candidates WHERE cnt = 1
        ),
        occupied AS (
            SELECT source_item_id FROM contract_items WHERE source_item_id IS NOT NULL
        ),
        free_plan AS (
            SELECT up.pi_id, up.purchase_id, up.norm_name
            FROM unique_plan up
            LEFT JOIN occupied o ON o.source_item_id = up.pi_id
            WHERE o.source_item_id IS NULL
        ),
        null_ci AS (
            SELECT ci.id AS ci_id, ci.purchase_id, lower(btrim(ci.name)) AS norm_name
            FROM contract_items ci
            WHERE ci.source_item_id IS NULL
        )
        UPDATE contract_items ci
        SET source_item_id = fp.pi_id
        FROM null_ci nci
        JOIN free_plan fp
            ON fp.purchase_id = nci.purchase_id AND fp.norm_name = nci.norm_name
        WHERE ci.id = nci.ci_id
          AND ci.source_item_id IS NULL
    """))

    # Step 2: unique (quantity, unit_price) match — strict on both sides.
    op.execute(sa.text("""
        WITH plan_candidates AS (
            SELECT id AS pi_id, purchase_id, quantity, unit_price,
                   count(*) OVER (PARTITION BY purchase_id, quantity, unit_price) AS cnt
            FROM purchase_items
            WHERE quantity IS NOT NULL AND unit_price IS NOT NULL
        ),
        unique_plan AS (
            SELECT pi_id, purchase_id, quantity, unit_price FROM plan_candidates WHERE cnt = 1
        ),
        occupied AS (
            SELECT source_item_id FROM contract_items WHERE source_item_id IS NOT NULL
        ),
        free_plan AS (
            SELECT up.pi_id, up.purchase_id, up.quantity, up.unit_price
            FROM unique_plan up
            LEFT JOIN occupied o ON o.source_item_id = up.pi_id
            WHERE o.source_item_id IS NULL
        ),
        ci_candidates AS (
            SELECT ci.id AS ci_id, ci.purchase_id, ci.quantity, ci.unit_price,
                   count(*) OVER (PARTITION BY ci.purchase_id, ci.quantity, ci.unit_price) AS cnt
            FROM contract_items ci
            WHERE ci.source_item_id IS NULL
              AND ci.quantity IS NOT NULL AND ci.unit_price IS NOT NULL
        ),
        unique_ci AS (
            SELECT ci_id, purchase_id, quantity, unit_price FROM ci_candidates WHERE cnt = 1
        )
        UPDATE contract_items ci
        SET source_item_id = fp.pi_id
        FROM unique_ci uc
        JOIN free_plan fp
            ON fp.purchase_id = uc.purchase_id
           AND fp.quantity = uc.quantity
           AND fp.unit_price = uc.unit_price
        WHERE ci.id = uc.ci_id
          AND ci.source_item_id IS NULL
    """))

    # Step 3: positional 1-to-1, only where remaining counts match exactly.
    op.execute(sa.text("""
        WITH occupied AS (
            SELECT source_item_id FROM contract_items WHERE source_item_id IS NOT NULL
        ),
        free_plan AS (
            SELECT pi.id AS pi_id, pi.purchase_id,
                   row_number() OVER (PARTITION BY pi.purchase_id ORDER BY pi.id) AS rn
            FROM purchase_items pi
            LEFT JOIN occupied o ON o.source_item_id = pi.id
            WHERE o.source_item_id IS NULL
        ),
        null_ci AS (
            SELECT ci.id AS ci_id, ci.purchase_id,
                   row_number() OVER (PARTITION BY ci.purchase_id ORDER BY ci.id) AS rn
            FROM contract_items ci
            WHERE ci.source_item_id IS NULL
        ),
        free_counts AS (
            SELECT purchase_id, count(*) AS free_cnt FROM free_plan GROUP BY purchase_id
        ),
        null_counts AS (
            SELECT purchase_id, count(*) AS null_cnt FROM null_ci GROUP BY purchase_id
        ),
        eligible_purchases AS (
            SELECT fc.purchase_id
            FROM free_counts fc
            JOIN null_counts nc ON nc.purchase_id = fc.purchase_id
            WHERE fc.free_cnt = nc.null_cnt
        )
        UPDATE contract_items ci
        SET source_item_id = fp.pi_id
        FROM null_ci nc
        JOIN free_plan fp ON fp.purchase_id = nc.purchase_id AND fp.rn = nc.rn
        JOIN eligible_purchases ep ON ep.purchase_id = nc.purchase_id
        WHERE ci.id = nc.ci_id
          AND ci.source_item_id IS NULL
    """))


def downgrade() -> None:
    # Откат восстановления данных бессмысленен: source_item_id, который тут
    # проставлен, — это ФАКТИЧЕСКИ утраченная информация, восстановленная
    # эвристикой (имя/цена/позиция). Обнулять её обратно значило бы намеренно
    # вернуть закупки в побитое состояние (снова «Категория ФЭО не определена»
    # в листах согласования) без какой-либо пользы.
    pass
