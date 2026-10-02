"""Регресс на прод-баг (2026-10-02): UniqueViolationError ix_contractors_inn_unique
(TRIM(inn)) при POST /api/contractors.

Контрагент id 53919 «ООО "НПП "ЩИТ"» был сохранён с ИНН '7723543065 '
(хвостовой пробел, обход модели через прямой SQL/импорт). create_contractor
искал существующего через `Contractor.inn == inn` (точное равенство) —
пробел ломал совпадение, код пытался создать дубль, а уникальный индекс по
TRIM(inn) в БД отклонял вставку → 500 вместо возврата существующей записи.

Проверяем:
1) модель Contractor нормализует inn/kpp/ogrn через validates() — хвостовые
   пробелы обрезаются при любом присваивании, не только в этом роутере
   (ПРАВИЛО №6 — один источник нормализации);
2) POST с ИНН без пробела находит контрагента, сохранённого с пробелом
   (через func.trim в create_contractor), и возвращает тот же id без 500.
"""
import pytest
from sqlalchemy import text

from app.models.contractor import Contractor


def test_contractor_model_strips_inn_kpp_ogrn_on_assign():
    c = Contractor(name="Тест Нормализация", inn=" 7723543065 ", kpp=" 772301001 ", ogrn=" 1027700132195 ")
    assert c.inn == "7723543065"
    assert c.kpp == "772301001"
    assert c.ogrn == "1027700132195"


def test_contractor_model_empty_reg_numbers_become_none():
    c = Contractor(name="Тест Пусто", inn="   ", kpp="", ogrn=None)
    assert c.inn is None
    assert c.kpp is None
    assert c.ogrn is None


@pytest.mark.asyncio
async def test_post_contractor_matches_existing_with_trailing_space_inn(
    db_session, client, test_org, superadmin_headers
):
    # Вставляем контрагента с пробелом в обход модели — напрямую SQL, как
    # это случилось на проде (импорт/ручная правка в БД), чтобы validates()
    # модели не успел нормализовать значение до вставки. Уникальный индекс
    # TRIM(inn) глобальный (не per-org), а эта же строка реально живёт в деве
    # как контрагент id 53919 — переиспользуем её, если уже есть, вместо
    # вставки второй (иначе сама эта вставка падает с тем же UniqueViolation,
    # который мы расследуем).
    existing_q = await db_session.execute(
        text("SELECT id FROM contractors WHERE TRIM(inn) = :inn"),
        {"inn": "7723543065"},
    )
    existing_id = existing_q.scalars().first()
    if existing_id is None:
        await db_session.execute(
            text(
                "INSERT INTO contractors (name, inn, org_id) "
                "VALUES (:name, :inn, :org_id)"
            ),
            {"name": 'ООО "НПП "ЩИТ"', "inn": "7723543065 ", "org_id": test_org.id},
        )
        await db_session.commit()
        existing_q = await db_session.execute(
            text("SELECT id FROM contractors WHERE TRIM(inn) = :inn"),
            {"inn": "7723543065"},
        )
        existing_id = existing_q.scalar_one()

    resp = await client.post(
        "/api/contractors/",
        json={"name": 'ООО "НПП "ЩИТ"', "inn": "7723543065"},
        headers=superadmin_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == existing_id
