"""organizations.inn уникален + дочистка дублей по ИНН

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-05 17:00:00.000000

Контекст: мерж дублей орг по ИНН (_merge_duplicate_orgs_by_inn) жил только в
lifespan и мог оставлять висячие ссылки, а главное — НЕ было гарантии на уровне
БД, что двух юрлиц с одним ИНН не существует. Бизнес-правило: ИНН уникален
(название может совпадать, ИНН — нет).

Миграция:
1. Дочищает дубли по ИНН в чистом SQL: survivor = MIN(id), все FK на
   organizations.id перепривязываются к survivor через information_schema
   (generic), при конфликте уникальных индексов junction-строки loser'а
   удаляются; затем losers удаляются.
2. Вешает партиальный UNIQUE-индекс на inn (для непустых) — впредь дубль
   по ИНН невозможен физически.
Идемпотентно: при отсутствии дублей цикл ничего не делает, индекс создаётся
через IF NOT EXISTS.
"""
from alembic import op

revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
      EXCEPTION WHEN unique_violation THEN
        -- junction-таблица: у survivor уже есть такая связь → дубль loser'а удаляем
        EXECUTE format('DELETE FROM %I WHERE %I = ANY($1)',
                       fk.table_name, fk.column_name)
          USING losers;
      END;
    END LOOP;

    DELETE FROM organizations WHERE id = ANY(losers);
  END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_inn
  ON organizations (inn)
  WHERE inn IS NOT NULL AND btrim(inn) <> '';
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_organizations_inn;")
