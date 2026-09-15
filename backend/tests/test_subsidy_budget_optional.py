# -*- coding: utf-8 -*-
"""Владелец (2026-09-15): «Почему в поле „Бюджет" нельзя поставить пусто —
„Ещё не определено"». Subsidy.budget был NOT NULL float — заставлял ставить
0/произвольное число сразу при создании субсидии.

Изменения (см. отчёт волны): app/models/subsidy.py (nullable=True),
app/schemas/subsidies.py (SubsidyCreate/SubsidyOut.budget: Optional[float]),
миграция ALTER COLUMN budget DROP NOT NULL, app/routers/dashboard_charts.py
(float(row.budget) — крашило /dashboard/charts ЦЕЛИКОМ для всех пользователей,
если хотя бы одна субсидия без бюджета).

Через реальный HTTP-клиент (ASGITransport) + реальную БД (db_session,
откатывается в конце теста, см. conftest.py) — не офлайн-моки: нужно
убедиться, что схема/модель/роут/сериализация складываются вместе и
budget=None доезжает через весь стек без 500/422.

Гонять по одному файлу — можно все тесты сразу (не завязаны на порядок,
каждый использует свежий db_session/test_org/superadmin_headers).
"""
import pytest
from sqlalchemy import select

from app.models.subsidy import Subsidy


@pytest.mark.asyncio
async def test_create_subsidy_without_budget_returns_200_and_null(client, superadmin_headers, test_org):
    """POST /subsidies/ без budget в теле — 200, budget в ответе — None (не 0,
    не 422). Раньше `budget: float` без default валил бы это 422."""
    resp = await client.post(
        "/api/subsidies/",
        json={"name": "Без бюджета C1", "year": 2026},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["budget"] is None
    # Эффективный бюджет для расчётов (feo_budget_total) остаётся числом (0,
    # не null) — дерево ФЭО ещё пустое и ручной budget не задан.
    assert data["feo_budget_total"] == 0
    assert data["calculated_budget"] == 0


@pytest.mark.asyncio
async def test_create_subsidy_with_explicit_null_budget(client, superadmin_headers):
    """budget: null явно в теле — тоже 200/None (не отличается от отсутствия
    ключа — SubsidyCreate.budget: Optional[float] = None в обоих случаях)."""
    resp = await client.post(
        "/api/subsidies/",
        json={"name": "Явный null C2", "year": 2026, "budget": None},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"] is None


@pytest.mark.asyncio
async def test_create_subsidy_with_empty_string_budget_normalizes_to_none(client, superadmin_headers):
    """Vuetify v-model.number оставляет '' (не null) на очищенном числовом
    поле — field_validator должен нормализовать это в None, а не 422."""
    resp = await client.post(
        "/api/subsidies/",
        json={"name": "Пустая строка C3", "year": 2026, "budget": ""},
        headers=superadmin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"] is None


@pytest.mark.asyncio
async def test_put_clears_previously_set_budget_to_null(client, superadmin_headers):
    """Создать с budget=100000, затем PUT с budget: null — бюджет должен
    ОЧИСТИТЬСЯ (update_subsidy валидирует тело как SubsidyCreate, full
    model_dump() без exclude_unset — null должен реально дойти до колонки)."""
    create_resp = await client.post(
        "/api/subsidies/",
        json={"name": "Будет очищена C4", "year": 2026, "budget": 100_000},
        headers=superadmin_headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    sid = create_resp.json()["id"]
    assert create_resp.json()["budget"] == 100_000

    put_resp = await client.put(
        f"/api/subsidies/{sid}",
        json={"name": "Будет очищена C4", "year": 2026, "budget": None},
        headers=superadmin_headers,
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["budget"] is None
    assert put_resp.json()["feo_budget_total"] == 0


@pytest.mark.asyncio
async def test_dashboard_charts_serializes_subsidy_without_budget(client, superadmin_headers, db_session):
    """/dashboard/charts не должен падать 500, если среди субсидий есть хотя
    бы одна с budget IS NULL (был баг: float(row.budget) без None-guard крашил
    ВЕСЬ ответ для ВСЕХ субсидий, не только для этой одной)."""
    create_resp = await client.post(
        "/api/subsidies/",
        json={"name": "Для дашборда без бюджета C5", "year": 2026},
        headers=superadmin_headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    sid = create_resp.json()["id"]

    # Прямая проверка на уровне модели: колонка реально NULL в БД, не 0.
    row = (await db_session.execute(select(Subsidy).where(Subsidy.id == sid))).scalar_one()
    assert row.budget is None

    charts_resp = await client.get("/api/dashboard/charts?scope=managed", headers=superadmin_headers)
    assert charts_resp.status_code == 200, charts_resp.text
    stats = charts_resp.json()["subsidy_stats"]
    row_out = next(s for s in stats if s["id"] == sid)
    assert row_out["budget"] is None
    assert row_out["feo_budget_total"] == 0
