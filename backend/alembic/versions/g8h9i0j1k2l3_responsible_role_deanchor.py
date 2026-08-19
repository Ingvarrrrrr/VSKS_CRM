"""«Ответственный исполнитель» — снять фиксированное ФИО из subsidy_approvers

БАГ (аудит 2026-08-19). В subsidy_approvers строка с ролью «Ответственный
исполнитель» задумана как роль-слот: конкретное ФИО определяется по каждой
закупке отдельно (см. подсказку UI, SubsidiesView.vue, и
onApproverRoleChange, который подставляет плейсхолдер
«_________________»). Но в БД для части субсидий там лежало живое ФИО:
  id=45 subsidy_id=51 (МИНПРОС_2026) full_name='Филиппов Дмитрий Павлович'
  id=23 subsidy_id=3  (КОС_2026)     full_name='Филиппов Д.П.'

Экран настроек субсидии это ФИО не показывал (владелец не видел источник),
но оно утекало в цепочку согласования КАЖДОЙ закупки субсидии
(purchase_approvals.start_approval копировал sa.full_name/sa.user_id один в
один) и в лист согласования/СЗ (documents.py подставлял резолв только когда
full_name было пустым/плейсхолдером — живое ФИО проходило как есть).
Приложение (backend/app/routers/subsidy_approvers.py,
purchase_approvals.py, documents.py) теперь принудительно игнорирует
сохранённое ФИО для этой роли (app/services/responsible_role.py); эта
миграция чистит уже накопленные данные того же класса.

ЧТО ДЕЛАЕТ (идемпотентно, безопасно для повторного прогона на проде):
  1. subsidy_approvers: для строк с role_name (после btrim) =
     'Ответственный исполнитель' принудительно full_name='_________________',
     user_id=NULL.
  2. purchase_approvals: для ЕЩЁ НЕ решённых (status='pending') строк той же
     роли подставляет реального ответственного закупки (assigned_user_id →
     его full_name, иначе purchases.responsible_person, иначе плейсхолдер) и
     user_id = purchases.assigned_user_id. Уже принятые решения
     (status <> 'pending') НЕ трогает — это история согласования, которая
     реально происходила с этим ФИО.

downgrade(): no-op — обратно вписывать конкретное ФИО в роль-слот нельзя,
это и есть баг, который чинит эта миграция.

Revision ID: g8h9i0j1k2l3
Revises: f6g7h8i9j0k1
Create Date: 2026-08-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'g8h9i0j1k2l3'
down_revision = 'f6g7h8i9j0k1'
branch_labels = None
depends_on = None

_ROLE = 'Ответственный исполнитель'
_PLACEHOLDER = '_________________'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "subsidy_approvers" in existing_tables:
        result = bind.execute(sa.text(
            "UPDATE subsidy_approvers SET full_name = :ph, user_id = NULL "
            "WHERE btrim(role_name) = :role "
            "AND (full_name IS DISTINCT FROM :ph OR user_id IS NOT NULL)"
        ), {"ph": _PLACEHOLDER, "role": _ROLE})
        print(f"[g8h9i0j1k2l3] subsidy_approvers: строк деанкорено = {result.rowcount}")

    if "purchase_approvals" in existing_tables and "purchases" in existing_tables and "users" in existing_tables:
        result = bind.execute(sa.text(
            "UPDATE purchase_approvals pa "
            "SET approver_full_name = COALESCE(NULLIF(btrim(u.full_name), ''), "
            "                                   NULLIF(btrim(p.responsible_person), ''), "
            "                                   :ph), "
            "    user_id = p.assigned_user_id "
            "FROM purchases p LEFT JOIN users u ON u.id = p.assigned_user_id "
            "WHERE pa.purchase_id = p.id "
            "AND btrim(pa.role_name) = :role "
            "AND pa.status = 'pending'"
        ), {"ph": _PLACEHOLDER, "role": _ROLE})
        print(f"[g8h9i0j1k2l3] purchase_approvals (pending): строк перепривязано = {result.rowcount}")


def downgrade() -> None:
    # no-op: обратно вписывать конкретное ФИО в роль-слот «Ответственный
    # исполнитель» нельзя — это и есть исходный баг.
    pass
