"""Автотесты для закупочной комиссии субсидии, рассмотрения заявок с ЭТП и генератора протокола ВСКС."""
import json
import os
import io
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import docx
import pytest
from fastapi import UploadFile

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.platform_publication import PlatformPublication
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.user import User
from app.routers.publication_results import (
    ApplyWinnerRequest,
    SaveResultsRequest,
    apply_winner_to_purchase,
    import_protocol_file,
    save_publication_results,
    upload_application_document,
)
from app.schemas.subsidies import SubsidyCreate, SubsidyOut, SubsidyUpdate
from app.services.documents.protocol_vsks import build_vsks_protocol_docx
from app.services.roseltorg.analog_matcher import build_rejection_reason_for_analogs
from app.services.roseltorg.protocol_parser import parse_protocol_file
from app.services.roseltorg.results import recalculate_places
from app.services.subsidy_write import apply_subsidy_update


def test_subsidy_schema_commission_members():
    """Тест сериализации и десериализации состава комиссии в Pydantic-схемах."""
    members_list = [
        {"full_name": "Цыганов Игорь Александрович", "role": "Председатель Комиссии"},
        {"full_name": "Иванова Ирина Владиславовна", "role": "Член Комиссии"},
    ]
    # SubsidyOut принимает JSON-строку из БД и парсит в список словарей
    out = SubsidyOut(
        id=1,
        name="Тестовая субсидия",
        year=2026,
        commission_order_number="86",
        commission_order_date=date(2024, 12, 25),
        commission_members=json.dumps(members_list, ensure_ascii=False),
    )
    assert out.commission_order_number == "86"
    assert out.commission_order_date == date(2024, 12, 25)
    assert isinstance(out.commission_members, list)
    assert len(out.commission_members) == 2
    assert out.commission_members[0]["full_name"] == "Цыганов Игорь Александрович"

    # SubsidyCreate / SubsidyUpdate корректно принимают список
    create = SubsidyCreate(
        name="Субсидия 2026",
        year=2026,
        commission_order_number="43",
        commission_order_date=date(2025, 8, 14),
        commission_members=members_list,
    )
    assert create.commission_order_number == "43"
    assert len(create.commission_members) == 2


@pytest.mark.asyncio
async def test_apply_subsidy_update_commission():
    """Тест сохранения и сериализации полей комиссии в сервисе apply_subsidy_update."""
    sub = Subsidy(name="Субсидия для протоколов", year=2026, status="approved")
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_res
    user = User(id=1, username="test", role="admin")
    update_data = {
        "commission_order_number": "101",
        "commission_order_date": date(2026, 1, 15),
        "commission_members": [
            {"full_name": "Слуцкий Роман Олегович", "role": "Председатель Комиссии"},
            {"full_name": "Лягин Андрей Анатольевич", "role": "Член Комиссии"},
        ],
    }
    await apply_subsidy_update(db, user, sub, update_data)
    assert sub.commission_order_number == "101"
    assert sub.commission_order_date == date(2026, 1, 15)
    assert isinstance(sub.commission_members, str)
    loaded_members = json.loads(sub.commission_members)
    assert len(loaded_members) == 2
    assert loaded_members[0]["role"] == "Председатель Комиссии"


def test_recalculate_places():
    """Тест пересчёта мест: сортировка по цене, отклонённым place = None."""
    apps = [
        {"application_number": "1", "price_with_vat": 200000.0, "admitted": True, "submitted_at": "10.05.2026 10:00"},
        {"application_number": "2", "price_with_vat": 150000.0, "admitted": True, "submitted_at": "10.05.2026 11:00"},
        {"application_number": "3", "price_with_vat": 120000.0, "admitted": False, "rejection_reason": "Нет ЭЦП"},
        {"application_number": "4", "price_with_vat": 180000.0, "admitted": True, "submitted_at": "10.05.2026 12:00"},
    ]
    res = recalculate_places(apps)
    # 2 (150k) -> 1 место, 4 (180k) -> 2 место, 1 (200k) -> 3 место, 3 -> None
    app2 = next(a for a in res if a["application_number"] == "2")
    app4 = next(a for a in res if a["application_number"] == "4")
    app1 = next(a for a in res if a["application_number"] == "1")
    app3 = next(a for a in res if a["application_number"] == "3")

    assert app2["place"] == 1
    assert app4["place"] == 2
    assert app1["place"] == 3
    assert app3["place"] is None


def test_parse_real_protocol_files():
    """Тест парсинга реальных образцов файлов протоколов с площадок."""
    p_alp = r"C:\Users\1\Downloads\Telegram Desktop\Протокол B3004261856309 Альп .docx"
    if os.path.exists(p_alp):
        with open(p_alp, "rb") as f:
            res = parse_protocol_file(p_alp, f.read())
        assert res["registration_number"] == "B3004261856309"
        assert res["total_applications"] == 5
        assert res["admitted_count"] == 2
        assert res["rejected_count"] == 3
        # Победитель с ценой 123 000 руб.
        winner = next(a for a in res["applications"] if a["place"] == 1)
        assert winner["price_with_vat"] == 123000.0
        assert "ГОРНОЛЫЖНЫЙ" in winner["supplier_name"]

    p_vsks_new = r"C:\Users\1\Downloads\Telegram Desktop\Протокол ВСКС new.docx"
    if os.path.exists(p_vsks_new):
        with open(p_vsks_new, "rb") as f:
            res2 = parse_protocol_file(p_vsks_new, f.read())
        assert res2["total_applications"] == 1
        assert res2["admitted_count"] == 1
        assert res2["rejected_count"] == 0
        assert res2["applications"][0]["price_with_vat"] == 1430000.0
        assert res2["commission_order_number"] == "86"


