"""Тест решения владельца по supplier_description (26.10.2026, уточнено
Задачей 1 в тот же день): apply_products_import с supplier_description=True
на реальной БД. Файловое описание заменяет описание в БД безусловно, КОГДА
оно не заметно короче старого; когда оно ЗАМЕТНО КОРОЧЕ (is_new_description_shorter,
app/services/product_description_merge.py, ПРАВИЛО №6) — описание не
заменяется целиком, а объединяется (merge_missing_lines): старое сохраняется
целиком, недостающие строки файла дописываются в конец (повод — 41 товар с
потерей техданных в прошлом dry-run rebuild_descriptions_from_sources.py).
Единственная защита, как и раньше — файл не даёт вообще ничего
(build_tech_description вернул пусто) — тогда старое описание не трогаем."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.services.products_import_apply import apply_products_import

_UNIQ = "ТестЗаменаОписанияБезусловно_20261026"


def _uniq_name(suffix: str) -> str:
    return f"{_UNIQ} {suffix} {uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_shorter_file_description_merges_instead_of_replacing(db_session, test_user):
    """Товар в БД с богатым описанием + файл даёт описание ЗАМЕТНО КОРОЧЕ
    (Задача 1, 26.10.2026) — старое НЕ теряется: результат = старое целиком
    + недостающая строка файла в конце."""
    name = _uniq_name("Богатое")
    old_description = "Рукав всасывающий ГРВ-80\nДиаметр: 80 мм\nМатериал: резина"
    product = Product(
        name=name, category="Прочее",
        description=old_description,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1, "characteristics": 2}
    data_rows = [(name, "Длина: 5 м", [])]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="supplier.json", current_user=test_user,
        supplier_description=True,
    )
    assert result["updated"] == 1, result

    await db_session.refresh(product)
    assert product.description == old_description + "\nДлина: 5 м"


@pytest.mark.asyncio
async def test_not_shorter_file_description_still_replaces_old(db_session, test_user):
    """Файловое описание НЕ заметно короче старого — поведение как раньше,
    полная замена (не объединение)."""
    name = _uniq_name("НеКороче")
    product = Product(
        name=name, category="Прочее",
        description="Старое короткое описание.",
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1, "characteristics": 2}
    new_description = "Новое описание, которое не короче старого и целиком заменяет его."
    data_rows = [(name, new_description, [])]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="supplier.json", current_user=test_user,
        supplier_description=True,
    )
    assert result["updated"] == 1, result

    await db_session.refresh(product)
    assert product.description == new_description


@pytest.mark.asyncio
async def test_empty_file_description_and_characteristics_keep_old_description(db_session, test_user):
    """Товар в БД с описанием + файл даёт ПУСТОЕ описание (нет текста и
    характеристик) — старое описание не трогаем (единственная защита)."""
    name = _uniq_name("Пусто")
    product = Product(name=name, category="Прочее", description="Старое описание из БД")
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    col_idx = {"name": 0, "description": 1, "characteristics": 2}
    data_rows = [(name, None, [])]

    result = await apply_products_import(
        db_session, data_rows, col_idx,
        filename="supplier.json", current_user=test_user,
        supplier_description=True,
    )
    assert result is not None

    await db_session.refresh(product)
    assert product.description == "Старое описание из БД"
