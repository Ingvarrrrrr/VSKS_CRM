# -*- coding: utf-8 -*-
"""Баг 2026-09-29 (РЕЕ-2026-00960, файл id=54, purchase_files.py:727 до правки):
GET /api/purchases/{id}/files/{fid}/view на файле с кириллическим/эмодзи именем
("Gmail - Чек + (1) подарок. 6 510,00 ₽.pdf") падал 500 UnicodeEncodeError —
Starlette кодирует значения заголовков в latin-1, а голый f'inline;
filename="{pf.filename}"' совал туда кириллицу как есть.

Тест воспроизводит РОВНО тот шаг, что падал (Starlette Headers.encode('latin-1')
в responses.py::init_headers) — не мокает его."""
from app.utils.http import content_disposition

CYRILLIC_NAME = 'Gmail - Чек + (1) подарок. 6 510,00 ₽.pdf'


def test_old_naive_pattern_reproduces_the_original_bug():
    """Контроль: подтверждаем, что баг реален — голый f-string с кириллицей
    в latin-1 заголовке действительно падает (та же операция, что Starlette
    делает при отправке ответа)."""
    naive_header = f'inline; filename="{CYRILLIC_NAME}"'
    try:
        naive_header.encode('latin-1')
        raise AssertionError('ожидался UnicodeEncodeError на наивном заголовке')
    except UnicodeEncodeError:
        pass


def test_content_disposition_inline_is_latin1_safe():
    header = content_disposition(CYRILLIC_NAME, 'inline')
    header.encode('latin-1')  # не должно бросать — это и есть сам баг/фикс
    assert header.startswith('inline; filename="')
    assert "filename*=UTF-8''" in header


def test_content_disposition_attachment_default_is_latin1_safe():
    header = content_disposition(CYRILLIC_NAME)
    header.encode('latin-1')
    assert header.startswith('attachment; filename="')


def test_content_disposition_ascii_fallback_has_no_cyrillic():
    """ascii_fallback (первая часть, до filename*=) обязана быть чистым ASCII —
    иначе .encode('latin-1') выше просто случайно бы не упал на этих байтах,
    не доказывая, что fallback действительно безопасен."""
    header = content_disposition(CYRILLIC_NAME, 'inline')
    fallback_part = header.split('; filename*=')[0]
    fallback_part.encode('ascii')  # бросит сам, если внутри осталась кириллица


def test_content_disposition_pure_ascii_name_unchanged_shape():
    header = content_disposition('invoice.pdf')
    assert header == 'attachment; filename="invoice.pdf"; filename*=UTF-8\'\'invoice.pdf'
