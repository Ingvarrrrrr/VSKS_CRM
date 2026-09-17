"""Правило №6 — жалоба владельца (2026-09-17, дословно): «по субсидии ФАДМ
пытаюсь выгрузить служебку на авансовый, она есть подгруженная моя, а
формируется служебка по глобальному шаблону».

Причина (см. отчёт сессии 2026-09-17): app/routers/wish_documents.py::
generate_wish_service_note держал СВОЮ копию логики резолва шаблона
(PRIMARY_FILE = "service_note_procurement.docx" / FALLBACK_FILE =
"service_note.docx") — она вообще не знала о doc_type 'service_note_advance'
и потому НИКОГДА не проверяла файл .../subsidies/{id}/service_note_advance.docx
для авансового компаньона заявки (wish.source == 'advance_report'), даже
когда владелец его загрузил. Общий /api/purchases/{pid}/documents/{doc_type}
резолвит корректно (единый _resolve_doc_template_path) — сломан был именно
этот, отдельный, wish-уровневый маршрут генерации.

Фикс: generate_wish_service_note теперь выбирает doc_type по wish.source
('advance_report' → service_note_advance, иначе — service_note_procurement,
как раньше) и резолвит файл ЧЕРЕЗ _resolve_doc_template_path — тот же
резолвер, что использует общий эндпоинт закупки (app/services/documents/
templates.py). Заодно на тот же резолвер переведены stages_merge.py и
fabrikant_package.py (раньше — эквивалентные, но отдельные копии той же
логики приоритета «субсидия → глобальный → fallback»).

Этот файл проверяет ОБА направления приоритета (иначе тест ловит только
«не упало», а не саму приоритетность) для ДВУХ типов документа, как требует
задание:
  1) служебная записка авансового компаньона заявки (service_note_advance) —
     именно то, что было сломано;
  2) ТЗ заявки (tech_spec → contract_tz.docx) — тот же резолвер на соседнем
     типе документа, для контроля, что приоритет субсидии не завязан только
     на один doc_type.

Регрессия подтверждена вручную: с временно возвращённой старой версией
generate_wish_service_note (PRIMARY_FILE/FALLBACK_FILE без учёta wish.source)
test_service_note_advance_uses_subsidy_template ниже падает — маркер
кастомного service_note_advance.docx не находится в сгенерированном docx,
потому что старый код искал только service_note_procurement.docx/
service_note.docx. После восстановления фикса тест снова проходит.
"""
import os
import shutil
import uuid
from io import BytesIO

import pytest
from docx import Document as _DocxDoc

from app.models.wish import Wish
from app.models.wish_item import WishItem

SUBSIDY_TEMPLATES_BASE = "/app/uploads/templates/subsidies"


def _template_exists(name: str) -> bool:
    return os.path.exists(f"/app/templates/{name}")


_SKIP_NO_ADVANCE_TEMPLATE = pytest.mark.skipif(
    not (_template_exists("service_note_advance.docx") or _template_exists("service_note.docx")),
    reason="ни service_note_advance.docx, ни фолбэк service_note.docx не найдены в контейнере",
)
_SKIP_NO_TZ_TEMPLATE = pytest.mark.skipif(
    not _template_exists("contract_tz.docx"),
    reason="contract_tz.docx не найден в контейнере",
)


