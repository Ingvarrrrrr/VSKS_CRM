"""backfill framework_seq для рамочных закупок, уже в работе (пункт 21)

Владелец (чек-лист, пункт 21, 2026-10-13): «порядковый номер внутри рамочного
договора — автоматическое число... на примере заявки 908». Разбор показал,
что _assign_framework_seq (app/routers/purchase_budget.py) был подключён к
созданию закупки / согласованию договора / смене контракта, но НЕ к общему
переходу статуса, которым закупка реально уходит в work_in_progress
(app/routers/purchase_transitions.py::transition_status, и bypass
OWNER_ROLES там же) — тот путь правит отдельный коммит кода, а эта миграция
только лечит данные, уже накопленные без него.

На проде (SELECT, 2026-10-13): закупка №908 (рамочный договор №109,
purchase_contract_type=framework_cumulative, status=work_in_progress) —
framework_seq = NULL, единственная закупка этого договора. Закупка №913 из
примера владельца оказалась НЕ рамочной (contract_id NULL, type='single') —
к этому пункту не относится.

Backfill: для каждой НЕ-NULL связки (contract_id, purchase_contract_type IN
framework_cumulative/framework_with_amount) с framework_seq IS NULL и
статусом >= work_in_progress (т.е. уже реально «в работе», не черновик/план)
присваивает следующие по порядку номера (по id), начиная ПОСЛЕ уже занятого
максимума в этом договоре — существующие номера не трогает и не
перенумеровывает (условие WHERE framework_seq IS NULL в UPDATE).

Идемпотентна: повторный запуск не находит строк с framework_seq IS NULL в
этом наборе (после первого прогона все обновлены) — WHERE/JOIN сами собой
становятся no-op.
"""
from alembic import op

revision = 'b2c4d6e8f0a2'
down_revision = 't5u7w9y1a3c5'
branch_labels = None
depends_on = None

_WORK_STATUSES = (
    'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid', 'split'
)

_SQL = f"""
WITH base AS (
    SELECT p.id, p.contract_id,
           COALESCE(
               (SELECT MAX(p2.framework_seq) FROM purchases p2
                WHERE p2.contract_id = p.contract_id), 0
           ) AS base_max
    FROM purchases p
    WHERE p.framework_seq IS NULL
      AND p.contract_id IS NOT NULL
      AND p.purchase_contract_type IN ('framework_cumulative', 'framework_with_amount')
      AND p.status IN {_WORK_STATUSES}
),
numbered AS (
    SELECT id, contract_id, base_max,
           ROW_NUMBER() OVER (PARTITION BY contract_id ORDER BY id) AS rn
    FROM base
)
UPDATE purchases p
SET framework_seq = numbered.base_max + numbered.rn
FROM numbered
WHERE p.id = numbered.id
  AND p.framework_seq IS NULL;
"""


def upgrade() -> None:
    op.execute(_SQL)


def downgrade() -> None:
    # Данные-бэкфилл необратим осознанно (номер нужен для реальных закупок
    # «в работе», обнулять его откатом миграции опаснее, чем оставить) —
    # downgrade — no-op, как и для прочих чисто data-фиксов в проекте.
    pass
