"""organizations без contractor_id — автопривязка по ИНН + дозаполнение + отчёт

Revision ID: t2v4x6z8b0d2
Revises: n7q9s1u3w5y7
Create Date: 2026-09-05 00:00:00.000000

Контекст (Правило №6, волна D1): `organizations.{inn,kpp,ogrn,address,
signatory*,full_name}` дублируют `contractors.*`. Копировались один раз при
создании (`_materialize_org_from_contractor`, `_auto_link_contractor_by_inn`),
дальше правились независимо — карточка контрагента меняла `contractors.*`, а
`organizations.*` оставались как были. С этой волны читающий код
(`app/services/org_requisites.py`) при заданном `contractor_id` берёт
реквизиты ИЗ КОНТРАГЕНТА — значит, org без привязки к контрагенту показывали
бы устаревшие/более бедные данные, если её не привязать.

2026-09-07 (по факту на проде, org id=5 «АНО ЦЕНТРПОИСК»): у контрагента
`full_name` было пусто, у org — заполнено. Слепое "контрагент побеждает"
стёрло бы наименование заказчика в документах. Поэтому шаг 3 ниже —
ДОЗАПОЛНЕНИЕ, а не просто отчёт: пустые поля контрагента дозаполняются из
org (симметрично рантайм-фолбэку в `org_requisites()`), и только реальные
КОНФЛИКТЫ (оба поля непустые и различаются) остаются отчётом за владельцем.

Что делает миграция (идемпотентно, каждый шаг — отдельный op.execute,
т.к. asyncpg не умеет несколько команд в одном prepared statement):

1. Для organizations с `contractor_id IS NULL` и непустым `inn` — привязать к
   уже существующему Contractor с тем же ИНН (MIN(id), если дублей несколько).
2. Для оставшихся (contractor_id всё ещё NULL, inn непустой) — создать
   Contractor из текущих реквизитов организации и привязать.
3. Для organizations, УЖЕ привязанных к contractor_id: там, где у контрагента
   поле пусто/NULL, а у org — есть значение, ДОЗАПОЛНИТЬ контрагента этим
   значением (идемпотентно — при повторном прогоне поле контрагента уже не
   пусто, условие не сработает повторно), с RAISE NOTICE построчно на
   каждое дозаполненное поле:
   'org_contractor_backfill contractor_id=<id> contractor_name=<name> field=<field> copied_from_org_id=<id> org_name=<name> value=<val>'
4. Для оставшихся случаев — оба поля непустые и РАЗЛИЧАЮТСЯ (настоящий
   конфликт, шаг 3 сюда не полез) — по-прежнему НИЧЕГО не перезаписывать
   автоматически, только залогировать через RAISE NOTICE:
   'org_contractor_diff id=<org_id> name=<org_name> field=<field> org=<val> contractor=<val>'
   — видно в выводе `alembic upgrade` / логах контейнера при деплое.

downgrade — no-op: привязка по ИНН, создание контрагентов и дозаполнение их
пустых полей необратимы без снапшота (тот же паттерн, что и в
b6c7d8e9f0a1_subsidy_org_to_grantee.py).
"""
from alembic import op

revision = 't2v4x6z8b0d2'
down_revision = 'n7q9s1u3w5y7'
branch_labels = None
depends_on = None


_LINK_EXISTING = """
UPDATE organizations o
SET contractor_id = m.contractor_id
FROM (
    SELECT o2.id AS org_id, (
        SELECT MIN(c.id) FROM contractors c WHERE c.inn = o2.inn
    ) AS contractor_id
    FROM organizations o2
    WHERE o2.contractor_id IS NULL
      AND o2.inn IS NOT NULL AND btrim(o2.inn) <> ''
) m
WHERE o.id = m.org_id AND m.contractor_id IS NOT NULL;
"""

_CREATE_AND_LINK = """
WITH to_create AS (
    SELECT o.id AS org_id, o.name, o.full_name, o.inn, o.kpp, o.ogrn, o.address,
           o.signatory, o.signatory_position, o.signatory_last_name,
           o.signatory_first_name, o.signatory_middle_name
    FROM organizations o
    WHERE o.contractor_id IS NULL
      AND o.inn IS NOT NULL AND btrim(o.inn) <> ''
),
inserted AS (
    INSERT INTO contractors (
        name, full_name, inn, kpp, ogrn, address, signatory,
        signatory_position, signatory_last_name, signatory_first_name,
        signatory_middle_name, org_id
    )
    SELECT
        COALESCE(NULLIF(btrim(t.name), ''), t.inn), t.full_name, t.inn, t.kpp,
        t.ogrn, t.address, t.signatory, t.signatory_position,
        t.signatory_last_name, t.signatory_first_name, t.signatory_middle_name,
        t.org_id
    FROM to_create t
    RETURNING id, org_id
)
UPDATE organizations o
SET contractor_id = i.id
FROM inserted i
WHERE o.id = i.org_id;
"""