async def _make_subsidy(db_session, org_id):
    from app.models.subsidy import Subsidy
    s = Subsidy(
        name=f"TestSubsidyOverride-{uuid.uuid4().hex[:8]}", year=2026, budget=1_000_000,
        require_planned_dates=False, org_id=org_id,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


def _write_marker_template(path: str, marker: str) -> None:
    """Минимальный валидный docxtpl-шаблон: абзац с маркером + плейсхолдер
    {{ subsidy_name }}, который точно есть в контексте обоих эндпоинтов —
    рендер не падает на необъявленной переменной."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = _DocxDoc()
    doc.add_paragraph(f"{marker} {{{{ subsidy_name }}}}")
    doc.save(path)


def _extract_text(content: bytes) -> str:
    doc = _DocxDoc(BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs)


# ---------------------------------------------------------------------------
# 1) Служебная записка авансового компаньона заявки — service_note_advance
# ---------------------------------------------------------------------------

@_SKIP_NO_ADVANCE_TEMPLATE
@pytest.mark.asyncio
async def test_service_note_advance_uses_subsidy_template(client, db_session, auth_headers, test_org, test_user):
    """Wish с source='advance_report' + subsidy override → маркер кастомного
    шаблона обязан попасть в сгенерированный docx."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    marker = f"МАРКЕР-АВАНС-{uuid.uuid4().hex[:8]}"
    tpl_path = os.path.join(SUBSIDY_TEMPLATES_BASE, str(subsidy.id), "service_note_advance.docx")
    _write_marker_template(tpl_path, marker)
    try:
        w = Wish(
            org_id=test_org.id,
            subsidy_id=subsidy.id,
            title="Возмещение по авансовому отчёту — тест override",
            status="submitted",
            source="advance_report",
            created_by=test_user.id,
        )
        db_session.add(w)
        await db_session.flush()
        db_session.add(WishItem(
            wish_id=w.id, item_name="Кабель тестовый", quantity=1, unit="шт",
            unit_price=1000, total_price=1000,
        ))
        await db_session.commit()
        await db_session.refresh(w)

        resp = await client.get(f"/api/wishes/{w.id}/documents/service_note", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        text = _extract_text(resp.content)
        assert marker in text, (
            f"Кастомный шаблон субсидии {subsidy.id} (service_note_advance) не использован — "
            f"маркер {marker!r} отсутствует в сгенерированном docx"
        )
    finally:
        shutil.rmtree(os.path.join(SUBSIDY_TEMPLATES_BASE, str(subsidy.id)), ignore_errors=True)


@_SKIP_NO_ADVANCE_TEMPLATE
@pytest.mark.asyncio
async def test_service_note_advance_falls_back_to_global_without_override(client, db_session, auth_headers, test_org, test_user):
    """Без файла шаблона субсидии генерация не падает и не содержит «чужого»
    маркера — глобальное поведение сохранено (пункт 5 задания)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    # ВАЖНО: каталог .../subsidies/{id}/ НЕ создаём — override отсутствует.
    w = Wish(
        org_id=test_org.id,
        subsidy_id=subsidy.id,
        title="Возмещение — без кастомного шаблона",
        status="submitted",
        source="advance_report",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id, item_name="Кабель тестовый 2", quantity=1, unit="шт",
        unit_price=500, total_price=500,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    resp = await client.get(f"/api/wishes/{w.id}/documents/service_note", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.content) > 1000, "Ожидался полноценный .docx даже без override"
    text = _extract_text(resp.content)
    assert "МАРКЕР-АВАНС-" not in text


# ---------------------------------------------------------------------------
# 2) ТЗ заявки — tech_spec → contract_tz.docx (второй тип документа)
# ---------------------------------------------------------------------------

@_SKIP_NO_TZ_TEMPLATE
@pytest.mark.asyncio
async def test_wish_tech_spec_uses_subsidy_template(client, db_session, auth_headers, test_org, test_user):
    """Тот же резолвер (_resolve_doc_template_path), другой doc_type — субсидийный
    override обязан выигрывать и здесь (контроль, что приоритет не завязан на
    один-единственный тип документа)."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    marker = f"МАРКЕР-ТЗ-{uuid.uuid4().hex[:8]}"
    tpl_path = os.path.join(SUBSIDY_TEMPLATES_BASE, str(subsidy.id), "tech_spec.docx")
    _write_marker_template(tpl_path, marker)
    try:
        w = Wish(
            org_id=test_org.id,
            subsidy_id=subsidy.id,
            title="Заявка для проверки override ТЗ",
            status="draft",
            created_by=test_user.id,
        )
        db_session.add(w)
        await db_session.flush()
        db_session.add(WishItem(
            wish_id=w.id, item_name="Ноутбук тестовый override", quantity=1, unit="шт",
            unit_price=10000, total_price=10000,
        ))
        await db_session.commit()
        await db_session.refresh(w)

        resp = await client.get(f"/api/wishes/{w.id}/documents/tech_spec", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        text = _extract_text(resp.content)
        assert marker in text, (
            f"Кастомный шаблон субсидии {subsidy.id} (tech_spec) не использован"
        )
    finally:
        shutil.rmtree(os.path.join(SUBSIDY_TEMPLATES_BASE, str(subsidy.id)), ignore_errors=True)


@_SKIP_NO_TZ_TEMPLATE
@pytest.mark.asyncio
async def test_wish_tech_spec_falls_back_to_global_without_override(client, db_session, auth_headers, test_org, test_user):
    """Без override ТЗ заявки рендерится глобальным шаблоном без ошибок."""
    subsidy = await _make_subsidy(db_session, test_org.id)
    w = Wish(
        org_id=test_org.id,
        subsidy_id=subsidy.id,
        title="Заявка ТЗ без override",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id, item_name="Ноутбук тестовый без override", quantity=1, unit="шт",
        unit_price=10000, total_price=10000,
    ))
    await db_session.commit()
    await db_session.refresh(w)

    resp = await client.get(f"/api/wishes/{w.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    text = _extract_text(resp.content)
    assert "МАРКЕР-ТЗ-" not in text
