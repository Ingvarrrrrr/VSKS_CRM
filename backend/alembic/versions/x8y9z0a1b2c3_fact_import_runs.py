"""fact_import_runs — «Импорт факта» (уже совершённые закупки из таблиц
ведения субсидии, задача 02.10.2026, план breezy-mixing-lovelace.md часть 2).

Добавляет идемпотентно (IF NOT EXISTS / inspector-guard, ПРАВИЛО миграций
— check_schema/автодеплой может перегонять upgrade head повторно):
  - таблица fact_import_runs: один прогон мастера «Импорт факта» (sheets/
    preview/commit), хранит decisions/mapping и итоговый report, чтобы
    GET /runs/{id} и POST /runs/{id}/rollback могли работать без повторного
    парсинга файла;
  - purchases.import_run_id, payments.import_run_id — FK SET NULL + индекс,
    чтобы rollback.py мог найти все объекты, созданные ОДНИМ прогоном, без
    побочных признаков (временный номер договора/manual-платёж без номера
    сами по себе не уникальны для прогона).

down_revision — после a1b3c5d7e9f1 (корректировка субсидии, bfb81880; цепочка перестроена 02.10, чтобы не было двух голов).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = 'x8y9z0a1b2c3'
down_revision = 'a1b3c5d7e9f1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if 'fact_import_runs' not in existing_tables:
        op.create_table(
            'fact_import_runs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('subsidy_id', sa.Integer(),
                       sa.ForeignKey('subsidies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(),
                       sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('filename', sa.String(length=500), nullable=True),
            sa.Column('sheet', sa.String(length=255), nullable=True),
            sa.Column('format', sa.String(length=20), nullable=True),  # 'columns' | 'sections'
            sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()),
                       nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column('decisions', postgresql.JSONB(astext_type=sa.Text()),
                       nullable=False, server_default=sa.text("'{}'::jsonb")),
            # status: 'committed' | 'rolled_back'
            sa.Column('status', sa.String(length=20), nullable=False, server_default='committed'),
            sa.Column('purchases_created', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('payments_created', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('contractors_created', sa.Integer(), nullable=False, server_default='0'),
            # created_refs — все id новых объектов этого прогона (contractor_ids,
            # contract_ids, planned_item_ids, purchase_ids) — rollback.py удаляет
            # по этим ссылкам осиротевшие объекты (контрагент/плановая позиция,
            # заведённые ТОЛЬКО этим прогоном), не по глобальному признаку.
            sa.Column('created_refs', postgresql.JSONB(astext_type=sa.Text()),
                       nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column('report', postgresql.JSONB(astext_type=sa.Text()),
                       nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_fact_import_runs_subsidy_id', 'fact_import_runs', ['subsidy_id'])

    purchases_cols = {c['name'] for c in inspector.get_columns('purchases')}
    if 'import_run_id' not in purchases_cols:
        op.add_column(
            'purchases',
            sa.Column('import_run_id', sa.Integer(),
                      sa.ForeignKey('fact_import_runs.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index('ix_purchases_import_run_id', 'purchases', ['import_run_id'])

    payments_cols = {c['name'] for c in inspector.get_columns('payments')}
    if 'import_run_id' not in payments_cols:
        op.add_column(
            'payments',
            sa.Column('import_run_id', sa.Integer(),
                      sa.ForeignKey('fact_import_runs.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index('ix_payments_import_run_id', 'payments', ['import_run_id'])


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    payments_cols = {c['name'] for c in inspector.get_columns('payments')}
    if 'import_run_id' in payments_cols:
        op.drop_index('ix_payments_import_run_id', table_name='payments')
        op.drop_column('payments', 'import_run_id')

    purchases_cols = {c['name'] for c in inspector.get_columns('purchases')}
    if 'import_run_id' in purchases_cols:
        op.drop_index('ix_purchases_import_run_id', table_name='purchases')
        op.drop_column('purchases', 'import_run_id')

    existing_tables = set(inspector.get_table_names())
    if 'fact_import_runs' in existing_tables:
        op.drop_index('ix_fact_import_runs_subsidy_id', table_name='fact_import_runs')
        op.drop_table('fact_import_runs')
