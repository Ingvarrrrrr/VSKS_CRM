"""scripts/merge_duplicate_products_by_name.py — слияние дублей каталога
товаров по точному совпадению названия.

Как и test_cleanup_bad_product_import.py / test_merge_duplicates_by_inn.py:
скрипт открывает СВОЮ собственную app.database.async_session и запускается
subprocess'ом (рассчитан на `docker exec ... python
scripts/merge_duplicate_products_by_name.py`), поэтому тест не использует
db_session (SAVEPOINT на одном connection скрипту не виден) — готовит данные
через реальный async_session, запускает скрипт subprocess'ом и убирает за
собой все созданные строки в finally.

Каждый сценарий использует свой уникальный run_id в названии товара и
--filter-name-substr с этим run_id — чтобы скрипт обрабатывал ТОЛЬКО группу
этого теста, а не все 41 реальную группу дублей локальной копии боевой БД.

Сценарии:
  - dry-run ничего не меняет, но верно печатает план (keep/remove, перенос
    полей, ссылки).
  - --yes сливает: пустой дубль удалён, keep донаполнен (unit, price+его
    метаданные), purchase_items/wish_items/product_price_history перевешены
    на keep, история цен НЕ потеряна (обе строки истории видны на keep).
  - supplier_products с конфликтующим UNIQUE(supplier_id, product_id):
    строка дубля удаляется вместо переноса, у keep остаётся ровно одна.
  - группа без описания ни у кого — не трогается совсем.
  - разные названия — не считаются дублями (группа не формируется).
"""
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.database import async_session
from app.models.organization import Organization
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.supplier import Supplier, SupplierProduct
from app.models.wish import Wish
from app.models.wish_item import WishItem

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_DIR / "scripts" / "merge_duplicate_products_by_name.py"


def _run_script(extra_args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *extra_args],
        capture_output=True,
        text=True,
        cwd=str(BACKEND_DIR),
    )


