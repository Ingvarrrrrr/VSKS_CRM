"""
Простейший слой работы с базой данных на SQLite
для хранения ФЭО и связанных справочников.

Цель: заменить временное хранение в Excel на локальную БД,
которую потом можно будет мигрировать в PostgreSQL.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, List, Optional

DB_FILE = Path(__file__).with_name("crm_local.db")


@contextmanager
def get_conn():
    """Контекстный менеджер подключения к SQLite."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Инициализация схемы БД (создание таблиц, если их нет)."""
    with get_conn() as conn:
        cur = conn.cursor()

        # Группы ФЭО (ФАДМ, МИНПРОСВЕТ, ЗО и т.п.)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feo_group (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL UNIQUE,
                name        TEXT NOT NULL
            )
            """
        )

        # Направления расходования ФЭО
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feo_direction (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id    INTEGER NOT NULL REFERENCES feo_group(id),
                name        TEXT NOT NULL,
                UNIQUE (group_id, name)
            )
            """
        )

        # Статьи затрат (наименование статей)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feo_cost_item (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id    INTEGER NOT NULL REFERENCES feo_group(id),
                name        TEXT NOT NULL,
                -- дополнительные поля (unit, plan_price) добавляются отдельно через ALTER TABLE
                UNIQUE (group_id, name)
            )
            """
        )

        # Обеспечиваем наличие колонок unit и plan_price без потери данных
        try:
            cur.execute("ALTER TABLE feo_cost_item ADD COLUMN unit TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE feo_cost_item ADD COLUMN plan_price REAL")
        except sqlite3.OperationalError:
            pass

        # Связка направление -> допустимые статьи затрат
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feo_direction_cost_item (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                direction_id    INTEGER NOT NULL REFERENCES feo_direction(id),
                cost_item_id    INTEGER NOT NULL REFERENCES feo_cost_item(id),
                UNIQUE (direction_id, cost_item_id)
            )
            """
        )

        # Аналог листа Unique: уникальные позиции / товары / услуги
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS unique_item (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                description     TEXT,
                cost_item_id    INTEGER REFERENCES feo_cost_item(id)
            )
            """
        )

        # Таблица базового ФЭО (по аналогии с WORK, но упрощённо)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feo_base (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id        INTEGER NOT NULL REFERENCES feo_group(id),
                direction_id    INTEGER NOT NULL REFERENCES feo_direction(id),
                cost_item_id    INTEGER NOT NULL REFERENCES feo_cost_item(id),
                quantity        REAL,
                unit            TEXT,
                amount          REAL,
                extra_json      TEXT    -- доп.колонки из WORK можно складывать сюда в виде JSON
            )
            """
        )

        # Предзаполняем группы, если их ещё нет
        seed_groups = [
            ("FADM", "ФАДМ"),
            ("MINPROSVET", "Минпросвет"),
            ("ZO", "Здравоохранение"),
            ("HO", "Хозяйственные нужды"),
            ("DNR", "ДНР"),
            ("LNR", "ЛНР"),
            ("MINTRUD", "Минтруд"),
            ("KOS", "КОС"),
        ]
        cur.executemany(
            """
            INSERT OR IGNORE INTO feo_group (code, name)
            VALUES (?, ?)
            """,
            seed_groups,
        )


