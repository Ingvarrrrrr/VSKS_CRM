"""
Шаблонизатор и markdown-парсер для сборщика правовых документов GALA.

Отвечает за две вещи:
1. Подстановки `{{путь.через.точку}}` (и `{{#each ...}}`) из operator.json в
   markdown-исходник — см. `legal/CONTRACT.md`, раздел «Язык шаблонов».
2. Разбор получившегося markdown в простое дерево узлов (AST), которое затем
   рендерят и render_html() (для frontend/src/legal/documents.generated.ts),
   и legal/render_docx.py (для .docx).

Единый AST для HTML и docx — чтобы структура документа не расходилась между
двумя выходами (ПРАВИЛО №6): формат данных один, отрисовщиков два.
"""
from __future__ import annotations

import html
import re
from datetime import date
from typing import Any


class BuildError(Exception):
    """Ошибка сборки — неизвестная подстановка, битый шаблон и т.п."""


_RU_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_today() -> str:
    d = date.today()
    return f"{d.day} {_RU_MONTHS[d.month - 1]} {d.year} г."


# ---------------------------------------------------------------------------
# Фильтр |short — сокращение ФИО до «Фамилия И.О.», идемпотентно.
# ---------------------------------------------------------------------------

_SHORT_FIO_RE = re.compile(r"^(\S+)\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.$")


def short_fio(value: str) -> str:
    value = value.strip()
    m = _SHORT_FIO_RE.match(value)
    if m:
        # Уже сокращено — нормализуем пробел между инициалами и возвращаем как есть.
        return f"{m.group(1)} {m.group(2)}.{m.group(3)}."
    parts = value.split()
    if len(parts) < 2:
        # Не похоже на «Фамилия Имя Отчество» (например, ещё не заполненный
        # плейсхолдер operator.json) — возвращаем без изменений.
        return value
    surname, rest = parts[0], parts[1:]
    initials = "".join(f"{p[0].upper()}." for p in rest if p)
    return f"{surname} {initials}"


_FILTERS = {"short": short_fio}


# ---------------------------------------------------------------------------
# Подстановки {{path}} / {{path|filter}} и блоки {{#each path}}...{{/each}}
# ---------------------------------------------------------------------------

_EACH_RE = re.compile(r"\{\{#each\s+([\w.]+)\s*\}\}(.*?)\{\{/each\}\}", re.DOTALL)
_TOKEN_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _resolve_path(context: dict[str, Any], path: str) -> Any:
    cur: Any = context
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _expand_each(text: str, context: dict[str, Any], doc_label: str) -> str:
    def repl(m: re.Match[str]) -> str:
        path, body = m.group(1), m.group(2)
        try:
            items = _resolve_path(context, path)
        except KeyError:
            raise BuildError(
                f"Неизвестная подстановка «{{{{#each {path}}}}}» в документе {doc_label}"
            )
        if not isinstance(items, list):
            raise BuildError(
                f"«{{{{#each {path}}}}}» в документе {doc_label} указывает не на список"
            )
        # Плейсхолдер текущего элемента внутри блока — поддержаны оба
        # распространённых варианта записи ({{.}} и {{this}}), чтобы источники
        # public/ и internal/ (их пишут разные исполнители параллельно) не
        # были обязаны совпадать по соглашению об имени.
        def render_item(item: Any) -> str:
            return body.replace("{{.}}", str(item)).replace("{{this}}", str(item))

        return "".join(render_item(item) for item in items)

    return _EACH_RE.sub(repl, text)


def _substitute(text: str, context: dict[str, Any], doc_label: str) -> str:
    def repl(m: re.Match[str]) -> str:
        expr = m.group(1)
        if "|" in expr:
            path, filt = (p.strip() for p in expr.split("|", 1))
        else:
            path, filt = expr, None
        try:
            value = _resolve_path(context, path)
        except KeyError:
            raise BuildError(
                f"Неизвестная подстановка «{{{{{expr}}}}}» в документе {doc_label}"
            )
        if isinstance(value, (dict, list)):
            raise BuildError(
                f"Подстановка «{{{{{expr}}}}}» в документе {doc_label} указывает "
                "на составное значение (список/объект), а не на текст"
            )
        text_value = str(value)
        if filt:
            fn = _FILTERS.get(filt)
            if fn is None:
                raise BuildError(
                    f"Неизвестный фильтр «{filt}» в документе {doc_label} ({{{{{expr}}}}})"
                )
            text_value = fn(text_value)
        return text_value

    return _TOKEN_RE.sub(repl, text)


