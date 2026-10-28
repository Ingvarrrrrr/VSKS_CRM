"""subsidy_calc_changes / account_contour_changes — отметки изменений
(append-only журналы) для кросс-запросного кэша compute_feo_plan_tree /
compute_account_contour_org_ids (владелец, 28.10.2026, замер прода:
compute_feo_plan_tree 1,64с на 11 субсидий, GET /api/purchases/?with_feo_excess=true
3,35с одиночно, в очереди на однопроцессном uvicorn — до 12-15с).

ПЕРЕДЕЛКА (ревью координатора, 28.10.2026, ДО применения на проде — правилась
именно эта миграция, не вторая): первая версия держала ПО ОДНОЙ UPDATE-строке
на субсидию (subsidy_calc_versions) и бампала её `UPDATE ... SET version =
version + 1` — это РЕАЛЬНАЯ строка, на которую берётся row lock до конца
транзакции. Два параллельных INSERT/UPDATE по одной субсидии (импорт ФЭО +
правка закупки) сериализовались бы друг за другом; перенос закупки/позиции
МЕЖДУ двумя субсидиями в разном порядке — классическая формула deadlock
(T1 держит лок строки субсидии A и ждёт B, T2 держит лок B и ждёт A).
Глобальная строка (subsidy_id=0, users/organizations) была ещё хуже — общая
точка сериализации на ВСЮ систему при каждом логине/правке сотрудника.

Новая схема — append-only: КАЖДОЕ изменение добавляет НОВУЮ строку (bigserial
id), не трогая никакую существующую — операции INSERT в разные строки друг
друга не блокируют (разные page-ы/разные строки, Postgres MVCC). "Версия"
субсидии = max(id) среди её строк — монотонно растёт, достаточно для
инвалидации кэша (не нужно точное число изменений). Один SELECT ... GROUP BY
на набор subsidy_id — тот же лёгкий запрос, что раньше.

Триггеры — FOR EACH STATEMENT с transition tables (REFERENCING NEW TABLE/OLD
TABLE), не ROW-level: один bulk INSERT/UPDATE/DELETE (импорт, пересборка
плана) пишет НЕ по строке в журнал, а DISTINCT subsidy_id затронутых строк
одним INSERT ... SELECT DISTINCT. DELETE берёт subsidy_id из OLD TABLE; UPDATE
берёт из ОБОИХ (NEW ∪ OLD) — перенос строки между субсидиями (смена
feo_category_id/purchase_id/subsidy_id) бьёт версию и старой, и новой.

Набор таблиц с триггером — тот же, что определён перехватом SQL
compute_feo_plan_tree (см. backend/tests/test_subsidy_calc_versions.py):
  subsidies, feo_categories, feo_planned_items, plan_excess_approvals,
  plan_excess_approval_steps, purchases, purchase_items, purchase_approvals,
  purchase_files, contract_items — через subsidy_calc_changes;
  users (full_name/username) и organizations — через account_contour_changes
  (users бьёт в зарезервированную строку subsidy_id=0 того же журнала
  subsidy_calc_changes — связь с конкретной субисдией дорогая/неоднозначная,
  см. docstring compute_feo_plan_tree про finalizer_names; organizations —
  в ОТДЕЛЬНЫЙ журнал account_contour_changes, т.к. это единственная таблица,
  которую реально читает compute_account_contour_org_ids).

Чистка (п. владельца «лёгкий DELETE, не обязательно на каждом запросе»):
НЕ встроена в триггер/каждый запрос — отдельная функция
cleanup_subsidy_calc_changes()/cleanup_account_contour_changes(), которую
Python-слой (subsidy_calc_versions.py) дёргает не чаще раза в час (throttle
в памяти процесса), удаляя строки субсидии, у которых есть более новая с тем
же subsidy_id.

Idempotent: отдельно обрабатывает случай, когда ЭТА ЖЕ миграция уже
применялась в старой (UPDATE-строка) редакции — явно дропает старые
триггеры/функции/таблицы по именам ПЕРЕД созданием новых объектов.

Revision ID: f5a7c9e1b3d5
Revises: d4e6f8a0b2c4
Create Date: 2026-10-28 00:00:00.000000

Примечание (проверка multiple heads, 28.10.2026): два head на момент создания
— d4e6f8a0b2c4 (эта ветка) и w2x4y6z8a0b2 (чужая незакоммиченная
product_words_mv). Цепляемся за d4e6f8a0b2c4, чужую ветку не трогаем/не сливаем.
Миграция НИГДЕ, кроме локального стенда автора задачи, не применялась —
переписана целиком (не добавлена вторая), безопасно для прода/staging.
"""
import sqlalchemy as sa
from alembic import op

