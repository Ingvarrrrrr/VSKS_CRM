"""feo_planned_items: FK-целостность purchase_items/wish_items.feo_planned_item_id

БАГ (владелец, 2026-08-17: «Где превышение 80 318? Где его увидеть?»). На проде
найдены висячие ссылки: purchase_item 2897 (feo_planned_item_id=809) и
purchase_item 2923 (feo_planned_item_id=1409) указывают на строки
feo_planned_items, которых больше нет. Из-за этого обе позиции пропадают с
экрана целиком (к плановой строке не подставляются — такой нет; в блок «Не
привязаны к плану» не попадают — там фильтр по ПУСТОЙ привязке), а их сумма
при этом продолжает учитываться в «в закупках» категории — необъяснимое для
владельца превышение плана.

ПРИЧИНА (проверено локально на копии прод-БД: `\d purchase_items`, `\d
wish_items` — секция "Foreign-key constraints:" пуста для обеих таблиц). У
purchase_items.feo_planned_item_id и wish_items.feo_planned_item_id в БД
никогда не было настоящего FK-констрейнта, хотя SQLAlchemy-модели
(app/models/purchase_item.py, app/models/wish_item.py) с самого начала
объявляют `ForeignKey(..., ondelete="SET NULL")` — эта DDL никогда не
применялась (таблица заведена до перехода проекта на alembic, прод-бейзлайн
77a79dee6f2f не включал эти констрейнты). Из-за отсутствия FK жёсткое удаление
плановой позиции (DELETE /api/feo-planned-items/{id}) молча оставляло
ссылающиеся строки битыми.

Отдельно: feo_planned_items.feo_category_id → feo_categories(id) в БД УЖЕ
имеет ON DELETE CASCADE (проверено `\d feo_categories`) — удаление категории
ФЭО (или каскадно всей субсидии) удаляет строки feo_planned_items средствами
самой БД, в обход Python-кода роутеров. Значит починка только на уровне
эндпоинта недостаточна — нужен FK и на уровне БД, чтобы ни один путь удаления
(ручной DELETE, каскад категории, каскад субсидии, будущий код) не мог оставить
висячую ссылку.

ЧТО ДЕЛАЕТ МИГРАЦИЯ (идемпотентно, безопасно для повторного прогона на проде):
  1. Для purchase_items и wish_items считает и печатает (print, видно в логах
     деплоя) число строк, где feo_planned_item_id указывает на несуществующую
     запись feo_planned_items — ДО какой-либо очистки.
  2. Обнуляет (UPDATE ... SET feo_planned_item_id = NULL) только эти висячие
     ссылки. Сами строки purchase_items/wish_items НЕ трогает и не удаляет —
     меняется только видимость привязки, суммы/количества/статусы позиции
     остаются как есть.
  3. Добавляет реальные FK-констрейнты
     purchase_items.feo_planned_item_id → feo_planned_items(id) ON DELETE SET NULL
     wish_items.feo_planned_item_id → feo_planned_items(id) ON DELETE SET NULL
     через guard по pg_constraint (Postgres не поддерживает
     "ADD CONSTRAINT IF NOT EXISTS" для FK) — без этого шаг 3 упал бы при
     повторном прогоне. Констрейнт можно добавить только ПОСЛЕ шага 2 —
     иначе ADD CONSTRAINT сам упадёт на уже существующих висячих ссылках.

Деактивация плановой позиции (is_active=false) эту миграцию не касается —
строка feo_planned_items остаётся на месте, ссылки на неё валидны и НЕ
обнуляются (это осознанное поведение прикладного кода, не баг целостности).

downgrade(): снимает добавленные FK-констрейнты. Обнулённые в шаге 2 висячие
ссылки НЕ восстанавливает — восстанавливать нечего, feo_planned_items с этими
id не существует, ссылка была логически битой уже до этой миграции.

Revision ID: x9y8z7w6v5u4
Revises: s1t2u3v4w5x6
Create Date: 2026-08-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'x9y8z7w6v5u4'
down_revision = 's1t2u3v4w5x6'
branch_labels = None
depends_on = None

_LINKS = (
    ("purchase_items", "purchase_items_feo_planned_item_id_fkey"),
    ("wish_items", "wish_items_feo_planned_item_id_fkey"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "feo_planned_items" not in existing_tables:
        return

    # --- 1+2. Найти и обнулить висячие ссылки, залогировав числа ДО очистки ---
    for table, _fk_name in _LINKS:
        if table not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "feo_planned_item_id" not in cols:
            continue

        dangling_count = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} t "
            "WHERE t.feo_planned_item_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM feo_planned_items f WHERE f.id = t.feo_planned_item_id)"
        )).scalar()
        print(f"[x9y8z7w6v5u4] {table}: висячих ссылок feo_planned_item_id ДО очистки = {dangling_count}")

        if dangling_count:
            result = bind.execute(sa.text(
                f"UPDATE {table} t SET feo_planned_item_id = NULL "
                "WHERE t.feo_planned_item_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM feo_planned_items f WHERE f.id = t.feo_planned_item_id)"
            ))
            print(f"[x9y8z7w6v5u4] {table}: обнулено строк = {result.rowcount}")

    # --- 3. Реальные FK-констрейнты ON DELETE SET NULL (idempotent guard) ---
    for table, fk_name in _LINKS:
        if table not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "feo_planned_item_id" not in cols:
            continue

        already_exists = bind.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conname = :name"
        ), {"name": fk_name}).scalar()
        if already_exists:
            print(f"[x9y8z7w6v5u4] {fk_name} уже существует — пропуск")
            continue

        op.execute(sa.text(
            f"ALTER TABLE {table} ADD CONSTRAINT {fk_name} "
            "FOREIGN KEY (feo_planned_item_id) REFERENCES feo_planned_items(id) ON DELETE SET NULL"
        ))
        print(f"[x9y8z7w6v5u4] {fk_name} создан")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, fk_name in _LINKS:
        if table not in existing_tables:
            continue
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {fk_name}"))