def test_build_vsks_protocol_docx_all_three_scenarios():
    """Тест генерации протокола ВСКС для всех трёх сценариев."""
    purchase = MagicMock(spec=Purchase)
    purchase.id = 777
    purchase.subject = "Поставка аварийно-спасательного снаряжения"
    purchase.estimated_price = Decimal("500000.00")
    purchase.procurement_notice_number = "B3004261856309"
    purchase.request_type = "request_proposals"
    purchase.fabrikant_no_nmcd = False
    purchase.org_id = 1
    purchase.customer_contractor_id = None

    subsidy = MagicMock(spec=Subsidy)
    subsidy.commission_order_number = "86"
    subsidy.commission_order_date = date(2024, 12, 25)
    subsidy.commission_members = [
        {"full_name": "Цыганов Игорь Александрович", "role": "Председатель Комиссии"},
        {"full_name": "Иванова Ирина Владиславовна", "role": "Член Комиссии"},
    ]

    org = MagicMock(spec=Organization)
    org.name = "ВСЕРОССИЙСКИЙ СТУДЕНЧЕСКИЙ КОРПУС СПАСАТЕЛЕЙ"
    org.short_name = "ВОМО «ВСКС»"
    org.address = "119454, город Москва, пр-кт Вернадского, д. 78 строен 8"

    # Сценарий 1: Ровно 1 допущенная заявка (несостоявшаяся с единственной заявкой)
    res_1 = {
        "registration_number": "B3004261856309",
        "notice_date": "2026-04-30",
        "applications": [
            {
                "application_number": "1",
                "supplier_name": "ООО «СПАСАТЕЛЬ»",
                "inn": "7701234567",
                "kpp": "770101001",
                "price_with_vat": 1430000.0,
                "vat_label": "в т.ч. НДС 20%",
                "admitted": True,
                "place": 1,
            }
        ],
    }
    bytes_1 = build_vsks_protocol_docx(purchase, subsidy, org, None, res_1)
    doc1 = docx.Document(io.BytesIO(bytes_1))
    full_text_1 = "\n".join(p.text for p in doc1.paragraphs)
    assert "ПРОТОКОЛ" in full_text_1
    assert "РАБОТЫ КОМИССИИ" in full_text_1
    assert "признать закупку несостоявшейся, по причине наличия только одной заявки" in full_text_1
    assert "ООО «СПАСАТЕЛЬ»" in full_text_1
    assert "1 430 000,00 руб." in full_text_1
    assert "миллион" in full_text_1

    # Сценарий 2: >= 2 допущенных заявок (состоялась)
    res_2 = {
        "registration_number": "B3004261856309",
        "notice_date": "2026-04-30",
        "applications": [
            {
                "application_number": "1",
                "supplier_name": "ООО «СПАСАТЕЛЬ»",
                "inn": "7701234567",
                "price_with_vat": 120000.0,
                "admitted": True,
                "place": 1,
            },
            {
                "application_number": "2",
                "supplier_name": "ООО «ЭВОЛЮЦИЯ»",
                "inn": "0278938329",
                "price_with_vat": 150000.0,
                "admitted": True,
                "place": 2,
            },
            {
                "application_number": "3",
                "supplier_name": "ИП Силивря",
                "inn": "231517543049",
                "price_with_vat": 110000.0,
                "admitted": False,
                "rejection_reason": "Заявка не подписана",
                "place": None,
            },
        ],
    }
    bytes_2 = build_vsks_protocol_docx(purchase, subsidy, org, None, res_2)
    doc2 = docx.Document(io.BytesIO(bytes_2))
    full_text_2 = "\n".join(p.text for p in doc2.paragraphs)
    assert "5.1. Признать победителем закупки ООО «СПАСАТЕЛЬ»" in full_text_2
    assert "5.2. Заказчик вправе заключить договор с победителем закупки." in full_text_2
    assert "Количество поданных на ЭТП заявок на участие в закупке: 3" in full_text_2
    assert "Количество отклоненных заявок участников: 1" in full_text_2
    assert "Количество заявок участников, признанных соответствующими требованиям закупочной документации: 2" in full_text_2

    # Сценарий 3: 0 допущенных заявок
    res_3 = {
        "registration_number": "B3004261856309",
        "notice_date": "2026-04-30",
        "applications": [
            {
                "application_number": "1",
                "supplier_name": "ООО «БРАК»",
                "price_with_vat": 100000.0,
                "admitted": False,
                "rejection_reason": "Не соответствует ТЗ",
            }
        ],
    }
    bytes_3 = build_vsks_protocol_docx(purchase, subsidy, org, None, res_3)
    doc3 = docx.Document(io.BytesIO(bytes_3))
    full_text_3 = "\n".join(p.text for p in doc3.paragraphs)
    assert "Признать закупку несостоявшейся по причине отсутствия заявок" in full_text_3


@pytest.mark.asyncio
async def test_save_and_apply_winner_logic():
    """Тест сохранения результатов и авто-применения победителя в закупку."""
    pub = PlatformPublication(
        id=10,
        purchase_id=777,
        platform="roseltorg_rb",
        platform_number="B9999999999",
    )
    purchase = Purchase(
        id=777,
        subject="Поставка тестового оборудования",
        planned_total_price=Decimal("150000.00"),
        status="ordered",
    )
    user = User(id=1, username="test", role="admin")

    db = AsyncMock()

    async def fake_get(model, pk):
        if model == PlatformPublication and pk == 10:
            return pub
        if model == Purchase and pk == 777:
            return purchase
        return None

    db.get = AsyncMock(side_effect=fake_get)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    mock_ensure = AsyncMock(return_value=purchase)
    with patch("app.routers.publication_results.ensure_purchase_visible", new=mock_ensure):
        save_req = SaveResultsRequest(
            registration_number="B9999999999",
            protocol_number="№B9999999999-1",
            protocol_date="2026-05-15",
            meeting_time="16:30",
            meeting_address="г. Москва, пр-кт Вернадского",
            commission_order_number="43",
            commission_order_date="2025-08-14",
            commission_members=[{"full_name": "Цыганов И.А.", "role": "Председатель Комиссии"}],
            applications=[
                {
                    "application_number": "1",
                    "supplier_name": "ООО Победитель",
                    "supplier_short_name": "ООО Победитель",
                    "inn": "7704410937",
                    "kpp": "771901001",
                    "price_with_vat": 123000.0,
                    "vat_label": "в т.ч. НДС 20%",
                    "admitted": True,
                },
                {
                    "application_number": "2",
                    "supplier_name": "ООО Отклонённый",
                    "inn": "231517543049",
                    "price_with_vat": 110000.0,
                    "admitted": False,
                    "rejection_reason": "Заявка не подписана",
                },
            ],
        )
        res_save = await save_publication_results(pub_id=10, body=save_req, db=db, current_user=user)
        assert res_save["ok"] is True
        assert res_save["results"]["admitted_count"] == 1
        assert res_save["results"]["rejected_count"] == 1
        assert res_save["results"]["applications"][0]["place"] == 1

        # Проверяем перенос победителя в закупку
        res_winner = await apply_winner_to_purchase(pub_id=10, db=db, current_user=user)
        assert res_winner["ok"] is True
        assert res_winner["contract_price"] == 123000.0
        assert float(purchase.contract_price) == 123000.0
        assert purchase.procurement_protocol_number == "№B9999999999-1"


@pytest.mark.asyncio
async def test_import_protocol_file_router():
    """Тест эндпоинта импорта файла протокола через UploadFile."""
    pub = PlatformPublication(
        id=10,
        purchase_id=777,
        platform="roseltorg_rb",
        platform_number="B3004261856309",
    )
    user = User(id=1, username="test", role="admin")
    db = AsyncMock()
    db.get = AsyncMock(return_value=pub)

    p_alp = r"C:\Users\1\Downloads\Telegram Desktop\Протокол B3004261856309 Альп .docx"
    if os.path.exists(p_alp):
        with open(p_alp, "rb") as f:
            content = f.read()
        file_mock = UploadFile(filename="Протокол B3004261856309 Альп .docx", file=io.BytesIO(content))

        mock_ensure = AsyncMock()
        with patch("app.routers.publication_results.ensure_purchase_visible", new=mock_ensure):
            res_import = await import_protocol_file(pub_id=10, file=file_mock, db=db, current_user=user)
            assert res_import["ok"] is True
            assert res_import["results"]["registration_number"] == "B3004261856309"
            assert res_import["results"]["admitted_count"] == 2


