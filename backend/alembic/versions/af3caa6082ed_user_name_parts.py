"""users: last_name/first_name/middle_name как источник истины для ФИО

Владелец (2026-09-01): форма «Добавить сотрудника» принимала ФИО одной строкой
— туда попадал мусор вроде «Новичкова Оль». Добавляем три отдельных поля;
отчество необязательно (у части людей его нет).

Архитектура: last_name/first_name/middle_name — источник истины, full_name
остаётся ПРОИЗВОДНЫМ полем, пересобирается через compose_fio() при любом
создании/переименовании пользователя (app/services/fio.py:resolve_user_name_input,
используется в routers/users.py create/update, Excel-импорте сотрудников,
/api/register, services/fleet_seed.py). Десятки мест в коде (документы,
листы согласования, служебки, чаты, списки) продолжают читать full_name как
раньше — их трогать не нужно.

ЧТО ДЕЛАЕТ (идемпотентно, безопасно для повторного прогона):
  1. ADD COLUMN IF NOT EXISTS last_name/first_name/middle_name VARCHAR(100).
  2. Бэкфилл: для строк с last_name IS NULL и непустым full_name — разбираем
     через ту же логику, что и split_fio (app/services/fio.py):
       - 3+ слова → (слово[0], слово[1], остаток) — разобрано "на 3 части";
       - 2 слова  → (слово[0], слово[1], NULL) — разобрано "на 2 части" (без отчества);
       - 1 слово  → (слово[0], NULL, NULL) — не разобралось, кладём в last_name.
     Guard `last_name IS NULL` — второй прогон ничего не трогает.

Revision ID: af3caa6082ed
Revises: 5324bd4399ee
Create Date: 2026-09-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'af3caa6082ed'
down_revision = '5324bd4399ee'
branch_labels = None
depends_on = None

_TAG = "[af3caa6082ed]"


def _split_fio(raw: str):
    """Копия правил app/services/fio.py:split_fio — миграции не импортируют app.*."""
    if not raw or not raw.strip():
        return (None, None, None)
    words = raw.strip().split()
    if len(words) >= 3:
        return (words[0], words[1], " ".join(words[2:]))
    if len(words) == 2:
        return (words[0], words[1], None)
    return (words[0], None, None)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return

    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(100)"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(100)"))
    op.execute(sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS middle_name VARCHAR(100)"))

    rows = bind.execute(sa.text(
        """
        SELECT id, full_name FROM users
        WHERE last_name IS NULL AND full_name IS NOT NULL AND btrim(full_name) <> ''
        """
    )).fetchall()

    three_parts = 0
    two_parts = 0
    unparsed = 0
    for row_id, full_name in rows:
        last, first, middle = _split_fio(full_name)
        if middle:
            three_parts += 1
        elif first:
            two_parts += 1
        else:
            unparsed += 1
        bind.execute(
            sa.text(
                "UPDATE users SET last_name = :last, first_name = :first, middle_name = :middle WHERE id = :id"
            ),
            {"last": last, "first": first, "middle": middle, "id": row_id},
        )
    print(
        f"{_TAG} бэкфилл full_name -> 3 поля: всего строк={len(rows)}, "
        f"разобрано на 3 части={three_parts}, на 2 части (без отчества)={two_parts}, "
        f"не разобралось (одно слово, в last_name)={unparsed}"
    )


def downgrade() -> None:
    # No-op намеренно: удаление колонок необратимо потеряло бы разобранные из
    # full_name данные, а откат схемы не должен разрушать данные. full_name
    # как производное поле продолжит работать даже если last/first/middle_name
    # останутся в базе после гипотетического отката кода.
    pass
