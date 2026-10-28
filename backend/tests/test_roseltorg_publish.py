# -*- coding: utf-8 -*-
"""Клиент Росэлторг.Бизнес (app/services/roseltorg/): позиции лота, авторизация
по личному токену, последовательность вызовов создания черновика, статус,
размещение черновика. Все сетевые вызовы замоканы (_rb_call/jwt) — НИКАКИХ
запросов к roseltorg.ru, по требованию задания.

Плюс тест на баг Фабриканта: `payload` не определён в _poll_fabrikant_result
(ветка «Без НМЦД», commit ad3ff808) — no_nmcd должен приходить параметром.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from datetime import date

from app.services.roseltorg.okei import okei_for_unit
from app.services.roseltorg.items import build_roseltorg_item_payloads
from app.services.roseltorg.auth import ROSELTORG_TEMPLATE_IDS
import app.services.roseltorg.client as rb_client


# ── okei.py ──────────────────────────────────────────────────────────────

def test_okei_known_units():
    assert okei_for_unit("шт") == "796"
    assert okei_for_unit("Штука") == "796"
    assert okei_for_unit("кг") == "166"
    assert okei_for_unit("компл.") == "839"


def test_okei_unknown_unit_returns_none():
    assert okei_for_unit("пог. м") is None
    assert okei_for_unit("") is None
    assert okei_for_unit(None) is None


# ── items.py: build_roseltorg_item_payloads ─────────────────────────────

def test_item_payload_known_unit_sets_okei_id():
    rows = [{"name": "Товар", "quantity": 3, "unit": "шт", "unit_price": 100, "description": "Описание"}]
    out = build_roseltorg_item_payloads(rows)
    assert len(out) == 1
    item = out[0]
    assert item["okeiId"] == "796"
    assert item["isArbitraryUnit"] is False
    assert item["quantity"] == "3"
    assert item["commodityItemPrice"] == "100"
    assert item["ordinalNumber"] == 1
    assert "arbitraryUnit" not in item


def test_item_payload_unknown_unit_is_arbitrary():
    rows = [{"name": "Услуга", "quantity": 1, "unit": "пог. м", "unit_price": 50, "description": ""}]
    out = build_roseltorg_item_payloads(rows)
    item = out[0]
    assert item["isArbitraryUnit"] is True
    assert item["arbitraryUnit"] == "пог. м"
    assert "okeiId" not in item


def test_item_payload_okpd2_from_purchase_level_code():
    rows = [{"name": "Товар", "quantity": 1, "unit": "шт", "unit_price": 1, "description": ""}]
    out = build_roseltorg_item_payloads(rows, okpd2_code="26.20.11", okpd2_name="Компьютеры")
    item = out[0]
    assert item["okpd2Code"] == "26.20.11"
    assert item["okpd2Name"] == "Компьютеры"


def test_item_payload_truncates_name_and_description():
    rows = [{
        "name": "Н" * 300, "quantity": 1, "unit": "шт", "unit_price": 1,
        "description": "О" * 1200,
    }]
    out = build_roseltorg_item_payloads(rows)
    assert len(out[0]["name"]) == 250
    assert len(out[0]["description"]) == 1000


def test_item_payload_skips_rows_without_name():
    rows = [{"name": "", "quantity": 1, "unit": "шт", "unit_price": 1, "description": ""}]
    assert build_roseltorg_item_payloads(rows) == []


def test_item_payload_no_nmcd_omits_commodity_item_price():
    """«Без НМЦД» — то же поле, что у Фабриканта (payload["no_nmcd"]):
    цены позиций не публикуются, ключ commodityItemPrice не шлём вовсе."""
    rows = [{"name": "Товар", "quantity": 1, "unit": "шт", "unit_price": 100, "description": ""}]
    out = build_roseltorg_item_payloads(rows, no_nmcd=True)
    assert "commodityItemPrice" not in out[0]


def test_item_payload_without_no_nmcd_keeps_commodity_item_price():
    rows = [{"name": "Товар", "quantity": 1, "unit": "шт", "unit_price": 100, "description": ""}]
    out = build_roseltorg_item_payloads(rows, no_nmcd=False)
    assert out[0]["commodityItemPrice"] == "100"


def test_item_payload_okpd2_key_always_present_empty_when_missing():
    """Живая проверка (уточнение владельца 28.10.2026, черновик 303879):
    площадка принимает позицию с okpd2Code="" — ошибка была только когда
    ключа не было вовсе в теле. Ключ должен присутствовать всегда."""
    rows = [{"name": "Товар", "quantity": 1, "unit": "шт", "unit_price": 1, "description": ""}]
    out = build_roseltorg_item_payloads(rows)
    item = out[0]
    assert "okpd2Code" in item
    assert item["okpd2Code"] == ""
    assert "okpd2Name" in item
    assert item["okpd2Name"] == ""


# ── auth.py: шаблоны процедур (сверено владельцем живьём, GET /templates) ──

def test_template_ids_only_two_procedure_types():
    assert ROSELTORG_TEMPLATE_IDS == {"request_quotations": 8, "request_proposals": 9}


# ── client.py: оркестрация создания черновика (всё замокано) ───────────

class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeSession:
    """Достаточно для client.py: execute(...).scalar_one_or_none(), commit()."""
    def __init__(self, pub):
        self.pub = pub

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *a, **kw):
        return _FakeResult(self.pub)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def get(self, *a, **kw):
        return self.pub


def _fake_pub(**kwargs):
    base = dict(
        id=1, purchase_id=42, platform="roseltorg_rb", status="publishing",
        external_id=None, external_url=None, platform_number=None,
        platform_state=None, published_at=None, updated_at=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.fixture
def patched_session(monkeypatch):
    pub = _fake_pub()

    def _session_factory():
        return _FakeSession(pub)

    monkeypatch.setattr(rb_client, "async_session", _session_factory)
    return pub


async def test_call_roseltorg_no_token_sets_error(monkeypatch, patched_session):
    monkeypatch.setattr(rb_client, "ROSELTORG_TOKEN", "")

    async def fake_get_creds(db, user_id, platform):
        return None

    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    captured = {}

    async def fake_set_error(pub_id, text):
        captured["error"] = text

    monkeypatch.setattr(rb_client, "_set_pub_error", fake_set_error)

    await rb_client._call_roseltorg(1, {"purchase_id": 42}, user_id=1)
    assert "токен" in captured["error"].lower()


async def test_call_roseltorg_prefers_user_token_over_env(monkeypatch, patched_session):
    monkeypatch.setattr(rb_client, "ROSELTORG_TOKEN", "env-token")

    async def fake_get_creds(db, user_id, platform):
        assert platform == "roseltorg"
        return ("", "user-token")

    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    seen_tokens = []

    async def fake_jwt(token):
        seen_tokens.append(token)
        return "jwt-abc"

    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    calls = []

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        calls.append((method, url, body))
        if url.endswith("/new"):
            return {"data": {"noticeId": 123}}, 201
        if "/notice-lot" in url:
            return {"data": {"noticeLotId": 55}}, 201
        return {"data": {}}, 200

    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    async def fake_load_rows(db, purchase_id):
        return None, []

    monkeypatch.setattr(rb_client, "load_purchase_item_rows", fake_load_rows)

    async def fake_set_success(*a, **kw):
        pass

    monkeypatch.setattr(rb_client, "_set_pub_success", fake_set_success)

    payload = {"purchase_id": 42, "subject": "Тест", "nmck": 1000, "okpd2_code": "26.20.11"}
    await rb_client._call_roseltorg(1, payload, user_id=1)
    assert seen_tokens == ["user-token"]


async def test_call_roseltorg_no_okpd2_still_creates_draft(monkeypatch, patched_session):
    """Уточнение владельца 28.10.2026 (живая проверка, черновик 303879): ОКПД2
    НЕ обязателен — без кода черновик создаётся как обычно, позиция уходит с
    okpd2Code=''."""
    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    calls = []

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        calls.append((url, body))
        if url.endswith("/new"):
            return {"success": True, "data": {"noticeId": 5}}, 201
        if url.endswith("/notice-lot"):
            return {"success": True, "data": {"noticeLotId": 50}}, 201
        return {"success": True, "data": {}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    async def fake_load_rows(db, purchase_id):
        return None, [{"name": "Товар", "quantity": 1, "unit": "шт", "unit_price": 1, "description": ""}]
    monkeypatch.setattr(rb_client, "load_purchase_item_rows", fake_load_rows)

    results_box = {}

    async def fake_set_success(pub_id, external_id=None, external_url=None, status="published",
                                platform_number=None, platform_state=None):
        results_box["status"] = status
    monkeypatch.setattr(rb_client, "_set_pub_success", fake_set_success)

    await rb_client._call_roseltorg(1, {"purchase_id": 42, "subject": "Тест", "nmck": 1}, user_id=1)

    assert results_box["status"] == "draft"
    item_call = next(c for c in calls if "/notice/lot/50/items" in c[0])
    assert item_call[1]["data"]["okpd2Code"] == ""
    assert item_call[1]["data"]["okpd2Name"] == ""


async def test_call_roseltorg_sequence_new_put_lot_items(monkeypatch, patched_session):
    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    calls = []

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        calls.append((method, url, body))
        if url.endswith("/new"):
            return {"success": True, "data": {"noticeId": 123}}, 201
        if url.endswith(f"/notices/123"):
            return {"success": True, "data": {}}, 200
        if url.endswith("/notice-lot"):
            return {"success": True, "data": {"noticeLotId": 55}}, 201
        if "/items" in url:
            return {"success": True, "data": {}}, 201
        return {"success": True, "data": {}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    async def fake_load_rows(db, purchase_id):
        return None, [{"name": "Товар", "quantity": 2, "unit": "шт", "unit_price": 10, "description": ""}]
    monkeypatch.setattr(rb_client, "load_purchase_item_rows", fake_load_rows)

    results_box = {}

    async def fake_set_success(pub_id, external_id=None, external_url=None, status="published",
                                platform_number=None, platform_state=None):
        results_box["status"] = status
        results_box["external_id"] = external_id
        results_box["external_url"] = external_url
    monkeypatch.setattr(rb_client, "_set_pub_success", fake_set_success)

    payload = {
        "purchase_id": 42, "subject": "Поставка воды", "nmck": 50000,
        "procedure_type": "request_quotations", "okpd2_code": "26.20.11", "okpd2_name": "Компьютеры",
        "delivery_address": "г. Москва, ул. Ленина, 1", "delivery_region": "Москва",
        "proposal_end": "2026-11-12T12:00", "summing_up_date": "2026-11-13T12:00",
        "org_inn": "7700000001",  # не должен попасть в тело PUT (mainCustomerInn убран)
    }
    await rb_client._call_roseltorg(1, payload, user_id=1)

    urls_in_order = [c[1] for c in calls]
    assert urls_in_order[0].endswith("/notices/8/new")  # request_quotations → шаблон 8
    assert any("/notices/123" in u and u.endswith("/notices/123") for u in urls_in_order)  # PUT
    assert any(u.endswith("/notice-lot") for u in urls_in_order)
    assert any("/notice/lot/55/items" in u for u in urls_in_order)

    # PUT /notices/{id}: обёртка {"data": {...}}, Order — 3 этапа, Begin=сегодня,
    # mainCustomerInn НЕ отправляется (владелец, живая проверка на черновике 303879)
    put_call = next(c for c in calls if c[1].endswith("/notices/123"))
    put_data = put_call[2]["data"]
    assert "mainCustomerInn" not in put_data
    order = put_data["Order"]
    assert [s["type"] for s in order] == [
        "AcceptanceApplicationsDateBegin", "AcceptanceApplicationsDateEnd", "SummingUp",
    ]
    today_iso = f"{date.today().isoformat()}T00:00:00"
    assert order[0]["date"] == today_iso
    assert order[0]["time"] == today_iso
    assert order[1]["date"] == "2026-11-12T00:00:00"
    assert order[1]["time"] == "2026-11-12T12:00:00"
    assert order[2]["date"] == "2026-11-13T00:00:00"
    assert order[2]["time"] == "2026-11-13T12:00:00"

    # notice-lot: тело в обёртке {"data": {...}}, currency="643" (не "RUB")
    lot_call = next(c for c in calls if c[1].endswith("/notice-lot"))
    lot_data = lot_call[2]["data"]
    assert lot_data["initialSum"] == "50000"
    assert lot_data["currency"] == "643"
    assert lot_data["DeliveryDetails"] == "г. Москва, ул. Ленина, 1"
    assert lot_data["region"] == "Москва"

    # Позиция содержит ОКПД2 (обязателен у площадки)
    item_call = next(c for c in calls if "/notice/lot/55/items" in c[1])
    assert item_call[2]["data"]["okpd2Code"] == "26.20.11"

    # Результат — ЧЕРНОВИК, не published (владелец: не публиковать автоматически);
    # ссылка — кабинет площадки (точный адрес черновика неизвестен)
    assert results_box["status"] == "draft"
    assert results_box["external_id"] == "123"
    assert results_box["external_url"] == "https://business.roseltorg.ru/"


async def test_call_roseltorg_no_proposal_end_no_summing_up_sends_only_begin(monkeypatch, patched_session):
    """Если конец приёма/подведение итогов не заданы — этапы не шлём, площадка
    заполнит их в кабинете (владелец, живая проверка)."""
    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    calls = []

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        calls.append((method, url, body))
        if url.endswith("/new"):
            return {"success": True, "data": {"noticeId": 7}}, 201
        if url.endswith("/notice-lot"):
            return {"success": True, "data": {"noticeLotId": 1}}, 201
        return {"success": True, "data": {}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    async def fake_load_rows(db, purchase_id):
        return None, []
    monkeypatch.setattr(rb_client, "load_purchase_item_rows", fake_load_rows)

    async def fake_set_success(*a, **kw):
        pass
    monkeypatch.setattr(rb_client, "_set_pub_success", fake_set_success)

    payload = {"purchase_id": 42, "subject": "Тест", "nmck": 1, "okpd2_code": "26.20.11"}
    await rb_client._call_roseltorg(1, payload, user_id=1)

    put_call = next(c for c in calls if c[1].endswith("/notices/7"))
    order = put_call[2]["data"]["Order"]
    assert [s["type"] for s in order] == ["AcceptanceApplicationsDateBegin"]


async def test_call_roseltorg_lot_success_false_sets_error(monkeypatch, patched_session):
    """Площадка отвечает HTTP 200 с success:false (напр. "Currency not found.")
    — это ошибка, а не успех (владелец, живая проверка)."""
    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        if url.endswith("/new"):
            return {"success": True, "data": {"noticeId": 9}}, 201
        if url.endswith("/notices/9"):
            return {"success": True, "data": {}}, 200
        if url.endswith("/notice-lot"):
            return {"success": False, "errors": ["Currency not found."]}, 200
        return {"success": True, "data": {}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    captured = {}

    async def fake_set_error(pub_id, text):
        captured["error"] = text
    monkeypatch.setattr(rb_client, "_set_pub_error", fake_set_error)

    payload = {"purchase_id": 42, "subject": "Тест", "nmck": 1, "okpd2_code": "26.20.11"}
    await rb_client._call_roseltorg(1, payload, user_id=1)

    assert "Currency not found" in captured["error"]


async def test_call_roseltorg_no_nmcd_omits_initial_sum_and_item_price(monkeypatch, patched_session):
    """«Без НМЦД» (payload["no_nmcd"], то же поле, что у Фабриканта): лот без
    initialSum (не "0" — живая проверка: площадка принимает лот без ключа,
    37 из 57 опубликованных лотов именно такие), позиции без commodityItemPrice."""
    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    calls = []

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        calls.append((url, body))
        if url.endswith("/new"):
            return {"success": True, "data": {"noticeId": 11}}, 201
        if url.endswith("/notice-lot"):
            return {"success": True, "data": {"noticeLotId": 70}}, 201
        return {"success": True, "data": {}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    async def fake_load_rows(db, purchase_id):
        return None, [{"name": "Товар", "quantity": 1, "unit": "шт", "unit_price": 500, "description": ""}]
    monkeypatch.setattr(rb_client, "load_purchase_item_rows", fake_load_rows)

    async def fake_set_success(*a, **kw):
        pass
    monkeypatch.setattr(rb_client, "_set_pub_success", fake_set_success)

    payload = {
        "purchase_id": 42, "subject": "Тест", "nmck": 0, "no_nmcd": True,
        "okpd2_code": "26.20.11",
    }
    await rb_client._call_roseltorg(1, payload, user_id=1)

    lot_call = next(c for c in calls if c[0].endswith("/notice-lot"))
    assert "initialSum" not in lot_call[1]["data"]

    item_call = next(c for c in calls if "/notice/lot/70/items" in c[0])
    assert "commodityItemPrice" not in item_call[1]["data"]


async def test_call_roseltorg_template_request_proposals():
    assert ROSELTORG_TEMPLATE_IDS["request_proposals"] == 9


async def test_publish_draft_requires_existing_draft(monkeypatch):
    pub = _fake_pub(status="pending", external_id=None)

    def _session_factory():
        return _FakeSession(pub)
    monkeypatch.setattr(rb_client, "async_session", _session_factory)

    result = await rb_client.publish_roseltorg_draft(1, user_id=1)
    assert result["ok"] is False
    assert "черновика" in result["detail"].lower()


async def test_publish_draft_calls_publish_endpoint(monkeypatch):
    pub = _fake_pub(status="draft", external_id="123")

    def _session_factory():
        return _FakeSession(pub)
    monkeypatch.setattr(rb_client, "async_session", _session_factory)

    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    calls = []

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        calls.append(url)
        return {"success": True, "data": {}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    async def fake_set_success(*a, **kw):
        pass
    monkeypatch.setattr(rb_client, "_set_pub_success", fake_set_success)

    result = await rb_client.publish_roseltorg_draft(1, user_id=1)
    assert result["ok"] is True
    assert any(u.endswith("/notices/123/publish") for u in calls)


async def test_publish_draft_success_false_is_error(monkeypatch):
    """HTTP 200 c success:false — ошибка, не размещение (та же rb_ok, что
    и при создании черновика)."""
    pub = _fake_pub(status="draft", external_id="123")

    def _session_factory():
        return _FakeSession(pub)
    monkeypatch.setattr(rb_client, "async_session", _session_factory)

    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    async def fake_rb_call(jwt, url, body=None, method="POST"):
        return {"success": False, "errors": {"notice": "Процедура не готова к размещению"}}, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    captured = {}

    async def fake_set_error(pub_id, text):
        captured["error"] = text
    monkeypatch.setattr(rb_client, "_set_pub_error", fake_set_error)

    result = await rb_client.publish_roseltorg_draft(1, user_id=1)
    assert result["ok"] is False
    assert "не готова к размещению" in result["detail"]
    assert "не готова к размещению" in captured["error"]


async def test_refresh_status_maps_notice_state(monkeypatch):
    pub = _fake_pub(status="draft", external_id="123")

    def _session_factory():
        return _FakeSession(pub)
    monkeypatch.setattr(rb_client, "async_session", _session_factory)

    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    async def fake_rb_call(jwt, url, body=None, method="GET"):
        return {
            "success": True,
            "data": {"noticeId": 123, "noticeState": "noticePublished",
                      "procedureRegistrationNumber": "B123", "lastError": []},
        }, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    result = await rb_client.refresh_roseltorg_status(1, user_id=1)
    assert result["ok"] is True
    assert pub.status == "published"
    assert pub.platform_number == "B123"


async def test_refresh_status_draft_with_last_error(monkeypatch):
    """GET /notices/{id}/status формат живой проверки: noticeState='noticeDraft',
    непустой lastError — показывается пользователю."""
    pub = _fake_pub(status="draft", external_id="123")

    def _session_factory():
        return _FakeSession(pub)
    monkeypatch.setattr(rb_client, "async_session", _session_factory)

    async def fake_get_creds(db, user_id, platform):
        return ("", "user-token")
    monkeypatch.setattr(rb_client, "_get_platform_creds", fake_get_creds)

    async def fake_jwt(token):
        return "jwt-abc"
    monkeypatch.setattr(rb_client, "get_roseltorg_jwt", fake_jwt)

    async def fake_rb_call(jwt, url, body=None, method="GET"):
        return {
            "success": True,
            "data": {"noticeId": 123, "noticeState": "noticeDraft",
                      "procedureId": None, "procedureRegistrationNumber": None,
                      "lastError": ["Не заполнены обязательные поля лота"]},
        }, 200
    monkeypatch.setattr(rb_client, "rb_call", fake_rb_call)

    result = await rb_client.refresh_roseltorg_status(1, user_id=1)
    assert result["ok"] is True
    assert pub.status == "draft"
    assert "Не заполнены обязательные поля лота" in result["detail"]


# ── Баг Фабриканта: payload не определён в _poll_fabrikant_result ──────

async def test_fabrikant_poll_no_nmcd_reaches_attach_documents(monkeypatch):
    """Регрессия: до фикса `payload.get("no_nmcd")` падал NameError (payload
    не параметр функции). no_nmcd должен приходить параметром из
    _call_fabrikant и доходить до _attach_documents_to_notice."""
    import app.services.publications_fabrikant_client as fab

    captured = {}

    async def fake_attach(pub_id, purchase_id_str, purchase_db_id, auth, no_nmcd=False):
        captured["no_nmcd"] = no_nmcd

    async def fake_procedure_state(purchase_id_str, auth):
        return {"state": "Черновик", "procedure_number": None, "procedure_url": "http://x/draft"}

    async def fake_set_success(*a, **kw):
        pass

    async def fake_set_platform_number(*a, **kw):
        pass

    monkeypatch.setattr(fab, "_attach_documents_to_notice", fake_attach)
    monkeypatch.setattr(fab, "_fabrikant_procedure_state", fake_procedure_state)
    monkeypatch.setattr(fab, "_set_pub_success", fake_set_success)
    monkeypatch.setattr(fab, "_set_pub_platform_number", fake_set_platform_number)

    resp_text = (
        "<responseIsReady>true</responseIsReady>"
        "<procedureNumber>P-1</procedureNumber>"
        "<draftProcedureUrl>http://x/draft</draftProcedureUrl>"
    )

    class _FakeResp:
        status = 200
        def read(self):
            return resp_text.encode("utf-8")

    def fake_urlopen(req, timeout=30, context=None):
        return _FakeResp()

    monkeypatch.setattr(fab.urllib.request, "urlopen", fake_urlopen)

    await fab._poll_fabrikant_result(
        pub_id=1, request_id="REQ1", auth="Zm9vOmJhcg==",
        attach_documents=True, purchase_id_str="100", purchase_db_id=100,
        no_nmcd=True,
    )

    assert captured["no_nmcd"] is True
