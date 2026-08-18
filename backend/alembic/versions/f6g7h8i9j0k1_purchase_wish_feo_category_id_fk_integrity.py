"""FK-целостность purchase_items/wish_items/wishes.feo_category_id

БАГ (тот же класс, что x9y8z7w6v5u4, найден при разведке по следам того
инцидента, 2026-08-17). У purchase_items.feo_category_id, wish_items.feo_category_id
и wishes.feo_category_id в БД НИКОГДА не было настоящего FK-констрейнта — ни
на проде, ни локально (проверено `information_schema` + `\d`), хотя
SQLAlchemy-модели (app/models/purchase_item.py, app/models/wish_item.py,
app/models/wish.py) с самого начала объявляют `ForeignKey(..., ondelete="SET
NULL")`. Для сравнения: products.feo_category_id и purchases.feo_category_id
такой констрейнт ИМЕЮТ (ON DELETE SET NULL) — несогласованность возникла
потому, что эти три колонки либо старше alembic-бейзлайна, либо добавлялись
вручную (см. TODO-комментарий над wish_items.feo_category_id: "ALTER TABLE
wish_items ADD COLUMN IF NOT EXISTS ... REFERENCES feo_categories(id)" — DDL
из TODO так и не была применена).

ПОСЛЕДСТВИЯ висячей ссылки (проверено по коду app/services/feo_plan.py):
plan_consumption_by_category/ordered_consumption_by_category/
purchase_item_fact_amount строят суммы «в закупках»/«заказано»/«факт» через
`.join(FeoCategory, FeoCategory.id == COALESCE(PurchaseItem.feo_category_id,
Purchase.feo_category_id))` — это INNER JOIN. Если feo_category_id ссылается
на несуществующую категорию, строка целиком выпадает из джойна: сумма позиции
НЕ попадает ни в одну ветку дерева ФЭО, ни в потолок субсидии, ни в KPI —
тихо исчезает из отчётности, при этом сама позиция закупки/заявки остаётся
на месте и видна в списке закупок (её достают не через FeoCategory, а
напрямую по purchase_id). Обратный эффект по сравнению с багом
feo_planned_item_id (там сумма продолжала засчитываться, вызывая фантомное
превышение) — здесь сумма тихо пропадает из расчётов, недосчёт незаметен,
пока кто-то вручную не сверит «сумма позиций» с «сумма по дереву ФЭО».

РАЗВЕДКА (2026-08-17): на ПРОДЕ живых висячих ссылок на момент проверки НЕТ
(0 по всем трём колонкам). На локальной копии обнаруженные 3 строки
purchase_items (id 2899/2904/2905, "Great Wall POER", по 8 380 000 каждая) —
НЕ прод-данные и НЕ применимы к боевым: это артефакт того, что
backend/tests/test_feo_plan_tree_scenarios.py фикстура `db_session` (см.
tests/conftest.py) коммитит напрямую в `app.database.async_session`, то есть
в ту же локальную БД, без отката — прогон pytest локально оставляет мусорные
Purchase/PurchaseItem/FeoCategory/Subsidy (имена вида "TestSubsidy-<hash>",
org_id IS NULL). Сама КЛАСС ошибки (отсутствие FK) при этом реален и на
проде, и локально — просто на проде пока нет строк, которые бы его проявили;
констрейнт добавляется превентивно, тем же способом, что уже применён для
feo_planned_item_id в x9y8z7w6v5u4.

ЧТО ДЕЛАЕТ МИГРАЦИЯ (идемпотентно, безопасно для повторного прогона на проде):
  1. Для purchase_items, wish_items, wishes считает и печатает (print, видно
     в логах деплоя) число строк, где feo_category_id указывает на
     несуществующую feo_categories — ДО какой-либо очистки.
  2. Обнуляет (UPDATE ... SET feo_category_id = NULL) только эти висячие
     ссылки. Сами строки НЕ трогает и не удаляет — суммы/количества/статусы
     позиции остаются как есть, меняется только (уже итак нерабочая)
     привязка к категории.
  3. Добавляет реальные FK-констрейнты ON DELETE SET NULL (согласовано с уже
     существующими products_feo_category_id_fkey / purchases_feo_category_id_fkey
     — та же колонка на соседних таблицах уже SET NULL, RESTRICT сломал бы
     единообразие и заблокировал бы удаление/реорганизацию категорий ФЭО,
     у которых есть хоть одна позиция закупки/заявки):
     purchase_items.feo_category_id → feo_categories(id) ON DELETE SET NULL
     wish_items.feo_category_id     → feo_categories(id) ON DELETE SET NULL
     wishes.feo_category_id         → feo_categories(id) ON DELETE SET NULL
     через guard по pg_constraint (Postgres не поддерживает "ADD CONSTRAINT
     IF NOT EXISTS" для FK) — без него шаг 3 упал бы при повторном прогоне.
     Констрейнт можно добавить только ПОСЛЕ шага 2 — иначе ADD CONSTRAINT сам
     упадёт на уже существующих висячих ссылках.

downgrade(): снимает добавленные FK-констрейнты. Обнулённые в шаге 2 висячие
ссылки НЕ восстанавливает — восстанавливать нечего, feo_categories с этими id
не существует, ссылка была логически битой уже до этой миграции.

Revision ID: f6g7h8i9j0k1
Revises: x9y8z7w6v5u4
Create Date: 2026-08-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6g7h8i9j0k1'
down_revision = 'x9y8z7w6v5u4'
branch_labels = None
depends_on = None

_LINKS = (
    ("purchase_items", "purchase_items_feo_category_id_fkey"),
    ("wish_items", "wish_items_feo_category_id_fkey"),
    ("wishes", "wishes_feo_category_id_fkey"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "feo_categories" not in existing_tables:
        return

    # --- 1+2. Найти и обнулить висячие ссылки, залогировав числа ДО очистки ---
    for table, _fk_name in _LINKS:
        if table not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "feo_category_id" not in cols:
            continue

        dangling_count = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} t "
            "WHERE t.feo_category_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM feo_categories f WHERE f.id = t.feo_category_id)"
        )).scalar()
        print(f"[f6g7h8i9j0k1] {table}: висячих ссылок feo_category_id ДО очистки = {dangling_count}")

        if dangling_count:
            result = bind.execute(sa.text(
                f"UPDATE {table} t SET feo_category_id = NULL "
                "WHERE t.feo_category_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM feo_categories f WHERE f.id = t.feo_category_id)"
            ))
            print(f"[f6g7h8i9j0k1] {table}: обнулено строк = {result.rowcount}")

    # --- 3. Реальные FK-констрейнты ON DELETE SET NULL (idempotent guard) ---
    for table, fk_name in _LINKS:
        if table not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "feo_category_id" not in cols:
            continue

        already_exists = bind.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = :name"
        ), {"name": fk_name}).scalar()
        if already_exists:
            print(f"[f6g7h8i9j0k1] {fk_name} уже существует — пропуск")
            continue

        op.execute(sa.text(
            f"ALTER TABLE {table} ADD CONSTRAINT {fk_name} "
            "FOREIGN KEY (feo_category_id) REFERENCES feo_categories(id) ON DELETE SET NULL"
        ))
        print(f"[f6g7h8i9j0k1] {fk_name} создан")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, fk_name in _LINKS:
        if table not in existing_tables:
            continue
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {fk_name}"))