def test_parse_ole2_doc_protocol_real():
    """Тест парсинга реального бинарного .doc протокола Росэлторга B1203261732335."""
    p_doc = r"C:\Users\1\Downloads\Telegram Desktop\2026-03-31 Протокол B1203261732335.doc"
    if not os.path.exists(p_doc):
        pytest.skip("Файл протокола .doc не найден")

    with open(p_doc, "rb") as f:
        res = parse_protocol_file(p_doc, f.read())

    assert res["registration_number"] == "B1203261732335"
    assert res["notice_date"] == "2026-03-12"
    assert "B1203261732335" in res["protocol_number"]
    assert res["commission_order_number"] == "1/з-25"
    assert res["commission_order_date"] == "2025-02-18"
    assert len(res["commission_members"]) >= 3
    # Проверяем председателя комиссии
    chair = next((m for m in res["commission_members"] if "председатель" in m["role"].lower()), None)
    assert chair is not None
    assert "Артеева" in chair["full_name"]


def test_parse_tkp_pdf_with_alternatives_real():
    """Тест парсинга реального PDF ТКП с аналогами (ИП Колесников Н.Ю., 14 позиций, 486 920 руб.)."""
    p_tkp = r"C:\Users\1\Downloads\Telegram Desktop\23_10_26_Приложение_№2_Форма_технико_коммерческого_предложения_.pdf"
    if not os.path.exists(p_tkp):
        pytest.skip("Файл ТКП .pdf не найден")

    with open(p_tkp, "rb") as f:
        res = parse_protocol_file(p_tkp, f.read())

    app = res.get("application") or (res.get("applications", [{}])[0] if res.get("applications") else {})
    assert "Колесников" in app.get("supplier_name", "")
    assert app.get("inn") == "665405057672"
    assert app.get("price_with_vat") == 486920.0

    positions = app.get("positions", [])
    assert len(positions) == 14

    # Проверяем распознавание аналогов
    pos1 = next(p for p in positions if p["item_num"] == 1)
    assert pos1["is_alternative"] is True
    assert "СЛЕДОПЫТ" in pos1["offered_name"]

    pos4 = next(p for p in positions if p["item_num"] == 4)
    assert pos4["is_alternative"] is True
    assert "Naturehike" in pos4["offered_name"] or "Naturehike" in pos4["offered_specs"]

    pos11 = next(p for p in positions if p["item_num"] == 11)
    assert pos11["is_alternative"] is True
    assert "Grizzly" in pos11["offered_name"] or "Grizzly" in pos11["offered_specs"]


def test_parse_multi_supplier_xlsx_and_forma_docx_real():
    """Тест парсинга сводного Протокол итоговый.xlsx и Форма_заявки.docx."""
    p_xlsx = r"C:\Users\1\Downloads\Протокол итоговый.xlsx"
    if os.path.exists(p_xlsx):
        with open(p_xlsx, "rb") as f:
            res_xlsx = parse_protocol_file(p_xlsx, f.read())
        apps = res_xlsx.get("applications", [])
        assert len(apps) == 4
        # 3 допущены, 1 отклонен по аналогам (Колесников)
        assert res_xlsx["admitted_count"] == 3
        assert res_xlsx["rejected_count"] == 1
        kolesnikov = next((a for a in apps if "665405057672" in a.get("inn", "") or "Колесников" in a.get("supplier_name", "")), None)
        assert kolesnikov is not None
        assert kolesnikov["admitted"] is False
        assert "не соответствуют ТЗ" in kolesnikov["rejection_reason"]
        # Отклонённые позиции по п. 4, п. 6...
        rej_pos = [p for p in kolesnikov["positions"] if p.get("compliance_status") == "analog_rejected"]
        assert len(rej_pos) >= 2

    p_docx = r"C:\Users\1\Downloads\Telegram Desktop\Форма_заявки.docx"
    if os.path.exists(p_docx):
        with open(p_docx, "rb") as f:
            res_docx = parse_protocol_file(p_docx, f.read())
        app_docx = res_docx.get("application", {})
        assert len(app_docx.get("positions", [])) >= 10


@pytest.mark.asyncio
async def test_analog_rejection_reason_and_winner_apply_with_alternatives():
    """Тест автоформирования причины отклонения аналогов и переноса принятых аналогов победителя."""
    # 1. Формирование причины отклонения
    sample_positions = [
        {"item_num": 1, "compliance_status": "compliant", "compliance_note": ""},
        {"item_num": 4, "compliance_status": "analog_rejected", "compliance_note": "объём 11 л вместо 15 л"},
        {"item_num": 6, "compliance_status": "analog_rejected", "compliance_note": ""},
    ]
    reason = build_rejection_reason_for_analogs(sample_positions)
    assert "п. 4" in reason
    assert "п. 6" in reason
    assert "объём 11 л вместо 15 л" in reason
    assert "не соответствуют техническому заданию" in reason

    # 2. Перенос попозиционных цен и принятых аналогов победителя в PurchaseItem
    purchase = MagicMock(spec=Purchase)
    purchase.id = 555
    purchase.contract_price = None
    purchase.procurement_protocol_number = None

    item1 = MagicMock(spec=PurchaseItem)
    item1.id = 101
    item1.item_name = "Газовая плитка Turbojet"
    item1.accepted_name = None
    item1.unit_price = Decimal("1000.00")
    item1.total_price = Decimal("2000.00")
    item1.final_unit_price = None
    item1.final_total = None
    item1.tz_description = ""

    item2 = MagicMock(spec=PurchaseItem)
    item2.id = 102
    item2.item_name = "Палатка кемпинговая"
    item2.accepted_name = None
    item2.unit_price = Decimal("8000.00")
    item2.total_price = Decimal("16000.00")
    item2.final_unit_price = None
    item2.final_total = None
    item2.tz_description = ""

    winner_app = {
        "supplier_name": "ООО Снабжение",
        "inn": "7701234567",
        "price_with_vat": 18200.0,
        "admitted": True,
        "place": 1,
        "positions": [
            {
                "item_num": 1,
                "purchase_item_id": 101,
                "offered_name": "Плита наст. газовая Следопыт",
                "offered_specs": "Следопыт модель 1",
                "unit_price": 1100.0,
                "total_price": 2200.0,
                "is_alternative": True,
                "compliance_status": "analog_accepted",
            },
            {
                "item_num": 2,
                "purchase_item_id": 102,
                "offered_name": "Палатка кемпинговая",
                "offered_specs": "По ТЗ",
                "unit_price": 8000.0,
                "total_price": 16000.0,
                "is_alternative": False,
                "compliance_status": "compliant",
            },
        ],
    }

    pub = PlatformPublication(
        id=20,
        purchase_id=555,
        platform="roseltorg_rb",
        platform_number="B1234567",
        results_data=json.dumps({"protocol_number": "№B1234567-1", "applications": [winner_app]}, ensure_ascii=False),
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=pub)

    # Mock execute для Contractor, PurchaseItem и ContractItem
    async def mock_execute(stmt, *args, **kwargs):
        res = MagicMock()
        stmt_str = str(stmt).lower()
        if "from contractors" in stmt_str:
            ctr = MagicMock()
            ctr.id = 88
            ctr.name = "ООО Снабжение"
            res.scalars.return_value.first.return_value = ctr
        elif "from purchase_items" in stmt_str:
            res.scalars.return_value.all.return_value = [item1, item2]
        else:
            res.scalars.return_value.all.return_value = []
            res.scalars.return_value.first.return_value = None
        return res

    db.execute = AsyncMock(side_effect=mock_execute)

    user = User(id=1, username="test", role="admin")

    with patch("app.routers.publication_results.ensure_purchase_visible", return_value=purchase):
        apply_req = ApplyWinnerRequest(apply_positions_prices=True, apply_accepted_alternatives=True)
        res = await apply_winner_to_purchase(pub_id=20, body=apply_req, db=db, current_user=user)

    assert res["ok"] is True
    assert res["contractor_id"] == 88
    assert res["contract_price"] == 18200.0
    assert res["updated_positions_count"] == 2
    assert res["applied_alternatives_count"] == 1
    # Проверяем перенос цен и принятого аналога в item1
    assert item1.unit_price == Decimal("1100.0")
    assert item1.total_price == Decimal("2200.0")
    assert item1.accepted_name == "Плита наст. газовая Следопыт"


