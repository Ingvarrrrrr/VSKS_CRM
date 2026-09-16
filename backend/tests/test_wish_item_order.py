"""Regression test — жалоба владельца (2026-09-16, прод, заявка №67):

«Порядок позиций не идёт в том же порядке, что в загружаемом файле».

Причина: Wish.items / Purchase.items (relationship) и явные select(WishItem)/
select(PurchaseItem) в wish_convert.py / wish_distribution.py / wish_serializers.py
не имели order_by. Postgres без ORDER BY отдаёт строки в физическом порядке
хранения, а не в порядке id (=порядок загрузки файла/ввода) — порядок «плывёт»
после любого UPDATE позиции (строка физически переезжает).

Фикс — models/wish.py и models/purchase.py: `order_by="...Item.id"` на
relationship items (покрывает ВСЕ selectinload(...Wish.items)/
selectinload(Purchase.items), включая GET /api/wishes/{id} и GET
/api/purchases/{pid}), плюс .order_by(...Item.id) на явные select() в
wish_convert.py/wish_distribution.py/wish_serializers.py, которые строят
purchase_items из wish.items при конвертации.

Проверено вручную (временно откатывал order_by у Wish.items, прогонял тест,
возвращал обратно — без git, просто правкой файла):
  - без order_by relationship.property.order_by == False (НЕ None — ловушка,
    сам сначала написал assert `is not None`, он проходил и без фикса; тест
    ниже проверяет на falsy);
  - сырой SQL той же таблицы БЕЗ ORDER BY после UPDATE средней позиции
    физически разошёлся с id-порядком: [2969, 2970, 2972, 2973, 2971] вместо
    [2969, 2970, 2971, 2972, 2973] — механизм дефекта заявки №67 воспроизведён
    напрямую;
  - однако GET /api/wishes/{id} (Часть 2, через selectinload) в этом прогоне
    ВСЁ РАВНО вернул верный порядок даже без order_by — план запроса
    selectin-стратегии (WHERE wish_id IN (...)) на маленькой тестовой таблице,
    видимо, использовал индексный скан по PK, а не seq scan по куче, так что
    id-порядок совпал со случаем. Это ЗНАЧИТ: HTTP-тест (Часть 2/3) сам по
    себе НЕ гарантированно ловит регрессию — он документирует ожидаемое
    поведение и годится смотреть за реальный дефект, а единственная
    ДЕТЕРМИНИРОВАННАЯ защита — Часть 1 (проверка на уровне маппера).

Часть 1 (test_relationship_order_by_is_set): статическая проверка на уровне
маппера — единственная часть, которая падает 100% воспроизводимо при потере
order_by, независимо от того, решит ли Postgres физически переставить строки
и от того, какой план запроса выберет планировщик на конкретном прогоне.

Часть 2 (test_wish_items_returned_in_id_order_after_update) — то же самое
сквозь HTTP: 5 позиций, UPDATE средней, GET /api/wishes/{id} — первая позиция
обязана быть первой (по id = по порядку загрузки), а не то, что физически
лежит в хранилище первым. Печатает [info], если физический порядок разошёлся
с id — рабочая демонстрация механизма, но НЕ единственная гарантия (см. выше).

Часть 3 (test_purchase_items_returned_in_id_order_after_update) — аналогично
для закупки (Purchase.items).
"""
import pytest
from sqlalchemy import select, text

from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.wish import Wish
from app.models.wish_item import WishItem

# Имена как в жалобе владельца (заявка №67): в файле первой шла «Спусковое
# устройство Венто Стопор-десантер», в заявке (без ORDER BY) первой оказалась
# «Страховочная привязь Профи Мастер» — порядок ввода/файла должен быть
# восстановлен по id.
_FILE_ORDER_NAMES = [
    "Спусковое устройство Венто Стопор-десантер",
    "Страховочная привязь Профи Мастер",
    "Карабин стальной муфтованный",
    "Верёвка статическая 10мм",
    "Каска защитная альпинистская",
]


def test_relationship_order_by_is_set():
    """Без order_by у relationship SQLAlchemy не гарантирует порядок выдачи —
    эта проверка детерминированно ловит регрессию (order_by стал None/убран),
    не завися от того, воспроизведёт ли конкретный прогон физическую
    перестановку строк в Postgres."""
    # SQLAlchemy: relationship без явного order_by хранит property.order_by == False
    # (не None!) — сравнение с `is not None` эту регрессию НЕ ловит (сам наступил
    # на это при подготовке теста: убрал order_by и test всё равно проходил).
    # Проверяем явно на falsy, чтобы False тоже считался регрессией.
    wish_order = Wish.items.property.order_by
    assert wish_order, (
        "Wish.items relationship потерял order_by — вернётся дефект заявки №67 "
        "(порядок позиций «плывёт» после любого UPDATE)"
    )
    purchase_order = Purchase.items.property.order_by
    assert purchase_order, (
        "Purchase.items relationship потерял order_by — тот же дефект для закупки"
    )


