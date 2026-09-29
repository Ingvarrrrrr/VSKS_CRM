"""Прод-инцидент РЕЕ-2026-00962 (сессия 2026-09-29): чек с несколькими
одинаковыми строками (один товар просканирован несколько раз подряд, каждая
строка quantity=1) терял количество — _dedup_purchase_items_core потом видел
их как «точные дубли» (name+total) и просто удалял лишние до одной штуки,
вместо суммирования. Итог позиций закупки расходился с суммой чеков.

Ошибка 1 (эта проверка): строки ВНУТРИ ОДНОГО чека с тем же именем+ценой
должны схлопываться в ОДНУ позицию с суммарным количеством ДО создания
PurchaseItem (app/services/receipts_parsing.py::_merge_duplicate_receipt_items,
вызывается из receipts_creation.py и receipts_recompute.py).

Уточнение владельца: одинаковый товар из РАЗНЫХ чеков — НЕ схлопывается,
остаётся отдельными позициями со своими receipt_id (пример из инцидента:
ARO — 1 шт в чеке А, 4 шт в чеке Б — это две позиции, не одна на 5 шт).

Ошибка 2: ContractItem — одна строка договора на позицию; повторный
PUT /contract-items с той же позицией не должен плодить дубли строк договора
(replace_all_contract_items — atomic delete-then-insert, регрессия здесь же).
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.purchase_item import PurchaseItem
from app.models.contract_item import ContractItem


def _fns_json(fn: str, fd: int, fp: str, items: list[dict]) -> dict:
    """Минимальный валидный payload в форме FNS mobile-app JSON export,
    который понимает app.services.receipts_parsing._parse_fns_json_receipt."""
    return {
        "fiscalDriveNumber": fn,
        "fiscalDocumentNumber": fd,
        "fiscalSign": fp,
        "dateTime": "2026-09-14T12:00:00",
        "totalSum": int(sum(float(it["price"]) * it.get("quantity", 1) for it in items) * 100),
        "userInn": "7700000000",
        "user": "ООО Тест Поставщик",
        "items": [
            {
                "name": it["name"],
                "quantity": it.get("quantity", 1),
                "price": int(float(it["price"]) * 100),  # копейки
                "sum": int(float(it["price"]) * it.get("quantity", 1) * 100),
                "nds": it.get("nds", 6),
            }
            for it in items
        ],
    }


async def _import_json(client, headers, purchase_id, payload):
    import io
    files = {"file": ("check.json", io.BytesIO(__import__("json").dumps(payload).encode("utf-8")), "application/json")}
    resp = await client.post(
        f"/api/purchases/{purchase_id}/receipts/import-json",
        headers=headers, files=files,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_duplicate_lines_within_one_receipt_merge_into_one_position(
    client, auth_headers, db_session, make_purchase,
):
    """4 одинаковые строки (то же имя, та же цена, qty=1 каждая) ОДНОГО
    чека -> ОДНА позиция закупки с quantity=4 и total = сумме строк."""
    p = await make_purchase(purchase_method="advance")

    payload = _fns_json(
        fn="9999000000000001", fd=101, fp="1111111101",
        items=[
            {"name": "19Л ВОДА ARO Б/Г ПЭТ", "price": Decimal("489")},
            {"name": "19Л ВОДА ARO Б/Г ПЭТ", "price": Decimal("489")},
            {"name": "19Л ВОДА ARO Б/Г ПЭТ", "price": Decimal("489")},
            {"name": "19Л ВОДА ARO Б/Г ПЭТ", "price": Decimal("489")},
        ],
    )
    for it in payload["items"]:
        it["quantity"] = 1

    await _import_json(client, auth_headers, p.id, payload)

    rows = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()

    assert len(rows) == 1, f"ожидалась 1 позиция, получено {len(rows)}: {[r.item_name for r in rows]}"
    item = rows[0]
    assert item.quantity == Decimal("4")
    assert item.total_price == Decimal("1956.00") or item.total_price == Decimal("1956")


@pytest.mark.asyncio
async def test_same_item_in_two_different_receipts_stays_two_positions(
    client, auth_headers, db_session, make_purchase,
):
    """Тот же товар (то же имя+цена) в ДВУХ РАЗНЫХ чеках закупки — ДВЕ
    отдельные позиции со своими receipt_id, количество НЕ суммируется через
    чеки (пример владельца: ARO 1 шт в чеке А, 4 шт в чеке Б -> 2 позиции)."""
    p = await make_purchase(purchase_method="advance")

    payload_a = _fns_json(
        fn="9999000000000002", fd=201, fp="2222222201",
        items=[{"name": "19Л ВОДА ARO Б/Г ПЭТ", "price": Decimal("489")}],
    )
    payload_a["items"][0]["quantity"] = 1

    payload_b = _fns_json(
        fn="9999000000000003", fd=202, fp="2222222202",
        items=[{"name": "19Л ВОДА ARO Б/Г ПЭТ", "price": Decimal("489")}] * 4,
    )
    for it in payload_b["items"]:
        it["quantity"] = 1

    await _import_json(client, auth_headers, p.id, payload_a)
    await _import_json(client, auth_headers, p.id, payload_b)

    rows = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
        .order_by(PurchaseItem.id)
    )).scalars().all()

    assert len(rows) == 2, f"ожидалось 2 позиции (по одной на чек), получено {len(rows)}"
    quantities = sorted(float(r.quantity) for r in rows)
    assert quantities == [1.0, 4.0]
    receipt_ids = {r.receipt_id for r in rows}
    assert len(receipt_ids) == 2, "позиции разных чеков обязаны иметь разные receipt_id"


@pytest.mark.asyncio
async def test_put_purchase_preserves_receipt_id_for_cross_receipt_duplicates(
    client, auth_headers, db_session, make_purchase,
):
    """Прод-инцидент РЕЕ-2026-00962 (30.09): PUT /purchases/{id} (форма
    закупки, автосохранение) заменяет ВСЕ позиции целиком из payload — если
    payload не несёт receipt_id (раньше PurchaseItemCreate его вообще не
    принимал — pydantic молча отбрасывал поле, а фронт его и не собирал),
    привязка к чеку терялась, и следующий GET (auto-recompute) мог склеить
    одинаковые (имя, цена) позиции РАЗНЫХ чеков в одну или перепривязать не к
    тому чеку.

    Эта проверка — по правилу владельца «одинаковые строки склеиваются ТОЛЬКО
    внутри одного чека»: две позиции с одинаковым именем+ценой, но из разных
    чеков, отправленные в PUT С их receipt_id, обязаны остаться отдельными
    позициями со СВОИМИ receipt_id — ни дедуп, ни последующий GET (recompute)
    не должны их тронуть."""
    from app.models.purchase_receipt import PurchaseReceipt

    p = await make_purchase(purchase_method="advance")

    receipt_a = PurchaseReceipt(purchase_id=p.id, fiscal_document_number=301, source="manual")
    receipt_b = PurchaseReceipt(purchase_id=p.id, fiscal_document_number=302, source="manual")
    db_session.add_all([receipt_a, receipt_b])
    await db_session.commit()
    await db_session.refresh(receipt_a)
    await db_session.refresh(receipt_b)

    payload = {
        "subject": "Test cross-receipt duplicates",
        "purchase_method": "advance",
        "items": [
            {
                "item_name": "Тариф МТС «Для ноутбука» Услуга/РФ",
                "quantity": "1",
                "unit": "шт",
                "unit_price": "800",
                "total_price": "800",
                "receipt_id": receipt_a.id,
            },
            {
                "item_name": "Тариф МТС «Для ноутбука» Услуга/РФ",
                "quantity": "1",
                "unit": "шт",
                "unit_price": "800",
                "total_price": "800",
                "receipt_id": receipt_b.id,
            },
        ],
    }
    resp = await client.put(f"/api/purchases/{p.id}", json=payload, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2, f"обе позиции обязаны остаться, получено {len(body['items'])}"
    receipt_ids_in_response = sorted(i["receipt_id"] for i in body["items"])
    assert receipt_ids_in_response == sorted([receipt_a.id, receipt_b.id]), (
        f"receipt_id не сохранены из payload: {receipt_ids_in_response}"
    )

    rows = (await db_session.execute(
        select(PurchaseItem).where(PurchaseItem.purchase_id == p.id)
    )).scalars().all()
    assert len(rows) == 2
    assert {r.receipt_id for r in rows} == {receipt_a.id, receipt_b.id}

    # Следующий GET (auto-recompute на этой же закупке) не должен их склеить
    # или перепривязать заново — receipt_id уже верный и полный (нет NULL,
    # который раньше запускал dedup/fuzzy-match шаги на этих строках).
    get_resp = await client.get(f"/api/purchases/{p.id}", headers=auth_headers)
    assert get_resp.status_code == 200
    get_body = get_resp.json()
    assert len(get_body["items"]) == 2
    assert sorted(i["receipt_id"] for i in get_body["items"]) == sorted([receipt_a.id, receipt_b.id])


@pytest.mark.asyncio
async def test_repeated_put_contract_items_does_not_duplicate_rows(
    client, admin_headers, make_purchase_with_items,
):
    """Два подряд PUT /contract-items с одной и той же позицией (тот же
    source_item_id) -> ОДНА строка договора, не две (replace_all_contract_items
    — atomic delete-then-insert)."""
    p = await make_purchase_with_items(items_count=1, item_total=Decimal("500"))

    body = [{
        "source_item_id": None,  # заполним после получения id позиции
        "name": "Item 1",
        "quantity": "1",
        "unit": "шт",
        "unit_price": "500",
        "total": "500",
    }]

    # Получить id позиции ТЗ
    items_resp = await client.get(f"/api/purchases/{p.id}", headers=admin_headers)
    assert items_resp.status_code == 200, items_resp.text

    from sqlalchemy import select as _sel
    # Достаём source_item_id напрямую через отдельный запрос к БД недоступно тут
    # без db_session — используем copy-from-purchase, который создаёт ровно 1↔1
    # связь, а затем проверяем что повторный PUT с тем же source_item_id не
    # плодит вторую строку.
    copy_resp = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase", headers=admin_headers,
    )
    assert copy_resp.status_code == 200, copy_resp.text
    created = copy_resp.json()
    assert len(created) == 1
    source_item_id = created[0]["source_item_id"]

    payload = [{
        "source_item_id": source_item_id,
        "name": "Item 1",
        "quantity": "1",
        "unit": "шт",
        "unit_price": "500",
        "total": "500",
    }]

    put1 = await client.put(
        f"/api/purchases/{p.id}/contract-items", json=payload, headers=admin_headers,
    )
    assert put1.status_code == 200, put1.text
    put2 = await client.put(
        f"/api/purchases/{p.id}/contract-items", json=payload, headers=admin_headers,
    )
    assert put2.status_code == 200, put2.text

    list_resp = await client.get(f"/api/purchases/{p.id}/contract-items", headers=admin_headers)
    assert list_resp.status_code == 200
    rows = list_resp.json()
    matching = [r for r in rows if r["source_item_id"] == source_item_id]
    assert len(matching) == 1, f"ожидалась 1 строка договора на позицию, получено {len(matching)}"


@pytest.mark.asyncio
async def test_put_contract_items_with_duplicate_source_id_in_one_payload_collapses(
    client, admin_headers, make_purchase_with_items,
):
    """Прод-инцидент РЕЕ-2026-00962: PUT с НЕСКОЛЬКИМИ строками, ссылающимися
    на ОДНУ и ту же плановую позицию (тот же source_item_id, одинаковые
    quantity/unit_price — не разбиение) -> сохраняется ОДНА строка, не N."""
    p = await make_purchase_with_items(items_count=1, item_total=Decimal("500"))

    copy_resp = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase", headers=admin_headers,
    )
    assert copy_resp.status_code == 200, copy_resp.text
    source_item_id = copy_resp.json()[0]["source_item_id"]

    # 6 идентичных строк на один и тот же source_item_id в ОДНОМ payload —
    # ровно сценарий инцидента (повторные автосохранения стадии «Договор»
    # после каждого загруженного чека присылали список с накопленными
    # повторами).
    payload = [
        {
            "source_item_id": source_item_id,
            "name": "Item 1",
            "quantity": "1",
            "unit": "шт",
            "unit_price": "500",
            "total": "500",
        }
        for _ in range(6)
    ]

    resp = await client.put(
        f"/api/purchases/{p.id}/contract-items", json=payload, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    matching = [r for r in created if r["source_item_id"] == source_item_id]
    assert len(matching) == 1, f"ожидалась 1 строка договора, получено {len(matching)}"

    list_resp = await client.get(f"/api/purchases/{p.id}/contract-items", headers=admin_headers)
    rows = list_resp.json()
    assert len([r for r in rows if r["source_item_id"] == source_item_id]) == 1


@pytest.mark.asyncio
async def test_put_contract_items_duplicate_source_id_different_qty_rejected(
    client, admin_headers, make_purchase_with_items,
):
    """Дубли того же source_item_id с РАЗНЫМ quantity/unit_price — похоже на
    ошибочно отправленное разбиение, не безопасно угадывать какую строку
    оставить -> 409 с понятной причиной, ничего не сохраняется молча."""
    p = await make_purchase_with_items(items_count=1, item_total=Decimal("500"))
    copy_resp = await client.post(
        f"/api/purchases/{p.id}/contract-items/copy-from-purchase", headers=admin_headers,
    )
    source_item_id = copy_resp.json()[0]["source_item_id"]

    payload = [
        {"source_item_id": source_item_id, "name": "Item 1", "quantity": "1",
         "unit": "шт", "unit_price": "300", "total": "300"},
        {"source_item_id": source_item_id, "name": "Item 1", "quantity": "1",
         "unit": "шт", "unit_price": "200", "total": "200"},
    ]
    resp = await client.put(
        f"/api/purchases/{p.id}/contract-items", json=payload, headers=admin_headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["details"]["code"] == "CONTRACT_ITEM_DUPLICATE_SOURCE_AMBIGUOUS"
