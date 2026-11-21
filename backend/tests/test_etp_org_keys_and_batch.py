"""Тесты разрешения учётных данных ЭТП и пакетной проверки закупок (ЭТП).

Спецификация:
1. resolve_purchase_etp_credentials:
   а) своя орг с ключом -> отдаёт её расшифрованный ключ;
   б) регион (не ВСКС) без ключа -> ok=False (не подставляет общий ключ ВСКС из .env);
   в) ВСКС (7731178803) или без орг -> разрешён fallback на .env;
   г) verify_organizer_inn: несовпадение ИНН -> ошибка 422;
2. batch-check:
   - отсев закупки без ТЗ;
   - отсев закупки с дублирующимися позициями;
   - пропуск корректной закупки.
"""
import base64
import json
import uuid
import pytest
from fastapi import HTTPException

from app.models.contractor import Contractor
from app.models.organization import Organization
from app.models.subsidy import Subsidy
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.services.cred_crypto import encrypt_password
from app.services.etp_credentials import (
    resolve_purchase_etp_credentials,
    verify_organizer_inn,
    VSKS_INN,
)
from app.routers.publications_batch import BatchCheckRequest, batch_check_purchases


async def _create_org(db, name_prefix="Org", inn="1234567890", roseltorg_token=None):
    contractor = Contractor(
        name=f"{name_prefix}-{uuid.uuid4().hex[:6]}",
        inn=inn,
    )
    db.add(contractor)
    await db.flush()

    org = Organization(
        contractor_id=contractor.id,
        roseltorg_token_encrypted=encrypt_password(roseltorg_token) if roseltorg_token else None,
    )
    db.add(org)
    await db.flush()
    return org


async def _create_subsidy(db, org_id=None):
    sub = Subsidy(
        name=f"Субсидия-{uuid.uuid4().hex[:6]}",
        year=2026,
        org_id=org_id,
    )
    db.add(sub)
    await db.flush()
    return sub


async def _create_purchase(db, subsidy_id=None, subject="Тестовая закупка", delivery_address="г. Москва, ул. Тверская, д. 1"):
    p = Purchase(
        subject=subject,
        subsidy_id=subsidy_id,
        delivery_address=delivery_address,
        purchase_method="single",
    )
    db.add(p)
    await db.flush()
    return p


@pytest.mark.asyncio
async def test_resolve_etp_credentials_own_org_key(db_session):
    """Своя организация с ключом: отдаёт её расшифрованный ключ."""
    secret_token = "org-secret-token-xyz-123"
    org = await _create_org(db_session, "Регион", inn="5001002000", roseltorg_token=secret_token)
    sub = await _create_subsidy(db_session, org_id=org.id)
    purchase = await _create_purchase(db_session, subsidy_id=sub.id)

    res = await resolve_purchase_etp_credentials(db_session, purchase.id, "roseltorg_rb")
    assert res["ok"] is True
    assert res["token"] == secret_token
    assert res["org_inn"] == "5001002000"
    assert res["org_id"] == org.id


@pytest.mark.asyncio
async def test_resolve_etp_credentials_region_no_key_forbids_env_fallback(db_session, monkeypatch):
    """Регион (не ВСКС) без ключа: не подставляет общий ключ ВСКС из .env (ok=False)."""
    monkeypatch.setenv("ROSELTORG_TOKEN", "vsks-server-fallback-token")

    # Организация с ИНН региона (не ВСКС) и без собственного ключа
    org = await _create_org(db_session, "Регион Без Ключа", inn="6164000000", roseltorg_token=None)
    sub = await _create_subsidy(db_session, org_id=org.id)
    purchase = await _create_purchase(db_session, subsidy_id=sub.id)

    res = await resolve_purchase_etp_credentials(db_session, purchase.id, "roseltorg_rb")
    assert res["ok"] is False
    assert res.get("token") is None
    assert "нет ключа Росэлторга" in res.get("error", "")


@pytest.mark.asyncio
async def test_resolve_etp_credentials_vsks_allows_env_fallback(db_session, monkeypatch):
    """Организация ВСКС (ИНН 7731178803) или без привязки к орг: разрешён fallback на .env."""
    monkeypatch.setenv("ROSELTORG_TOKEN", "vsks-shared-token-7731178803")

    # 1. Организация с ИНН ВСКС
    vsks_org = await _create_org(db_session, "ВСКС Главный", inn=VSKS_INN, roseltorg_token=None)
    sub = await _create_subsidy(db_session, org_id=vsks_org.id)
    p1 = await _create_purchase(db_session, subsidy_id=sub.id)

    res1 = await resolve_purchase_etp_credentials(db_session, p1.id, "roseltorg_rb")
    assert res1["ok"] is True
    assert res1["token"] == "vsks-shared-token-7731178803"
    assert res1["org_inn"] == VSKS_INN

    # 2. Закупка без субсидии / без организации
    p2 = await _create_purchase(db_session, subsidy_id=None)
    res2 = await resolve_purchase_etp_credentials(db_session, p2.id, "roseltorg_rb")
    assert res2["ok"] is True
    assert res2["token"] == "vsks-shared-token-7731178803"


