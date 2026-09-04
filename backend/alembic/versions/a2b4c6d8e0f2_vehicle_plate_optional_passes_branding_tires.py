"""Карточка ТС (владелец, 2026-09): гос. номер необязателен, произвольные
пропуска, брендирование Да/Нет + состояние, переименование ЛКП, сезонные
комплекты резины.

MERGE-ревизия: на момент написания в репозитории было ДВЕ головы alembic —
y8z9a1b2c3d4 (vehicle_home_base_city, ветка карточки ТС) и z1a2b3c4d5e6
(feo_planned_item_unit_price, ветка ФЭО) — они разъехались, потому что были
закоммичены параллельно в разных сессиях без общего родителя-мержа (в этом
проекте это уже третий раз, см. TASKS.md). down_revision ниже — кортеж из
ОБЕИХ голов: эта ревизия одновременно мержит дерево alembic в одну голову И
несёт реальные DDL-изменения задания.

Семь пунктов задания:
  1. vehicles.plate — NOT NULL снят (уникальность сохранена, в Postgres
     несколько NULL не конфликтуют). Машина без номера опознаётся по VIN.
  2. Новая таблица vehicle_passes — произвольный набор пропусков на машину
     (замена 10 фиксированных колонок vehicles.pass_*). Данные НЕПУСТЫХ
     старых колонок перенесены сюда (idempotent: NOT EXISTS-guard — повторный
     прогон не задвоит строки). Старые 10 колонок НЕ удалены.
  3. vehicles.has_branding — новая колонка (Да/Нет), проставлена TRUE там, где
     props.branding (текст) был непустой. Текст остаётся как "состояние".
  4. (без DDL — пояснения "откуда данные" добавлены в реестр полей, не в БД).
  5. props.paint_condition: "Идеальное, есть сколы" → "Хорошее - есть сколы"
     (значение справочника переименовано; старое распознаётся при импорте
     как алиас, но в самой БД приведено к новому написанию).
  6. (без DDL — проверка дат в API/импорте, не структура БД).
  7. Резина — 6 новых колонок (лето/зима × радиус/профиль/состояние).
     vehicles.tires_condition (общее устаревшее поле) перенесено в
     tires_summer_condition, если props.tires_type = 'Летняя' или пуст;
     иначе в tires_winter_condition, если 'Зимняя'.

Revision ID: a2b4c6d8e0f2
Revises: y8z9a1b2c3d4, z1a2b3c4d5e6
Create Date: 2026-09-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a2b4c6d8e0f2'
down_revision = ('y8z9a1b2c3d4', 'z1a2b3c4d5e6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Пункт 1: гос. номер необязателен ────────────────────────────────────
    # DROP NOT NULL идемпотентно само по себе (повторный прогон на уже
    # nullable-колонке не ошибка).
    op.execute(sa.text("ALTER TABLE vehicles ALTER COLUMN plate DROP NOT NULL"))

    # ── Пункт 2: таблица vehicle_passes + перенос данных ────────────────────
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS vehicle_passes (
            id SERIAL PRIMARY KEY,
            vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            status VARCHAR(20),
            expires_at DATE,
            note VARCHAR(300),
            CONSTRAINT uq_vehicle_passes_vehicle_name UNIQUE (vehicle_id, name)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_vehicle_passes_vehicle_id ON vehicle_passes (vehicle_id)"
    ))

    # Перенос НЕПУСТЫХ значений пяти старых пар колонок → vehicle_passes.
    # NOT EXISTS-guard на (vehicle_id, name) — идемпотентно при повторном прогоне.
    for col_status, col_until, pass_name in (
        ("pass_zo", "pass_zo_until", "ЗО"),
        ("pass_ho", "pass_ho_until", "ХО"),
        ("pass_dnr", "pass_dnr_until", "ДНР"),
        ("pass_lnr", "pass_lnr_until", "ЛНР"),
        ("pass_moscow", "pass_moscow_until", "Москва"),
    ):
        op.execute(sa.text(f"""
            INSERT INTO vehicle_passes (vehicle_id, name, status, expires_at)
            SELECT v.id, :pass_name, v.{col_status}, v.{col_until}
            FROM vehicles v
            WHERE (v.{col_status} IS NOT NULL OR v.{col_until} IS NOT NULL)
              AND NOT EXISTS (
                  SELECT 1 FROM vehicle_passes p
                  WHERE p.vehicle_id = v.id AND p.name = :pass_name
              )
        """).bindparams(pass_name=pass_name))

    # ── Пункт 3: брендирование — признак Да/Нет отдельно от состояния ──────
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS has_branding BOOLEAN"))
    op.execute(sa.text("""
        UPDATE vehicles
        SET has_branding = TRUE
        WHERE has_branding IS NULL
          AND trim(COALESCE(props->>'branding', '')) <> ''
    """))

    # ── Пункт 5: переименование значения ЛКП ────────────────────────────────
    op.execute(sa.text("""
        UPDATE vehicles
        SET props = jsonb_set(props, '{paint_condition}', to_jsonb('Хорошее - есть сколы'::text))
        WHERE props->>'paint_condition' = 'Идеальное, есть сколы'
    """))

    # ── Пункт 7: резина — сезонные комплекты ────────────────────────────────
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tires_summer_radius VARCHAR(20)"))
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tires_summer_profile VARCHAR(20)"))
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tires_summer_condition VARCHAR(100)"))
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tires_winter_radius VARCHAR(20)"))
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tires_winter_profile VARCHAR(20)"))
    op.execute(sa.text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS tires_winter_condition VARCHAR(100)"))

    # tires_condition (устаревшее общее поле) → сезонный комплект по props.tires_type.
    # Если tires_type не указан/неизвестен — считаем "Летняя" разумным умолчанием
    # (см. обоснование в отчёте задачи): не теряем текст, кладём в летний комплект.
    op.execute(sa.text("""
        UPDATE vehicles
        SET tires_summer_condition = tires_condition
        WHERE tires_condition IS NOT NULL
          AND tires_summer_condition IS NULL
          AND (props->>'tires_type' = 'Летняя' OR props->>'tires_type' IS NULL)
    """))
    op.execute(sa.text("""
        UPDATE vehicles
        SET tires_winter_condition = tires_condition
        WHERE tires_condition IS NOT NULL
          AND tires_winter_condition IS NULL
          AND props->>'tires_type' = 'Зимняя'
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS tires_winter_condition"))
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS tires_winter_profile"))
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS tires_winter_radius"))
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS tires_summer_condition"))
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS tires_summer_profile"))
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS tires_summer_radius"))
    op.execute(sa.text("ALTER TABLE vehicles DROP COLUMN IF EXISTS has_branding"))
    op.execute(sa.text("DROP TABLE IF EXISTS vehicle_passes"))
    # plate: восстановить NOT NULL — best-effort, только если сейчас нет NULL-строк
    # (иначе откат оставит plate nullable, что безопаснее, чем упасть с ошибкой).
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM vehicles WHERE plate IS NULL) THEN
                ALTER TABLE vehicles ALTER COLUMN plate SET NOT NULL;
            END IF;
        END $$;
    """))
