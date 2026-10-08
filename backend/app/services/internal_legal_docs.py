"""Единый реестр внутренних правовых документов для закрытого раздела
«Документы» админки (решение владельца 08.10.2026 — все документы проекта
живут на сайте: публичные открыто, внутренние по 152-ФЗ только администратору).

Источник данных — backend/app/services/legal_internal_docs_generated.py
(СГЕНЕРИРОВАН legal/build.py из legal/operator.json + legal/sources/internal/*.md,
см. legal/CONTRACT.md). Это ЕДИНСТВЕННОЕ место в backend/, которое знает про
список и содержимое внутренних документов — app/routers/admin_legal_docs.py
читает только отсюда, не хранит и не пересчитывает список документов второй
раз (ПРАВИЛО №6).
"""
from __future__ import annotations

from app.services.legal_internal_docs_generated import INTERNAL_LEGAL_DOCS

# Словарь по slug строится один раз при импорте модуля — поиск документа по
# slug идёт по этому словарю, а не по файловой системе: запрошенный slug,
# которого нет среди сгенерированных ключей, не может привести ни к чтению
# произвольного файла, ни к path traversal.
_DOCS_BY_SLUG: dict[str, dict[str, str]] = {d["slug"]: d for d in INTERNAL_LEGAL_DOCS}


def list_internal_legal_docs() -> list[dict[str, str]]:
    """Список документов без HTML — для перечня в админке."""
    return [{k: v for k, v in d.items() if k != "html"} for d in INTERNAL_LEGAL_DOCS]


def get_internal_legal_doc(slug: str) -> dict[str, str] | None:
    """Документ по slug, включая HTML. None, если slug не из реестра."""
    return _DOCS_BY_SLUG.get(slug)