def test_parse_protocol_file_docx_application():
    """Тест вызова parse_protocol_file на DOCX форме заявки (проверка отсутствия NameError и распознавания)."""
    import docx

    doc = docx.Document()
    doc.add_paragraph("ФОРМА ЗАЯВКИ НА УЧАСТИЕ В ЗАКУПКЕ")
    # Таблица 0: Сведения об участнике
    t0 = doc.add_table(rows=2, cols=2)
    t0.rows[0].cells[0].text = "Наименование участника"
    t0.rows[0].cells[1].text = "ООО 'РосСпецТех'"
    t0.rows[1].cells[0].text = "ИНН участника"
    t0.rows[1].cells[1].text = "7722998877"

    # Таблица 1: Предложение по позициям
    t1 = doc.add_table(rows=2, cols=6)
    hdr = t1.rows[0]
    hdr.cells[0].text = "№"
    hdr.cells[1].text = "Наименование"
    hdr.cells[2].text = "Ед. изм."
    hdr.cells[3].text = "Кол-во"
    hdr.cells[4].text = "Цена за ед."
    hdr.cells[5].text = "Сумма"

    r1 = t1.rows[1]
    r1.cells[0].text = "1"
    r1.cells[1].text = "Спальный мешок Экстрим-2 (Аналог)"
    r1.cells[2].text = "шт"
    r1.cells[3].text = "5"
    r1.cells[4].text = "3000,00"
    r1.cells[5].text = "15000,00"

    bio = io.BytesIO()
    doc.save(bio)
    content = bio.getvalue()

    p_items = [{"id": 1, "name": "Спальный мешок арктический", "quantity": 5}]
    parsed = parse_protocol_file("Форма_заявки.docx", content, purchase_items=p_items)

    assert parsed.get("is_single_application") is True
    app_data = parsed["application"]
    assert "РосСпецТех" in app_data.get("supplier_name", "")
    assert app_data.get("inn") == "7722998877"
    assert app_data.get("price_with_vat") == 15000.0
    assert len(app_data.get("positions", [])) == 1
    pos = app_data["positions"][0]
    assert "Спальный мешок Экстрим-2" in pos["offered_name"]
    assert pos["is_alternative"] is True


@pytest.mark.asyncio
async def test_upload_application_document_route():
    """Тест эндпоинта upload_application_document: прикрепление ТКП к конкретной заявке и пересчёт."""
    purchase = MagicMock(id=77, is_archived=False)
    pub = PlatformPublication(
        id=33,
        purchase_id=77,
        platform="roseltorg_rb",
        platform_number="B555444",
        results_data=json.dumps({
            "protocol_number": "№B555444-1",
            "applications": [
                {
                    "application_number": "1",
                    "supplier_name": "Заявка № 1",
                    "price_with_vat": 50000.0,
                    "admitted": True,
                    "documents": [],
                }
            ],
        }, ensure_ascii=False),
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=pub)
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    user = User(id=1, username="test", role="admin")

    # Создаём фиктивный docx файл
    import docx
    doc = docx.Document()
    doc.add_paragraph("ФОРМА ЗАЯВКИ")
    t0 = doc.add_table(rows=1, cols=2)
    t0.rows[0].cells[0].text = "Наименование"
    t0.rows[0].cells[1].text = "ООО Реальный Поставщик"
    bio = io.BytesIO()
    doc.save(bio)
    file_bytes = bio.getvalue()

    upload_file = UploadFile(
        filename="ТКП_Участник_1.docx",
        file=io.BytesIO(file_bytes),
    )

    with patch("app.routers.publication_results.ensure_purchase_visible", return_value=purchase), \
         patch("app.routers.publication_results.get_purchase_items_brief", return_value=[]), \
         patch("app.routers.publication_results.save_publication_file", return_value=("safe_tkp.docx", "/api/publications/33/results/files/safe_tkp.docx", file_bytes)):

        res = await upload_application_document(
            pub_id=33,
            app_idx=0,
            file=upload_file,
            db=db,
            current_user=user,
        )

    assert res["ok"] is True
    assert res["pub_id"] == 33
    saved_results = res["results"]
    assert len(saved_results["applications"]) == 1
    target_app = saved_results["applications"][0]
    # Проверяем, что обновилось наименование и прикрепился документ
    assert "Реальный Поставщик" in target_app["supplier_name"]
    assert len(target_app["documents"]) == 1
    assert target_app["documents"][0]["name"] == "ТКП_Участник_1.docx"


