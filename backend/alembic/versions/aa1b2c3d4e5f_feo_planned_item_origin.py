"""feo_planned_items.is_feo_breakdown / is_internal_plan — происхождение
плановой позиции (владелец, 2026-09-01).

ПРИЧИНА (дословно владелец): «Надо добавить при выборе плановой позиции: это
плановая позиция в соответствии с ФЭО или только в соответствии с нашим
внутренним планом, а в ФЭО разбивки не было... Ведь когда есть жёсткая
разбивка ФЭО — значит покупать будут именно эти вещи. А если в ФЭО написано
"канцтовары" ... это ты уже сам можешь запланировать, ... это не ФЭО, из-за
него не надо будет так жёстко отчитываться». ДВЕ НЕЗАВИСИМЫЕ галочки (не
переключатель) — обе могут быть True/False одновременно, это осознанно.

  feo_planned_items:
    is_feo_breakdown  BOOLEAN NOT NULL DEFAULT FALSE — жёсткая построчная
                       разбивка ФЭО реально существует для этой позиции.
    is_internal_plan  BOOLEAN NOT NULL DEFAULT FALSE — в ФЭО была только более
                       широкая категория (или позиции вовсе не было) — состав
                       придумали сами, отчётность по ней не такая жёсткая.

Идемпотентно (ADD COLUMN IF NOT EXISTS) — безопасно против повторного прогона
и против check_schema (migrate.py гонит upgrade head на старте, конфликт DDL
роняет прод в 502). Бэкфилл ниже — тоже идемпотентен по построению (UPDATE по
условиям текущих данных, а не по разовому списку id — повторный прогон не
меняет уже проставленные значения предсказуемым образом).

БЭКФИЛЛ существующих строк — правило разобрано по коду создания
FeoPlannedItem (см. app/routers/feo_categories.py, app/services/
plan_autoassign.py, backend/scripts/migrate_category_plan_to_planned_items.py)
и ПРОВЕРЕНО цифрами на локальной базе (402 строки на момент миграции):

  1) auto_created = TRUE (автозаведено из заявки/закупки/бэкфилла закупок вне
     плана, plan_autoassign.py) → is_internal_plan. Позиция никогда не была
     построчной разбивкой ФЭО — она родилась из реального расхода, а не из
     файла ФЭО. [27 строк]

  2) auto_created = FALSE И notes указывает на «план категории целиком, без
     построчной разбивки», перенесённый в плановую позицию одним из трёх
     известных путей (миграция migrate_category_plan_to_planned_items.py,
     конвертация ручного плана категории в SubsidiesView.vue, перенос из
     родительской категории-направления) → is_internal_plan. Плановая
     позиция здесь — это ЦЕЛАЯ категория/направление, ставшая одной строкой,
     а не позиция из детального Ур.5-файла ФЭО. Совпадение по notes (не по
     конкретным id — правило переживёт новые такие переносы):
       notes = 'из импорта ФЭО'                              (импорт ФЭО,
         "план строки" — категория-total без детальной разбивки, вторая
         точка создания в feo_categories.py, ~строка 2634)
       notes = 'перенесено из плана категории'                (миграция
         migrate_category_plan_to_planned_items.py)
       notes = 'Конвертировано из ручного плана категории'    (кнопка
         «Перенести в плановую позицию» в SubsidiesView.vue)
       notes LIKE 'Перенесено из категории ФЭО%'               (перенос
         с направления на лист)
     [329 строк локально: 328 + 1]

  3) auto_created = FALSE И notes IS NULL/пусто — это ЛИБО детальная Ур.5-
     строка настоящего импорта ФЭО (первая точка создания в
     feo_categories.py, ~строка 2477 — notes там НЕ проставляется вовсе),
     ЛИБО позиция, заведённая человеком вручную через диалог «Добавить
     плановую позицию» (SubsidiesView.vue) — а он notes тоже не отправляет.
     У текущей модели данных нет прямого столбца, различающего эти два
     случая, но есть косвенный: строки одного запуска импорта Excel создаются
     ПОСЛЕДОВАТЕЛЬНО внутри одного HTTP-запроса за доли секунды одна за
     другой (db.flush() на каждую строку цикла), тогда как ручное добавление
     через диалог — отдельный запрос человека, отстоящий от любой другой
     плановой позиции на минуты/часы/дни. Проверено на локальных данных
     (запрос с LAG/LEAD по created_at): 42 из 45 таких строк лежат в плотных
     пачках (соседняя строка — той же секунды или ~0.1-0.15 сек), 3 строки
     полностью одиноки (ближайший сосед — от 45 минут до нескольких дней).
     Порог 5 секунд между соседними по created_at строками (без привязки к
     категории — импорт одного файла ФЭО обычно затрагивает много категорий
     подряд) отделяет одно от другого с очень большим запасом:
       есть «соседняя» строка (любой категории) в пределах 5 секунд по
         created_at → is_feo_breakdown (детальный Ур.5-импорт)     [42]
       полностью изолированная строка (нет соседа ближе 5 секунд)
         → is_internal_plan (заведено руками)                      [3]

Итого по локальной базе (402 строки): is_internal_plan = 27 + 329 + 3 = 359,
is_feo_breakdown = 42, ни одного флага не выставлено внутренне противоречиво
(обе галочки — независимые булевы поля, пересечение здесь пустое, но модель
это не запрещает — владелец явно просил именно так).

Revision ID: aa1b2c3d4e5f
Revises: q7r8s9t0u1v2
Create Date: 2026-09-01 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'aa1b2c3d4e5f'
down_revision = 'q7r8s9t0u1v2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return

    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "is_feo_breakdown BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items ADD COLUMN IF NOT EXISTS "
        "is_internal_plan BOOLEAN NOT NULL DEFAULT FALSE"
    ))

    # ---- бэкфилл (см. докстринг выше для полного разбора правила) ---------

    # 1) auto_created = TRUE → внутренний план.
    op.execute(sa.text(
        "UPDATE feo_planned_items SET is_internal_plan = TRUE "
        "WHERE auto_created = TRUE AND is_internal_plan = FALSE AND is_feo_breakdown = FALSE"
    ))

    # 2) notes указывает на «план категории целиком» → внутренний план.
    op.execute(sa.text(
        "UPDATE feo_planned_items SET is_internal_plan = TRUE "
        "WHERE auto_created = FALSE AND is_internal_plan = FALSE AND is_feo_breakdown = FALSE AND ("
        "  notes = 'из импорта ФЭО' "
        "  OR notes = 'перенесено из плана категории' "
        "  OR notes = 'Конвертировано из ручного плана категории' "
        "  OR notes LIKE 'Перенесено из категории ФЭО%'"
        ")"
    ))

    # 3) Оставшиеся (auto_created = FALSE, notes IS NULL/пусто) — кластерный
    # признак по created_at: есть сосед (любой категории) в пределах 5 секунд
    # → детальный Ур.5-импорт (is_feo_breakdown), иначе изолированная строка
    # → заведено руками (is_internal_plan).
    op.execute(sa.text("""
        WITH remaining AS (
            SELECT id, created_at,
                LAG(created_at) OVER (ORDER BY created_at) AS prev_ts,
                LEAD(created_at) OVER (ORDER BY created_at) AS next_ts
            FROM feo_planned_items
            WHERE auto_created = FALSE
              AND is_internal_plan = FALSE AND is_feo_breakdown = FALSE
              AND (notes IS NULL OR notes = '')
        ),
        classified AS (
            SELECT id,
                (
                    (prev_ts IS NOT NULL AND created_at - prev_ts <= INTERVAL '5 seconds')
                    OR (next_ts IS NOT NULL AND next_ts - created_at <= INTERVAL '5 seconds')
                ) AS has_import_sibling
            FROM remaining
        )
        UPDATE feo_planned_items fpi
        SET is_feo_breakdown = classified.has_import_sibling,
            is_internal_plan = NOT classified.has_import_sibling
        FROM classified
        WHERE fpi.id = classified.id
    """))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'feo_planned_items' not in inspector.get_table_names():
        return
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS is_feo_breakdown"
    ))
    op.execute(sa.text(
        "ALTER TABLE feo_planned_items DROP COLUMN IF EXISTS is_internal_plan"
    ))
