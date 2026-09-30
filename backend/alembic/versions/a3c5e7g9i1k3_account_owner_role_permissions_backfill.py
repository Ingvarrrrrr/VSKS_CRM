"""Backfill: role_permissions для account_owner там, где есть admin=True, но
для account_owner строки нет вообще.

Баг (проверено на проде, владелец 2026-09-30): account_owner (владелец
аккаунта, id=5) не имел action-права wish.edit_feo —
app.auth.permissions.get_effective_actions не возвращал этот ключ. Из-за этого
в карточке заявки у согласующего-владельца была скрыта кнопка «Создать в
плане закупок» и правка ФЭО (фронт: canEditWishFeo в
frontend/src/composables/wishes/useWishForm.ts). Причина —
app/startup/permission_seeds.py::_wish_edit_feo_action ROLE_DEFAULTS не
содержал account_owner (роль иерархически выше admin: employee < manager <
org_admin < admin < account_owner < superadmin, см.
app/auth/permissions.py ROLE_RANK).

Тот же класс дефекта (Правило №6 — «пример владельца = класс проблемы»)
найден и в app/startup/permission_seeds.py::_payment_registry_tab_and_actions
(payment_registry/payment.import/payment.confirm/payment.unbind — admin=True,
account_owner не заведён вообще; на проде это уже закрыто историческим
alembic/versions/z3a4b5c6d7e8_phase22_permissions.sql, но идемпотентный
python-сид этого не знал и на свежей БД оставлял пробел). Оба python-сида
поправлены отдельно (Правило №6 — один источник правды на будущее); эта
миграция закрывает разрыв в уже накопленных данных на проде одним запросом,
не точечно по ключам.

Общее правило переноса: для каждого ключа, где admin имеет granted=True, а у
account_owner строки нет вообще (не False осознанно, а именно отсутствие),
завести account_owner=True. Идемпотентно — NOT IN пересчитывается каждый
прогон, повторный запуск не находит новых строк.

Revision ID: a3c5e7g9i1k3
Revises: b7d9f1h3j5k7
Create Date: 2026-09-30 00:00:02.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a3c5e7g9i1k3"
down_revision = "b7d9f1h3j5k7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        INSERT INTO role_permissions (role_name, key, granted)
        SELECT 'account_owner', key, TRUE
        FROM role_permissions
        WHERE role_name = 'admin'
          AND granted = TRUE
          AND key NOT IN (
              SELECT key FROM role_permissions WHERE role_name = 'account_owner'
          )
    """))
    if result.rowcount:
        print(f"[a3c5e7g9i1k3] account_owner role_permissions backfilled from admin: {result.rowcount}")


def downgrade() -> None:
    # Намеренно no-op — откат означал бы отбирать у account_owner права,
    # которые он и так должен был иметь по иерархии ролей (баг был именно в
    # их отсутствии, а не в осознанном ограничении); тот же подход, что у
    # соседних data-backfill миграций (b7d9f1h3j5k7 и раньше).
    pass