def test_build_and_parse_standardized_tkp_xlsx_roundtrip():
    """Тест генерации стандартизированного бланка ТКП и детерминированного парсинга заполненного файла."""
    import openpyxl
    from app.services.documents.tkp_form_xlsx import build_standardized_tkp_xlsx

    rows = [
        {"item_id": 101, "name": "Палатка 4-местная", "description": "Водонепроницаемость 3000 мм", "quantity": 2, "unit": "шт.", "unit_price": 15000.0},
        {"item_id": 102, "name": "Фонарь аккумуляторный", "description": "Световой поток не менее 1000 лм, IP65", "quantity": 5, "unit": "шт.", "unit_price": 2000.0},
        {"item_id": 103, "name": "Спальный мешок", "description": "Температура комфорта -5°C", "quantity": 10, "unit": "шт.", "unit_price": 4000.0},
    ]

    xlsx_bytes = build_standardized_tkp_xlsx(rows, purchase_id=555, purchase_subject="Поставка снаряжения", customer_name="ВСКС")
    assert len(xlsx_bytes) > 1000

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active

    # Заполняем реквизиты поставщика
    ws["C4"] = "ООО «ТехноСнаб»"
    ws["C5"] = "7701234567"
    ws["C6"] = "770101001"
    ws["C7"] = "+7 (495) 123-45-67, info@technosnab.ru"
    ws["C8"] = "в т.ч. НДС 20%"
    ws["C9"] = 30
    ws["C10"] = "исх. № 42/26 от 15.11.2026"

    # Заполняем цены единиц
    ws["I13"] = 1500.0
    ws["I14"] = 2400.0
    ws["I15"] = 500.0

    # Позиция 2 — аналог (эквивалент)
    ws["G14"] = "Эквивалент (аналог)"
    ws["H14"] = "Фонарь ФОС-3М (световой поток 1200 лм, IP65)"

    buf = io.BytesIO()
    wb.save(buf)
    filled_bytes = buf.getvalue()

    parsed = parse_protocol_file("Приложение_2_Форма_ТКП.xlsx", filled_bytes)

    assert parsed.get("is_single_application") is True
    app = parsed.get("application") or parsed["applications"][0]

    assert app["supplier_name"] == "ООО «ТехноСнаб»"
    assert app["inn"] == "7701234567"
    assert app["kpp"] == "770101001"
    assert app["contacts"] == "+7 (495) 123-45-67, info@technosnab.ru"
    assert app["vat_label"] == "в т.ч. НДС 20%"
    assert app["admitted"] is True
    assert app["rejection_reason"] == ""
    assert app["validity_days"] == 30

    # Расчёт итоговой суммы: 2*1500 + 5*2400 + 10*500 = 3000 + 12000 + 5000 = 20000.0
    assert app["price"] == 20000.0
    assert app["price_with_vat"] == 20000.0

    assert len(app["positions"]) == 3
    pos1 = app["positions"][0]
    assert pos1["is_alternative"] is False
    assert pos1["compliance_status"] == "compliant"
    assert pos1["total_price"] == 3000.0

    pos2 = app["positions"][1]
    assert pos2["is_alternative"] is True
    assert pos2["compliance_status"] == "analog_pending"
    assert pos2["decision"] == "analog_pending"
    assert "ФОС-3М" in pos2["offered_specs"]
    assert pos2["total_price"] == 12000.0

    pos3 = app["positions"][2]
    assert pos3["is_alternative"] is False
    assert pos3["compliance_status"] == "compliant"
    assert pos3["total_price"] == 5000.0


def test_standardized_tkp_xlsx_short_validity_auto_rejected():
    """Тест автоматического отклонения заявки при сроке действия ТКП менее 30 рабочих дней."""
    import openpyxl
    from app.services.documents.tkp_form_xlsx import build_standardized_tkp_xlsx

    rows = [
        {"item_id": 1, "name": "Бензопила", "description": "Мощность 2 кВт", "quantity": 1, "unit": "шт.", "unit_price": 25000.0},
    ]

    xlsx_bytes = build_standardized_tkp_xlsx(rows, purchase_id=100)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active

    ws["C4"] = "ООО «СпецИнструмент»"
    ws["C5"] = "7722334455"
    ws["C9"] = 15  # Недопустимо короткий срок (< 30 раб. дн.)
    ws["I13"] = 23000.0

    buf = io.BytesIO()
    wb.save(buf)
    filled_bytes = buf.getvalue()

    parsed = parse_protocol_file("Приложение_2_Форма_ТКП.xlsx", filled_bytes)
    assert parsed.get("is_single_application") is True
    app = parsed.get("application") or parsed["applications"][0]

    assert app["admitted"] is False
    assert "15 раб. дн." in app["rejection_reason"]
    assert "не менее 30 рабочих дней" in app["rejection_reason"]


def test_build_and_parse_standardized_tkp_pdf_roundtrip():
    """Тест 100%-точного roundtrip генерации и парсинга заполняемого PDF-бланка ТКП (AcroForm)."""
    import fitz
    from app.services.documents.tkp_form_pdf import build_standardized_tkp_pdf

    rows = [
        {"item_id": 10, "name": "Жилет спасательный", "description": "ГОСТ Р 58108-2019, 100Н", "quantity": 10, "unit": "шт.", "unit_price": 1500.0},
        {"item_id": 11, "name": "Каска защитная", "description": "Каска пожарного КП-2020", "quantity": 4, "unit": "шт.", "unit_price": 4000.0},
        {"item_id": 12, "name": "Перчатки диэлектрические", "description": "Класс 0, бесшовные", "quantity": 15, "unit": "пар", "unit_price": 900.0},
    ]

    pdf_bytes = build_standardized_tkp_pdf(rows, purchase_id=777, purchase_subject="Поставка СИЗ", customer_name="ВСКС")
    assert pdf_bytes.startswith(b"%PDF")

    # Поставщик открывает интерактивный PDF и заполняет виджеты
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    p0 = doc[0]

    widget_map = {w.field_name: w for w in p0.widgets()}
    assert "supplier_name" in widget_map
    assert "inn" in widget_map
    assert "item_0_unit_price" in widget_map

    widget_map["supplier_name"].field_value = "ООО «СпецПоставка»"
    widget_map["supplier_name"].update()

    widget_map["inn"].field_value = "7722334455"
    widget_map["inn"].update()

    widget_map["vat_rate"].field_value = "в т.ч. НДС 20%"
    widget_map["vat_rate"].update()

    widget_map["validity_days"].field_value = "30"
    widget_map["validity_days"].update()

    widget_map["item_0_unit_price"].field_value = "1200"
    widget_map["item_0_unit_price"].update()

    widget_map["item_1_unit_price"].field_value = "3500"
    widget_map["item_1_unit_price"].update()
    widget_map["item_1_offer_type"].field_value = "Эквивалент (аналог)"
    widget_map["item_1_offer_type"].update()
    widget_map["item_1_offered_specs"].field_value = "Каска защитная КЗ-Профи (ударопрочный ABS)"
    widget_map["item_1_offered_specs"].update()

    widget_map["item_2_unit_price"].field_value = "800"
    widget_map["item_2_unit_price"].update()

    filled_pdf_bytes = doc.tobytes()

    # Парсим через единую точку входа parse_protocol_file
    parsed = parse_protocol_file("Приложение_2_Форма_ТКП.pdf", filled_pdf_bytes)
    assert parsed.get("is_single_application") is True
    app = parsed.get("application") or parsed["applications"][0]

    assert app["supplier_name"] == "ООО «СпецПоставка»"
    assert app["inn"] == "7722334455"
    assert app["vat_label"] == "в т.ч. НДС 20%"
    assert app["validity_days"] == 30
    assert app["admitted"] is True
    assert app["rejection_reason"] == ""

    # Расчёт суммы: 10*1200 + 4*3500 + 15*800 = 12000 + 14000 + 12000 = 38000.0
    assert app["price"] == 38000.0
    assert app["price_with_vat"] == 38000.0

    assert len(app["positions"]) == 3
    pos0 = app["positions"][0]
    assert pos0["item_num"] == 1
    assert pos0["purchase_item_id"] == 10
    assert pos0["requested_name"] == "Жилет спасательный"
    assert pos0["unit_price"] == 1200.0
    assert pos0["total_price"] == 12000.0
    assert pos0["is_alternative"] is False
    assert pos0["decision"] == "accepted"

    pos1 = app["positions"][1]
    assert pos1["item_num"] == 2
    assert pos1["purchase_item_id"] == 11
    assert pos1["requested_name"] == "Каска защитная"
    assert pos1["unit_price"] == 3500.0
    assert pos1["total_price"] == 14000.0
    assert pos1["is_alternative"] is True
    assert pos1["decision"] == "analog_pending"
    assert pos1["compliance_status"] == "analog_pending"
    assert "КЗ-Профи" in pos1["offered_specs"]

    pos2 = app["positions"][2]
    assert pos2["item_num"] == 3
    assert pos2["purchase_item_id"] == 12
    assert pos2["unit_price"] == 800.0
    assert pos2["total_price"] == 12000.0
    assert pos2["is_alternative"] is False


