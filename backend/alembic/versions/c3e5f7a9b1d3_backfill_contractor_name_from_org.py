"""Бэкфилл contractors.name там, где оно пусто — org id=69 на проде (27.10.2026).

Повод: организация, созданная через OrgCreateDialog.vue/useOrgCreate.ts с
ЯВНО выбранным существующим контрагентом (`contractor_id` передан в POST
/api/organizations/), раньше НИКОГДА не записывала форму создания org в
контрагента ("данные контрагента и так побеждают" — app/routers/
organizations.py::create_organization). Если у контрагента `name` было
пустым (историческая запись), введённое пользователем короткое наименование
молча терялось, а `organizations.name` (column_property от Contractor.name,
Правило №6, см. app/models/organization.py) оставался NULL — список
организаций отдавал пустую строку, а /api/hierarchy/graph падал 500
ResponseValidationError (OrgOut.name: str).

Корневой фикс (тот же коммит) — create_organization заполняет пустые поля
контрагента из формы НЕЗАВИСИМО от того, явно ли передан contractor_id;
непустые поля контрагента не трогает (побеждает контрагент, второй источник
не заводим). Эта миграция — только разовый бэкфилл уже существующих битых
строк, созданных ДО фикса.

Источник имени для бэкфилла, по приоритету (COALESCE, первое непустое):
1) contractors.full_name (обычно есть — из ЕГРЮЛ);
2) физическая (осиротевшая, Правило №6) колонка organizations.name —
   _legacy_name в app/models/organization.py — снимок, который форма
   создания отправляла в body, но backend не сохранял (JOIN по contractor_id);
3) 'Контрагент #<id>' — чтобы НЕ NULL колонка (contractors.name nullable=False
   в модели) не оставалась пустой строкой ни у одной записи.

Идемпотентно: UPDATE только там, где name IS NULL или пуст после trim —
повторный прогон ничего не меняет.

Перепривязана к актуальной единственной голове alembic `a8c0e2f4b6d8`.

Revision ID: c3e5f7a9b1d3
Revises: a8c0e2f4b6d8
Create Date: 2026-10-28 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e5f7a9b1d3"
down_revision = "a8c0e2f4b6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        """
        UPDATE contractors c
        SET name = COALESCE(
            NULLIF(btrim(c.full_name), ''),
            NULLIF(btrim(o.name), ''),
            'Контрагент #' || c.id
        )
        FROM organizations o
        WHERE o.contractor_id = c.id
          AND (c.name IS NULL OR btrim(c.name) = '')
        """
    ))
    # Контрагенты без привязанной организации (не должно встречаться на
    # проде, но защищаемся от той же пустоты вне JOIN выше).
    bind.execute(sa.text(
        """
        UPDATE contractors c
        SET name = 'Контрагент #' || c.id
        WHERE (c.name IS NULL OR btrim(c.name) = '')
        """
    ))


def downgrade() -> None:
    # Бэкфилл — необратимо объединён с уже существующими данными, как и у
    # аналогичных backfill-миграций в проекте (см. w6x7y8z9a0b1).
    pass