def get_groups() -> List[sqlite3.Row]:
    """Список групп ФЭО (для вкладок)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, code, name FROM feo_group ORDER BY id")
        return cur.fetchall()


def get_group_id_by_code(code: str) -> Optional[int]:
    """Получение ID группы ФЭО по коду (например, 'ZO', 'FADM')."""
    code = (code or "").strip().upper()
    if not code:
        return None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM feo_group WHERE UPPER(code) = ?",
            (code,),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None


def get_directions_by_group(group_id: int) -> List[sqlite3.Row]:
    """Список направлений ФЭО по группе."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name
            FROM feo_direction
            WHERE group_id = ?
            ORDER BY name
            """,
            (group_id,),
        )
        return cur.fetchall()


def get_cost_items_for_direction(direction_id: int) -> List[sqlite3.Row]:
    """Список статей затрат, допустимых для выбранного направления."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ci.id, ci.name
            FROM feo_cost_item ci
            JOIN feo_direction_cost_item link
                ON link.cost_item_id = ci.id
            WHERE link.direction_id = ?
            ORDER BY ci.name
            """,
            (direction_id,),
        )
        return cur.fetchall()


def get_cost_item_details(cost_item_id: int) -> Optional[sqlite3.Row]:
    """Получение единицы измерения и плановой цены для статьи затрат."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, group_id, name, unit, plan_price
            FROM feo_cost_item
            WHERE id = ?
            """,
            (cost_item_id,),
        )
        row = cur.fetchone()
        return row


def get_unique_items_for_cost_item(cost_item_id: int) -> List[sqlite3.Row]:
    """Элементы из Unique, связанные с конкретной статьёй затрат."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description
            FROM unique_item
            WHERE cost_item_id = ?
            ORDER BY name
            """,
            (cost_item_id,),
        )
        return cur.fetchall()


def get_all_unique_items() -> List[sqlite3.Row]:
    """Все элементы Unique (когда нет привязки к конкретной статье затрат)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description
            FROM unique_item
            ORDER BY name
            """
        )
        return cur.fetchall()


def upsert_direction(group_id: int, name: str) -> int:
    """Создание/поиск направления ФЭО внутри группы."""
    name = name.strip()
    if not name:
        raise ValueError("Пустое название направления ФЭО")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id FROM feo_direction
            WHERE group_id = ? AND name = ?
            """,
            (group_id, name),
        )
        row = cur.fetchone()
        if row:
            return int(row["id"])
        cur.execute(
            """
            INSERT INTO feo_direction (group_id, name)
            VALUES (?, ?)
            """,
            (group_id, name),
        )
        return int(cur.lastrowid)


def upsert_cost_item(group_id: int, name: str) -> int:
    """Создание/поиск статьи затрат внутри группы."""
    name = name.strip()
    if not name:
        raise ValueError("Пустое наименование статьи затрат")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id FROM feo_cost_item
            WHERE group_id = ? AND name = ?
            """,
            (group_id, name),
        )
        row = cur.fetchone()
        if row:
            return int(row["id"])
        cur.execute(
            """
            INSERT INTO feo_cost_item (group_id, name)
            VALUES (?, ?)
            """,
            (group_id, name),
        )
        return int(cur.lastrowid)


def update_cost_item_details(cost_item_id: int, unit: Optional[str], plan_price: Optional[float]) -> None:
    """Обновление единицы измерения и плановой цены для статьи затрат."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE feo_cost_item
            SET unit = COALESCE(?, unit),
                plan_price = COALESCE(?, plan_price)
            WHERE id = ?
            """,
            (unit, plan_price, cost_item_id),
        )


def link_direction_to_cost_items(direction_id: int, cost_item_ids: Iterable[int]) -> None:
    """Задать (или дополнить) допустимые статьи затрат для направления."""
    ids = list(cost_item_ids)
    if not ids:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT OR IGNORE INTO feo_direction_cost_item (direction_id, cost_item_id)
            VALUES (?, ?)
            """,
            [(direction_id, cid) for cid in ids],
        )


def add_unique_item(name: str, description: str = "", cost_item_id: Optional[int] = None) -> int:
    """Добавление записи в аналог листа Unique."""
    name = name.strip()
    if not name:
        raise ValueError("Пустое название элемента Unique")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO unique_item (name, description, cost_item_id)
            VALUES (?, ?, ?)
            """,
            (name, description or "", cost_item_id),
        )
        return int(cur.lastrowid)


def reset_all_data() -> None:
    """
    Полная очистка рабочих таблиц (без удаления групп).
    Удобно при повторном импорте из сметы.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM feo_base")
        cur.execute("DELETE FROM unique_item")
        cur.execute("DELETE FROM feo_direction_cost_item")
        cur.execute("DELETE FROM feo_cost_item")
        cur.execute("DELETE FROM feo_direction")

