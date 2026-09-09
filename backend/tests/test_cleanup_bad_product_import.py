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
    assert "Из них со ссылками (НЕ будут удалены): 1" in result.stdout
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
    assert "УДАЛЕНО: 2" in result.stdout

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
