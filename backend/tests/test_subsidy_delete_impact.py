"""app/services/subsidy_delete_impact.py — единственный источник подсчёта
зависимостей субсидии перед удалением (Правило №6), общий для GET
/subsidies/{id}/delete-impact (предупреждение в UI) и DELETE /subsidies/{id}
(гейт на 409).

Владелец удалил 2 видимые закупки субсидии «ЦентрПоиск_2026» (id=46) — счётчик
блокера не изменился, оставшиеся 11 были status='wishes' (заявки, не
переданные в работу), которые реестр закупок (scope='purchases') скрывает
безусловно (см. app/routers/purchases.py), пока status не запрошен явно.
КЛЮЧЕВОЙ СМЫСЛ этого теста — зафиксировать, что счётчик блокировки удаления
и то, что пользователь видит в реестре по каждому фильтру (?status=wishes,
?status=split, обычный реестр) СЧИТАЮТСЯ ИЗ ОДНОГО ИСТОЧНИКА и не могут
разъехаться: закупка со status='wishes'/'split' обязана НЕ попадать в группу
'purchases' (ту же, что видна в реестре БЕЗ явного фильтра статуса), а счётчик
группы ('count') обязан быть согласован со списком её объектов ('items').

Тесты идут через реальную БД (db_session — транзакция с откатом, см.
conftest.py), т.к. get_subsidy_delete_impact делает реальные SELECT'ы с JOIN.
"""
import uuid

from app.models.contract import Contract
from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.purchase import Purchase
from app.models.subsidy import Subsidy
from app.services.subsidy_delete_impact import (
    format_delete_block_message,
    get_subsidy_delete_impact,
    has_blocking_dependents,
)


async def _make_subsidy(db_session) -> Subsidy:
    subsidy = Subsidy(name=f"Тест-субсидия-{uuid.uuid4().hex[:8]}", year=2026)
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)
    return subsidy


async def test_groups_split_by_status(db_session):
    """Три закупки с разными статусами обязаны разложиться РОВНО по трём
    разным группам — это и есть разбивка, которой раньше не было (владелец
    видел одно слитное число «11 закупок»)."""
    subsidy = await _make_subsidy(db_session)
    p_regular = Purchase(subsidy_id=subsidy.id, item_name="Обычная закупка", status="in_progress")
    p_wish = Purchase(subsidy_id=subsidy.id, item_name="Заявка не в работе", status="wishes")
    p_split = Purchase(subsidy_id=subsidy.id, item_name="Разделённая (родитель)", status="split")
    db_session.add_all([p_regular, p_wish, p_split])
    await db_session.commit()
    await db_session.refresh(p_regular)
    await db_session.refresh(p_wish)
    await db_session.refresh(p_split)

    impact = await get_subsidy_delete_impact(db_session, subsidy.id)

    assert impact["purchases"]["count"] == 1
    assert [it["id"] for it in impact["purchases"]["items"]] == [p_regular.id]
    assert impact["wishes"]["count"] == 1
    assert [it["id"] for it in impact["wishes"]["items"]] == [p_wish.id]
    assert impact["split"]["count"] == 1
    assert [it["id"] for it in impact["split"]["items"]] == [p_split.id]


async def test_wishes_and_split_not_counted_as_regular_purchases(db_session):
    """Ядро бага владельца: status='wishes' и status='split' НЕ попадают в
    группу 'purchases' — ровно те статусы, которые реестр закупок
    (scope='purchases' в app/routers/purchases.py) скрывает по умолчанию.
    Без этого разделения владелец не мог объяснить расхождение между тем, что
    видно в реестре, и тем, что требует блокировка удаления."""
    subsidy = await _make_subsidy(db_session)
    db_session.add_all([
        Purchase(subsidy_id=subsidy.id, item_name="Заявка 1", status="wishes"),
        Purchase(subsidy_id=subsidy.id, item_name="Заявка 2", status="wishes"),
        Purchase(subsidy_id=subsidy.id, item_name="Родитель разделения", status="split"),
    ])
    await db_session.commit()

    impact = await get_subsidy_delete_impact(db_session, subsidy.id)

    assert impact["purchases"]["count"] == 0
    assert impact["wishes"]["count"] == 2
    assert impact["split"]["count"] == 1
    # Но всё вместе всё равно блокирует удаление — это и была претензия
    # владельца: 0 видимых в реестре закупок не значит "можно удалить".
    assert has_blocking_dependents(impact) is True
    message = format_delete_block_message(subsidy.name, impact)
    assert message is not None
    assert "2 заявок, не переданных в работу" in message
    assert "разделённых закупок" in message
    # Обычных "закупок" в тексте отказа быть не должно — их и не было.
    assert "0 закупок" not in message


async def test_count_consistent_with_items(db_session):
    """Счётчик группы ('count') обязан быть согласован со списком её объектов
    ('items') — иначе UI (SubsidyDeleteDialog.vue) мог бы показать число,
    для которого нет ни одной ссылки на объект (эксплуатационный смысл того
    же требования «счётчик и список из одного источника»)."""
    subsidy = await _make_subsidy(db_session)
    purchases = [
        Purchase(subsidy_id=subsidy.id, item_name=f"Закупка {i}", status="in_progress")
        for i in range(3)
    ]
    contract = Contract(number="Д-1", contract_type="single", subsidy_id=subsidy.id, subject="Тестовый договор")
    db_session.add_all([*purchases, contract])
    await db_session.commit()

    impact = await get_subsidy_delete_impact(db_session, subsidy.id)

    assert impact["purchases"]["count"] == len(impact["purchases"]["items"]) == 3
    assert impact["contracts"]["count"] == len(impact["contracts"]["items"]) == 1
    assert {it["id"] for it in impact["purchases"]["items"]} == {p.id for p in purchases}


async def test_feo_categories_and_planned_items_counted(db_session):
    subsidy = await _make_subsidy(db_session)
    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Направление расходов")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    item = FeoPlannedItem(feo_category_id=cat.id, name="Плановая позиция")
    db_session.add(item)
    await db_session.commit()

    impact = await get_subsidy_delete_impact(db_session, subsidy.id)

    assert impact["feo_categories"] == 1
    assert impact["planned_items"] == 1


async def test_no_dependents_does_not_block_deletion(db_session):
    """Свежая субсидия без единой закупки/заявки/договора/ФЭО-категории —
    удаление не должно блокироваться НИКАКИМ мнимым зависимостям (все
    четыре группы обязаны быть пустыми и с нулевым count)."""
    subsidy = await _make_subsidy(db_session)

    impact = await get_subsidy_delete_impact(db_session, subsidy.id)

    for key in ("purchases", "wishes", "split", "contracts"):
        assert impact[key]["count"] == 0
        assert impact[key]["items"] == []
    assert impact["feo_categories"] == 0
    assert impact["planned_items"] == 0
    assert has_blocking_dependents(impact) is False
    assert format_delete_block_message(subsidy.name, impact) is None