def render_template(
    source_text: str,
    operator: dict[str, Any],
    doc_meta: dict[str, str],
    doc_label: str,
) -> str:
    """Подставляет значения operator.json + doc.* + today в markdown-исходник."""
    context: dict[str, Any] = dict(operator)
    context["doc"] = doc_meta
    context["today"] = format_today()
    text = _expand_each(source_text, context, doc_label)
    text = _substitute(text, context, doc_label)
    return text


# ---------------------------------------------------------------------------
# Мини-markdown -> AST. Поддержаны: ##/### заголовки, абзацы, - / * списки,
# 1. нумерованные списки, > цитаты, **bold** внутри строк.
# ---------------------------------------------------------------------------

Span = tuple[str, bool]  # (текст, bold)
Node = tuple[str, Any]

_BOLD_RE = re.compile(r"(\*\*[^*]+\*\*)")
_UL_RE = re.compile(r"^[-*]\s+")
_OL_RE = re.compile(r"^\d+\.\s+")


def parse_inline(line: str) -> list[Span]:
    spans: list[Span] = []
    for part in _BOLD_RE.split(line):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            spans.append((part[2:-2], True))
        else:
            spans.append((part, False))
    return spans


def parse_markdown(text: str) -> list[Node]:
    lines = text.split("\n")
    nodes: list[Node] = []
    para_buffer: list[str] = []

    def flush_para() -> None:
        if not para_buffer:
            return
        joined = " ".join(l.strip() for l in para_buffer if l.strip())
        if joined:
            nodes.append(("p", parse_inline(joined)))
        para_buffer.clear()

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        if stripped.startswith("### "):
            flush_para()
            nodes.append(("h3", parse_inline(stripped[4:].strip())))
            i += 1
            continue
        if stripped.startswith("## "):
            flush_para()
            nodes.append(("h2", parse_inline(stripped[3:].strip())))
            i += 1
            continue
        if stripped.startswith("# "):
            flush_para()
            nodes.append(("h2", parse_inline(stripped[2:].strip())))
            i += 1
            continue
        if stripped.startswith("> "):
            flush_para()
            nodes.append(("blockquote", parse_inline(stripped[2:].strip())))
            i += 1
            continue
        if _UL_RE.match(stripped):
            flush_para()
            items: list[list[Span]] = []
            while i < n and _UL_RE.match(lines[i].strip()):
                items.append(parse_inline(_UL_RE.sub("", lines[i].strip(), count=1)))
                i += 1
            nodes.append(("ul", items))
            continue
        if _OL_RE.match(stripped):
            flush_para()
            items = []
            while i < n and _OL_RE.match(lines[i].strip()):
                items.append(parse_inline(_OL_RE.sub("", lines[i].strip(), count=1)))
                i += 1
            nodes.append(("ol", items))
            continue
        para_buffer.append(lines[i])
        i += 1

    flush_para()
    return nodes


# ---------------------------------------------------------------------------
# AST -> HTML. Всё текстовое содержимое (и статичный markdown, и подставленные
# значения) экранируется html.escape — литеральный "<script>" в исходнике или
# в operator.json не может превратиться в тег.
# ---------------------------------------------------------------------------


def _render_spans(spans: list[Span]) -> str:
    out = []
    for text, bold in spans:
        escaped = html.escape(text, quote=False)
        out.append(f"<strong>{escaped}</strong>" if bold else escaped)
    return "".join(out)


def render_html(nodes: list[Node]) -> str:
    parts: list[str] = []
    for kind, payload in nodes:
        if kind in ("h2", "h3", "p", "blockquote"):
            tag = {"blockquote": "blockquote"}.get(kind, kind)
            parts.append(f"<{tag}>{_render_spans(payload)}</{tag}>")
        elif kind in ("ul", "ol"):
            items = "".join(f"<li>{_render_spans(sp)}</li>" for sp in payload)
            parts.append(f"<{kind}>{items}</{kind}>")
        else:  # pragma: no cover - защитная ветка на случай нового типа узла
            raise BuildError(f"Неизвестный тип узла markdown: {kind}")
    return "".join(parts)
