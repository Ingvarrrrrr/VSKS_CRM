# -*- coding: utf-8 -*-
"""Правило владельца: в ШАБЛОНЕ блок «ЛЕГЕНДА — как читать этот шаблон»
есть и шаблон с ней всегда можно скачать для правки; в ГОТОВОМ документе
(заполненном данными закупки/заявки) легенды быть не должно.

Единственное место удаления (ПРАВИЛО №6) — strip_template_legend()
(app/services/documents/docx_post.py). Этот файл проверяет:
  1) offline-рендер реальных шаблонов + strip_template_legend убирает блок,
     не трогая остальной текст документа (абзацы/таблицы совпадают кроме
     самой легенды) — для service_note_procurement.docx, tech_spec_request.docx,
     contract_tz.docx (используется для «ТЗ закупки»/«ТЗ заявки»);
  2) живой HTTP-путь GET /api/wishes/{id}/documents/service_note и
     .../tech_spec (единственные document-эндпоинты заявки) не содержит
     «ЛЕГЕНДА» в готовом файле;
  3) скачивание САМОГО шаблона не тронуто: raw-байты файла на диске (то,
     что отдают subsidy_templates.py:425 и subsidy_approvers.py:176 — они
     НЕ импортируют strip_template_legend, см. grep в отчёте) по-прежнему
     содержат «ЛЕГЕНДА».
"""
import os
import tempfile
from io import BytesIO

import docx
import pytest
from docxtpl import DocxTemplate

from app.services.documents.docx_post import strip_template_legend
from app.models.wish import Wish
from app.models.wish_item import WishItem


_THIS_DIR = os.path.dirname(__file__)
_TEMPLATES_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "templates"))

LEGEND_TEMPLATES = [
    "service_note_procurement.docx",
    "tech_spec_request.docx",
    "contract.docx",
]


def _doc_paragraph_texts(docx_bytes: bytes) -> list[str]:
    d = docx.Document(BytesIO(docx_bytes))
    return [p.text for p in d.paragraphs]


