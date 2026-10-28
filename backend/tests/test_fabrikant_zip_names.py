# -*- coding: utf-8 -*-
"""Баг (владелец, прод, 28.10.2026): имя файла в ZIP пакета Фабрикант
(/api/purchases/{pid}/fabrikant-package) назначалось ПО ПОЗИЦИИ в списке
`rendered` — фиксированный список русских базовых имён
["Инструкция", "Форма_заявки", "Документация", "Проект_договора", "ТЗ"]
проходился `next()` по порядку. render_fabrikant_package_files пропускает
документ, который не отрендерился (например, «Проект договора» падает на
проверке НДС-основания) — тогда следующий документ в списке `rendered``
сдвигается на позицию пропущенного, и получает ЕГО имя: ТЗ попадало в архив
под именем «Проект_договора.docx».

Исправление: имя в ZIP теперь назначается по самому документу — через
FABRIKANT_PKG_ZIP_BASENAMES (ключ — ascii-база файла, единственный источник
соответствия doc_key → короткое русское имя, см.
app/services/documents/fabrikant_package.py, ПРАВИЛО №6), а не по позиции.

Тест вызывает чистую функцию build_fabrikant_zip_bytes напрямую — без БД/HTTP,
имитируя именно случай «один документ выпал» (здесь — «Проект договора»).
"""
import sys
import os
import zipfile
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.documents.fabrikant_package import (
    build_fabrikant_zip_bytes,
    FABRIKANT_PKG_FILE_NAMES,
)


def _fake_bytes(label: str) -> bytes:
    return f"fake-docx-bytes:{label}".encode("utf-8")


def test_skipped_doc_does_not_shift_names():
    """«Проект договора» не отрендерился — ТЗ должен остаться «ТЗ.docx»,
    не стать «Проект_договора.docx»; errors.txt должен присутствовать."""
    # FABRIKANT_PKG_FILE_NAMES = [(doc_key, ascii_name, ru_title), ...]
    by_key = {dk: (ascii_name, ru_title) for dk, ascii_name, ru_title in FABRIKANT_PKG_FILE_NAMES}

    # Успешно отрендерились все, КРОМЕ fabrikant_contract_project (пропущен —
    # как при падении проверки НДС-основания в реальном коде).
    skip_key = "fabrikant_contract_project"
    rendered = []
    for doc_key, (ascii_name, ru_title) in by_key.items():
        if doc_key == skip_key:
            continue
        rendered.append((ascii_name, ru_title, _fake_bytes(doc_key)))

    errors = [f"{by_key[skip_key][0]}: ValueError: основание освобождения от НДС не указано"]

    zip_bytes = build_fabrikant_zip_bytes(rendered, errors)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

    # ТЗ — последний по порядку в FABRIKANT_PKG_FILE_NAMES, значит он был
    # бы сдвинут на позицию пропущенного "Проект_договора" старым (позиционным)
    # кодом. Должен остаться "ТЗ.docx".
    assert "ТЗ.docx" in names, f"ТЗ должно называться ТЗ.docx, получили: {names}"
    assert "Проект_договора.docx" not in names, (
        f"Пропущенный документ не должен появляться в архиве под своим именем, "
        f"и тем более не должно это имя достаться соседнему документу: {names}"
    )
    assert "errors.txt" in names

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert zf.read("ТЗ.docx") == _fake_bytes("tech_spec_request")


def test_all_docs_rendered_keeps_original_names():
    """Успешный случай (все 5 документов отрендерились) — имена в ZIP
    должны остаться прежними: Инструкция/Форма_заявки/Документация/
    Проект_договора/ТЗ (+ .docx), без errors.txt."""
    rendered = [
        (ascii_name, ru_title, _fake_bytes(doc_key))
        for doc_key, ascii_name, ru_title in FABRIKANT_PKG_FILE_NAMES
    ]
    zip_bytes = build_fabrikant_zip_bytes(rendered, [])

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())

    assert names == {
        "Инструкция.docx",
        "Форма_заявки.docx",
        "Документация.docx",
        "Проект_договора.docx",
        "ТЗ.docx",
    }
