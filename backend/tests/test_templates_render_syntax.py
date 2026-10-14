# -*- coding: utf-8 -*-
"""Страж синтаксиса шаблонов (14.10.2026): каждый backend/templates/*.docx
обязан пройти docxtpl-рендер на пустом контексте БЕЗ TemplateSyntaxError.

Повод: service_note_delivery.docx падал `TemplateSyntaxError: Encountered
unknown tag 'tr'` на ЛЮБОМ render() — причина была структурной (строки-теги
{%tr for item in items %} / {%tr endfor %} лежали СНАРУЖИ <w:tbl> вместо
того, чтобы быть содержимым строк таблицы — docxtpl превращает такой тег в
`{% for %}`/`{% endfor %}` только когда он внутри <w:tr>; снаружи текст
доходит до Jinja2 как литеральный неизвестный тег «tr»). Починено
patch_offbuild.py::_fix_service_note_delivery_tr_placement. До этого дефект
был явно задокументирован как allowlist-исключение в
test_template_vars_all_defined.py — этот страж не даёт ему вернуться молча
(ни в этом файле, ни в любом другом .docx).

Намеренно проверяет ТОЛЬКО TemplateSyntaxError — отсутствие переменной в
контексте (UndefinedError) это другой класс дефекта, уже под охраной
test_template_vars_all_defined.py (сверяет корневые переменные разметки с
TEMPLATE_VARIABLES). Пустой контекст здесь — минимальный: он обязан
долистать XML→Jinja2-компиляцию, а не фактически напечатать документ.

Запускать внутри контейнера (docxtpl только там, backend/templates
смонтирован по тому же пути) — как смежные test_template_vars_all_defined.py
/ test_template_variables_complete.py.
"""
import os

import pytest

TEMPLATES_DIR = "/app/templates"

# Служебные/не-шаблонные файлы — пропускаем явно, с причиной, не молча.
_SKIP_FILES = {
    # Office lock-файл (создаётся при открытом документе), не настоящий .docx.
    "~$роший вариант листа согласования.docx": "office lock-файл, не содержимое",
    # Справочный шаблон «Руководство по разметке» для авторов шаблонов —
    # иллюстративные {{ x }}/{% for item in ... %} с несуществующими
    # переменными НАМЕРЕННО (это сам пример синтаксиса, не рабочий документ).
    # Синтаксис валиден (TemplateSyntaxError не будет), но рендер падает на
    # UndefinedError — другой класс дефекта, вне предмета этого стража.
    "ШАБЛОН_ПЕРЕМЕННЫЕ.docx": "справочный пример разметки, не рабочий шаблон",
}


def _iter_docx_files():
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        if fname.endswith(".docx"):
            yield fname


@pytest.mark.parametrize("fname", list(_iter_docx_files()))
def test_template_renders_without_syntax_error(fname):
    if fname in _SKIP_FILES:
        pytest.skip(_SKIP_FILES[fname])

    from docxtpl import DocxTemplate
    from jinja2 import TemplateSyntaxError

    path = os.path.join(TEMPLATES_DIR, fname)
    tpl = DocxTemplate(path)
    try:
        tpl.render({})
    except TemplateSyntaxError as e:
        pytest.fail(
            f"{fname}: TemplateSyntaxError на пустом контексте: {e}. "
            "Частая причина — {%tr/{%p/{%cellbg ...%} тег лежит СНАРУЖИ "
            "своей строки/параграфа/ячейки таблицы, а не внутри неё "
            "(docxtpl разворачивает такие теги только изнутри <w:tr>/<w:p>/"
            "<w:tc> — см. patch_offbuild.py::"
            "_fix_service_note_delivery_tr_placement как образец фикса)."
        )
    except Exception:
        # Любая другая ошибка (например, UndefinedError из-за отсутствующей
        # в context переменной) — не предмет этого стража, см. docstring.
        pass