@pytest_asyncio.fixture
async def merge_scenario():
    """Полный сценарий одной группы дублей + группа без описания (контроль) +
    товар с другим именем (контроль fuzzy-запрета). Убирает всё за собой."""
    run_id = uuid.uuid4().hex[:8]
    dup_name = f"Тестовый Дубль Товара {run_id}"
    no_desc_name = f"Тестовая Группа Без Описания {run_id}"
    other_name = f"Совсем Другой Товар {run_id}"

    ids: dict[str, int] = {}
    purchase_id = None
    wish_id = None

    async with async_session() as db:
        org = Organization(name=f"TestOrg-merge-{run_id}")
        db.add(org)
        await db.commit()
        await db.refresh(org)

        # keep-кандидат: описание + фото есть, unit и price пустые.
        p_keep = Product(
            name=dup_name, category="Прочее",
            description="Полное описание товара для ТЗ",
            photo_url="https://example.test/photo.jpg",
        )
        # дубль: пустая карточка, но с unit и price — должны переехать на keep.
        p_dup = Product(
            name=f"  {dup_name}  ", category="Прочее",  # лишние пробелы по краям — normalize_name должен схлопнуть
            unit="шт", price="123.45", price_source="manual",
        )
        p_no_desc_a = Product(name=no_desc_name, category="Прочее")
        p_no_desc_b = Product(name=no_desc_name, category="Прочее")
        p_other = Product(name=other_name, category="Прочее", description="У этого тоже есть описание")
        db.add_all([p_keep, p_dup, p_no_desc_a, p_no_desc_b, p_other])
        await db.commit()
        for p in (p_keep, p_dup, p_no_desc_a, p_no_desc_b, p_other):
            await db.refresh(p)
        ids = {
            "keep": p_keep.id, "dup": p_dup.id,
            "no_desc_a": p_no_desc_a.id, "no_desc_b": p_no_desc_b.id,
            "other": p_other.id,
        }

        # Ссылки на ДУБЛЬ, которые должны переехать на keep при merge.
        purchase = Purchase(status="planned", item_type="goods", item_name="Test purchase (merge dup script)")
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        purchase_id = purchase.id
        db.add(PurchaseItem(purchase_id=purchase.id, product_id=p_dup.id, item_name="dup ref item", quantity=1))

        wish = Wish(org_id=org.id, title="Test wish (merge dup script)", status="draft")
        db.add(wish)
        await db.commit()
        await db.refresh(wish)
        wish_id = wish.id
        db.add(WishItem(wish_id=wish.id, product_id=p_dup.id, item_name="dup wish item", quantity=1))

        # История цен есть у ОБОИХ — обе строки должны сохраниться и после
        # merge указывать на keep (владелец: средняя цена по всей истории).
        db.add(ProductPriceHistory(product_id=p_keep.id, price=100, source="import"))
        db.add(ProductPriceHistory(product_id=p_dup.id, price=200, source="import"))

        # supplier_products: конфликтующая пара (supplier, keep) уже
        # существует — после merge строка дубля для того же supplier должна
        # быть УДАЛЕНА (не создавать нарушение UNIQUE), а не перенесена.
        supplier = Supplier(name=f"TestSupplier-{run_id}", org_id=org.id)
        db.add(supplier)
        await db.commit()
        await db.refresh(supplier)
        db.add(SupplierProduct(supplier_id=supplier.id, product_id=p_keep.id, source="manual"))
        db.add(SupplierProduct(supplier_id=supplier.id, product_id=p_dup.id, source="manual"))
        ids["supplier"] = supplier.id

        await db.commit()

    try:
        yield {"run_id": run_id, "dup_name": dup_name, "no_desc_name": no_desc_name,
               "other_name": other_name, "ids": ids}
    finally:
        async with async_session() as db:
            await db.execute(text("DELETE FROM wish_items WHERE wish_id = :wid"), {"wid": wish_id})
            await db.execute(text("DELETE FROM wishes WHERE id = :wid"), {"wid": wish_id})
            await db.execute(text("DELETE FROM purchase_items WHERE purchase_id = :pid"), {"pid": purchase_id})
            await db.execute(text("DELETE FROM purchases WHERE id = :pid"), {"pid": purchase_id})
            await db.execute(
                text("DELETE FROM supplier_products WHERE supplier_id = :sid"), {"sid": ids["supplier"]},
            )
            await db.execute(text("DELETE FROM suppliers WHERE id = :sid"), {"sid": ids["supplier"]})
            product_ids = [v for k, v in ids.items() if k != "supplier"]
            await db.execute(
                text("DELETE FROM product_price_history WHERE product_id = ANY(:ids)"), {"ids": product_ids},
            )
            await db.execute(text("DELETE FROM products WHERE id = ANY(:ids)"), {"ids": product_ids})
            org = (await db.execute(
                text("SELECT id FROM organizations WHERE name = :n"), {"n": f"TestOrg-merge-{run_id}"},
            )).scalar()
            if org:
                await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": org})
            await db.commit()


@pytest.mark.asyncio
async def test_dry_run_changes_nothing(merge_scenario):
    run_id = merge_scenario["run_id"]
    ids = merge_scenario["ids"]

    result = _run_script(["--dry-run", "--filter-name-substr", run_id.lower()])
    assert result.returncode == 0, result.stderr
    assert "Групп к слиянию: 1" in result.stdout
    assert "Групп пропущено (нет описания ни у кого): 1" in result.stdout
    assert f"оставить id={ids['keep']}" in result.stdout
    assert f"удалить ids=[{ids['dup']}]" in result.stdout
    assert "DRY-RUN" in result.stdout

    async with async_session() as db:
        remaining = (await db.execute(
            select(Product.id).where(Product.id.in_([ids["keep"], ids["dup"], ids["no_desc_a"], ids["no_desc_b"]]))
        )).scalars().all()
    # Ничего не удалено ни в одной группе.
    assert set(remaining) == {ids["keep"], ids["dup"], ids["no_desc_a"], ids["no_desc_b"]}


