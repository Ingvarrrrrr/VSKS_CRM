"""payments basis-колонки DDL + партиальные уникальные индексы + чистка contract_number

Третья очередь утверждённого плана (`synchronous-knitting-thacker.md`), Этап 6:
  1. payments += expense_code, basis_kind, basis_number, basis_date, basis_key,
     basis_label — модель (app/models/payment.py) уже объявляет эти колонки
     (добавлены предыдущей волной), эта миграция даёт им реальный DDL
     (idempotent — ADD COLUMN только если колонки ещё нет, через inspector).
  2. Частичные уникальные индексы:
       - (bank_payment_id, purchase_id) WHERE bank_payment_id IS NOT NULL —
         один банковский платёж не может быть дважды разнесён на ОДНУ И ТУ ЖЕ
         закупку (на разные закупки одной группы — можно, это split-платёж).
       - (purchase_id, basis_key) WHERE basis_key IS NOT NULL AND matched_confirmed
         — «одно назначение — один платёж» (app/services/payment_basis.py::basis_key,
         app/services/payment_lookup.py::attach), для ежемесячных: аренда за март
         и за апрель получают РАЗНЫЕ basis_key и оба проходят.
     Перед созданием — detect-then-fix pre-check на уже существующие дубли (стиль
     f6g7h8i9j0k1_*): если дубли найдены, индекс НЕ создаётся — только WARNING
     со счётчиком в логах деплоя, чтобы не ронять миграцию на проде вручную
     заведёнными конфликтующими записями. Локально payments пуста (0 строк) —
     дублей быть не может, оба индекса создаются на первом прогоне.
  3. UPDATE purchases SET contract_number = NULL WHERE btrim(contract_number) =
     'Нет данных' — 258 закупок локально (сверено 2026-08-19) слипаются в один
     фиктивный «договор» и портят группировку рамочных
     (app/services/payment_target.py::_group_key_for). 'Нет данных' — это
     импортовый прочерк, не настоящий номер договора.

downgrade() — no-op: см. паттерн y2z3a4b5c6d7/f517d1525628 (посчитанные/очищенные
данные не откатываем; частичные индексы — чисто defensive, снимать их незачем).

Chain note (2026-08-19): изначально планировался прямо на f517d1525628, но
параллельная волна добавила d6f2a9c1e4b8 (wishes rejected_by) тем же родителем
— во избежание двух голов (`alembic upgrade head` падает при multiple heads)
эта миграция подключена ПОСЛЕ неё, а не параллельно.

Revision ID: b4c8e1a6f3d9
Revises: d6f2a9c1e4b8
Create Date: 2026-08-19 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c8e1a6f3d9'
down_revision = 'd6f2a9c1e4b8'
branch_labels = None
depends_on = None


_PAYMENT_COLUMNS = [
    ("expense_code", "VARCHAR(10)"),
    ("basis_kind", "VARCHAR(20)"),
    ("basis_number", "VARCHAR(100)"),
    ("basis_date", "DATE"),
    ("basis_key", "VARCHAR(300)"),
    ("basis_label", "VARCHAR(300)"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- 1. payments.* колонки (idempotent) ---
    if inspector.has_table("payments"):
        existing_cols = {c["name"] for c in inspector.get_columns("payments")}
        for col_name, col_type in _PAYMENT_COLUMNS:
            if col_name not in existing_cols:
                op.execute(sa.text(f"ALTER TABLE payments ADD COLUMN {col_name} {col_type}"))
                print(f"[b4c8e1a6f3d9] payments.{col_name} добавлен")

        # --- 2a. (bank_payment_id, purchase_id) WHERE bank_payment_id IS NOT NULL ---
        dup_bp_purchase = bind.execute(sa.text("""
            SELECT count(*) FROM (
                SELECT bank_payment_id, purchase_id
                FROM payments
                WHERE bank_payment_id IS NOT NULL
                GROUP BY bank_payment_id, purchase_id
                HAVING count(*) > 1
            ) d
        """)).scalar()
        if dup_bp_purchase:
            print(f"[b4c8e1a6f3d9] WARNING: {dup_bp_purchase} дублей (bank_payment_id, purchase_id) — "
                  "индекс ix_payments_bank_payment_purchase_uniq НЕ создан, разберите вручную")
        else:
            op.execute(sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_bank_payment_purchase_uniq "
                "ON payments (bank_payment_id, purchase_id) WHERE bank_payment_id IS NOT NULL"
            ))
            print("[b4c8e1a6f3d9] ix_payments_bank_payment_purchase_uniq создан")

        # --- 2b. (purchase_id, basis_key) WHERE basis_key IS NOT NULL AND matched_confirmed ---
        dup_purchase_basis = bind.execute(sa.text("""
            SELECT count(*) FROM (
                SELECT purchase_id, basis_key
                FROM payments
                WHERE basis_key IS NOT NULL AND matched_confirmed = TRUE
                GROUP BY purchase_id, basis_key
                HAVING count(*) > 1
            ) d
        """)).scalar()
        if dup_purchase_basis:
            print(f"[b4c8e1a6f3d9] WARNING: {dup_purchase_basis} дублей (purchase_id, basis_key) — "
                  "индекс ix_payments_purchase_basis_key_uniq НЕ создан, разберите вручную")
        else:
            op.execute(sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_purchase_basis_key_uniq "
                "ON payments (purchase_id, basis_key) WHERE basis_key IS NOT NULL AND matched_confirmed = TRUE"
            ))
            print("[b4c8e1a6f3d9] ix_payments_purchase_basis_key_uniq создан")

    # --- 3. purchases.contract_number = 'Нет данных' → NULL ---
    if inspector.has_table("purchases"):
        result = bind.execute(sa.text(
            "UPDATE purchases SET contract_number = NULL WHERE btrim(contract_number) = 'Нет данных'"
        ))
        print(f"[b4c8e1a6f3d9] purchases.contract_number 'Нет данных' → NULL: строк очищено = {result.rowcount}")


def downgrade() -> None:
    # No-op намеренно: DDL-колонки payments используются новой логикой разнесения
    # (app/services/payment_lookup.py), частичные индексы — defensive-only,
    # очистка contract_number — данные, откатывать в 'Нет данных' незачем.
    pass
