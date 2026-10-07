"""feo_categories.is_payroll — признак «статья ФОТ» (ФОТ и иные выплаты
персоналу), для четвёртой корзины `payroll` в разбивках по типу позиции.

Повод: субсидия «ДНР» (прод id 76) — позиции на статьях «ФОТ ДНР», «НДФЛ
13%», «страховой взнос 7,8%», «командировочные» падали в «без типа», хотя у
колонки «Товар/услуга/работа» для статей типа нет вовсе (это ФОТ, не товар и
не услуга) — план .planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2.

Правило имени — ОДНА функция app.services.feo_payroll.is_payroll_name
(ПРАВИЛО №6), эта же миграция её НЕ дублирует: SQL-регулярка ниже — прямой
перевод той же функции на POSIX regex (слово «фот» как отдельное слово, не
подстрока «фото-/фотография»; на проде статья «Расходы на приобретение...
фото-, видеотехники...» ложно совпала бы без границ слова — проверено перед
миграцией, см. отчёт сессии). Если is_payroll_name когда-либо изменится,
разовый backfill здесь не переигрывается — новые/изменённые статьи метит
импорт (feo_import_apply.py) и ручной переключатель, а не повторный прогон
этой миграции.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — проект гоняет `alembic upgrade
head` при старте контейнера.

Revision ID: e3f5g7h9i1j3
Revises: s7u9w1y3a5c7
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f5g7h9i1j3'
down_revision = 's7u9w1y3a5c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE feo_categories ADD COLUMN IF NOT EXISTS is_payroll "
        "BOOLEAN NOT NULL DEFAULT false"
    ))
    # Разовый бэкфилл — ТА ЖЕ формула, что app.services.feo_payroll.is_payroll_name
    # (регистронезависимо; «фот» только как отдельное слово — не подстрока
    # «фото»/«фотография», см. докстринг выше):
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
    op.execute(sa.text("ALTER TABLE feo_categories DROP COLUMN IF EXISTS is_payroll"))
