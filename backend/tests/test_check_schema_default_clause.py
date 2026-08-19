"""Unit-тесты для _col_default_clause (backend/check_schema.py).

Инцидент деплоя 2026-08-19: `check_schema.py --apply`, который автодеплой
запускает ДО старта бэкенда, упал на `ALTER TABLE payments ADD COLUMN
IF NOT EXISTS payment_source VARCHAR(20) DEFAULT manual NOT NULL;` —
голая Python-строка server_default='manual' подставлялась в SQL без
кавычек, и Postgres принял `manual` за ссылку на несуществующую колонку
(asyncpg.exceptions.FeatureNotSupportedError: cannot use column reference
in DEFAULT expression). Эти тесты — чистые функции, живой БД не требуют.
"""
from sqlalchemy import Column, String, Boolean, Integer, text

from check_schema import _col_default_clause, _is_sql_expression, _quote_default_literal


# === _col_default_clause: server_default ===

def test_string_server_default_gets_quoted():
    """Ровно кейс инцидента: server_default='manual' → DEFAULT 'manual', не DEFAULT manual."""
    col = Column(
        "payment_source", String(20),
        nullable=False, default="manual", server_default="manual",
    )
    assert _col_default_clause(col) == " DEFAULT 'manual'"


def test_string_server_default_with_apostrophe_is_escaped():
    col = Column("note", String(50), server_default="O'Brien")
    assert _col_default_clause(col) == " DEFAULT 'O''Brien'"


def test_text_expression_server_default_is_not_quoted():
    """text("now()") — валидное SQL-выражение, кавычить нельзя."""
    col = Column("created_at", String(20), server_default=text("now()"))
    assert _col_default_clause(col) == " DEFAULT now()"


def test_keyword_string_server_default_is_not_quoted():
    """server_default='false' (как в Payment.confirmed_by_statement) — SQL-ключевое
    слово, а не строковый литерал: должно остаться DEFAULT false, без кавычек."""
    col = Column(
        "confirmed_by_statement", Boolean,
        nullable=False, default=False, server_default="false",
    )
    assert _col_default_clause(col) == " DEFAULT false"


def test_numeric_string_server_default_is_not_quoted():
    col = Column("retries", Integer, server_default="0")
    assert _col_default_clause(col) == " DEFAULT 0"


# === _col_default_clause: Python-side default (col.default) ===

def test_python_side_bool_default_renders_true_false():
    assert _col_default_clause(Column("flag", Boolean, default=True)) == " DEFAULT TRUE"
    assert _col_default_clause(Column("flag2", Boolean, default=False)) == " DEFAULT FALSE"


def test_python_side_number_default_rendered_as_is():
    assert _col_default_clause(Column("retries2", Integer, default=3)) == " DEFAULT 3"


def test_python_side_string_default_is_quoted_and_escaped():
    col = Column("status", String(20), default="it's fine")
    assert _col_default_clause(col) == " DEFAULT 'it''s fine'"


# === helpers ===

def test_is_sql_expression():
    assert _is_sql_expression("now()")
    assert _is_sql_expression("TRUE")
    assert _is_sql_expression("CURRENT_TIMESTAMP")
    assert _is_sql_expression("42")
    assert _is_sql_expression("-3.5")
    assert not _is_sql_expression("manual")
    assert not _is_sql_expression("statement")


def test_quote_default_literal():
    assert _quote_default_literal("manual") == "'manual'"
    assert _quote_default_literal("O'Brien") == "'O''Brien'"
    assert _quote_default_literal("now()") == "now()"