@pytest.mark.asyncio
async def test_verify_organizer_inn_validation():
    """Сверка ИНН: совпадение проходит, несовпадение вызывает 422."""
    # Совпадение - успешно
    verify_organizer_inn("7731178803", "7731178803", "ВСКС")

    # Пустые значения не блокируют
    verify_organizer_inn(None, "7731178803", "ВСКС")
    verify_organizer_inn("7731178803", None, "ВСКС")

    # Несовпадение ИНН площадки и организации субсидии -> 422
    with pytest.raises(HTTPException) as exc:
        verify_organizer_inn("7700000000", "7731178803", "ВСКС")
    assert exc.value.status_code == 422
    assert "не совпадает с ИНН организации субсидии" in exc.value.detail


@pytest.mark.asyncio
async def test_batch_check_missing_tz_and_duplicates(db_session, superadmin_user, monkeypatch):
    """Проверка batch-check: отсев закупок без ТЗ и с дублирующимися позициями."""
    monkeypatch.setenv("ROSELTORG_TOKEN", "mock-token")

    # Мокаем сетевой вызов авторизации Росэлторга для теста
    payload_bytes = json.dumps({"company_inn": VSKS_INN}).encode("utf-8")
    fake_jwt = "header." + base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=") + ".sig"

    async def _mock_get_roseltorg_jwt(token: str):
        return fake_jwt

    monkeypatch.setattr("app.services.roseltorg.auth.get_roseltorg_jwt", _mock_get_roseltorg_jwt)

    org = await _create_org(db_session, "ТестОрг", inn=VSKS_INN)
    sub = await _create_subsidy(db_session, org_id=org.id)

    # Закупка 1: позиция без ТЗ
    p_no_tz = await _create_purchase(db_session, subsidy_id=sub.id, subject="Закупка без ТЗ")
    item_no_tz = PurchaseItem(
        purchase_id=p_no_tz.id,
        item_name="Ноутбук рабочий",
        quantity=1,
        unit="Штука",
        tz_description=None,
    )
    db_session.add(item_no_tz)

    # Закупка 2: дублирующиеся позиции
    p_dups = await _create_purchase(db_session, subsidy_id=sub.id, subject="Закупка с дублями")
    item_dup1 = PurchaseItem(
        purchase_id=p_dups.id,
        item_name="Стол офисный",
        quantity=2,
        unit="Штука",
        tz_description="ТЗ стола",
    )
    item_dup2 = PurchaseItem(
        purchase_id=p_dups.id,
        item_name="стол офисный",  # дубль с разным регистром
        quantity=3,
        unit="Штука",
        tz_description="ТЗ стола 2",
    )
    db_session.add_all([item_dup1, item_dup2])

    # Закупка 3: корректная позиция с ТЗ и уникальными именами
    p_valid = await _create_purchase(db_session, subsidy_id=sub.id, subject="Корректная закупка")
    item_ok = PurchaseItem(
        purchase_id=p_valid.id,
        item_name="Кресло эргономичное",
        quantity=1,
        unit="Штука",
        tz_description="Качественное эргономичное кресло с регулировкой",
    )
    db_session.add(item_ok)
    await db_session.commit()

    # Проверяем через router-функцию batch_check_purchases
    req = BatchCheckRequest(
        purchase_ids=[p_no_tz.id, p_dups.id, p_valid.id],
        platform="roseltorg_rb",
    )
    results = await batch_check_purchases(req, db=db_session, current_user=superadmin_user)
    assert len(results) == 3

    r_map = {r.purchase_id: r for r in results}

    # Закупка 1: отсеяна из-за отсутствия ТЗ
    assert r_map[p_no_tz.id].ready is False
    assert any("Нет ТЗ" in iss for iss in r_map[p_no_tz.id].issues)

    # Закупка 2: отсеяна из-за повторяющихся позиций
    assert r_map[p_dups.id].ready is False
    assert any("повторяющиеся позиции" in iss for iss in r_map[p_dups.id].issues)

    # Закупка 3: готова к отправке
    assert r_map[p_valid.id].ready is True
    assert len(r_map[p_valid.id].issues) == 0
