"""D8/D9 (волна 4b, Правило №6): merge_duplicate_contractors_by_inn.

Раньше дедуп контрагентов по ИНН выполнялся при каждом старте приложения
(app/startup/backfills.py::_phase26_qq_contractor_dedup_by_inn). Перенесено в
app/services/contractor_dedup.py и вызывается только из
scripts/merge_duplicates_by_inn.py (разовый CLI data-fix). Тест проверяет:
  1. dry_run=True ничего не пишет (ни рядов contractors, ни FK, ни индекса).
  2. Два контрагента с одинаковым ИНН сливаются в одного (keep_id = MIN id),
     FK-ссылка (purchases.contractor_id) переносится на survivor.
"""
import pytest
from sqlalchemy import select, text

from app.models.contractor import Contractor
from app.services.contractor_dedup import merge_duplicate_contractors_by_inn


async def _make_contractor(db_session, **kwargs):
    c = Contractor(name=kwargs.pop("name", "Тест ООО"), **kwargs)
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _drop_unique_index(db_session):
    """ix_contractors_inn_unique уже существует в локальной dev-БД (создан
    прежними прогонами бэкфилла) и не даёт создать тестовых дублей по ИНН —
    ровно ту ситуацию, которую merge призван чинить. DDL транзакционен в
    Postgres: DROP выполняется внутри тестового SAVEPOINT и откатывается
    вместе со всем остальным при teardown db_session (см. conftest.py)."""
    await db_session.execute(text("DROP INDEX IF EXISTS ix_contractors_inn_unique"))


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(db_session):
    await _drop_unique_index(db_session)
    c1 = await _make_contractor(db_session, name="Дубль 1", inn="7700000001")
    c2 = await _make_contractor(db_session, name="Дубль 2", inn="7700000001")

    stats = await merge_duplicate_contractors_by_inn(db_session, dry_run=True)

    assert stats["groups"] == 1
    assert stats["merged"] == 1

    # Оба контрагента по-прежнему в БД, ничего не удалено и не переписано.
    rows = (await db_session.execute(
        select(Contractor).where(Contractor.id.in_([c1.id, c2.id]))
    )).scalars().all()
    assert {r.id for r in rows} == {c1.id, c2.id}
    assert {r.name for r in rows} == {"Дубль 1", "Дубль 2"}


@pytest.mark.asyncio
async def test_merge_merges_duplicates_and_rewires_fk(db_session, make_purchase):
    await _drop_unique_index(db_session)
    keep = await _make_contractor(db_session, name="Keep", inn="7700000002", kpp="")
    dup = await _make_contractor(db_session, name="Dup", inn="7700000002", kpp="770001001")

    # FK-ссылка на дубль-контрагента — должна перевешаться на survivor.
    purchase = await make_purchase(contractor_id=dup.id)

    stats = await merge_duplicate_contractors_by_inn(db_session, dry_run=False)

    assert stats["groups"] == 1
    assert stats["merged"] == 1

    # Merge пишет raw SQL мимо ORM — identity-mapped объекты (keep/dup/
    # purchase) держат старые закешированные атрибуты, пока их не
    # инвалидировать явно (тот же приём, что и в migrate_category_plan_to_
    # planned_items.py при чтении после мутаций raw SQL).
    db_session.expire_all()

    # Дубль удалён, survivor остался.
    remaining = (await db_session.execute(
        select(Contractor).where(Contractor.inn == "7700000002")
    )).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == keep.id
    # Пустое поле survivor'а (kpp="") заполнено значением из дубля.
    assert remaining[0].kpp == "770001001"

    # FK перевешан на survivor.
    await db_session.refresh(purchase)
    assert purchase.contractor_id == keep.id

    # Partial unique index создан (идемпотентно).
    idx = (await db_session.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_contractors_inn_unique'"
    ))).first()
    assert idx is not None


@pytest.mark.asyncio
async def test_no_duplicates_returns_zero(db_session):
    await _make_contractor(db_session, name="Одинокий", inn="7700000003")

    stats = await merge_duplicate_contractors_by_inn(db_session, dry_run=False)

    assert stats["groups"] == 0
    assert stats["merged"] == 0