revision = 'f5a7c9e1b3d5'
down_revision = 'd4e6f8a0b2c4'
branch_labels = None
depends_on = None


# Таблицы, где subsidy_id — физическая колонка самой строки.
_DIRECT_TABLES = ('feo_categories', 'plan_excess_approvals', 'purchases')
# Таблицы, где subsidy_id резолвится через purchases.subsidy_id по purchase_id.
_VIA_PURCHASE_TABLES = ('purchase_items', 'purchase_approvals', 'purchase_files', 'contract_items')
# Все таблицы, пишущие в subsidy_calc_changes (глобальная строка subsidy_id=0
# при TRUNCATE — TRUNCATE не вызывает ROW/STATEMENT-триггеры с transition
# tables, и точный набор subsidy_id из опустевшей таблицы взять нельзя;
# subsidy_id=0 уже входит в ключ версии ЛЮБОЙ субсидии в get_subsidy_versions,
# так что глобальный бамп инвалидирует кэш всех субсидий — safe over-invalidation).
_SUBSIDY_CALC_TABLES = (
    _DIRECT_TABLES
    + ('subsidies',)
    + _VIA_PURCHASE_TABLES
    + ('feo_planned_items', 'plan_excess_approval_steps', 'users')
)
# Таблицы, пишущие в account_contour_changes при TRUNCATE.
_ACCOUNT_CONTOUR_TABLES = ('organizations',)


