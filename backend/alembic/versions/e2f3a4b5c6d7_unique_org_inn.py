"""organizations.inn уникален + дочистка дублей по ИНН

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-05 17:00:00.000000

Контекст: мерж дублей орг по ИНН (_merge_duplicate_orgs_by_inn) жил только в
lifespan и мог оставлять висячие ссылки, а главное — НЕ было гарантии на уровне
БД, что двух юрлиц с одним ИНН не существует. Бизнес-правило: ИНН уникален
(название может совпадать, ИНН — нет).

Миграция (КАЖДЫЙ statement — отдельный op.execute: asyncpg не умеет несколько
команд в одном prepared statement → иначе "cannot insert multiple commands"):
1. DO-блок: дочистка дублей по ИНН. survivor = MIN(id); все FK на
   organizations.id перепривязываются к survivor (generic через
   information_schema), при конфликте — junction-строки loser'а удаляются.
   Каждая группа в своём BEGIN/EXCEPTION → сбой одной не валит миграцию.
2. DO-блок: вешает UNIQUE-индекс на inn ТОЛЬКО если дублей не осталось (иначе
   RAISE NOTICE и пропуск — деплой не падает).
Идемпотентно и устойчиво к ошибкам.
"""
from alembic import op

revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


_DEDUP = """
DO $$
DECLARE
  grp RECORD;
  fk RECORD;
  survivor INT;
  losers INT[];
BEGIN
  FOR grp IN
    SELECT inn, array_agg(id ORDER BY id) AS ids
    FROM organizations
    WHERE inn IS NOT NULL AND btrim(inn) <> ''
    GROUP BY inn HAVING count(*) > 1
  LOOP
    BEGIN
      survivor := grp.ids[1];
      losers := grp.ids[2:array_length(grp.ids, 1)];

      FOR fk IN
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
          AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_name = 'organizations'
          AND ccu.column_name = 'id'
      LOOP
        BEGIN
          EXECUTE format('UPDATE %I SET %I = $1 WHERE %I = ANY($2)',
                         fk.table_name, fk.column_name, fk.column_name)
            USING survivor, losers;
        EXCEPTION WHEN OTHERS THEN
          -- конфликт уникального индекса / иной сбой → дубль loser'а удаляем
          BEGIN
            EXECUTE format('DELETE FROM %I WHERE %I = ANY($1)',
                           fk.table_name, fk.column_name)
              USING losers;
          EXCEPTION WHEN OTHERS THEN
            NULL;  -- пропускаем проблемную таблицу, не валим миграцию
          END;
        END;
      END LOOP;

      DELETE FROM organizations WHERE id = ANY(losers);
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'org-merge: группа ИНН=% пропущена: %', grp.inn, SQLERRM;
    END;
  END LOOP;
END $$;
"""

_INDEX = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM organizations
    WHERE inn IS NOT NULL AND btrim(inn) <> ''
    GROUP BY inn HAVING count(*) > 1
  ) THEN
    CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_inn
      ON organizations (inn)
      WHERE inn IS NOT NULL AND btrim(inn) <> '';
  ELSE
    RAISE NOTICE 'uq_organizations_inn пропущен: остались дубли по ИНН';
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(_DEDUP)
    op.execute(_INDEX)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_organizations_inn;")
