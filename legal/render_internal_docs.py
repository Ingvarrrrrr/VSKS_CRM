"""Запись backend/app/services/legal_internal_docs_generated.py — HTML
внутренних документов (kind == "internal") для закрытого раздела
«Документы» админки (решение владельца 08.10.2026, см. legal/README.md).

Выделено из legal/build.py (ПРАВИЛО №5 — build.py отвечает за оркестрацию
сборки public/internal документов и docx, этот модуль — только за запись
одного конкретного generated-файла, по аналогии с render_docx.py).

Единственный читатель сгенерированного файла —
backend/app/services/internal_legal_docs.py (ПРАВИЛО №6: список и
содержимое внутренних документов не дублируются больше нигде в backend/).
"""
from __future__ import annotations

import json
from pathlib import Path


def _py_string(value: str) -> str:
    # json.dumps даёт валидный питоновский строковый литерал (двойные кавычки,
    # корректное экранирование) — та же техника, что для TS в build.py.
    return json.dumps(value, ensure_ascii=False)


def write_internal_docs_py(internal_py_path: Path, internal_records: list[dict]) -> None:
    """internal_records — список {slug, title, version, effective_date, html}
    в порядке operator.json (порядок появления документов = порядок
    отображения списка в админке, без сортировки по slug)."""
    lines: list[str] = [
        "\"\"\"СГЕНЕРИРОВАНО legal/build.py — не редактировать руками.",
        "",
        "Источник данных: legal/operator.json (блок documents, kind == \"internal\")",
        "и legal/sources/internal/*.md. Внутренние документы (модель угроз, акт",
        "уровня защищённости, уведомление РКН и т. п.) — закрытый раздел",
        "«Документы» админки, не публичная статика (решение владельца",
        "08.10.2026, legal/README.md). Читает этот файл только",
        "backend/app/services/internal_legal_docs.py — он и есть единственный",
        "реестр внутренних документов для backend (ПРАВИЛО №6).",
        "",
        "Пересобрать: python legal/build.py",
        "\"\"\"",
        "from __future__ import annotations",
        "",
        "INTERNAL_LEGAL_DOCS: tuple[dict[str, str], ...] = (",
    ]
    for r in internal_records:
        lines.append("    {")
        lines.append(f"        \"slug\": {_py_string(r['slug'])},")
        lines.append(f"        \"title\": {_py_string(r['title'])},")
        lines.append(f"        \"version\": {_py_string(r['version'])},")
        lines.append(f"        \"effective_date\": {_py_string(r['effective_date'])},")
        lines.append(f"        \"html\": {_py_string(r['html'])},")
        lines.append("    },")
    lines.append(")")
    lines.append("")

    internal_py_path.parent.mkdir(parents=True, exist_ok=True)
    internal_py_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
