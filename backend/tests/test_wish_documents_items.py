# -*- coding: utf-8 -*-
"""Служебка заявки (wish_documents.py::generate_wish_service_note) собирала
items_list третьей ручной копией — отдельным циклом по w.items с
effective_item_tz(it, it.product), не знавшей про build_tz_rows (слияние
дублей ТЗ), effective_vat_on_top/document_unit_price (цена «сверху» НДС) и
item_form_summary/menu_lines (спецформы). Каноничный построитель —
_build_items_list_from_purchase_items (app/services/documents/contexts.py),
его уже использует generate_wish_tech_spec в том же файле и
fabrikant_package.py.

Правило №6: этот файл проверяет (а) что wish_documents.py импортирует и
зовёт ИМЕННО эту функцию (идентичность объекта, не вторую копию-дубль),
и (б) офлайн, без БД (SimpleNamespace, как test_fabrikant_package_description.py),
что description строки заявки приходит из item.tz_description так же, как
у обычного документа.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

from app.services.documents.contexts import _build_items_list_from_purchase_items

_WISH_DOCUMENTS_PATH = Path(__file__).resolve().parents[1] / "app" / "routers" / "wish_documents.py"


def _stub_item(*, item_name, tz_description=None, product=None, item_type="Товар",
                quantity=2, unit_price=100, total_price=200, unit="шт.", product_id=None):
    return SimpleNamespace(
        item_name=item_name, tz_description=tz_description, product=product,
        product_id=product_id if product_id is not None else getattr(product, "id", None),
        item_type=item_type, quantity=quantity, unit_price=unit_price,
        total_price=total_price, unit=unit, vat_on_top=None, feo_category_id=None,
        item_form=None, extra_attrs=None,
    )


def _stub_product(*, description="", item_kind="товар"):
    return SimpleNamespace(id=1, description=description, item_kind=item_kind,
                            characteristics=None)


def _stub_wish(items):
    """Минимальный Wish-дубль — только атрибуты, которые читает построитель
    (getattr с дефолтом внутри него безопасно обходится без остальных)."""
    return SimpleNamespace(
        items=items, tz_duplicate_decisions=None, vat_mode="uniform",
        tz_vat_on_top=False, description_mode=None,
    )


def test_wish_documents_imports_canonical_items_list_builder():
    """wish_documents.py не заводит собственную сборку items_list для
    служебки — явный import внутри generate_wish_service_note ссылается
    ровно на _build_items_list_from_purchase_items, не на вторую копию."""
    source = _WISH_DOCUMENTS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.documents.contexts":
            imported_names.update(alias.name for alias in node.names)
    assert "_build_items_list_from_purchase_items" in imported_names
    # Нет третьей ручной копии: generate_wish_service_note больше не содержит
    # собственного "for idx, it in enumerate(w.items ...)" цикла с
    # "items_list.append(" — только один общий построитель на оба endpoint'а.
    assert source.count("items_list.append(") == 0


def test_wish_items_list_description_comes_from_tz_description():
    """item.tz_description заполнено у позиции заявки — именно оно должно
    попасть в description строки служебки/ТЗ заявки (тот же построитель,
    что печатает описание закупки)."""
    item = _stub_item(item_name="Огнетушитель ОП-5", tz_description="Порошковый, 5 кг, класс ABCE")
    w = _stub_wish([item])

    items_list = _build_items_list_from_purchase_items(w)

    assert len(items_list) == 1
    assert items_list[0]["description"] == "Порошковый, 5 кг, класс ABCE"
    assert items_list[0]["name"] == "Огнетушитель ОП-5"


def test_wish_items_list_description_falls_back_to_catalog_product():
    """Без собственного tz_description у строки заявки — описание из
    каталожного product.description (тот же фолбэк, что у обычной закупки)."""
    product = _stub_product(description="Штатив телескопический, алюминий")
    item = _stub_item(item_name="Штатив", tz_description=None, product=product, product_id=product.id)
    w = _stub_wish([item])

    items_list = _build_items_list_from_purchase_items(w)

    assert items_list[0]["description"] == "Штатив телескопический, алюминий"