def _render_raw_bytes(template_path: str, ctx: dict) -> bytes:
    t = DocxTemplate(template_path)
    t.render(ctx)
    fd = tempfile.mktemp(suffix=".docx")
    t.save(fd)
    try:
        with open(fd, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(fd)
        except OSError:
            pass


# Пустой контекст: тот же трюк, что и _check_template_render_ok()
# (routers/subsidy_templates.py) использует для пробного рендера при
# загрузке шаблонов — подтверждено вручную в контейнере backend_a, что все
# три шаблона рендерятся с tpl.render({}) без исключения.
def _render_with_empty_ctx(template_path: str) -> bytes:
    t = DocxTemplate(template_path)
    t.render({})
    fd = tempfile.mktemp(suffix=".docx")
    t.save(fd)
    try:
        with open(fd, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(fd)
        except OSError:
            pass


@pytest.mark.parametrize("template_name", LEGEND_TEMPLATES)
def test_raw_template_contains_legend_on_disk(template_name):
    """Скачивание ШАБЛОНА (subsidy_templates.py / subsidy_approvers.py отдают
    файл как есть, strip_template_legend не импортируют) — легенда на месте."""
    template_path = os.path.join(_TEMPLATES_DIR, template_name)
    assert os.path.isfile(template_path), f"Шаблон не найден: {template_path}"
    with open(template_path, "rb") as f:
        raw = f.read()
    txt = "\n".join(_doc_paragraph_texts(raw))
    assert "ЛЕГЕНДА" in txt, f"[{template_name}] ожидалась «ЛЕГЕНДА» в исходном шаблоне"


@pytest.mark.parametrize("template_name", LEGEND_TEMPLATES)
def test_strip_template_legend_removes_block_keeps_rest(template_name):
    """strip_template_legend() на отрендеренном документе: «ЛЕГЕНДА» пропадает,
    а абзацы ПОСЛЕ разделителя-«—————» остаются байт-в-байт теми же (контент
    документа не вырезан вместе с легендой)."""
    template_path = os.path.join(_TEMPLATES_DIR, template_name)
    assert os.path.isfile(template_path), f"Шаблон не найден: {template_path}"

    rendered = _render_with_empty_ctx(template_path)
    before_paras = _doc_paragraph_texts(rendered)
    assert any("ЛЕГЕНДА" in p for p in before_paras), (
        f"[{template_name}] рендер должен ещё содержать «ЛЕГЕНДА» до strip"
    )

    stripped = strip_template_legend(rendered)
    after_paras = _doc_paragraph_texts(stripped)

    assert not any("ЛЕГЕНДА" in p for p in after_paras), (
        f"[{template_name}] «ЛЕГЕНДА» осталась после strip_template_legend"
    )

    # Абзацы документа ПОСЛЕ легенды (хвост before_paras, начиная сразу
    # после строки-разделителя из одних «—») должны совпасть с хвостом
    # after_paras — ничего лишнего не вырезано.
    sep_idx = None
    for i, p in enumerate(before_paras):
        s = p.strip()
        if s and all(ch == "—" for ch in s):
            sep_idx = i
            break
    assert sep_idx is not None, f"[{template_name}] строка-разделитель «—————» не найдена в исходном рендере"
    expected_tail = before_paras[sep_idx + 1:]
    assert after_paras == expected_tail, (
        f"[{template_name}] текст документа после легенды изменился — "
        f"strip_template_legend вырезал лишнее или не всё"
    )
    assert len(after_paras) > 0, f"[{template_name}] после strip не осталось ни одного абзаца документа"


def test_strip_template_legend_noop_when_no_legend():
    """Кастомный шаблон без блока «ЛЕГЕНДА» — байты возвращаются без изменений."""
    template_path = os.path.join(_TEMPLATES_DIR, "contract_services.docx")
    assert os.path.isfile(template_path), f"Шаблон не найден: {template_path}"
    with open(template_path, "rb") as f:
        raw = f.read()
    txt = "\n".join(_doc_paragraph_texts(raw))
    assert "ЛЕГЕНДА" not in txt, "contract_services.docx неожиданно содержит «ЛЕГЕНДА» — выбери другой шаблон без неё для этого теста"
    assert strip_template_legend(raw) == raw


def _template_exists(name: str) -> bool:
    return os.path.exists(f"/app/templates/{name}")


_SKIP_NO_TEMPLATES = pytest.mark.skipif(
    not (_template_exists("service_note_procurement.docx") and _template_exists("tech_spec_request.docx")),
    reason="service_note_procurement.docx / tech_spec_request.docx not available in test environment",
)


@_SKIP_NO_TEMPLATES
@pytest.mark.asyncio
async def test_wish_service_note_document_has_no_legend(client, db_session, auth_headers, test_org, test_user):
    """GET /api/wishes/{id}/documents/service_note — готовая служебка заявки
    не содержит «ЛЕГЕНДА» (strip_template_legend вызван из wish_documents.py)."""
    w = Wish(
        org_id=test_org.id,
        title="Тестовая заявка для легенды 20261019",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id,
        item_name="Позиция для проверки легенды",
        quantity=1,
        unit="шт",
        unit_price=1000,
        total_price=1000,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    resp = await client.get(f"/api/wishes/{w.id}/documents/service_note", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    txt = "\n".join(_doc_paragraph_texts(resp.content))
    assert "ЛЕГЕНДА" not in txt, "готовая служебная записка содержит служебный блок «ЛЕГЕНДА»"
    assert len(txt.strip()) > 0, "документ пуст после strip — вырезано лишнее"


@_SKIP_NO_TEMPLATES
@pytest.mark.asyncio
async def test_wish_tech_spec_document_has_no_legend(client, db_session, auth_headers, test_org, test_user):
    """GET /api/wishes/{id}/documents/tech_spec — готовое ТЗ заявки не
    содержит «ЛЕГЕНДА»."""
    w = Wish(
        org_id=test_org.id,
        title="Тестовая заявка ТЗ для легенды 20261019",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id,
        item_name="Позиция ТЗ для проверки легенды",
        quantity=1,
        unit="шт",
        unit_price=1000,
        total_price=1000,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    resp = await client.get(f"/api/wishes/{w.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    txt = "\n".join(
        cell.text
        for table in docx.Document(BytesIO(resp.content)).tables
        for row in table.rows
        for cell in row.cells
    ) + "\n" + "\n".join(_doc_paragraph_texts(resp.content))
    assert "ЛЕГЕНДА" not in txt, "готовое ТЗ заявки содержит служебный блок «ЛЕГЕНДА»"
