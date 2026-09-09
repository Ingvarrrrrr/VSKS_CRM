"""Задача C (dreamy-booping-piglet.md): scripts/cleanup_bad_product_import.py.

Скрипт (как и merge_duplicates_by_inn.py) открывает СВОЮ собственную
app.database.async_session и запускается как отдельный процесс — это
намеренно (см. докстринг скрипта: он рассчитан на `docker exec ... python
scripts/cleanup_bad_product_import.py`, а не на импорт внутрь FastAPI-роутов).
Тестовый conftest.db_session изолирует тест SAVEPOINT'ом на ОДНОМ connection
(см. докстринг conftest.py) — subprocess открывает другой connection и
committed-строки из db_session ему не видны. Поэтому этот тест НЕ использует
db_session: он готовит данные через реальный async_session (настоящие
commit'ы в локальную dev-БД), запускает скрипт subprocess'ом и сам убирает
за собой все созданные строки в finally — ровно то, что требует задача
("прогон по одному узлу... за собой прибрать созданные записи").

Сценарий:
  - p_plain   — подпадает под критерий (дата/категория/имя из файла), без
                ссылок → должен быть удалён при --yes.
  - p_second  — второй товар, подпадающий под критерий, тоже без ссылок →
                тоже должен быть удалён (проверяем, что удаляются ВСЕ
                подходящие, не только первый).
  - p_other   — та же дата, но имя/категория НЕ из списка → контроль, что
                критерий строгий (него скрипт не должен трогать вообще).
  - p_ref     — подпадает под критерий, но на него ссылается purchase_items
                → должен остаться нетронутым даже при --yes.

Второй сценарий (--with-price-history, доработка после прод dry-run: 172 из
1022 кандидатов оказались связаны ИСКЛЮЧИТЕЛЬНО через product_price_history —
ту же мусорную историю, что создал ошибочный импорт):
  - p_ph_only    — подпадает под критерий, ссылка есть ТОЛЬКО из
                   product_price_history → удаляется вместе с историей при
                   `--yes --with-price-history`, но НЕ удаляется без флага.
  - p_other_ref  — подпадает под критерий, ссылка из purchase_items (другая
                   таблица) → не удаляется НИ ПРИ КАКИХ флагах, в т.ч. с
                   --with-price-history.
"""
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.database import async_session
from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_DIR / "scripts" / "cleanup_bad_product_import.py"

# Заведомо не пересекается ни с какой реальной датой импорта на локальной БД.
TEST_DATE = "2099-01-01"
TEST_UPDATED_AT = datetime(2099, 1, 1, 12, 0, 0)


def _run_script(names_file: Path, extra_args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--date", TEST_DATE, "--names-file", str(names_file), *extra_args],
        capture_output=True,
        text=True,
        cwd=str(BACKEND_DIR),
    )


@pytest.fixture
def scenario_names():
    """Два уникальных «имени-категории» для этого прогона — исключает
    коллизию с реальными данными и с параллельными прогонами теста."""
    run_id = uuid.uuid4().hex[:8]
    return {
        "match_a": f"ТестКатегорияA-{run_id}",
        "match_b": f"ТестКатегорияB-{run_id}",
        "other": f"ДругоеИмя-{run_id}",
    }


@pytest.fixture
def names_file(tmp_path, scenario_names):
    path = tmp_path / "names.txt"
    path.write_text(
        scenario_names["match_a"] + "\n" + scenario_names["match_b"] + "\n",
        encoding="utf-8",
    )
    return path


@pytest_asyncio.fixture
async def products(scenario_names):
    """Создаёт 4 реальных товара (+ purchase/purchase_item для ссылки) прямым
    коммитом в БД и гарантированно убирает их за собой по id, независимо от
    того, что уже удалил сам скрипт."""
    ids = {}
    purchase_id = None
    async with async_session() as db:
        p_plain = Product(name=scenario_names["match_a"], category="Прочее", updated_at=TEST_UPDATED_AT)
        p_second = Product(name=scenario_names["match_b"], category="Прочее", updated_at=TEST_UPDATED_AT)
        p_other = Product(name=scenario_names["other"], category="Другая категория", updated_at=TEST_UPDATED_AT)
        p_ref = Product(name=scenario_names["match_a"], category="Прочее", updated_at=TEST_UPDATED_AT)
        db.add_all([p_plain, p_second, p_other, p_ref])
        await db.commit()
        for p in (p_plain, p_second, p_other, p_ref):
            await db.refresh(p)
        ids = {"plain": p_plain.id, "second": p_second.id, "other": p_other.id, "ref": p_ref.id}

        purchase = Purchase(status="planned", item_type="goods", item_name="Test purchase (cleanup script)")
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        purchase_id = purchase.id

        item = PurchaseItem(purchase_id=purchase.id, product_id=p_ref.id, item_name="ref item", quantity=1)
        db.add(item)
        await db.commit()

    try:
        yield ids
    finally:
        async with async_session() as db:
            await db.execute(text("DELETE FROM purchase_items WHERE purchase_id = :pid"), {"pid": purchase_id})
            await db.execute(text("DELETE FROM purchases WHERE id = :pid"), {"pid": purchase_id})
            await db.execute(text("DELETE FROM products WHERE id = ANY(:ids)"), {"ids": list(ids.values())})
            await db.commit()