_BACKFILL_EMPTY_CONTRACTOR_FIELDS = """
DO $$
DECLARE
  r RECORD;
  fields TEXT[] := ARRAY['full_name','inn','kpp','ogrn','address','signatory',
                          'signatory_position','signatory_last_name',
                          'signatory_first_name','signatory_middle_name'];
  fname TEXT;
  o_val TEXT;
  c_val TEXT;
BEGIN
  FOR r IN
    SELECT o.id AS org_id, o.name AS org_name, c.id AS contractor_id, c.name AS contractor_name
    FROM organizations o
    JOIN contractors c ON c.id = o.contractor_id
  LOOP
    FOREACH fname IN ARRAY fields LOOP
      EXECUTE format('SELECT %I::text FROM organizations WHERE id = $1', fname) USING r.org_id INTO o_val;
      EXECUTE format('SELECT %I::text FROM contractors WHERE id = $1', fname) USING r.contractor_id INTO c_val;
      IF btrim(COALESCE(c_val, '')) = '' AND btrim(COALESCE(o_val, '')) <> '' THEN
        EXECUTE format('UPDATE contractors SET %I = $1 WHERE id = $2', fname) USING o_val, r.contractor_id;
        RAISE NOTICE 'org_contractor_backfill contractor_id=% contractor_name=% field=% copied_from_org_id=% org_name=% value=%',
          r.contractor_id, r.contractor_name, fname, r.org_id, r.org_name, o_val;
      END IF;
    END LOOP;
  END LOOP;
END $$;
"""

_REPORT_DIVERGENCES = """
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT o.id, o.name,
           o.full_name AS o_full_name, c.full_name AS c_full_name,
           o.inn AS o_inn, c.inn AS c_inn,
           o.kpp AS o_kpp, c.kpp AS c_kpp,
           o.ogrn AS o_ogrn, c.ogrn AS c_ogrn,
           o.address AS o_address, c.address AS c_address,
           o.signatory AS o_signatory, c.signatory AS c_signatory,
           o.signatory_position AS o_sp, c.signatory_position AS c_sp,
           o.signatory_last_name AS o_sln, c.signatory_last_name AS c_sln,
           o.signatory_first_name AS o_sfn, c.signatory_first_name AS c_sfn,
           o.signatory_middle_name AS o_smn, c.signatory_middle_name AS c_smn
    FROM organizations o
    JOIN contractors c ON c.id = o.contractor_id
  LOOP
    -- Только настоящие конфликты: ОБА поля непустые и различаются (пустые
    -- поля контрагента уже дозаполнены шагом выше — сюда не попадают).
    IF btrim(COALESCE(r.o_full_name, '')) <> '' AND btrim(COALESCE(r.c_full_name, '')) <> '' AND r.o_full_name IS DISTINCT FROM r.c_full_name THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=full_name org=% contractor=%', r.id, r.name, r.o_full_name, r.c_full_name;
    END IF;
    IF btrim(COALESCE(r.o_inn, '')) <> '' AND btrim(COALESCE(r.c_inn, '')) <> '' AND r.o_inn IS DISTINCT FROM r.c_inn THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=inn org=% contractor=%', r.id, r.name, r.o_inn, r.c_inn;
    END IF;
    IF btrim(COALESCE(r.o_kpp, '')) <> '' AND btrim(COALESCE(r.c_kpp, '')) <> '' AND r.o_kpp IS DISTINCT FROM r.c_kpp THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=kpp org=% contractor=%', r.id, r.name, r.o_kpp, r.c_kpp;
    END IF;
    IF btrim(COALESCE(r.o_ogrn, '')) <> '' AND btrim(COALESCE(r.c_ogrn, '')) <> '' AND r.o_ogrn IS DISTINCT FROM r.c_ogrn THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=ogrn org=% contractor=%', r.id, r.name, r.o_ogrn, r.c_ogrn;
    END IF;
    IF btrim(COALESCE(r.o_address, '')) <> '' AND btrim(COALESCE(r.c_address, '')) <> '' AND r.o_address IS DISTINCT FROM r.c_address THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=address org=% contractor=%', r.id, r.name, r.o_address, r.c_address;
    END IF;
    IF btrim(COALESCE(r.o_signatory, '')) <> '' AND btrim(COALESCE(r.c_signatory, '')) <> '' AND r.o_signatory IS DISTINCT FROM r.c_signatory THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=signatory org=% contractor=%', r.id, r.name, r.o_signatory, r.c_signatory;
    END IF;
    IF btrim(COALESCE(r.o_sp, '')) <> '' AND btrim(COALESCE(r.c_sp, '')) <> '' AND r.o_sp IS DISTINCT FROM r.c_sp THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=signatory_position org=% contractor=%', r.id, r.name, r.o_sp, r.c_sp;
    END IF;
    IF btrim(COALESCE(r.o_sln, '')) <> '' AND btrim(COALESCE(r.c_sln, '')) <> '' AND r.o_sln IS DISTINCT FROM r.c_sln THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=signatory_last_name org=% contractor=%', r.id, r.name, r.o_sln, r.c_sln;
    END IF;
    IF btrim(COALESCE(r.o_sfn, '')) <> '' AND btrim(COALESCE(r.c_sfn, '')) <> '' AND r.o_sfn IS DISTINCT FROM r.c_sfn THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=signatory_first_name org=% contractor=%', r.id, r.name, r.o_sfn, r.c_sfn;
    END IF;
    IF btrim(COALESCE(r.o_smn, '')) <> '' AND btrim(COALESCE(r.c_smn, '')) <> '' AND r.o_smn IS DISTINCT FROM r.c_smn THEN
      RAISE NOTICE 'org_contractor_diff id=% name=% field=signatory_middle_name org=% contractor=%', r.id, r.name, r.o_smn, r.c_smn;
    END IF;
  END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_LINK_EXISTING)
    op.execute(_CREATE_AND_LINK)
    op.execute(_BACKFILL_EMPTY_CONTRACTOR_FIELDS)
    op.execute(_REPORT_DIVERGENCES)


def downgrade() -> None:
    pass