def _drop_old_update_based_objects() -> None:
    """Снос ПЕРВОЙ (UPDATE-строка) редакции этой же миграции, если она уже
    была применена локально — идемпотентно, безопасно звать и на чистой БД
    (все DROP — IF EXISTS)."""
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_organizations_contour_version ON organizations"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_organizations_contour()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_users_calc_version ON users"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_users_calc_version()"))
    for _tbl, _fn in (
        ('purchase_items', 'trg_bump_purchase_items'),
        ('purchase_approvals', 'trg_bump_purchase_approvals'),
        ('purchase_files', 'trg_bump_purchase_files'),
        ('contract_items', 'trg_bump_contract_items'),
    ):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_fn}_trg ON {_tbl}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_fn}()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_purchases_calc_version ON purchases"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_purchases()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_plan_excess_approval_steps_calc_version ON plan_excess_approval_steps"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_plan_excess_approval_steps()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_plan_excess_approvals_calc_version ON plan_excess_approvals"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_plan_excess_approvals()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_feo_planned_items_calc_version ON feo_planned_items"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_feo_planned_items()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_feo_categories_calc_version ON feo_categories"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_feo_categories()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_subsidies_calc_version ON subsidies"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_bump_subsidies()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS bump_account_contour_version()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS bump_subsidy_calc_version(BIGINT)"))
    op.execute(sa.text("DROP TABLE IF EXISTS account_contour_version"))
    op.execute(sa.text("DROP TABLE IF EXISTS subsidy_calc_versions"))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    _drop_old_update_based_objects()

    # ------------------------------------------------------------------
    # 1) Append-only журналы
    # ------------------------------------------------------------------
    if 'subsidy_calc_changes' not in existing_tables:
        op.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS subsidy_calc_changes (
                id BIGSERIAL PRIMARY KEY,
                subsidy_id BIGINT NOT NULL,
                changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        op.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_subsidy_calc_changes_subsidy_id_id "
            "ON subsidy_calc_changes (subsidy_id, id)"
        ))

    if 'account_contour_changes' not in existing_tables:
        op.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS account_contour_changes (
                id BIGSERIAL PRIMARY KEY,
                changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))

    # Начальные строки: глобальная (subsidy_id=0) + по одной на каждую уже
    # существующую субсидию — первый запрос после миграции не промахивается
    # мимо версии (get_subsidy_versions и так трактует "нет строки" как 0,
    # но явная строка дешевле/предсказуемее).
    op.execute(sa.text("INSERT INTO subsidy_calc_changes (subsidy_id) VALUES (0)"))
    op.execute(sa.text("INSERT INTO account_contour_changes DEFAULT VALUES"))
    if 'subsidies' in existing_tables:
        op.execute(sa.text(
            "INSERT INTO subsidy_calc_changes (subsidy_id) SELECT id FROM subsidies"
        ))

    # ------------------------------------------------------------------
    # 2) Триггерные функции — STATEMENT-level, transition tables, DISTINCT
    #    INSERT (bulk-операция пишет один раз на затронутую субсидию, не на
    #    строку).
    # ------------------------------------------------------------------

    # --- Прямые таблицы (subsidy_id — своя колонка) -------------------
    for _tbl in _DIRECT_TABLES:
        base = f"trg_{_tbl}_calc"
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {base}_ins() RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO subsidy_calc_changes (subsidy_id)
                SELECT DISTINCT subsidy_id FROM new_rows WHERE subsidy_id IS NOT NULL;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {base}_del() RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO subsidy_calc_changes (subsidy_id)
                SELECT DISTINCT subsidy_id FROM old_rows WHERE subsidy_id IS NOT NULL;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {base}_upd() RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO subsidy_calc_changes (subsidy_id)
                SELECT DISTINCT subsidy_id FROM new_rows WHERE subsidy_id IS NOT NULL
                UNION
                SELECT DISTINCT subsidy_id FROM old_rows WHERE subsidy_id IS NOT NULL;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        for _ev, _suffix, _ref in (
            ('INSERT', 'ins', 'REFERENCING NEW TABLE AS new_rows'),
            ('DELETE', 'del', 'REFERENCING OLD TABLE AS old_rows'),
            ('UPDATE', 'upd', 'REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows'),
        ):
            trg_name = f"{base}_{_suffix}_trg"
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON {_tbl}"))
            op.execute(sa.text(f"""
                CREATE TRIGGER {trg_name}
                AFTER {_ev} ON {_tbl}
                {_ref}
                FOR EACH STATEMENT EXECUTE FUNCTION {base}_{_suffix}();
            """))

    # --- feo_planned_items: через feo_category_id → feo_categories.subsidy_id
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_feo_planned_items_calc_ins() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT fc.subsidy_id FROM new_rows nr
            JOIN feo_categories fc ON fc.id = nr.feo_category_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_feo_planned_items_calc_del() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT fc.subsidy_id FROM old_rows ord
            JOIN feo_categories fc ON fc.id = ord.feo_category_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_feo_planned_items_calc_upd() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT fc.subsidy_id FROM new_rows nr JOIN feo_categories fc ON fc.id = nr.feo_category_id
            UNION
            SELECT DISTINCT fc.subsidy_id FROM old_rows ord JOIN feo_categories fc ON fc.id = ord.feo_category_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    for _ev, _suffix, _ref in (
        ('INSERT', 'ins', 'REFERENCING NEW TABLE AS new_rows'),
        ('DELETE', 'del', 'REFERENCING OLD TABLE AS old_rows'),
        ('UPDATE', 'upd', 'REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows'),
    ):
        trg_name = f"trg_feo_planned_items_calc_{_suffix}_trg"
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON feo_planned_items"))
        op.execute(sa.text(f"""
            CREATE TRIGGER {trg_name}
            AFTER {_ev} ON feo_planned_items
            {_ref}
            FOR EACH STATEMENT EXECUTE FUNCTION trg_feo_planned_items_calc_{_suffix}();
        """))

    # --- plan_excess_approval_steps: через approval_id → plan_excess_approvals.subsidy_id
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_plan_excess_approval_steps_calc_ins() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT pea.subsidy_id FROM new_rows nr
            JOIN plan_excess_approvals pea ON pea.id = nr.approval_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_plan_excess_approval_steps_calc_del() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT pea.subsidy_id FROM old_rows ord
            JOIN plan_excess_approvals pea ON pea.id = ord.approval_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_plan_excess_approval_steps_calc_upd() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT pea.subsidy_id FROM new_rows nr JOIN plan_excess_approvals pea ON pea.id = nr.approval_id
            UNION
            SELECT DISTINCT pea.subsidy_id FROM old_rows ord JOIN plan_excess_approvals pea ON pea.id = ord.approval_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    for _ev, _suffix, _ref in (
        ('INSERT', 'ins', 'REFERENCING NEW TABLE AS new_rows'),
        ('DELETE', 'del', 'REFERENCING OLD TABLE AS old_rows'),
        ('UPDATE', 'upd', 'REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows'),
    ):
        trg_name = f"trg_plan_excess_approval_steps_calc_{_suffix}_trg"
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON plan_excess_approval_steps"))
        op.execute(sa.text(f"""
            CREATE TRIGGER {trg_name}
            AFTER {_ev} ON plan_excess_approval_steps
            {_ref}
            FOR EACH STATEMENT EXECUTE FUNCTION trg_plan_excess_approval_steps_calc_{_suffix}();
        """))

    # --- subsidies — сама строка (subsidy_id = id).
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_subsidies_calc_ins() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id) SELECT DISTINCT id FROM new_rows;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_subsidies_calc_del() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id) SELECT DISTINCT id FROM old_rows;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_subsidies_calc_upd() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT DISTINCT id FROM new_rows UNION SELECT DISTINCT id FROM old_rows;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    for _ev, _suffix, _ref in (
        ('INSERT', 'ins', 'REFERENCING NEW TABLE AS new_rows'),
        ('DELETE', 'del', 'REFERENCING OLD TABLE AS old_rows'),
        ('UPDATE', 'upd', 'REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows'),
    ):
        trg_name = f"trg_subsidies_calc_{_suffix}_trg"
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON subsidies"))
        op.execute(sa.text(f"""
            CREATE TRIGGER {trg_name}
            AFTER {_ev} ON subsidies
            {_ref}
            FOR EACH STATEMENT EXECUTE FUNCTION trg_subsidies_calc_{_suffix}();
        """))

    # --- purchase_items/purchase_approvals/purchase_files/contract_items —
    #     через purchase_id → purchases.subsidy_id.
    for _tbl in _VIA_PURCHASE_TABLES:
        base = f"trg_{_tbl}_calc"
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {base}_ins() RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO subsidy_calc_changes (subsidy_id)
                SELECT DISTINCT p.subsidy_id FROM new_rows nr
                JOIN purchases p ON p.id = nr.purchase_id
                WHERE p.subsidy_id IS NOT NULL;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {base}_del() RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO subsidy_calc_changes (subsidy_id)
                SELECT DISTINCT p.subsidy_id FROM old_rows ord
                JOIN purchases p ON p.id = ord.purchase_id
                WHERE p.subsidy_id IS NOT NULL;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {base}_upd() RETURNS TRIGGER AS $$
            BEGIN
                INSERT INTO subsidy_calc_changes (subsidy_id)
                SELECT DISTINCT p.subsidy_id FROM new_rows nr JOIN purchases p ON p.id = nr.purchase_id
                WHERE p.subsidy_id IS NOT NULL
                UNION
                SELECT DISTINCT p.subsidy_id FROM old_rows ord JOIN purchases p ON p.id = ord.purchase_id
                WHERE p.subsidy_id IS NOT NULL;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """))
        for _ev, _suffix, _ref in (
            ('INSERT', 'ins', 'REFERENCING NEW TABLE AS new_rows'),
            ('DELETE', 'del', 'REFERENCING OLD TABLE AS old_rows'),
            ('UPDATE', 'upd', 'REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows'),
        ):
            trg_name = f"{base}_{_suffix}_trg"
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON {_tbl}"))
            op.execute(sa.text(f"""
                CREATE TRIGGER {trg_name}
                AFTER {_ev} ON {_tbl}
                {_ref}
                FOR EACH STATEMENT EXECUTE FUNCTION {base}_{_suffix}();
            """))

    # --- users: только реальная смена full_name/username → ОДНА строка
    #     subsidy_id=0 на весь statement (не по пользователю).
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_users_calc_upd() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id)
            SELECT 0 WHERE EXISTS (
                SELECT 1 FROM new_rows nt JOIN old_rows ot ON ot.id = nt.id
                WHERE nt.full_name IS DISTINCT FROM ot.full_name
                   OR nt.username IS DISTINCT FROM ot.username
            );
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_users_calc_upd_trg ON users"))
    op.execute(sa.text("""
        CREATE TRIGGER trg_users_calc_upd_trg
        AFTER UPDATE ON users
        REFERENCING NEW TABLE AS new_rows OLD TABLE AS old_rows
        FOR EACH STATEMENT EXECUTE FUNCTION trg_users_calc_upd();
    """))

    # --- organizations — вся таблица, account_contour_changes, ОДНА строка
    #     на весь statement.
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_organizations_contour() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO account_contour_changes DEFAULT VALUES;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_organizations_contour_trg ON organizations"))
    op.execute(sa.text("""
        CREATE TRIGGER trg_organizations_contour_trg
        AFTER INSERT OR UPDATE OR DELETE ON organizations
        FOR EACH STATEMENT EXECUTE FUNCTION trg_organizations_contour();
    """))

    # ------------------------------------------------------------------
    # 3) TRUNCATE — transition tables (REFERENCING NEW/OLD TABLE) не
    #    поддерживаются на TRUNCATE в PostgreSQL, и после TRUNCATE таблица
    #    уже пуста — точечный набор subsidy_id взять негде. Поэтому отдельная
    #    пара AFTER TRUNCATE FOR EACH STATEMENT триггеров пишет ОДНУ
    #    глобальную строку (subsidy_id=0 — уже входит в ключ версии любой
    #    субсидии) — безопасный over-инвалидейт всего кэша целиком.
    # ------------------------------------------------------------------
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_truncate_bump_subsidy_calc() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO subsidy_calc_changes (subsidy_id) VALUES (0);
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    for _tbl in _SUBSIDY_CALC_TABLES:
        trg_name = f"trg_{_tbl}_truncate_calc_trg"
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON {_tbl}"))
        op.execute(sa.text(f"""
            CREATE TRIGGER {trg_name}
            AFTER TRUNCATE ON {_tbl}
            FOR EACH STATEMENT EXECUTE FUNCTION trg_truncate_bump_subsidy_calc();
        """))

    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION trg_truncate_bump_account_contour() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO account_contour_changes DEFAULT VALUES;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """))
    for _tbl in _ACCOUNT_CONTOUR_TABLES:
        trg_name = f"trg_{_tbl}_truncate_contour_trg"
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg_name} ON {_tbl}"))
        op.execute(sa.text(f"""
            CREATE TRIGGER {trg_name}
            AFTER TRUNCATE ON {_tbl}
            FOR EACH STATEMENT EXECUTE FUNCTION trg_truncate_bump_account_contour();
        """))


def downgrade() -> None:
    for _tbl in _SUBSIDY_CALC_TABLES:
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{_tbl}_truncate_calc_trg ON {_tbl}"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_truncate_bump_subsidy_calc()"))
    for _tbl in _ACCOUNT_CONTOUR_TABLES:
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{_tbl}_truncate_contour_trg ON {_tbl}"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_truncate_bump_account_contour()"))

    for _tbl in _DIRECT_TABLES + ('subsidies',) + _VIA_PURCHASE_TABLES + ('feo_planned_items', 'plan_excess_approval_steps'):
        base = f"trg_{_tbl}_calc"
        for _suffix in ('ins', 'del', 'upd'):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {base}_{_suffix}_trg ON {_tbl}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {base}_{_suffix}()"))

    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_organizations_contour_trg ON organizations"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_organizations_contour()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_users_calc_upd_trg ON users"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS trg_users_calc_upd()"))

    op.execute(sa.text("DROP TABLE IF EXISTS account_contour_changes"))
    op.execute(sa.text("DROP TABLE IF EXISTS subsidy_calc_changes"))