def test_standardized_tkp_pdf_short_validity_auto_rejected():
    """Тест автоотклонения при сроке действия ТКП в PDF менее 30 дней."""
    import fitz
    from app.services.documents.tkp_form_pdf import build_standardized_tkp_pdf

    rows = [{"item_id": 1, "name": "Фонарь", "description": "Светодиодный", "quantity": 2, "unit": "шт.", "unit_price": 500.0}]
    pdf_bytes = build_standardized_tkp_pdf(rows, purchase_id=123)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    widget_map = {w.field_name: w for w in page.widgets()}
    widget_map["supplier_name"].field_value = "ИП Иванов И.И."
    widget_map["supplier_name"].update()
    widget_map["validity_days"].field_value = "10"  # < 30 дней!
    widget_map["validity_days"].update()
    widget_map["item_0_unit_price"].field_value = "450"
    widget_map["item_0_unit_price"].update()

    filled_pdf_bytes = doc.tobytes()

    parsed = parse_protocol_file("Приложение_2_Форма_ТКП.pdf", filled_pdf_bytes)
    assert parsed.get("is_single_application") is True
    app = parsed.get("application") or parsed["applications"][0]

    assert app["admitted"] is False
    assert "10 раб. дн." in app["rejection_reason"]
    assert "не менее 30 рабочих дней" in app["rejection_reason"]


def test_excel_sheet_protection_and_copied_shifted_table_parsing():
    """Тест жёсткой защиты листа Excel и устойчивости парсера к скопированным/сдвинутым таблицам без маркера."""
    import openpyxl
    from app.services.documents.tkp_form_xlsx import build_standardized_tkp_xlsx

    rows = [
        {"item_id": 5, "name": "Лопата штыковая", "description": "Сталь 65Г", "quantity": 10, "unit": "шт.", "unit_price": 800.0},
    ]

    xlsx_bytes = build_standardized_tkp_xlsx(rows, purchase_id=55)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active

    # 1. Проверяем Sheet Protection
    assert ws.protection.sheet is True
    assert ws.protection.selectLockedCells is False
    # Ячейка цены участника I13 должна быть разблокирована (locked == False)
    assert ws["I13"].protection.locked is False
    # Ячейка наименования C13 должна быть заблокирована (locked == True)
    assert ws["C13"].protection.locked is True

    # 2. Создаём с нуля «испорченный/скопированный поставщиком» файл со сдвинутыми строками и без GALA_TKP_V1
    wb_corrupted = openpyxl.Workbook()
    ws_c = wb_corrupted.active
    ws_c.title = "Мое_Предложение"

    # Сдвинутая шапка (начиная со строки 3 вместо 1, без маркера GALA_TKP_V1)
    ws_c.cell(3, 2, "Форма технико-коммерческого предложения на конкурс")
    ws_c.cell(5, 2, "Наименование участника:")
    ws_c.cell(5, 4, "ООО «Альфа-Сервис»")
    ws_c.cell(6, 2, "ИНН участника:")
    ws_c.cell(6, 4, "7711223344")
    ws_c.cell(7, 2, "Ставка НДС:")
    ws_c.cell(7, 4, "Без НДС")
    ws_c.cell(8, 2, "Срок действия ТКП (раб. дн.):")
    ws_c.cell(8, 4, 45)

    # Таблица товаров со сдвигом колонок (начиная со строки 11 и колонки B вместо A)
    # B: №, C: Наименование, D: Требования, E: Ед., F: Кол-во, G: Тип, H: Предложение, I: Цена, J: Стоимость
    ws_c.cell(11, 2, "№ п/п")
    ws_c.cell(11, 3, "Наименование продукции")
    ws_c.cell(11, 4, "Требования Заказчика")
    ws_c.cell(11, 5, "Ед. изм.")
    ws_c.cell(11, 6, "Кол-во")
    ws_c.cell(11, 7, "Тип предложения")
    ws_c.cell(11, 8, "Предложение участника")
    ws_c.cell(11, 9, "Цена за ед., руб.")
    ws_c.cell(11, 10, "Стоимость, руб.")

    # Строка 12 — товар (аналог)
    ws_c.cell(12, 2, 1)
    ws_c.cell(12, 3, "Лопата штыковая")
    ws_c.cell(12, 4, "Сталь 65Г")
    ws_c.cell(12, 5, "шт.")
    ws_c.cell(12, 6, 10)
    ws_c.cell(12, 7, "Аналог (эквивалент)")
    ws_c.cell(12, 8, "Лопата титановая сверхпрочная Т-1")
    ws_c.cell(12, 9, 950.0)
    ws_c.cell(12, 10, 9500.0)

    # Строка 13 — Итого
    ws_c.cell(13, 2, "ИТОГО:")
    ws_c.cell(13, 10, 9500.0)

    buf_c = io.BytesIO()
    wb_corrupted.save(buf_c)
    corrupted_bytes = buf_c.getvalue()

    # Парсим через parse_protocol_file
    parsed_c = parse_protocol_file("Кривой_ТКП_от_участника.xlsx", corrupted_bytes)
    assert parsed_c.get("is_single_application") is True
    app_c = parsed_c.get("application") or parsed_c["applications"][0]

    assert app_c["supplier_name"] == "ООО «Альфа-Сервис»"
    assert app_c["inn"] == "7711223344"
    assert app_c["vat_label"] == "Без НДС"
    assert app_c["validity_days"] == 45
    assert app_c["admitted"] is True
    assert app_c["price"] == 9500.0

    assert len(app_c["positions"]) == 1
    p_c = app_c["positions"][0]
    assert p_c["requested_name"] == "Лопата штыковая"
    assert p_c["is_alternative"] is True
    assert p_c["decision"] == "analog_pending"
    assert "Лопата титановая" in p_c["offered_specs"]
    assert p_c["unit_price"] == 950.0
    assert p_c["total_price"] == 9500.0