@pytest.mark.asyncio
async def test_yes_merges_moves_refs_backfills_and_keeps_price_history(merge_scenario):
    run_id = merge_scenario["run_id"]
    ids = merge_scenario["ids"]

    result = _run_script(["--yes", "--filter-name-substr", run_id.lower()])
    assert result.returncode == 0, result.stderr
    assert "ПРИМЕНЕНО: удалено 1 товаров" in result.stdout

    async with async_session() as db:
        # Пустой дубль удалён.
        dup_row = (await db.execute(select(Product.id).where(Product.id == ids["dup"]))).scalar()
        assert dup_row is None

        # Группа без описания ни у кого — не тронута.
        no_desc_remaining = (await db.execute(
            select(Product.id).where(Product.id.in_([ids["no_desc_a"], ids["no_desc_b"]]))
        )).scalars().all()
        assert set(no_desc_remaining) == {ids["no_desc_a"], ids["no_desc_b"]}

        # keep донаполнен пустыми полями из дубля, непустое (description,
        # photo_url) не тронуто.
        keep = (await db.execute(select(Product).where(Product.id == ids["keep"]))).scalar_one()
        assert keep.unit == "шт"
        assert float(keep.price) == 123.45
        assert keep.price_source == "manual"
        assert keep.description == "Полное описание товара для ТЗ"
        assert keep.photo_url == "https://example.test/photo.jpg"

        # Ссылки перевешены на keep.
        purchase_item_product = (await db.execute(
            text("SELECT product_id FROM purchase_items WHERE purchase_id = :pid"),
            {"pid": (await db.execute(
                text("SELECT id FROM purchases WHERE item_name = 'Test purchase (merge dup script)'")
            )).scalar()},
        )).scalar()
        assert purchase_item_product == ids["keep"]

        wish_item_product = (await db.execute(
            text("SELECT product_id FROM wish_items WHERE item_name = 'dup wish item'"),
        )).scalar()
        assert wish_item_product == ids["keep"]

        # История цен НЕ потеряна: обе строки (100 и 200) теперь на keep.
        ph_prices = sorted((await db.execute(
            text("SELECT price FROM product_price_history WHERE product_id = :pid ORDER BY price"),
            {"pid": ids["keep"]},
        )).scalars().all())
        assert [float(p) for p in ph_prices] == [100.0, 200.0]

        # supplier_products: конфликтующая пара удалена, у keep осталась
        # ровно одна строка для этого supplier (не задвоилась).
        sp_count = (await db.execute(
            text("SELECT COUNT(*) FROM supplier_products WHERE supplier_id = :sid AND product_id = :pid"),
            {"sid": ids["supplier"], "pid": ids["keep"]},
        )).scalar()
        assert sp_count == 1
        sp_dup_count = (await db.execute(
            text("SELECT COUNT(*) FROM supplier_products WHERE product_id = :pid"), {"pid": ids["dup"]},
        )).scalar()
        assert sp_dup_count == 0


@pytest.mark.asyncio
async def test_different_names_are_not_grouped_as_duplicates(merge_scenario):
    """Контроль запрета fuzzy: товар с ДРУГИМ названием (даже если тоже есть
    описание) не должен попасть ни в какую группу и не должен быть тронут."""
    run_id = merge_scenario["run_id"]
    ids = merge_scenario["ids"]

    result = _run_script(["--dry-run", "--filter-name-substr", run_id.lower()])
    assert result.returncode == 0, result.stderr
    assert str(ids["other"]) not in result.stdout

    async with async_session() as db:
        other = (await db.execute(select(Product.id).where(Product.id == ids["other"]))).scalar()
    assert other == ids["other"]
