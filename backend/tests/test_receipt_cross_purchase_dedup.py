"""Независимая приёмка (2026-09-17, п.2 и п.7): дедуп нераспознанного чека
(file_type='receipt') по content_hash в purchase_files.py::upload_file.

КОНТЕКСТ ПРИВАТНОСТИ: раньше кросс-закупочный поиск дубля шёл по ВСЕЙ таблице
purchase_files без учёта того, вправе ли текущий пользователь видеть закупку,
где файл уже лежит. Две разные организации, загрузившие байт-идентичный файл
(шаблон/пустой бланк), получали 409 с номером ЧУЖОЙ закупки — утечка данных
между организациями И ложная блокировка.

Исправление ограничивает поиск дубля контуром видимости пользователя
(build_visibility_clause из app/auth/visibility.py, тот же источник, что и у
списка закупок — ПРАВИЛО №6):
  - тот же файл во ВТОРОЙ закупке СВОЕГО контура (обе доступны пользователю,
    например через PurchaseMember) — отклоняется 409 с номером первой закупки;
  - тот же файл в закупке пользователя из ДРУГОЙ организации, к которой у
    текущего пользователя нет вообще никакого отношения (не member/не
    approver/не assigned), — загрузка НЕ находит дубль в scoped-запросе и
    проходит как обычная (без утечки чужих реквизитов и без ложной блокировки).
"""
import uuid

import pytest

from app.auth.jwt import create_access_token
from app.models.organization import Organization
from app.models.purchase_event import PurchaseMember

RECEIPT_BYTES_OWN = b"%PDF-1.4 same-bytes-own-contour-test"
RECEIPT_BYTES_CROSS = b"%PDF-1.4 same-bytes-cross-org-test"


async def _add_member(db_session, purchase_id: int, user_id: int):
    db_session.add(PurchaseMember(purchase_id=purchase_id, user_id=user_id, role="member"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_dedup_blocks_second_upload_within_own_visible_contour(
    client, auth_headers, test_user, db_session, make_purchase,
):
    """Тот же файл в двух закупках, обе видны текущему пользователю
    (PurchaseMember в обеих) — вторая загрузка отклоняется 409 с номером
    первой закупки (ровно жалоба владельца п.6б: внёс один чек в 945 и 941)."""
    p1 = await make_purchase()
    await _add_member(db_session, p1.id, test_user.id)
    p2 = await make_purchase()
    await _add_member(db_session, p2.id, test_user.id)

    r1 = await client.post(
        f"/api/purchases/{p1.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("a.pdf", RECEIPT_BYTES_OWN, "application/pdf")},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        f"/api/purchases/{p2.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("b.pdf", RECEIPT_BYTES_OWN, "application/pdf")},
    )
    assert r2.status_code == 409, r2.text
    body = r2.json()
    assert body["details"]["code"] == "RECEIPT_DUPLICATE"
    assert body["details"]["purchase_id"] == p1.id


@pytest.mark.asyncio
async def test_dedup_ignores_purchase_outside_visible_contour(
    client, auth_headers, test_user, db_session, make_purchase, make_user,
):
    """Тот же файл уже лежит в закупке ДРУГОЙ организации, к которой у
    test_user нет никакого отношения — загрузка в СВОЮ закупку с тем же
    содержимым обязана пройти как обычная (200), без 409 и без чужих
    реквизитов в ответе."""
    other_org = Organization(name=f"OtherOrg-{uuid.uuid4().hex[:8]}")
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    other_user = await make_user(role="employee", org_id=other_org.id)
    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': other_user.username, 'org_id': other_user.org_id})}"
    }

    p_other = await make_purchase()
    await _add_member(db_session, p_other.id, other_user.id)

    r_other = await client.post(
        f"/api/purchases/{p_other.id}/files",
        headers=other_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("x.pdf", RECEIPT_BYTES_CROSS, "application/pdf")},
    )
    assert r_other.status_code == 200, r_other.text

    p_mine = await make_purchase()
    await _add_member(db_session, p_mine.id, test_user.id)

    r_mine = await client.post(
        f"/api/purchases/{p_mine.id}/files",
        headers=auth_headers,
        data={"file_type": "receipt", "doc_format": "scan"},
        files={"file": ("y.pdf", RECEIPT_BYTES_CROSS, "application/pdf")},
    )
    # Контур видимости test_user не включает p_other (не member/не assigned/
    # не approver) — scoped-запрос дубля его не находит, загрузка проходит.
    assert r_mine.status_code == 200, r_mine.text
    assert r_mine.json()["file_type"] == "receipt"
