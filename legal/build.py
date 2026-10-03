#!/usr/bin/env python3
"""
Сборщик правовых документов GALA. Контракт — legal/CONTRACT.md.

Читает legal/operator.json (единственный источник реквизитов и версий —
ПРАВИЛО №6), рендерит markdown из legal/sources/{public,internal}/*.md и
пишет:
  - frontend/src/legal/documents.generated.ts — только kind == "public",
    интерфейс LegalDoc/LEGAL_DOCS/LEGAL_DOC_LIST/LEGAL_VERSION/OPERATOR
    (см. CONTRACT.md);
  - backend/app/services/legal_generated.py — константы, нужные бэкенду
    (сроки 152-ФЗ из deadlines_working_days, перечень документов согласия
    для регистрации). Бэкендовский образ собирается из каталога backend/ и
    не видит legal/operator.json (см. CONTRACT.md) — этот файл едет в образ
    вместе с остальным кодом, поэтому backend/app/services/legal_constants.py
    больше не читает JSON с диска;
  - legal/out/<slug>.docx — все документы, публичные и внутренние.

Использование:
    python legal/build.py            # собрать
    python legal/build.py --check    # собрать во временную папку и сверить
                                      # с тем, что уже лежит в репозитории;
                                      # код возврата 1, если отличается
                                      # (для CI/pre-commit)

Сборка идемпотентна: повторный запуск без изменений исходников даёт
байт-идентичные файлы (проверяется sha256; см. legal/README.md).
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

# Позволяет запускать `python legal/build.py` из любого cwd — соседние модули
# render_md.py / render_docx.py всегда рядом с этим файлом, а не с cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_docx import build_internal_docx, build_public_docx, save_docx_deterministic  # noqa: E402
from render_md import BuildError, parse_markdown, render_html, render_template  # noqa: E402

LEGAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = LEGAL_DIR.parent
OPERATOR_PATH = LEGAL_DIR / "operator.json"
OUT_DIR = LEGAL_DIR / "out"
TS_OUT_PATH = REPO_ROOT / "frontend" / "src" / "legal" / "documents.generated.ts"
PY_OUT_PATH = REPO_ROOT / "backend" / "app" / "services" / "legal_generated.py"

# Перечень slug публичных документов, на согласие с которыми пользователь
# ставит ОДИН флажок при регистрации (backend/app/routers/organizations.py,
# POST /api/register). Это подмножество kind == "public" — оферта и cookies
# не запрашиваются отдельным согласием при регистрации. В operator.json такого
# флага нет (это решение процесса регистрации, а не реквизит оператора), поэтому
# перечень живёт здесь и уезжает в legal_generated.py при сборке — единственное
# место в репозитории, где он записан (ПРАВИЛО №6).
REGISTRATION_CONSENT_SLUGS: tuple[str, ...] = ("privacy", "consent")


def load_operator() -> dict:
    with open(OPERATOR_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _compute_legal_version(public_records: list[dict]) -> str:
    """Версия всего комплекта публичных документов — для фиксации факта согласия.

    Не отдельное поле в operator.json (это было бы вторым источником истины
    поверх версий отдельных документов, ПРАВИЛО №6): детерминированно
    вычисляется из slug:version каждого публичного документа, отсортированных
    по slug. Меняется, как только меняется версия любого из документов.
    """
    return "+".join(f"{r['slug']}:{r['version']}" for r in sorted(public_records, key=lambda r: r["slug"]))


def _ts_string(value: str) -> str:
    # json.dumps даёт валидный TS/JS строковый литерал (двойные кавычки),
    # корректно экранируя обратные слэши, кавычки и юникод — без риска
    # столкнуться с обратными кавычками/${...} внутри html.
    return json.dumps(value, ensure_ascii=False)


_PLACEHOLDER_RE = re.compile(r"^\{\{.*\}\}$")


def _op_value(value: str) -> str:
    """Значение реквизита оператора для экспорта в TS.

    Поле ещё не заполнено в operator.json, если всё его значение целиком —
    плейсхолдер вида `{{ИНН}}` (ПРАВИЛО №6: такие поля существуют только для
    оферты/внутренних документов юрлица и не должны утекать на публичные
    страницы как буквальный текст `{{...}}`). Экспортируем пустую строку —
    фронт (LegalFooter.vue и т.п.) уже умеет скрывать пустые поля через `v-if`.
    """
    if isinstance(value, str) and _PLACEHOLDER_RE.match(value.strip()):
        return ""
    return value


def _ts_ident(slug: str) -> str:
    """Безопасный TS-идентификатор для константы документа по его slug."""
    safe = re.sub(r"[^0-9a-zA-Z_]", "_", slug)
    if not safe or safe[0].isdigit():
        safe = f"_{safe}"
    return f"_doc_{safe}"


def build_all(out_root: Path, ts_path: Path, py_path: Path) -> None:
    operator = load_operator()
    docs = operator.get("documents", [])

    out_root.mkdir(parents=True, exist_ok=True)

    # slug публичных документов, на согласие с которыми регистрация ссылается
    # (REGISTRATION_CONSENT_SLUGS), обязан быть опубликован — иначе на фронте
    # появится ссылка на страницу, которой нет в LEGAL_DOCS.
    published_by_slug = {d["slug"]: d.get("published", True) for d in docs if d["kind"] == "public"}
    for slug in REGISTRATION_CONSENT_SLUGS:
        if slug not in published_by_slug:
            raise BuildError(
                f"REGISTRATION_CONSENT_SLUGS ссылается на неизвестный публичный документ «{slug}»"
            )
        if not published_by_slug[slug]:
            raise BuildError(
                f"REGISTRATION_CONSENT_SLUGS ссылается на документ «{slug}», у которого published=false"
            )

    public_records: dict[str, dict] = {}

    for doc in docs:
        slug = doc["slug"]
        kind = doc["kind"]
        title = doc["title"]
        doc_label = f"«{title}» ({slug})"
        source_path = LEGAL_DIR / doc["source"]

        if not source_path.exists():
            if kind == "public":
                raise BuildError(f"Не найден исходник публичного документа {doc_label}: {source_path}")
            # Внутренние документы пишет параллельный исполнитель — их
            # отсутствие на текущий момент не должно ломать сборку публичных.
            print(f"[legal/build] пропуск {doc_label}: нет файла {source_path}", file=sys.stderr)
            continue

        source_text = source_path.read_text(encoding="utf-8")
        doc_meta = {
            "title": title,
            "version": doc.get("version", ""),
            "effective_date": doc.get("effective_date", ""),
            "slug": slug,
            "route": doc.get("route", ""),
        }
        rendered_md = render_template(source_text, operator, doc_meta, doc_label)
        nodes = parse_markdown(rendered_md)

        if kind == "public":
            # published=false (по умолчанию true) — документ не попадает на
            # фронт (LEGAL_DOCS/LEGAL_DOC_LIST), docx собирается всё равно
            # (нужен, например, юристу до публикации). Проверка выше
            # гарантирует, что REGISTRATION_CONSENT_SLUGS на такой slug не
            # ссылается.
            if doc.get("published", True):
                public_records[slug] = {
                    "slug": slug,
                    "route": doc["route"],
                    "title": title,
                    "version": doc_meta["version"],
                    "effectiveDate": doc_meta["effective_date"],
                    "html": render_html(nodes),
                }
            document = build_public_docx(title, nodes)
        elif kind == "internal":
            document = build_internal_docx(title, nodes, operator)
        else:
            raise BuildError(f"Неизвестный kind «{kind}» у документа {doc_label}")

        save_docx_deterministic(document, out_root / f"{slug}.docx")

    _write_ts(ts_path, public_records, docs, operator)
    _write_py(py_path, operator)


def _write_py(py_path: Path, operator: dict) -> None:
    """Пишет backend/app/services/legal_generated.py — константы 152-ФЗ,
    нужные бэкенду, ровно в тех блоках, что реально используются
    (backend/app/services/legal_constants.py). Лишнего из operator.json
    сюда не тащим (сейчас это только deadlines_working_days и перечень
    документов согласия для регистрации) — при появлении новой потребности
    добавлять блок здесь и там, где он реально нужен, а не «на будущее».
    """
    try:
        deadlines = operator["deadlines_working_days"]
    except KeyError as exc:
        raise BuildError(
            "В operator.json отсутствует блок 'deadlines_working_days' — "
            "правовые сроки по 152-ФЗ негде взять."
        ) from exc

    deadline_items = sorted((k, v) for k, v in deadlines.items() if not k.startswith("_"))

    lines: list[str] = [
        "\"\"\"СГЕНЕРИРОВАНО legal/build.py — не редактировать руками.",
        "",
        "Источник данных: legal/operator.json (блок deadlines_working_days) и",
        "legal/build.py (REGISTRATION_CONSENT_SLUGS — перечень документов согласия",
        "для регистрации, это решение процесса регистрации, а не реквизит",
        "оператора, поэтому в operator.json его нет).",
        "",
        "Существует, потому что backend-образ собирается из каталога backend/ и",
        "не видит legal/ (см. legal/CONTRACT.md) — этот файл едет в образ вместе",
        "с остальным кодом. Читает его только",
        "backend/app/services/legal_constants.py.",
        "",
        "Пересобрать: python legal/build.py",
        "\"\"\"",
        "from __future__ import annotations",
        "",
        "DEADLINES_WORKING_DAYS: dict[str, int] = {",
    ]
    for key, value in deadline_items:
        lines.append(f"    {_py_string(key)}: {int(value)!r},")
    lines.append("}")
    lines.append("")
    lines.append("REGISTRATION_CONSENT_DOCUMENTS: tuple[str, ...] = (")
    for slug in REGISTRATION_CONSENT_SLUGS:
        lines.append(f"    {_py_string(slug)},")
    lines.append(")")
    lines.append("")

    py_path.parent.mkdir(parents=True, exist_ok=True)
    py_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _py_string(value: str) -> str:
    # json.dumps даёт валидный питоновский строковый литерал (двойные кавычки,
    # корректное экранирование) — так же, как _ts_string для TS.
    return json.dumps(value, ensure_ascii=False)


def _write_ts(ts_path: Path, public_records: dict[str, dict], all_docs: list[dict], operator: dict) -> None:
    order = [d["slug"] for d in all_docs if d["kind"] == "public"]
    ordered = [public_records[s] for s in order if s in public_records]
    legal_version = _compute_legal_version(ordered)

    op = operator.get("operator", {})
    site = operator.get("site", {})

    lines: list[str] = [
        "// СГЕНЕРИРОВАНО legal/build.py — не редактировать руками.",
        "// Источник данных: legal/operator.json + legal/sources/public/*.md",
        "// Документы с operator.json → documents[].published === false сюда не",
        "// попадают (LEGAL_DOCS/LEGAL_DOC_LIST) — только .docx для них всё равно",
        "// собирается в legal/out/. OPERATOR.* поля, чьё значение в operator.json",
        "// целиком плейсхолдер вида {{...}}, экспортируются пустой строкой.",
        "",
        "export interface LegalDoc {",
        "  slug: string",
        "  route: string",
        "  title: string",
        "  version: string",
        "  effectiveDate: string",
        "  html: string",
        "}",
        "",
    ]

    # Каждый документ — именованная константа; LEGAL_DOC_LIST и LEGAL_DOCS
    # строятся из них прямыми ссылками, без индексации Record<string, LegalDoc>.
    # Индексный доступ (LEGAL_DOCS["slug"]) с noUncheckedIndexedAccess (базовый
    # @vue/tsconfig) типизируется как `LegalDoc | undefined` — здесь его нет
    # вовсе, поэтому проверка типов честно проходит без `!`/`as`.
    idents = {r["slug"]: _ts_ident(r["slug"]) for r in ordered}
    for r in ordered:
        ident = idents[r["slug"]]
        lines.append(f"const {ident}: LegalDoc = {{")
        lines.append(f"  slug: {_ts_string(r['slug'])},")
        lines.append(f"  route: {_ts_string(r['route'])},")
        lines.append(f"  title: {_ts_string(r['title'])},")
        lines.append(f"  version: {_ts_string(r['version'])},")
        lines.append(f"  effectiveDate: {_ts_string(r['effectiveDate'])},")
        lines.append(f"  html: {_ts_string(r['html'])},")
        lines.append("}")
        lines.append("")

    lines.append("export const LEGAL_DOC_LIST: LegalDoc[] = [")
    for r in ordered:
        lines.append(f"  {idents[r['slug']]},")
    lines.append("]")
    lines.append("")

    lines.append("export const LEGAL_DOCS: Record<string, LegalDoc> = {")
    for r in ordered:
        lines.append(f"  {_ts_string(r['slug'])}: {idents[r['slug']]},")
    lines.append("}")
    lines.append("")

    lines.append(f"export const LEGAL_VERSION: string = {_ts_string(legal_version)}")
    lines.append("")

    lines.append("export const OPERATOR = {")
    lines.append(f"  form: {_ts_string(_op_value(op.get('form', '')))},")
    lines.append(f"  fullName: {_ts_string(_op_value(op.get('full_name', '')))},")
    lines.append(f"  inn: {_ts_string(_op_value(op.get('inn', '')))},")
    lines.append(f"  ogrn: {_ts_string(_op_value(op.get('ogrn', '')))},")
    lines.append(f"  legalAddress: {_ts_string(_op_value(op.get('legal_address', '')))},")
    lines.append(f"  supportEmail: {_ts_string(_op_value(site.get('support_email', '')))},")
    lines.append(f"  legalEmail: {_ts_string(_op_value(site.get('legal_email', '')))},")
    lines.append(f"  siteUrl: {_ts_string(_op_value(site.get('url', '')))},")
    lines.append(f"  filled: {'true' if operator.get('filled', False) else 'false'},")
    lines.append("}")
    lines.append("")

    ts_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _all_files(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


def run_check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tmp_out = tmp_path / "out"
        tmp_ts = tmp_path / "documents.generated.ts"
        tmp_py = tmp_path / "legal_generated.py"
        build_all(tmp_out, tmp_ts, tmp_py)

        problems: list[str] = []

        if not TS_OUT_PATH.exists():
            problems.append(f"нет {TS_OUT_PATH}")
        elif TS_OUT_PATH.read_bytes() != tmp_ts.read_bytes():
            problems.append(f"{TS_OUT_PATH} отличается от пересобранного варианта")

        if not PY_OUT_PATH.exists():
            problems.append(f"нет {PY_OUT_PATH}")
        elif PY_OUT_PATH.read_bytes() != tmp_py.read_bytes():
            problems.append(f"{PY_OUT_PATH} отличается от пересобранного варианта")

        expected = _all_files(tmp_out)
        actual = _all_files(OUT_DIR)
        for rel in sorted(expected - actual):
            problems.append(f"нет {OUT_DIR / rel}")
        for rel in sorted(actual - expected):
            problems.append(f"лишний файл {OUT_DIR / rel} (текущие исходники его не производят)")
        for rel in sorted(expected & actual):
            if (tmp_out / rel).read_bytes() != (OUT_DIR / rel).read_bytes():
                problems.append(f"{OUT_DIR / rel} отличается от пересобранного варианта")

        if problems:
            print("legal/build.py --check: РЕЗУЛЬТАТ ОТЛИЧАЕТСЯ ОТ РЕПОЗИТОРИЯ:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1

        print("legal/build.py --check: OK — репозиторий соответствует текущим исходникам")
        return 0


def main() -> None:
    check = "--check" in sys.argv[1:]
    try:
        if check:
            sys.exit(run_check())
        build_all(OUT_DIR, TS_OUT_PATH, PY_OUT_PATH)
        print(f"legal/build.py: собрано.\n  TS   -> {TS_OUT_PATH}\n  PY   -> {PY_OUT_PATH}\n  docx -> {OUT_DIR}")
    except BuildError as e:
        print(f"legal/build.py: ОШИБКА СБОРКИ: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
