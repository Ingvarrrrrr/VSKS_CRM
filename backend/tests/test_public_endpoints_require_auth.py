# -*- coding: utf-8 -*-
"""Аудит безопасности 2026-09-29: набор эндпоинтов отдавал данные/принимал
записи без входа (200 без токена на проде — subsidies GET/{id},
contractor-override GET/PUT, diag/columns, purchases responsible-persons и
kp-items, receipts pdf/png, publications PATCH /status, products
download-photos/download-photo/photo). Каждому добавлен Depends(get_current_user)
(где у соседей в файле есть более узкая проверка — она тоже добавлена, см.
app/routers/subsidies.py get_subsidy/contractor-override/upsert_contractor_override).

Этот тест — регрессионный барьер: без токена ЛЮБОЙ из перечисленных путей
обязан отвечать 401, а не 200/404/500. Не проверяет бизнес-логику самих
эндпоинтов (это покрыто их профильными тестами), только факт наличия гейта.
"""
import pytest

PROTECTED_ENDPOINTS = [
    ("GET", "/api/subsidies/diag/columns"),
    ("GET", "/api/subsidies/1"),
    ("GET", "/api/subsidies/1/contractor-override"),
    ("PUT", "/api/subsidies/1/contractor-override"),
    ("GET", "/api/purchases/responsible-persons"),
    ("GET", "/api/purchases/1/kp-items"),
    ("GET", "/api/purchases/1/receipts/1/pdf"),
    ("GET", "/api/purchases/1/receipts/1/png"),
    ("PATCH", "/api/publications/1/status"),
    ("POST", "/api/products/download-photos"),
    ("POST", "/api/products/1/download-photo"),
    ("POST", "/api/products/1/photo"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
async def test_endpoint_requires_auth(client, method, path):
    resp = await client.request(method, path, json={} if method in ("PUT", "PATCH") else None)
    assert resp.status_code == 401, (
        f"{method} {path} должен требовать вход (401 без токена), "
        f"получено {resp.status_code}: {resp.text[:200]}"
    )
