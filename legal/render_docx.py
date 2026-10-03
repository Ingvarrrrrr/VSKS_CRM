"""
AST -> .docx для сборщика правовых документов GALA.

Принимает то же дерево узлов, что render_md.render_html() (см. render_md.py),
и строит документ python-docx. Отдельная функция для внутренних документов
добавляет шапку организации и место для номера/даты/подписи — как требует
CONTRACT.md.

save_docx_deterministic() решает главную практическую проблему python-docx:
save() кладёт в каждую запись ZIP-архива текущее время (posix mtime с точностью
до секунды), поэтому два запуска сборки в разные секунды дают разные байты
файла, даже если содержимое документа не изменилось. Раздел docProps/core.xml
при этом НЕ трогается python-docx автоматически (created/modified — фиксированные
значения из встроенного шаблона), проверено эмпирически при разработке. Чтобы
получить байт-идентичный .docx независимо от времени запуска, после save()
архив перепаковывается с фиксированной датой у каждой записи.
"""
from __future__ import annotations

import io
import zipfile
from typing import Any

from docx import Document
from docx.document import Document as DocumentType

Node = tuple[str, Any]


def _add_spans(paragraph: Any, spans: list[tuple[str, bool]]) -> None:
    if not spans:
        return
    for text, bold in spans:
        run = paragraph.add_run(text)
        run.bold = bold


def _render_body(document: DocumentType, nodes: list[Node]) -> None:
    for kind, payload in nodes:
        if kind == "h2":
            p = document.add_heading("", level=1)
            _add_spans(p, payload)
        elif kind == "h3":
            p = document.add_heading("", level=2)
            _add_spans(p, payload)
        elif kind == "p":
            p = document.add_paragraph()
            _add_spans(p, payload)
        elif kind == "blockquote":
            p = document.add_paragraph(style="Intense Quote")
            _add_spans(p, payload)
        elif kind == "ul":
            for spans in payload:
                p = document.add_paragraph(style="List Bullet")
                _add_spans(p, spans)
        elif kind == "ol":
            for spans in payload:
                p = document.add_paragraph(style="List Number")
                _add_spans(p, spans)


def build_public_docx(title: str, nodes: list[Node]) -> DocumentType:
    document = Document()
    document.core_properties.title = title
    document.add_heading(title, level=0)
    _render_body(document, nodes)
    return document


def build_internal_docx(title: str, nodes: list[Node], operator: dict[str, Any]) -> DocumentType:
    document = Document()
    document.core_properties.title = title

    op = operator.get("operator", {})
    head = operator.get("head", {})

    letterhead = document.add_paragraph()
    letterhead.add_run(f"{op.get('form', '')} «{op.get('short_name', '')}»").bold = True
    document.add_paragraph(f"ИНН {op.get('inn', '')}  ОГРН {op.get('ogrn', '')}")
    document.add_paragraph(op.get("legal_address", ""))
    document.add_paragraph("№ ______________ от «____» _____________ 20___ г.")

    document.add_heading(title, level=0)
    _render_body(document, nodes)

    document.add_paragraph("")
    sig = document.add_paragraph()
    sig.add_run(f"{head.get('position', '')}").bold = False
    sig.add_run("   _______________   / " + head.get("fio", "") + " /")

    return document


def _freeze_zip(data: bytes) -> bytes:
    """Перепаковывает .docx (это ZIP) с фиксированными датами записей."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(src.namelist()):
            payload = src.read(name)
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, payload)
    return out.getvalue()


def save_docx_deterministic(document: DocumentType, path: Any) -> None:
    buf = io.BytesIO()
    document.save(buf)
    frozen = _freeze_zip(buf.getvalue())
    with open(path, "wb") as f:
        f.write(frozen)
