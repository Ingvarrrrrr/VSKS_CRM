"""feo_categories.plan_source/manual_plan_amount + plan_excess_approvals.plan_before/
plan_after (владелец, план zany-fluttering-mountain.md, 2026-08-13).

ПРИЧИНА. Категория «Расходные материалы для проведения окружных полуфиналов
соревнований» (id 3710, МИНПРОС_2026) висела с плашкой «план превышает заданный
вручную», хотя владелец эту сумму никогда не вводил — способ расчёта плана
УГАДЫВАЛСЯ по тому, пустые ли поля planned_quantity/planned_amount (см.
app/services/feo_plan.py, старый manual_plan_entered/excess_plan_over_manual).
Решение владельца: способ задаётся явным переключателем, а не угадывается.

  feo_categories:
    plan_source          VARCHAR(20) NOT NULL DEFAULT 'planned_items' —
                          'planned_items' (план = Σ плановых позиций категории) |
                          'manual_sum' (план = manual_plan_amount).
    manual_plan_amount    NUMERIC(15,2) NULL — плановая сумма ЦЕЛИКОМ (не за
                          единицу), вводится одним полем в режиме 'manual_sum'.

  plan_excess_approvals:
    plan_before  NUMERIC(15,2) NULL — план ДО согласования превышения.
    plan_after   NUMERIC(15,2) NULL — план ПОСЛЕ (см. app/models/plan_excess_approval.py).

БЭКФИЛЛ — ТОЛЬКО ЛИСТЬЯ (категории БЕЗ детей): у которых planned_quantity>0 AND
planned_amount>0 → plan_source='manual_sum', manual_plan_amount = их произведение.
НЕ-листья (направления/подкатегории) сознательно ИСКЛЮЧЕНЫ из бэкфилла, даже если
у них тоже заполнены planned_quantity/planned_amount старого формата — эти поля у
узлов С детьми исторически ИГНОРИРОВАЛИСЬ расчётом (compute_feo_plan_tree всегда
считал группу по Σ детей + собственным ИМЕНОВАННЫМ плановым позициям, НИКОГДА по
planned_quantity×planned_amount самой группы — см. её docstring, боевой пример
«Микроавтобус» после пропажи подкатегории показал цену 10 130 000 за штуку, id 905,
именно из-за такого поля). Обнаружено на локальной копии прод-базы: 39 групп с
обоими полями >0 (id 905 «Микроавтобус», 898 «Транспорт и техника», 863 и др.),
219 листьев — если бы бэкфилл затронул и группы, для них задним числом ожила бы
ровно та формула, которую чинили в прошлой сессии, а verification («ничего кроме
excess_plan_over_manual/manual_plan_entered/excess_plan_items не должно измениться»)
был бы нарушен по всем 39 категориям. Группа получает plan_source='manual_sum'
только если пользователь явно выберет это в форме (новый функционал вперёд, не
воскрешение старых мёртвых данных).

Идемпотентно (ADD COLUMN IF NOT EXISTS; бэкфилл — WHERE plan_source='planned_items'
AND manual_plan_amount IS NULL, безопасно против повторного прогона) — против
check_schema (migrate.py гонит upgrade head на старте, конфликт DDL роняет прод в 502).

Revision ID: q5r6s7t8u9v0
Revises: n0o1p2q3r4s5
Create Date: 2026-08-13 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'q5r6s7t8u9v0'
down_revision = 'n0o1p2q3r4s5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if 'feo_categories' in table_names:
        op.execute(sa.text(
            "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS "
            "plan_source VARCHAR(20) NOT NULL DEFAULT 'planned_items'"
        ))
        op.execute(sa.text(
            "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS "
            "manual_plan_amount NUMERIC(15, 2)"
        ))
        # Бэкфилл — см. docstring выше: ТОЛЬКО листья (нет дочерних категорий),
        # у которых оба старых поля > 0. Условие "plan_source='planned_items' AND
        # manual_plan_amount IS NULL" делает UPDATE идемпотентным — повторный
        # прогон (или прогон после ручной правки владельцем) ничего не перезапишет.
        op.execute(sa.text(
            """
            UPDATE feo_categories fc
            SET plan_source = 'manual_sum',
                manual_plan_amount = fc.planned_quantity * fc.planned_amount
            WHERE fc.planned_quantity IS NOT NULL AND fc.planned_amount IS NOT NULL
              AND fc.planned_quantity > 0 AND fc.planned_amount > 0
              AND fc.plan_source = 'planned_items'
              AND fc.manual_plan_amount IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM feo_categories ch WHERE ch.parent_id = fc.id
              )
            """
        ))

    if 'plan_excess_approvals' in table_names:
        op.execute(sa.text(
            "ALTER TABLE plan_excess_approvals ADD COLUMN IF NOT EXISTS "
            "plan_before NUMERIC(15, 2)"
        ))
        op.execute(sa.text(
            "ALTER TABLE plan_excess_approvals ADD COLUMN IF NOT EXISTS "
            "plan_after NUMERIC(15, 2)"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if 'plan_excess_approvals' in table_names:
        op.execute(sa.text("ALTER TABLE plan_excess_approvals DROP COLUMN IF EXISTS plan_after"))
        op.execute(sa.text("ALTER TABLE plan_excess_approvals DROP COLUMN IF EXISTS plan_before"))

    if 'feo_categories' in table_names:
        op.execute(sa.text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS manual_plan_amount"))
        op.execute(sa.text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS plan_source"))