@pytest.mark.asyncio
async def test_apply_winner_creates_contract_items_with_per_item_vat_and_offered_goods():
    """Тест автоматического создания ContractItem при применении победителя с разными ставками НДС."""
    from app.services.roseltorg.winner_apply_service import apply_winner_full
    from app.models.contract_item import ContractItem

    purchase = Purchase(
        id=999,
        subject="Поставка компьютерной техники и ПО",
        status="ordered",
    )
    item1 = PurchaseItem(
        id=1,
        purchase_id=999,
        item_name="Ноутбук базовый",
        quantity=Decimal("2"),
        unit="шт.",
        unit_price=Decimal("50000.00"),
        total_price=Decimal("100000.00"),
    )
    item2 = PurchaseItem(
        id=2,
        purchase_id=999,
        item_name="Программное обеспечение",
        quantity=Decimal("1"),
        unit="компл.",
        unit_price=Decimal("30000.00"),
        total_price=Decimal("30000.00"),
    )

    contract_items_added: list[ContractItem] = []

    def fake_add(obj):
        if isinstance(obj, ContractItem):
            contract_items_added.append(obj)

    db = AsyncMock()
    db.add = MagicMock(side_effect=fake_add)

    async def fake_execute(statement, *args, **kwargs):
        stmt_str = str(statement)
        mock_r = MagicMock()
        if "FROM purchase_items" in stmt_str:
            mock_r.scalars.return_value.all.return_value = [item1, item2]
        elif "FROM contract_items" in stmt_str:
            mock_r.scalars.return_value.all.return_value = []
        elif "FROM contractors" in stmt_str:
            mock_r.scalars.return_value.first.return_value = None
        else:
            mock_r.scalar_one_or_none.return_value = None
            mock_r.scalars.return_value.all.return_value = []
        return mock_r

    db.execute = AsyncMock(side_effect=fake_execute)

    winner = {
        "supplier_name": "ООО «ПромИТ»",
        "inn": "7705998877",
        "kpp": "770501001",
        "vat_label": "в т.ч. НДС 20%",
        "positions": [
            {
                "purchase_item_id": 1,
                "item_num": 1,
                "requested_name": "Ноутбук базовый",
                "offered_name": "Ноутбук Pro-15 (i7, 32GB)",
                "offered_specs": "Ноутбук Pro-15 (i7, 32GB, 1TB SSD)",
                "is_alternative": True,
                "compliance_status": "analog_accepted",
                "unit_price": 48000.0,
                "total_price": 96000.0,
                "vat_rate": "20%",
            },
            {
                "purchase_item_id": 2,
                "item_num": 2,
                "requested_name": "Программное обеспечение",
                "offered_name": "Программное обеспечение",
                "is_alternative": False,
                "compliance_status": "compliant",
                "unit_price": 25000.0,
                "total_price": 25000.0,
                "vat_rate": "Без НДС",
            },
        ],
    }

    with patch("app.routers.purchases._recalc_contract_price_from_contract_items", new=AsyncMock()):
        res = await apply_winner_full(
            db=db,
            purchase=purchase,
            winner=winner,
            protocol_number="№999-1",
            apply_positions_prices=True,
            apply_accepted_alternatives=True,
        )

    assert res["ok"] is True
    assert res["contractor_name"] == "ООО «ПромИТ»"
    assert res["updated_positions_count"] == 2
    assert res["applied_alternatives_count"] == 1
    assert res["created_contract_items_count"] == 2

    # Проверяем автовыбор режима НДС: разный НДС по позициям (20% и Без НДС) -> per_item!
    assert purchase.vat_mode == "per_item"
    assert purchase.vat_applicable is True
    assert res["vat_mode"] == "per_item"

    # Проверяем созданные ContractItem
    assert len(contract_items_added) == 2
    ci1, ci2 = contract_items_added[0], contract_items_added[1]

    assert ci1.source_item_id == 1
    assert ci1.name == "Ноутбук Pro-15 (i7, 32GB)"
    assert ci1.unit_price == Decimal("48000.0")
    assert ci1.total == Decimal("96000.0")
    assert ci1.vat_rate == "20%"

    assert ci2.source_item_id == 2
    assert ci2.name == "Программное обеспечение"
    assert ci2.unit_price == Decimal("25000.0")
    assert ci2.total == Decimal("25000.0")
    assert ci2.vat_rate == "Без НДС"

    # Проверяем обновление строк закупки
    assert item1.accepted_name == "Ноутбук Pro-15 (i7, 32GB)"
    assert item1.final_unit_price == Decimal("48000.0")
    assert item1.final_total == Decimal("96000.0")
    assert item1.vat_rate == "20%"
    assert item1.contractor_inn == "7705998877"

    assert item2.final_unit_price == Decimal("25000.0")
    assert item2.final_total == Decimal("25000.0")
    assert item2.vat_rate == "Без НДС"
    assert item2.contractor_inn == "7705998877"


@pytest.mark.asyncio
async def test_commission_members_auto_pull_from_subsidy_and_purchase_overrides():
    """Тест автоподстановки членов комиссии из субсидии, добавления людей в закупку и фильтрации отсутствующих в протоколе."""
    from app.services.roseltorg.results_builder import get_or_build_default_results
    from app.services.documents.protocol_vsks import build_vsks_protocol_docx
    import docx

    subsidy = Subsidy(
        id=77,
        name="Субсидия 2026",
        org_id=1,
        commission_order_number="Приказ-102",
        commission_order_date=date(2026, 3, 15),
        commission_members=json.dumps([
            {"full_name": "Петров Пётр Петрович", "position": "Руководитель службы", "role": "Председатель Комиссии"},
            {"full_name": "Сидоров Сидор Сидорович", "position": "Ведущий юрист", "role": "Член Комиссии"},
            {"full_name": "Козлова Анна Ивановна", "position": "Бухгалтер", "role": "Секретарь Комиссии"},
        ], ensure_ascii=False),
    )

    purchase = Purchase(
        id=101,
        subsidy_id=77,
        subject="Поставка офисной мебели",
    )

    # 1. Сценарий: pub.results_data существует, но в нём пустой commission_members
    pub = PlatformPublication(
        id=1,
        purchase_id=101,
        results_data=json.dumps({"applications": [], "commission_members": []}, ensure_ascii=False),
    )

    db = AsyncMock()
    db.get = AsyncMock(return_value=subsidy)

    res = await get_or_build_default_results(db, purchase, pub)
    assert len(res["commission_members"]) == 3
    assert res["commission_members"][0]["full_name"] == "Петров Пётр Петрович"
    assert res["commission_members"][0]["from_subsidy"] is True
    assert res["commission_members"][0]["present"] is True
    assert res["commission_order_number"] == "Приказ-102"
    assert res["commission_order_date"] == "2026-03-15"

    # 2. Пользователь в закупке:
    # - Отмечает Сидорова как отсутствующего (present: False)
    # - Добавляет нового человека именно в закупку (from_subsidy: False)
    custom_members = list(res["commission_members"])
    custom_members[1]["present"] = False  # Сидоров в отпуске
    custom_members.append({
        "full_name": "Михайлов Михаил Михайлович",
        "position": "Внешний эксперт",
        "role": "Член Комиссии",
        "present": True,
        "from_subsidy": False,
    })

    res["commission_members"] = custom_members

    # 3. Генерируем протокол ВСКС
    docx_bytes = build_vsks_protocol_docx(purchase, subsidy, None, None, res)
    doc = docx.Document(io.BytesIO(docx_bytes))

    full_text = "\n".join(p.text for p in doc.paragraphs)
    # В п. 1.3 указано общее число 4 человека (по приказу)
    assert "в составе 4-х человек" in full_text

    # В Таблице 0 (в присутствии:) только присутствующие (3 человека)
    t0 = doc.tables[0]
    t0_names = [row.cells[0].text for row in t0.rows[1:]]
    assert "Петров Пётр Петрович" in t0_names
    assert "Михайлов Михаил Михайлович" in t0_names
    assert "Сидоров Сидор Сидорович" not in t0_names  # Отсутствовал!

    # Проверяем роль и должность во 2-й колонке: f"{role} ({position})"
    t0_roles = [row.cells[1].text for row in t0.rows[1:]]
    assert any("Председатель Комиссии (Руководитель службы)" in r for r in t0_roles)
    assert any("Член Комиссии (Внешний эксперт)" in r for r in t0_roles)

    # В блоке подписей в конце отсутствующего Сидорова также нет
    assert "Сидоров С.С." not in full_text
    assert "Петров П.П." in full_text or "Петров П." in full_text


