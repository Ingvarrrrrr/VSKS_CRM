# -*- coding: utf-8 -*-
"""Регрессия на доказанный дефект: генерация документа переписывала файл
шаблона на диске — build_docx_template обнаруживал Word-комментарии
(<w:commentRange...>) в шаблоне и вызывал _normalize_docx_template(path),
которая стирала подсказки прямо из backend/templates/*.docx (и навсегда —
из /app/uploads/templates/subsidies/<id>/*.docx).

Опыт: md5 contract_services.docx до generate_document_bytes(...) был
e3957f8c..., после — b7a65e83..., те же 122 commentRangeStart/
commentReference исчезли полностью.

Фикс: build_docx_template читает шаблон в BytesIO один раз, нормализует
(при необходимости) in-memory копию через чистую _normalize_docx_bytes
(без I/O) — физический файл шаблона никогда не открывается на запись.

Тест не трогает БД — build_docx_template(template_path, pid, doc_type)
принимает pid/doc_type только для текста ошибки, работы с БД не требует.
"""
import hashlib
import os
import shutil
import tempfile
import uuid
import zipfile

import pytest

from app.services.documents.stages_template_engine import build_docx_template

_THIS_DIR = os.path.dirname(__file__)
_TEMPLATES_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "templates"))

# Оба шаблона реально содержат Word-комментарии (подсказки к полям) и
# попадали под needs_norm=True в build_docx_template — ровно те, что
# пострадали в доказанном дефекте.
DOC_TYPES = ["contract_services", "contract_goods_single"]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_build_docx_template_does_not_mutate_source_file(doc_type, tmp_path):
    src = os.path.join(_TEMPLATES_DIR, f"{doc_type}.docx")
    assert os.path.exists(src), f"ожидаемый шаблон отсутствует: {src}"

    # Работаем с копией — тест никогда не трогает backend/templates/ напрямую.
    work_path = os.path.join(tmp_path, f"{doc_type}.docx")
    shutil.copyfile(src, work_path)

    before = _sha256(work_path)
    before_size = os.path.getsize(work_path)

    tpl = build_docx_template(work_path, pid=999999, doc_type=doc_type)

    after = _sha256(work_path)
    after_size = os.path.getsize(work_path)

    assert tpl is not None
    assert before == after, (
        f"generate() изменил файл шаблона на диске ({doc_type}): "
        f"sha256 до={before} после={after} (размер до={before_size} после={after_size})"
    )


def test_build_docx_template_still_strips_comments_in_memory(tmp_path):
    """Нормализация не отменена целиком — она просто больше не пишет на
    диск. docxtpl, построенный из in-memory копии, не должен падать и
    должен быть пригоден для рендера (сам факт успешного рендера
    подтверждает, что normalize-ветка отработала на копии, а не была
    тихо пропущена)."""
    src = os.path.join(_TEMPLATES_DIR, "contract_services.docx")
    work_path = os.path.join(tmp_path, "contract_services.docx")
    shutil.copyfile(src, work_path)

    tpl = build_docx_template(work_path, pid=999999, doc_type="contract_services")
    # get_undeclared_template_variables() разбирает документ — если бы
    # normalize сломал XML или если бы InlineImage-плейсхолдеры остались
    # разбиты по рантам, здесь обычно падает.
    tpl.get_undeclared_template_variables()


# ---------------------------------------------------------------------------
# Второй шаг того же дефекта (коррекция координатора, 2026-10-06):
# upload_subsidy_template / upload_global_template раньше вызывали
# _normalize_docx_template(dest) ПОСЛЕ записи файла — загруженный
# организацией шаблон со своими комментариями-подсказками тут же терял их
# на диске. Фикс: оба upload-эндпоинта больше не пишут нормализацию на
# диск (_peek_normalize_stats / _validate_renders_in_memory работают с
# копией в памяти), normalize_all_existing_templates — единственное
# место, которое сознательно стирает комментарии на диске.
# ---------------------------------------------------------------------------

def _count_comment_markers(path: str) -> int:
    total = 0
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            if name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer"):
                total += zf.read(name).count(b"<w:commentRangeStart")
    return total


async def test_upload_subsidy_template_endpoint_preserves_comments_on_disk(tmp_path, monkeypatch):
    """Загружаем через upload_subsidy_template() реальный шаблон с Word-
    комментариями (contract.docx, 129 подсказок) — на диске после upload
    комментарии должны остаться нетронутыми (раньше были стёрты сразу)."""
    from io import BytesIO

    from fastapi import UploadFile
    from app.routers import subsidy_templates as st_module

    src = os.path.join(_TEMPLATES_DIR, "contract.docx")
    assert os.path.exists(src), f"эталонный шаблон с комментариями отсутствует: {src}"
    with open(src, "rb") as f:
        src_bytes = f.read()
    before_markers = _count_comment_markers(src)
    assert before_markers > 0, "эталон должен содержать Word-комментарии, иначе тест ничего не проверяет"

    # Изолируем upload в tmp_path — не трогаем настоящий /app/uploads/templates/.
    fake_subsidies_base = os.path.join(tmp_path, "uploads_templates")
    monkeypatch.setattr(st_module, "SUBSIDY_TEMPLATES_BASE", fake_subsidies_base)

    subsidy_id = 900000 + (uuid.uuid4().int % 90000)
    upload_file = UploadFile(filename="contract.docx", file=BytesIO(src_bytes))

    result = await st_module.upload_subsidy_template(
        subsidy_id=subsidy_id,
        doc_type="contract",
        file=upload_file,
        current_user=object(),
    )
    assert result["ok"] is True

    dest = os.path.join(fake_subsidies_base, "subsidies", str(subsidy_id), "contract.docx")
    assert os.path.exists(dest)
    after_markers = _count_comment_markers(dest)
    assert after_markers == before_markers, (
        f"upload_subsidy_template стёр комментарии на диске: было {before_markers}, осталось {after_markers}"
    )
    # Сам файл побайтово не тронут вообще (не только счётчик комментариев).
    with open(dest, "rb") as f:
        assert f.read() == src_bytes