@pytest.mark.asyncio
async def test_dry_run_changes_nothing_and_counts_correctly(products, names_file, scenario_names):
    result = _run_script(names_file, ["--dry-run"])
    assert result.returncode == 0, result.stderr

    # 3 кандидата (plain, second, ref), 1 со ссылкой (ref), 2 к удалению.
    expected_header = (
        f"Кандидатов на удаление (date(updated_at)={TEST_DATE}, category='Прочее', "
        "name из 2 значений файла): 3"
    )
    assert expected_header in result.stdout
    assert "К удалению: 2" in result.stdout
    assert "Связаны другими таблицами, кроме истории цен (НЕ удаляются ни при каком флаге): 1" in result.stdout
    assert "Связаны только историей цен (product_price_history)" in result.stdout
    assert ": 0 товаров, 0 записей истории" in result.stdout
    assert "DRY-RUN" in result.stdout

    async with async_session() as db:
        rows = (await db.execute(
            select(Product.id).where(Product.id.in_(list(products.values())))
        )).scalars().all()
    # Ничего не удалено — все 4 товара на месте.
    assert set(rows) == set(products.values())


@pytest.mark.asyncio
async def test_yes_deletes_only_eligible_without_refs(products, names_file, scenario_names):
    # Без --dry-run и без --yes скрипт обязан вести себя как dry-run (защита
    # от случайного запуска) — проверяем и это, прежде чем реально удалять.
    result_default = _run_script(names_file, [])
    assert result_default.returncode == 0, result_default.stderr
    assert "DRY-RUN" in result_default.stdout

    result = _run_script(names_file, ["--yes"])
    assert result.returncode == 0, result.stderr
    assert "УДАЛЕНО: 2 товаров, 0 записей истории цен." in result.stdout

    async with async_session() as db:
        remaining = (await db.execute(
            select(Product.id).where(Product.id.in_(list(products.values())))
        )).scalars().all()

    remaining_set = set(remaining)
    assert products["plain"] not in remaining_set
    assert products["second"] not in remaining_set
    # Контрольный товар (другое имя/категория) и товар со ссылкой остаются.
    assert products["other"] in remaining_set
    assert products["ref"] in remaining_set


@pytest.mark.asyncio
async def test_requires_both_date_and_names_file(names_file):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, cwd=str(BACKEND_DIR),
    )
    assert result.returncode != 0
    assert "--date" in result.stderr or "--date" in result.stdout


# ---------------------------------------------------------------------------
# --with-price-history (доработка после прод dry-run: 172/1022 кандидатов
# связаны ИСКЛЮЧИТЕЛЬНО через product_price_history — та же ошибочная
# загрузка создала мусорную историю цен, владелец решил удалять её вместе с
# товаром под отдельным флагом; ссылки из любой ДРУГОЙ таблицы по-прежнему
# блокируют удаление при любых флагах).
# ---------------------------------------------------------------------------

@pytest.fixture
def ph_scenario_names():
    run_id = uuid.uuid4().hex[:8]
    return {
        "ph_only": f"ТестКатегорияPH-{run_id}",
        "other_ref": f"ТестКатегорияOtherRef-{run_id}",
    }


@pytest.fixture
def ph_names_file(tmp_path, ph_scenario_names):
    path = tmp_path / "ph_names.txt"
    path.write_text(
        ph_scenario_names["ph_only"] + "\n" + ph_scenario_names["other_ref"] + "\n",
        encoding="utf-8",
    )
    return path


