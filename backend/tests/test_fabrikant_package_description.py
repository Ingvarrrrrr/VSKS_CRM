# -*- coding: utf-8 -*-
"""Баг (владелец, 28.10.2026): в пакете для Фабриканта (ТЗ.docx, шаблон
tech_spec_request, переменная {{item.description}}) описание позиций было
пустым — render_fabrikant_package_files собирал items_list собственным
ручным циклом по build_tz_rows с захардкоженным "description": "", а не
общим построителем, которым пользуется обычный документ
(_build_items_list_from_purchase_items, app/services/documents/contexts.py),
читающим item.tz_description / product.description через
effective_item_tz/effective_item_tz_44fz (ПРАВИЛО №6).

Исправление: fabrikant_package.py теперь зовёт тот же
_build_items_list_from_purchase_items — этот файл проверяет (а) что
fabrikant_package.py буквально импортирует и вызывает ИМЕННО эту функцию
(идентичность объекта, не вторую копию-дубль), и (б) офлайн, без БД
(SimpleNamespace, как test_fabrikant_contexts_single_source.py), что
description в items_list приходит из item.tz_description / каталожного
product.description — ровно так же, как у обычного документа.
"""
from types import SimpleNamespace

from app.services.documents import fabrikant_package as fp
from app.services.documents.contexts import _build_items_list_from_purchase_items


def test_fabrikant_package_uses_canonical_items_list_builder():
    """Единственный источник items_list для плановых документов — не вторая
    копия цикла внутри fabrikant_package.py."""
    assert fp._build_items_list_from_purchase_items is _build_items_list_from_purchase_items


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


def _stub_purchase(items):
    return SimpleNamespace(
        items=items, tz_duplicate_decisions=None, vat_mode="uniform",
        tz_vat_on_top=False, description_mode=None, contract_form=None,
    )


def test_items_list_description_comes_from_item_tz_description():
    """item.tz_description заполнено — именно оно должно попасть в
    description строки пакета (не пустая строка, как было до фикса)."""
    item = _stub_item(item_name="Огнетушитель ОП-5", tz_description="Порошковый, 5 кг, класс ABCE")
    p = _stub_purchase([item])

    items_list = _build_items_list_from_purchase_items(p)

    assert len(items_list) == 1
    assert items_list[0]["description"] == "Порошковый, 5 кг, класс ABCE"
    assert items_list[0]["name"] == "Огнетушитель ОП-5"
    assert items_list[0]["_product"] is None


def test_items_list_description_falls_back_to_catalog_product():
    """Без собственного tz_description у строки — описание берётся из
    каталожного product.description (тот же фолбэк, что и в обычном
    документе, app/services/item_tz.py::effective_item_tz)."""
    product = _stub_product(description="Штатив телескопический, алюминий")
    item = _stub_item(item_name="Штатив", tz_description=None, product=product, product_id=product.id)
    p = _stub_purchase([item])

    items_list = _build_items_list_from_purchase_items(p)

    assert items_list[0]["description"] == "Штатив телескопический, алюминий"
    assert items_list[0]["_product"] is product


def test_items_products_derived_from_builder_output_same_order():
    """fabrikant_package.py больше не ведёт items_products отдельным ручным
    append'ом в цикле — он берёт "_product" из того же items_list, в том же
    порядке (используется ниже для резолва фото tech_spec_request)."""
    product_a = _stub_product(description="Товар А")
    product_b = _stub_product(description="Товар Б")
    item_a = _stub_item(item_name="А", tz_description=None, product=product_a, product_id=1)
    item_b = _stub_item(item_name="Б", tz_description=None, product=product_b, product_id=2)
    p = _stub_purchase([item_a, item_b])

    items_list = _build_items_list_from_purchase_items(p)
    items_products = [it["_product"] for it in items_list]

    assert items_products == [product_a, product_b]
    assert [it["description"] for it in items_list] == ["Товар А", "Товар Б"]
