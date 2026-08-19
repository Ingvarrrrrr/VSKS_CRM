"""bank_payments/bank_statement_imports: org-скоуп, subsidy_id, external_doc_id

Этап 1 утверждённого плана (SaaS-изоляция реестра платежей).

БАГИ (аудит 2026-08-19):
  1. У bank_payments и bank_statement_imports НЕТ org_id вообще (у импорта
     только uploaded_by_id) — ни один эндпоинт реестра не фильтрует по
     организации, только require_tab/require_action. Пользователь другой
     организации видит всю чужую банковскую выписку — это приватные данные
     разных подписчиков SaaS.
  2. Колонка выгрузки «Идентификатор документа» парсером не читалась вовсе;
     дубли ловились только по source_row_hash (SHA-256 всей строки) — при
     малейшем отличии строки та же платёжка приезжала второй раз.
  3. Строки с отклонёнными статусами не импортировались вовсе — увидеть
     аннулированный платёж было негде.
  4. bank_payments.import_id был ON DELETE CASCADE — откат прогона сносил
     платежи вместе с журналом партии.

ЧТО ДЕЛАЕТ МИГРАЦИЯ (идемпотентно, безопасно для повторного прогона):
  1. bank_payments += org_id (FK organizations, SET NULL), subsidy_id (FK
     subsidies, SET NULL), external_doc_id varchar(100).
  2. Частичный уникальный индекс по external_doc_id (WHERE IS NOT NULL).
  3. bank_statement_imports += org_id, rows_no_subsidy.
  4. bank_payments.import_id: FK меняется с ON DELETE CASCADE на ON DELETE
     SET NULL (партия импорта теперь удаляется автоматически после успешного
     прогона — Этап 1 роутера, — платежи должны пережить это удаление).
  5. Бэкфилл: bank_payments.subsidy_id/org_id по совпадению
     bank_payments.basis_doc_number == subsidies.basis_doc_number (та же
     логика, что payment_matcher.resolve_subsidy использует как первый,
     самый точный шаг). Строки без опознанного соглашения остаются NULL —
     это не ошибка миграции, а честное отражение того, что субсидии с таким
     basis_doc_number в БД ещё нет.
  6. Право payment.registry_view (действие) — отдельный гейт для полного
     реестра/сверки/импорта, независимый от привязки платежа к закупке.
     Дефолтные грантополучатели — те же роли, что уже имели вкладку
     payment_registry (superadmin/admin/org_admin/manager/employee), чтобы
     миграция не меняла доступ существующих пользователей в день выката.

downgrade(): убирает добавленные констрейнты/индекс/колонки. Бэкфилленные
значения subsidy_id/org_id и permission-сиды не откатываются намеренно —
это данные, а не испорченное состояние, откатывать в NULL/убирать право
незачем (см. паттерн i0j1k2l3m4n5).

Revision ID: y2z3a4b5c6d7
Revises: i0j1k2l3m4n5
Create Date: 2026-08-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'y2z3a4b5c6d7'
down_revision = 'i0j1k2l3m4n5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "bank_payments" not in existing_tables or "bank_statement_imports" not in existing_tables:
        return

    bp_cols = {c["name"] for c in inspector.get_columns("bank_payments")}
    imp_cols = {c["name"] for c in inspector.get_columns("bank_statement_imports")}

    # --- 1. bank_payments: новые колонки ---
    if "org_id" not in bp_cols:
        op.execute(sa.text(
            "ALTER TABLE bank_payments ADD COLUMN org_id INTEGER "
            "REFERENCES organizations(id) ON DELETE SET NULL"
        ))
        print("[y2z3a4b5c6d7] bank_payments.org_id добавлен")
    if "subsidy_id" not in bp_cols:
        op.execute(sa.text(
            "ALTER TABLE bank_payments ADD COLUMN subsidy_id INTEGER "
            "REFERENCES subsidies(id) ON DELETE SET NULL"
        ))
        print("[y2z3a4b5c6d7] bank_payments.subsidy_id добавлен")
    if "external_doc_id" not in bp_cols:
        op.execute(sa.text(
            "ALTER TABLE bank_payments ADD COLUMN external_doc_id VARCHAR(100)"
        ))
        print("[y2z3a4b5c6d7] bank_payments.external_doc_id добавлен")

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_bank_payments_org_id ON bank_payments (org_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_bank_payments_subsidy_id ON bank_payments (subsidy_id)"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_bank_payment_external_doc_id "
        "ON bank_payments (external_doc_id) WHERE external_doc_id IS NOT NULL"
    ))

    # --- 2. bank_statement_imports: новые колонки ---
    if "org_id" not in imp_cols:
        op.execute(sa.text(
            "ALTER TABLE bank_statement_imports ADD COLUMN org_id INTEGER "
            "REFERENCES organizations(id) ON DELETE SET NULL"
        ))
        print("[y2z3a4b5c6d7] bank_statement_imports.org_id добавлен")
    if "rows_no_subsidy" not in imp_cols:
        op.execute(sa.text(
            "ALTER TABLE bank_statement_imports ADD COLUMN rows_no_subsidy INTEGER DEFAULT 0"
        ))
        print("[y2z3a4b5c6d7] bank_statement_imports.rows_no_subsidy добавлен")

    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_bank_statement_imports_org_id ON bank_statement_imports (org_id)"
    ))

    # --- 3. import_id: ON DELETE CASCADE → ON DELETE SET NULL + nullable ---
    # (Postgres не поддерживает "ADD CONSTRAINT IF NOT EXISTS" — guard по pg_constraint.)
    fk_row = bind.execute(sa.text(
        "SELECT confdeltype FROM pg_constraint "
        "WHERE conname = 'bank_payments_import_id_fkey' AND conrelid = 'bank_payments'::regclass"
    )).fetchone()
    if fk_row is not None and fk_row[0] != 'n':  # 'n' = SET NULL уже настроен
        op.execute(sa.text(
            "ALTER TABLE bank_payments ALTER COLUMN import_id DROP NOT NULL"
        ))
        op.execute(sa.text(
            "ALTER TABLE bank_payments DROP CONSTRAINT bank_payments_import_id_fkey"
        ))
        op.execute(sa.text(
            "ALTER TABLE bank_payments ADD CONSTRAINT bank_payments_import_id_fkey "
            "FOREIGN KEY (import_id) REFERENCES bank_statement_imports(id) ON DELETE SET NULL"
        ))
        print("[y2z3a4b5c6d7] bank_payments.import_id: FK переведён на ON DELETE SET NULL")
    elif fk_row is None:
        # Констрейнта нет вовсе (маловероятно, но на всякий случай создаём) —
        # уже нужного типа не найти, добавляем с SET NULL.
        op.execute(sa.text(
            "ALTER TABLE bank_payments ALTER COLUMN import_id DROP NOT NULL"
        ))
        op.execute(sa.text(
            "ALTER TABLE bank_payments ADD CONSTRAINT bank_payments_import_id_fkey "
            "FOREIGN KEY (import_id) REFERENCES bank_statement_imports(id) ON DELETE SET NULL"
        ))
        print("[y2z3a4b5c6d7] bank_payments.import_id: FK создан (ON DELETE SET NULL)")
    else:
        print("[y2z3a4b5c6d7] bank_payments.import_id: FK уже ON DELETE SET NULL — пропуск")

    # --- 4. Бэкфилл subsidy_id/org_id по basis_doc_number ---
    result = bind.execute(sa.text(
        "UPDATE bank_payments bp SET subsidy_id = s.id, org_id = s.org_id "
        "FROM subsidies s "
        "WHERE bp.basis_doc_number IS NOT NULL "
        "AND s.basis_doc_number IS NOT NULL "
        "AND trim(bp.basis_doc_number) = trim(s.basis_doc_number) "
        "AND bp.subsidy_id IS NULL"
    ))
    print(f"[y2z3a4b5c6d7] backfill bank_payments.subsidy_id/org_id: строк обновлено = {result.rowcount}")

    # --- 5. Право payment.registry_view ---
    op.execute(sa.text("""
        INSERT INTO permission_actions (action_key, description)
        VALUES ('payment.registry_view',
                'Просмотр полного реестра платежей (журнал импортов, сверка) — '
                'не ограничено привязкой к закупке')
        ON CONFLICT (action_key) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permissions (role_name, key, granted)
        SELECT r.role, 'payment.registry_view', TRUE
        FROM (VALUES ('superadmin'), ('account_owner'), ('admin'), ('org_admin'), ('manager'), ('employee'))
             AS r(role)
        ON CONFLICT (role_name, key) DO NOTHING
    """))
    print("[y2z3a4b5c6d7] payment.registry_view: действие + роли засеяны")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "bank_payments" not in existing_tables:
        return

    op.execute(sa.text("DROP INDEX IF EXISTS ix_bank_payment_external_doc_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_bank_payments_org_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_bank_payments_subsidy_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_bank_statement_imports_org_id"))

    op.execute(sa.text("ALTER TABLE bank_payments DROP CONSTRAINT IF EXISTS bank_payments_import_id_fkey"))
    op.execute(sa.text(
        "ALTER TABLE bank_payments ADD CONSTRAINT bank_payments_import_id_fkey "
        "FOREIGN KEY (import_id) REFERENCES bank_statement_imports(id) ON DELETE CASCADE"
    ))

    op.execute(sa.text("ALTER TABLE bank_payments DROP COLUMN IF EXISTS org_id"))
    op.execute(sa.text("ALTER TABLE bank_payments DROP COLUMN IF EXISTS subsidy_id"))
    op.execute(sa.text("ALTER TABLE bank_payments DROP COLUMN IF EXISTS external_doc_id"))
    op.execute(sa.text("ALTER TABLE bank_statement_imports DROP COLUMN IF EXISTS org_id"))
    op.execute(sa.text("ALTER TABLE bank_statement_imports DROP COLUMN IF EXISTS rows_no_subsidy"))

    # Право/сиды НЕ откатываем — см. docstring.