async def _seed_wish_with_items(db_session, test_org, test_user, names):
    w = Wish(
        org_id=test_org.id,
        title="Снаряжение для промальпа",
        status="draft",
        created_by=test_user.id,
    )
    db_session.add(w)
    await db_session.flush()
    for i, name in enumerate(names):
        db_session.add(WishItem(
            wish_id=w.id, item_name=name,
            quantity=1, unit_price=1000 * (i + 1), total_price=1000 * (i + 1),
        ))
    await db_session.commit()
    await db_session.refresh(w)
    return w


@pytest.mark.asyncio
async def test_wish_items_returned_in_id_order_after_update(db_session, client, auth_headers, test_org, test_user):
    w = await _seed_wish_with_items(db_session, test_org, test_user, _FILE_ORDER_NAMES)

    # id-порядок = порядок вставки = порядок файла (проверяем это сразу, до
    # какой-либо правки — иначе дальнейшее сравнение бессмысленно).
    ids_res = await db_session.execute(
        select(WishItem.id, WishItem.item_name).where(WishItem.wish_id == w.id).order_by(WishItem.id)
    )
    rows_by_id = ids_res.all()
    assert [r[1] for r in rows_by_id] == _FILE_ORDER_NAMES
    ordered_ids = [r[0] for r in rows_by_id]

    # Правка средней позиции — ровно то действие, после которого владелец
    # наблюдал «порядок как попало» на проде (любой UPDATE двигает строку
    # физически). Меняем длину текста, чтобы с наибольшей вероятностью
    # заставить Postgres переместить версию строки (non-HOT/иная страница).
    middle = await db_session.get(WishItem, ordered_ids[2])
    middle.item_name = "Карабин стальной муфтованный, оцинкованный, увеличенной прочности"
    await db_session.commit()

    # Явная демонстрация: без ORDER BY физический порядок хранения может не
    # совпадать с id-порядком (тот самый механизм из жалобы). Это just
    # информативная проверка — печатаем расхождение, если оно есть, но не
    # требуем его: физическая перестановка — деталь реализации Postgres,
    # которая не обязана детерминированно воспроизводиться на любой версии/
    # состоянии таблицы. Гарантия, которую действительно проверяет тест ниже —
    # что API отдаёт id-порядок НЕЗАВИСИМО от физического.
    raw = await db_session.execute(
        text("SELECT id FROM wish_items WHERE wish_id = :wid"), {"wid": w.id}
    )
    physical_order = [r[0] for r in raw.all()]
    if physical_order != ordered_ids:
        print(f"[info] физический порядок разошёлся с id-порядком: {physical_order} vs {ordered_ids} — воспроизведён механизм дефекта заявки №67")

    resp = await client.get(f"/api/wishes/{w.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned_ids = [it["id"] for it in body["items"]]
    assert returned_ids == ordered_ids, (
        f"GET /api/wishes/{{id}} вернул позиции не в id-порядке (порядке файла): "
        f"{returned_ids}, ожидался {ordered_ids}"
    )
    returned_names = [it["item_name"] for it in body["items"]]
    assert returned_names[0] == _FILE_ORDER_NAMES[0], (
        "Первой должна остаться позиция, которая была первой в файле "
        f"('{_FILE_ORDER_NAMES[0]}'), а не '{returned_names[0]}'"
    )


@pytest.mark.asyncio
async def test_purchase_items_returned_in_id_order_after_update(db_session, client, auth_headers, test_org, test_user):
    p = Purchase(status="plan_schedule", item_type="goods", item_name="Тестовая закупка снаряжения")
    db_session.add(p)
    await db_session.flush()
    for i, name in enumerate(_FILE_ORDER_NAMES):
        db_session.add(PurchaseItem(
            purchase_id=p.id, item_name=name,
            quantity=1, unit_price=1000 * (i + 1), total_price=1000 * (i + 1),
        ))
    await db_session.commit()
    await db_session.refresh(p)

    ids_res = await db_session.execute(
        select(PurchaseItem.id, PurchaseItem.item_name)
        .where(PurchaseItem.purchase_id == p.id).order_by(PurchaseItem.id)
    )
    rows_by_id = ids_res.all()
    assert [r[1] for r in rows_by_id] == _FILE_ORDER_NAMES
    ordered_ids = [r[0] for r in rows_by_id]

    middle = await db_session.get(PurchaseItem, ordered_ids[2])
    middle.item_name = "Карабин стальной муфтованный, оцинкованный, увеличенной прочности"
    await db_session.commit()

    resp = await client.get(f"/api/purchases/{p.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned_ids = [it["id"] for it in body["items"]]
    assert returned_ids == ordered_ids, (
        f"GET /api/purchases/{{id}} вернул позиции не в id-порядке: "
        f"{returned_ids}, ожидался {ordered_ids}"
    )
