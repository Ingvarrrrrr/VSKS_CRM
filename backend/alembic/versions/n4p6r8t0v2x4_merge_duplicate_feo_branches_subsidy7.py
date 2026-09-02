"""feo_categories: слияние задвоенных веток дерева ФЭО в субсидии id=7 (ФАДМ_2026)

Владелец согласовал слияние 2026-09-02. Дубли появились, судя по всему, от
повторного импорта ФЭО: в субсидии id=7 рядом с рабочей веткой «Техническое
оснащение деятельности штаба» (id=7 → 121 → …) висела почти одноимённая
ветка-дубль «Техническое оснащение штаба» (id=3668 → 3669 → …), из-за чего
алярм расхождения категорий ФЭО читался как бред — система сравнивала план
с самим собой по двум параллельным деревьям. Плюс отдельно найден полностью
пустой корень-дубль id=10 «Оказание услуг по транспортировке и проживанию»
(0 детей, 0 ссылок; живой аналог — id 69).

ФАКТИЧЕСКОЕ СОСТОЯНИЕ НА ПРОДЕ (проверено запросами перед написанием миграции):

  Рабочая ветка:
    7   «Техническое оснащение деятельности штаба»  (корень)
     └ 121 «Техническое оснащение деятельности штаба»
        ├ 122..126, 151, 973
        └ 3719 «Не определена»

  Ветка-дубль:
    3668 «Техническое оснащение штаба»  (корень, planned_quantity=500)
     └ 3669 «Техническое оснащение штаба»
        ├ 3670 «Закупка компьютеров»  budget 2000000, planned_quantity 6
        ├ 3718 «Не определена»
        └ 4624 «Ремонт техники»

  Пустой корень-дубль: 10 «Оказание услуг по транспортировке и проживанию»

ЧТО ДЕЛАЕТ МИГРАЦИЯ (строго в этом порядке):
  1. feo_planned_items.feo_category_id: 3669 → 121 (плановые позиции ветки-
     дубля переезжают в рабочий узел).
  2. feo_categories.parent_id узла 3670 «Закупка компьютеров»: 3669 → 121.
     Узел СОХРАНЯЕТСЯ вместе с именем/бюджетом/planned_quantity — владелец
     попросил перенести эту категорию в рабочую ветку как отдельный узел,
     а не сливать её с существующими категориями рабочей ветки.
  3. wishes.feo_category_id: 3718 → 3719 (обе — «Не определена», целевая уже
     в рабочей ветке).
  4. Удаление опустевших узлов ровно в порядке 3718, 4624, 3669, 3668, 10.

ОСОЗНАННАЯ ПОТЕРЯ ДАННЫХ: у удаляемого корня 3668 стоит planned_quantity=500.
Это значение уходит вместе с узлом безвозвратно. Осознанно и безопасно: план
в этом дереве считается по листьям (см. app.services.feo_plan), значение на
КОРНЕ дерева ни на что не влияет и нигде не читается.

ЗАЩИТА ОТ ЧУЖОЙ/ЛОКАЛЬНОЙ БАЗЫ: это миграция по жёстко зашитым id. Каждый
шаг переноса и каждое удаление предваряются проверкой, что узел
feo_categories с данным id существует, subsidy_id = 7 И name ТОЧНО совпадает
с ожидаемым именем на проде. Если не совпало — шаг молча пропускается,
никаких предположений о структуре чужой базы не делается. На базе без этих
данных (например, локальной чистой) миграция проходит без единой ошибки и
не трогает ничего.

ЗАПРЕТ СЛЕПОГО УДАЛЕНИЯ: непосредственно перед удалением каждого узла заново
пересчитываются ссылки на него по ВСЕМ внешним ключам, ведущим на
feo_categories(id) — список колонок собирается ДИНАМИЧЕСКИ из
information_schema (constraint_column_usage), а не хардкодится, это надёжнее
против дрейфа схемы. Отдельно проверяется наличие колонки feo_node_id у
purchase_items/wish_items (в этих двух таблицах она не гарантированно
объявлена как FK) — если она есть, ссылки по ней считаются тоже. Если после
всех переносов на узле остались ссылки — удаление ЭТОГО узла отменяется и
поднимается исключение с русским текстом (какой узел, сколько ссылок, из
каких таблиц/колонок). Лучше упавший деплой, чем каскадно снесённые данные.

ИДЕМПОТЕНТНОСТЬ: migrate.py гоняет `alembic upgrade head` при каждом старте
бэкенда. Каждый шаг охраняется проверкой «узел ещё существует» — при повторном
прогоне все переносы и удаления уже неприменимы (узлы удалены/переехали) и
молча пропускаются.

Revision ID: n4p6r8t0v2x4
Revises: k3m5p7r9t1v3
Create Date: 2026-09-02 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'n4p6r8t0v2x4'
down_revision = 'k3m5p7r9t1v3'
branch_labels = None
depends_on = None

_LOG = "[n4p6r8t0v2x4]"

_SUBSIDY_ID = 7

# Ожидаемые имена узлов — используются как защита от чужой базы: если id
# существует, но name не совпадает, шаг молча пропускается.
_EXPECTED_NAMES = {
    121: "Техническое оснащение деятельности штаба",
    3668: "Техническое оснащение штаба",
    3669: "Техническое оснащение штаба",
    3670: "Закупка компьютеров",
    3718: "Не определена",
    3719: "Не определена",
    4624: "Ремонт техники",
    10: "Оказание услуг по транспортировке и проживанию",
}


def _check_node(bind, node_id: int, expected_name: str) -> bool:
    """Узел существует, принадлежит subsidy_id=7 и name совпадает ТОЧНО."""
    row = bind.execute(
        sa.text(
            "SELECT name FROM feo_categories WHERE id = :id AND subsidy_id = :sid"
        ),
        {"id": node_id, "sid": _SUBSIDY_ID},
    ).fetchone()
    return bool(row) and row[0] == expected_name


def _discover_fk_columns(bind):
    """Динамически собрать все (таблица, колонка), где есть FK на
    feo_categories(id) — включая самоссылку feo_categories.parent_id."""
    rows = bind.execute(sa.text(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
           AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND ccu.table_name = 'feo_categories'
          AND ccu.column_name = 'id'
        """
    )).fetchall()
    columns = {(r[0], r[1]) for r in rows}

    # purchase_items/wish_items могут иметь feo_node_id без объявленного FK —
    # проверяем по information_schema и учитываем ссылки по этой колонке тоже.
    for table in ("purchase_items", "wish_items"):
        exists = bind.execute(sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t AND column_name = 'feo_node_id'
            """
        ), {"t": table}).scalar()
        if exists:
            columns.add((table, "feo_node_id"))

    return sorted(columns)


def _count_refs(bind, fk_columns, node_id: int):
    total = 0
    details = []
    for table, column in fk_columns:
        cnt = bind.execute(sa.text(
            f'SELECT count(*) FROM "{table}" WHERE "{column}" = :id'
        ), {"id": node_id}).scalar() or 0
        if cnt:
            total += cnt
            details.append(f"{table}.{column}={cnt}")
    return total, details


def _safe_delete(bind, fk_columns, node_id: int):
    expected_name = _EXPECTED_NAMES[node_id]
    if not _check_node(bind, node_id, expected_name):
        print(f"{_LOG} узел {node_id} не найден/не совпал по subsidy/имени — удаление пропущено")
        return

    total, details = _count_refs(bind, fk_columns, node_id)
    if total:
        raise RuntimeError(
            f"{_LOG} отменено удаление feo_categories id={node_id} "
            f"('{expected_name}'): на узел ещё есть {total} ссылок "
            f"({', '.join(details)}). Слепое удаление запрещено — проверьте "
            "перенос данных перед повторным прогоном."
        )

    bind.execute(sa.text("DELETE FROM feo_categories WHERE id = :id"), {"id": node_id})
    print(f"{_LOG} узел {node_id} ('{expected_name}') удалён")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "feo_categories" not in inspector.get_table_names():
        return

    # --- Шаг 1: feo_planned_items 3669 → 121 ---
    if _check_node(bind, 3669, _EXPECTED_NAMES[3669]) and _check_node(bind, 121, _EXPECTED_NAMES[121]):
        result = bind.execute(sa.text(
            "UPDATE feo_planned_items SET feo_category_id = 121 WHERE feo_category_id = 3669"
        ))
        print(f"{_LOG} шаг 1: перенесено {result.rowcount} строк feo_planned_items 3669→121")
    else:
        print(f"{_LOG} шаг 1 пропущен: узел 3669 и/или 121 не найден/не совпал")

    # --- Шаг 2: reparent 3670 «Закупка компьютеров» 3669 → 121 ---
    if _check_node(bind, 3670, _EXPECTED_NAMES[3670]) and _check_node(bind, 121, _EXPECTED_NAMES[121]):
        current_parent = bind.execute(sa.text(
            "SELECT parent_id FROM feo_categories WHERE id = 3670"
        )).scalar()
        if current_parent == 3669:
            bind.execute(sa.text("UPDATE feo_categories SET parent_id = 121 WHERE id = 3670"))
            print(f"{_LOG} шаг 2: узел 3670 перепривязан 3669→121")
        elif current_parent == 121:
            print(f"{_LOG} шаг 2: узел 3670 уже привязан к 121 — пропуск (идемпотентность)")
        else:
            print(f"{_LOG} шаг 2 пропущен: у узла 3670 parent_id={current_parent}, не 3669 и не 121")
    else:
        print(f"{_LOG} шаг 2 пропущен: узел 3670 и/или 121 не найден/не совпал")

    # --- Шаг 3: wishes 3718 → 3719 ---
    if _check_node(bind, 3718, _EXPECTED_NAMES[3718]) and _check_node(bind, 3719, _EXPECTED_NAMES[3719]):
        result = bind.execute(sa.text(
            "UPDATE wishes SET feo_category_id = 3719 WHERE feo_category_id = 3718"
        ))
        print(f"{_LOG} шаг 3: перенесено {result.rowcount} строк wishes 3718→3719")
    else:
        print(f"{_LOG} шаг 3 пропущен: узел 3718 и/или 3719 не найден/не совпал")

    # --- Шаг 4: удаление опустевших узлов строго в этом порядке ---
    fk_columns = _discover_fk_columns(bind)
    for node_id in (3718, 4624, 3669, 3668, 10):
        _safe_delete(bind, fk_columns, node_id)


def downgrade() -> None:
    # Осознанный no-op: восстановить удалённые id (3718, 4624, 3669, 3668, 10)
    # с теми же значениями нельзя — DELETE необратим, а auto-increment
    # последовательности feo_categories.id уже могли уйти вперёд. Резервная
    # копия базы перед этой миграцией снята на сервере:
    # /root/backups/feo_before_merge_20260902.sql — восстановление, если
    # понадобится, делается оттуда вручную, не через alembic downgrade.
    pass
