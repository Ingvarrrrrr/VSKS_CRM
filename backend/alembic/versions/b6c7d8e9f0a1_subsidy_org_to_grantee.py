"""subsidy org_id = grantee organization (data reconcile)

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-06 00:10:00.000000

Model change (Wave 2): субсидия принадлежит организации-грантополучателю
(subsidies.contractor_id — это получатель субсидии). Исторически org_id
проставлялся из org-переключателя создателя, из-за чего субсидии «уезжали»
не в ту организацию (кейс ДНР_2026: org_id=5 ЦЕНТРПОИСК вместо 29 Донецкое).

Эта миграция пересчитывает subsidies.org_id по грантополучателю:
  - match организацией по organizations.contractor_id = contractor.id (приоритет),
  - иначе по совпадению ИНН (organizations.inn = contractors.inn, непустой).

Безопасность:
  - Субсидии, чей contractor не имеет зеркальной организации (министерства:
    ФАДМ, Минтруд и т.п.), НЕ попадают в выборку — их org_id не меняется.
  - Идемпотентна: повторный запуск не находит расхождений (IS DISTINCT FROM).
  - downgrade — no-op: прежние «владельцы» невосстановимы без снапшота.
"""
from alembic import op

revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None

_RECONCILE_SQL = """
UPDATE subsidies s
SET org_id = m.org_id
FROM (
    SELECT DISTINCT ON (s2.id) s2.id AS subsidy_id, o.id AS org_id
    FROM subsidies s2
    JOIN contractors c ON c.id = s2.contractor_id
    JOIN organizations o
      ON o.contractor_id = c.id
      OR (o.inn IS NOT NULL AND btrim(o.inn) <> '' AND o.inn = c.inn)
    ORDER BY s2.id, (o.contractor_id = c.id) DESC, o.id
) m
WHERE s.id = m.subsidy_id AND s.org_id IS DISTINCT FROM m.org_id;
"""


def upgrade() -> None:
    op.execute(_RECONCILE_SQL)


def downgrade() -> None:
    pass