@pytest_asyncio.fixture
async def ph_products(ph_scenario_names):
    """p_ph_only — ссылка ТОЛЬКО из product_price_history (одна строка
    истории). p_other_ref — ссылка из purchase_items (другая таблица),
    контроль: должен остаться нетронутым даже с --with-price-history."""
    ids = {}
    purchase_id = None
    async with async_session() as db:
        p_ph_only = Product(name=ph_scenario_names["ph_only"], category="Прочее", updated_at=TEST_UPDATED_AT)
        p_other_ref = Product(name=ph_scenario_names["other_ref"], category="Прочее", updated_at=TEST_UPDATED_AT)
        db.add_all([p_ph_only, p_other_ref])
        await db.commit()
        for p in (p_ph_only, p_other_ref):
            await db.refresh(p)
        ids = {"ph_only": p_ph_only.id, "other_ref": p_other_ref.id}

        db.add(ProductPriceHistory(product_id=p_ph_only.id, price=100, source="import"))
        await db.commit()

        purchase = Purchase(status="planned", item_type="goods", item_name="Test purchase (cleanup script, PH)")
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        purchase_id = purchase.id

        item = PurchaseItem(purchase_id=purchase.id, product_id=p_other_ref.id, item_name="ref item", quantity=1)
        db.add(item)
        await db.commit()

    try:
        yield ids
    finally:
        async with async_session() as db:
            await db.execute(text("DELETE FROM purchase_items WHERE purchase_id = :pid"), {"pid": purchase_id})
            await db.execute(text("DELETE FROM purchases WHERE id = :pid"), {"pid": purchase_id})
            await db.execute(
                text("DELETE FROM product_price_history WHERE product_id = ANY(:ids)"),
                {"ids": list(ids.values())},
            )
            await db.execute(text("DELETE FROM products WHERE id = ANY(:ids)"), {"ids": list(ids.values())})
            await db.commit()


def _run_ph_script(names_file: Path, extra_args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--date", TEST_DATE, "--names-file", str(names_file), *extra_args],
        capture_output=True,
        text=True,
        cwd=str(BACKEND_DIR),
    )


@pytest.mark.asyncio
async def test_price_history_only_ref_blocked_without_flag(ph_products, ph_names_file):
    """Без --with-price-history товар со ссылкой только из
    product_price_history остаётся нетронутым — как и товар со ссылкой из
    purchase_items."""
    result = _run_ph_script(ph_names_file, ["--yes"])
    assert result.returncode == 0, result.stderr
    # Оба кандидата заблокированы (один — другой таблицей, другой — только
    # историей цен без --with-price-history) → "к удалению: 0", скрипт
    # завершается веткой "применять нечего", строка "УДАЛЕНО:" не печатается.
    assert "К удалению: 0" in result.stdout
    assert "Применять нечего (все кандидаты заблокированы ссылками)." in result.stdout
    assert "УДАЛЕНО:" not in result.stdout
    assert "Связаны только историей цен (product_price_history)" in result.stdout
    assert ": 1 товаров, 1 записей истории" in result.stdout
    assert "Связаны другими таблицами, кроме истории цен (НЕ удаляются ни при каком флаге): 1" in result.stdout

    async with async_session() as db:
        remaining = (await db.execute(
            select(Product.id).where(Product.id.in_(list(ph_products.values())))
        )).scalars().all()
    assert set(remaining) == set(ph_products.values())


@pytest.mark.asyncio
async def test_with_price_history_deletes_ph_only_but_not_other_ref(ph_products, ph_names_file):
    """С --yes --with-price-history: товар со ссылкой ТОЛЬКО из
    product_price_history удаляется вместе со своей историей; товар со
    ссылкой из purchase_items остаётся — другая таблица блокирует удаление
    даже с этим флагом."""
    result = _run_ph_script(ph_names_file, ["--yes", "--with-price-history"])
    assert result.returncode == 0, result.stderr
    assert "УДАЛЕНО: 1 товаров, 1 записей истории цен." in result.stdout

    async with async_session() as db:
        remaining_products = set((await db.execute(
            select(Product.id).where(Product.id.in_(list(ph_products.values())))
        )).scalars().all())
        remaining_ph = (await db.execute(
            text("SELECT count(*) FROM product_price_history WHERE product_id = :pid"),
            {"pid": ph_products["ph_only"]},
        )).scalar()

    assert ph_products["ph_only"] not in remaining_products
    assert ph_products["other_ref"] in remaining_products
    assert remaining_ph == 0
