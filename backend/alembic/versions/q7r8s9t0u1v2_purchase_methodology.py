"""Методичка договора (purchases.methodology) + консолидация contract_form

Владелец: методические рекомендации («большая»/«малая» отчётность) больше не
отдельные шаблоны текста договора, а отдельный документ, приклеиваемый к
любой из семи договорных форм при генерации (см. app/routers/documents.py
generate_document, docxcompose). Форма договора «услуги» объединена
в один файл (contract_services.docx) — большая/малая отчётность больше не
определяет ТЕКСТ договора, только приклеиваемую методичку.

Добавляет идемпотентно (ADD COLUMN IF NOT EXISTS):
  purchases:
    - methodology  VARCHAR(10)  NULL  ('large' | 'small' | 'none')

Миграция данных (см. upgrade()):
  - contract_form='services_large' → methodology='large'
  - contract_form IN ('services_small', 'services_food') → methodology='small'
  - contract_form IN ('services_large', 'services_small') → contract_form='services'
  - contract_form='services_food' остаётся БЕЗ ИЗМЕНЕНИЙ (отдельная форма,
    не сливается с 'services')

Revision ID: q7r8s9t0u1v2
Revises: p9r2t5v8x1z4
Create Date: 2026-08-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'q7r8s9t0u1v2'
down_revision = 'u3v4w5x6y7z8'
branch_labels = None
depends_on = None


def _cols(table: str) -> set:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    existing = _cols('purchases')

    if 'methodology' not in existing:
        op.add_column('purchases', sa.Column(
            'methodology', sa.String(10), nullable=True
        ))

    # Миграция данных — только если у покупок ещё стоит старая раскладка
    # contract_form. Порядок важен: methodology проставляется по СТАРОМУ
    # значению contract_form, до того как contract_form переименован.
    op.execute(sa.text(
        "UPDATE purchases SET methodology = 'large' WHERE contract_form = 'services_large'"
    ))
    op.execute(sa.text(
        "UPDATE purchases SET methodology = 'small' "
        "WHERE contract_form IN ('services_small', 'services_food')"
    ))
    op.execute(sa.text(
        "UPDATE purchases SET contract_form = 'services' "
        "WHERE contract_form IN ('services_large', 'services_small')"
    ))
    # contract_form='services_food' намеренно НЕ трогаем — отдельная форма.


def downgrade():
    # Данные (methodology / переименованный contract_form) не откатываем —
    # симметричного обратного маппинга нет (services_large и services_small
    # необратимо слились в 'services'). Откатывается только колонка.
    op.execute(sa.text(
        'ALTER TABLE purchases DROP COLUMN IF EXISTS methodology'
    ))