def test_subsidy_protocol_base_doc_copies_header_from_contract(tmp_path):
    """Тест автоматического извлечения колонтитулов и шапки из шаблона договора субсидии."""
    import docx
    from app.services.documents.protocol_docx_helpers import resolve_or_build_subsidy_protocol_base_doc

    sub_dir = tmp_path / "subsidies" / "88"
    sub_dir.mkdir(parents=True)

    # Создаём файл contract_goods_single.docx с уникальным колонтитулом организации
    contract_path = sub_dir / "contract_goods_single.docx"
    doc_src = docx.Document()
    hdr = doc_src.sections[0].header
    hdr.paragraphs[0].text = "РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВОМО ВСКС РЕСПУБЛИКИ КРЫМ"

    # Добавляем таблицу-шапку организации в начале тела
    tbl = doc_src.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "ЛОГОТИП"
    tbl.rows[0].cells[1].text = "ОТДЕЛЕНИЕ КРЫМ"
    doc_src.add_paragraph("ДОГОВОР ПОСТАВКИ № 123")
    doc_src.add_paragraph("Текст договора поставки...")
    doc_src.save(str(contract_path))

    # Вызываем resolve_or_build_subsidy_protocol_base_doc (для шаблона / скачивания)
    from app.services.documents.protocol_docx_helpers import is_valid_full_protocol_template
    from docxtpl import DocxTemplate

    base_doc = resolve_or_build_subsidy_protocol_base_doc(88, custom_dir=str(sub_dir), for_rendering=False)

    # 1. Проверяем, что создался файл procurement_protocol.docx в папке субсидии
    proto_file = sub_dir / "procurement_protocol.docx"
    assert proto_file.exists()

    # 2. Проверяем, что колонтитул организации сохранился
    assert "РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ" in base_doc.sections[0].header.paragraphs[0].text

    # 3. Проверяем, что текст договора удалён, а файл на диске — полноценный docxtpl-шаблон
    body_text = "\n".join(p.text for p in base_doc.paragraphs)
    assert "Текст договора поставки" not in body_text
    assert is_valid_full_protocol_template(str(proto_file))

    # 4. Проверяем, что docxtpl компилирует и рендерит пустой и заполненный контекст без ошибок
    tpl = DocxTemplate(str(proto_file))
    tpl.render({})
    tpl.render({"commission_members": [{"full_name": "Тестов Т.Т.", "role": "Член"}]})

    # 5. Проверяем режим for_rendering=True: тело очищено для python-docx, но логотип сохранён
    render_doc = resolve_or_build_subsidy_protocol_base_doc(88, custom_dir=str(sub_dir), for_rendering=True)
    assert len(render_doc.tables) == 1
    assert "ОТДЕЛЕНИЕ КРЫМ" in render_doc.tables[0].rows[0].cells[1].text


@pytest.mark.asyncio
async def test_publication_and_winner_status_transitions():
    """Проверяет переходы статусов и подстатусов закупки при размещении на площадке и выборе победителя."""
    from app.services.publications_status import sync_purchase_on_platform_published
    from app.services.roseltorg.winner_apply_service import apply_winner_full

    # 1. sync_purchase_on_platform_published: переход из plan_schedule в work_in_progress / on_platform
    p1 = Purchase(id=101, subject="Закупка 1", status="plan_schedule", substatus=None)
    sync_purchase_on_platform_published(p1)
    assert p1.status == "work_in_progress"
    assert p1.substatus == "on_platform"

    # Если уже tz_forming / kp_collecting -> также обновляет в on_platform
    p1_tz = Purchase(id=102, subject="Закупка TZ", status="work_in_progress", substatus="tz_forming")
    sync_purchase_on_platform_published(p1_tz)
    assert p1_tz.status == "work_in_progress"
    assert p1_tz.substatus == "on_platform"

    # Если уже contract_signing или contracted -> не понижает статус и подстатус
    p_advanced = Purchase(id=103, subject="Закупка на этапе подписания", status="work_in_progress", substatus="contract_signing")
    sync_purchase_on_platform_published(p_advanced)
    assert p_advanced.status == "work_in_progress"
    assert p_advanced.substatus == "contract_signing"

    p_contracted = Purchase(id=104, subject="Договор заключен", status="contracted", substatus=None)
    sync_purchase_on_platform_published(p_contracted)
    assert p_contracted.status == "contracted"
    assert p_contracted.substatus is None

    # 2. apply_winner_full: переход в status="work_in_progress", substatus="contract_signing"
    p2 = Purchase(id=105, subject="Закупка с победителем", status="work_in_progress", substatus="on_platform")
    db = AsyncMock()
    db.add = MagicMock()
    mock_r = MagicMock()
    mock_r.scalars.return_value.all.return_value = []
    mock_r.scalars.return_value.first.return_value = None
    mock_r.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_r)

    winner = {
        "supplier_name": "ООО «ТестПоставщик»",
        "inn": "7712345678",
        "price_with_vat": 150000.0,
        "positions": [],
    }

    with patch("app.routers.purchases._recalc_contract_price_from_contract_items", new=AsyncMock()):
        res2 = await apply_winner_full(
            db=db,
            purchase=p2,
            winner=winner,
            protocol_number="ПР-01",
        )
    assert res2["ok"] is True
    assert p2.status == "work_in_progress"
    assert p2.substatus == "contract_signing"
    assert res2["status"] == "work_in_progress"
    assert res2["substatus"] == "contract_signing"

    # 3. apply_winner_full: сохранение status="contracted" (не сбрасывается назад в work_in_progress)
    p3 = Purchase(id=106, subject="Закупка уже заключена", status="contracted", substatus="some_sub")
    with patch("app.routers.purchases._recalc_contract_price_from_contract_items", new=AsyncMock()):
        res3 = await apply_winner_full(
            db=db,
            purchase=p3,
            winner=winner,
            protocol_number="ПР-02",
        )
    assert res3["ok"] is True
    assert p3.status == "contracted"
    assert p3.substatus == "some_sub"
    assert res3["status"] == "contracted"
    assert res3["substatus"] == "some_sub"







