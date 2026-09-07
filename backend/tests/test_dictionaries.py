"""Правило №6 — единый источник справочников закупки (app/services/dictionaries.py)
и синхронизация с frontend/src/data/dictionaries.json.

Не требует db_session/Postgres — чистые словари и статический разбор AST,
как backend/scripts/check_alembic_single_head.py (см. его докстринг).
"""
import subprocess
import sys
from pathlib import Path

from app.routers.purchases import STATUS_ORDER
from app.services import dictionaries as d

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXPORT_SCRIPT = BACKEND_DIR / "scripts" / "export_dictionaries.py"


def test_status_labels_cover_status_order():
    """Каждый статус из STATUS_ORDER (purchases.py, канбан/фильтры) обязан
    иметь подпись в STATUS_LABELS — иначе на экране будет "сырой" ключ."""
    missing = [s for s in STATUS_ORDER if s not in d.STATUS_LABELS]
    assert not missing, f"STATUS_LABELS не содержит подписи для: {missing}"
    # и наоборот — в STATUS_LABELS нет статусов, которых уже нет в STATUS_ORDER
    # (мёртвая подпись — сигнал, что статус переименован/удалён не везде)
    extra = [s for s in d.STATUS_LABELS if s not in STATUS_ORDER]
    assert not extra, f"STATUS_LABELS содержит статусы вне STATUS_ORDER: {extra}"


def test_all_dictionaries_non_empty():
    for name in ("STATUS_LABELS", "SUBSTATUS_LABELS", "CONTRACT_TYPE_LABELS",
                 "PURCHASE_METHOD_LABELS", "PURCHASE_BASIS_LABELS"):
        assert getattr(d, name), f"{name} пуст"


def test_purchase_export_aliases_match_source():
    """purchase_export.py импортирует эти словари под именами _FOO_LABELS —
    убеждаемся, что алиасы не разошлись с источником (Правило №6: один
    показатель — одно значение везде, где он читается)."""
    from app.routers import purchase_export as pe

    assert pe._STATUS_LABELS is d.STATUS_LABELS
    assert pe._SUBSTATUS_LABELS is d.SUBSTATUS_LABELS
    assert pe._CONTRACT_TYPE_LABELS is d.CONTRACT_TYPE_LABELS
    assert pe._PURCHASE_METHOD_LABELS is d.PURCHASE_METHOD_LABELS
    assert pe._PURCHASE_BASIS_LABELS is d.PURCHASE_BASIS_LABELS


def test_export_dictionaries_check_passes():
    """frontend/src/data/dictionaries.json обязан быть в синхроне с бэкендом
    (тот же --check, что запускает CI, backend job, см. .github/workflows/ci.yml).
    Если тест упал — запустить `python backend/scripts/export_dictionaries.py`
    и закоммитить обновлённый JSON."""
    result = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT), "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"export_dictionaries.py --check упал:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
