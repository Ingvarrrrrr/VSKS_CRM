"""Повторный бэкфилл feo_categories.is_payroll по имени (найдено 13.10.2026,
план C:\\Users\\1\\.claude\\plans\\expense-kinds.md, задача «ДНР5»).

Повод: прод, субсидия «ДНР5» (id 97), статья «ФОТ и иные выплаты персоналу»
(33 881 012,80) — plan_payroll=0, вся сумма в unspecified. Причина — НЕ флаг
категории и НЕ регэксп is_payroll_name (он матчит это имя корректно): миграция
e3f5g7h9i1j3 (07.10.2026) проставила is_payroll ТОЛЬКО для категорий, уже
существовавших на момент её прогона, а её докстринг обещал, что дальше новые
статьи метит импорт — но импорт (app.services.feo_import_common.
find_or_create_category, единственное место, где импорт создаёт FeoCategory)
is_payroll вообще не трогал. Статья ДНР5 была создана/переимпортирована ПОСЛЕ
07.10.2026 и осталась is_payroll=false. Исправлено по месту в
find_or_create_category (теперь зовёт is_payroll_name при создании) — эта
миграция закрывает уже существующие такие дыры тем же разовым бэкфиллом, что
и e3f5g7h9i1j3 (та же формула app.services.feo_payroll.is_payroll_name,
ПРАВИЛО №6, SQL-перевод идентичен e3f5g7h9i1j3 построчно).

Идемпотентно — WHERE NOT is_payroll, безопасно гонять повторно.

Revision ID: d4f6h8j0k2l4
Revises: b2c4d6e8f0a2
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4f6h8j0k2l4'
down_revision = 'b2c4d6e8f0a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        r"""
        UPDATE feo_categories
        SET is_payroll = true
        WHERE NOT is_payroll
          AND (
            name ~* '(^|[^[:alpha:]])фот([^[:alpha:]]|$)'
            OR name ~* 'оплат[а-яё]*\s+труда'
            OR name ~* 'выплат[а-яё]*\s+персонал'
          )
        """
    ))


def downgrade() -> None:
    # Разовый бэкфилл — откат не возвращает прежние значения (как и у
    # e3f5g7h9i1j3), downgrade — no-op.
    pass
