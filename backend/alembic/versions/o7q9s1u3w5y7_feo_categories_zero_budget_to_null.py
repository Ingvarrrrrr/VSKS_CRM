"""feo_categories: backfill — «0» в budget/feo_amount становится NULL (владелец,
Волна 1 п.7/п.8, 2026-09-13).

ПРИЧИНА. Владелец, дословно (п.8): «Когда в поле финансирование по ФЭО введено
„0“, то в моём понимании это значит, что не задана сумма. Если алгоритм
считает, что любая сумма в плановых отображается как превышение — это
неправильно. Ведь если нет жёстко заданной суммы, то и сравнивать не с чем.»

app.services.feo_plan_tree.compute_feo_plan_tree._visit уже отличал NULL от
заданного значения (`budget = float(r.budget) if r.budget is not None else
None`) — модель (app/models/feo_category.py) допускала NULL="не задано" с
самого начала. Но explicit "0", сохранённый в базе (Excel-импорт нередко пишет
0 в пустую ячейку вместо NULL), проходил через `budget is not None` как ЗАДАННОЕ
финансирование → `full_display - budget > 0.005` срабатывало на любой
положительный план. Кодовая правка (см. compute_feo_plan_tree, тот же коммит:
0 теперь трактуется как «не задано» и на лету, НЕ дожидаясь этой миграции) уже
не даст новым нулям аукнуться, а эта миграция чистит то, что уже накопилось в
базе, чтобы отчёты/экспорт/другие потребители budget (compute_budget_map,
feo_planned_items_matching.kind, feo_plan_reads_tree.kind — все уже сравнивают
именно с NULL, не с 0) увидели правильную картину без правки кода на их
стороне.

feo_amount (стоимость за единицу по документу ФЭО) — тот же паттерн «NULL =
не задано / авто из детей» (см. её комментарий в модели) и та же путаница «0
вместо пустой ячейки» на импорте; исправляется тем же способом заодно, чтобы
не оставлять один и тот же смысл «не задано» представленным по-разному в двух
однотипных полях одной таблицы (ПРАВИЛО №6 — одно значение, один способ
хранить «не задано»). app.services.feo_import_links уже явно избегает 0
(`feo_amount.isnot(None), feo_amount != 0`) — эта миграция синхронизирует
данные с тем, что код уже ожидает.

Идемпотентно: WHERE ... = 0 — после первого прогона таких строк не остаётся,
повторный запуск ничего не меняет. Чистый DML (без DDL) — колонки budget/
feo_amount существуют с момента создания таблицы (см. models/feo_category.py),
ALTER TABLE не требуется.

Перед применением на проде посчитать затрагиваемые строки:
  SELECT
    (SELECT count(*) FROM feo_categories WHERE budget = 0) AS budget_zero_rows,
    (SELECT count(*) FROM feo_categories WHERE feo_amount = 0) AS feo_amount_zero_rows;

downgrade — no-op: различие «0» vs «изначально NULL» необратимо потеряно уже
на момент этой миграции (тот же паттерн, что и в
v3w5y7a9c1e3_user_org_position_backfill.py).

Revision ID: o7q9s1u3w5y7
Revises: c5e7g9i1k3m5
Create Date: 2026-09-13 00:00:00.000000
"""
from alembic import op

revision = 'o7q9s1u3w5y7'
down_revision = 'c5e7g9i1k3m5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE feo_categories SET budget = NULL WHERE budget = 0")
    op.execute("UPDATE feo_categories SET feo_amount = NULL WHERE feo_amount = 0")


def downgrade() -> None:
    pass
