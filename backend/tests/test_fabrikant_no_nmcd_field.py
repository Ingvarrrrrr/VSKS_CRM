# -*- coding: utf-8 -*-
"""purchases.fabrikant_no_nmcd — ЕДИНСТВЕННОЕ хранимое состояние «Без НМЦД»
для Фабриканта (владелец, 28.10.2026, ПРАВИЛО №6).

До правки «Без НМЦД» существовало только как эфемерный флаг диалога
ОТПРАВКИ пакета (PublishRequest.no_nmcd) — скачивание ZIP-пакета без
отправки (/api/purchases/{pid}/fabrikant-package,
app/routers/documents.py::download_fabrikant_package) никогда не знало об
этом выборе и всегда печатало настоящую НМЦД.

Этот файл проверяет (а) что download_fabrikant_package читает ИМЕННО
purchase.fabrikant_no_nmcd и передаёт его в render_fabrikant_package_files
(без БД — render_fabrikant_package_files подменена заглушкой, перехватывающей
аргументы вызова), и (б) что сам эффект на контексте документа —
"Не определена" для total_nmcd/total_nmck/nmck — даёт та же единственная
функция apply_no_nmcd_override, что и для публикации (см.
test_nmcd_undetermined.py, ПРАВИЛО №6 — не вторая проверка флага)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.routers.documents as documents_router
from app.services.documents.nmcd_undetermined import apply_no_nmcd_override


async def _call_download_fabrikant_package(monkeypatch, *, purchase_no_nmcd: bool):
    """Вызывает download_fabrikant_package напрямую (без HTTP/реальной БД) и
    возвращает no_nmcd, с которым он позвал render_fabrikant_package_files."""
    captured = {}

    async def fake_render(db, pid, current_user, no_nmcd=False):
        captured["no_nmcd"] = no_nmcd
        return ([("doc.docx", "Документ", b"fake")], [])

    monkeypatch.setattr(documents_router, "render_fabrikant_package_files", fake_render)
    monkeypatch.setattr(documents_router, "build_fabrikant_zip_bytes", lambda rendered, errors: b"PK\x03\x04fake-zip")

    async def fake_ensure_visible(current_user, pid, db):
        return None

    monkeypatch.setattr("app.auth.object_visibility.ensure_purchase_visible", fake_ensure_visible)

    fake_purchase = SimpleNamespace(fabrikant_no_nmcd=purchase_no_nmcd)
    fake_db = AsyncMock()
    fake_db.get.return_value = fake_purchase

    await documents_router.download_fabrikant_package(
        pid=123, db=fake_db, current_user=SimpleNamespace(id=1),
    )
    return captured["no_nmcd"]


async def test_download_passes_purchase_fabrikant_no_nmcd_true(monkeypatch):
    """purchase.fabrikant_no_nmcd=True → скачивание без отправки тоже должно
    получить «Без НМЦД» — то же поле, что читает диалог отправки."""
    no_nmcd = await _call_download_fabrikant_package(monkeypatch, purchase_no_nmcd=True)
    assert no_nmcd is True


async def test_download_passes_purchase_fabrikant_no_nmcd_false(monkeypatch):
    """По умолчанию (fabrikant_no_nmcd=False) скачивание ведёт себя как
    раньше — НМЦД печатается как обычно."""
    no_nmcd = await _call_download_fabrikant_package(monkeypatch, purchase_no_nmcd=False)
    assert no_nmcd is False


def test_context_effect_uses_canonical_override_not_a_second_check():
    """Эффект самого флага на контексте документа — «Не определена» для всех
    трёх алиасов НМЦД — считает только apply_no_nmcd_override (ПРАВИЛО №6);
    download_fabrikant_package выше не должен заводить вторую реализацию."""
    context = {"total_nmcd": "130 000,00", "total_nmck": "130 000,00", "nmck": "130 000,00"}
    apply_no_nmcd_override(context, no_nmcd=True)
    assert context["total_nmcd"] == "Не определена"
    assert context["total_nmck"] == "Не определена"
    assert context["nmck"] == "Не определена"
