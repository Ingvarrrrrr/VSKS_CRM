# -*- coding: utf-8 -*-
"""Корректировка утверждённой субсидии через проверку, волна 2B (02.10.2026,
план breezy-mixing-lovelace.md): создание плановой позиции из дерева ФЭО
субсидии обязано пройти assert_direct_edit (app.services.subsidy_revision_guard),
а создание ИЗ заявки (wish_id) — не считается прямой правкой субсидии, если
заявка реально относится к той же субсидии.

Вызывает роутер НАПРЯМУЮ (минуя FastAPI DI), по образцу
test_feo_history_wave2.py — current_user/wish_id/purchase_id передаются
явными keyword-аргументами, что проще реального HTTP-запроса через client и
не требует отдельного набора прав для исходного _check_planned_item_write_access
(монкипатчится ниже в no-op, чтобы тест изолированно проверял именно НОВЫЙ
гейт, а не всю матрицу прав — она уже покрыта test_feo_category_write_gate.py
и остаётся без изменений).

Флейк pytest-asyncio «different loop» (см. test_feo_history_wave2.py) — при
нестабильности гонять тесты этого файла по отдельности:
pytest tests/test_feo_item_write_wish_path.py::<name>.
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.wish import Wish


async def _make_approved_subsidy_with_category(db_session, org_id):
    subsidy = Subsidy(
        name=f"TestRevisionWishPath-{uuid.uuid4().hex[:8]}", year=2026,
        org_id=org_id, status="approved",
    )
    db_session.add(subsidy)
    await db_session.commit()
    await db_session.refresh(subsidy)

    cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Категория теста корректировки")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    return subsidy, cat


async def _make_wish(db_session, org_id, subsidy_id):
    wish = Wish(title="Тестовая заявка", status="draft", org_id=org_id, subsidy_id=subsidy_id)
    db_session.add(wish)
    await db_session.commit()
    await db_session.refresh(wish)
    return wish


def _planned_item_data(cat_id, name="Позиция корректировки"):
    from app.schemas.feo import FeoPlannedItemCreate
    return FeoPlannedItemCreate(
        feo_category_id=cat_id, name=name, quantity=Decimal("1"),
        unit="шт", amount=Decimal("100"), is_active=True,
    )


@pytest.mark.asyncio
async def test_create_from_feo_tree_without_subsidy_edit_is_blocked(monkeypatch, db_session, test_user, test_org):
    """Прямое создание плановой позиции из дерева ФЭО утверждённой субсидии
    (без wish_id/purchase_id) — обладатель без subsidy.edit/subsidy.correct
    обязан получить отказ (403/409), не 2xx."""
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    from app.routers import feo_planned_items as fpi

    async def _noop_access(*a, **kw):
        return None
    monkeypatch.setattr(fpi, "_check_planned_item_write_access", _noop_access)

    _subsidy, cat = await _make_approved_subsidy_with_category(db_session, org_id=test_org.id)
    data = _planned_item_data(cat.id)

    with pytest.raises(HTTPException) as exc_info:
        await fpi.create_planned_item(
            data=data, wish_id=None, purchase_id=None,
            db=db_session, current_user=test_user,
        )
    assert exc_info.value.status_code in (403, 409)


@pytest.mark.asyncio
async def test_create_with_wish_id_same_subsidy_passes(monkeypatch, db_session, test_user, test_org):
    """Создание ИЗ заявки той же субсидии (wish_id) — НЕ правка субсидии,
    гейт assert_direct_edit не блокирует, позиция создаётся."""
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    from app.routers import feo_planned_items as fpi

    async def _noop_access(*a, **kw):
        return None
    monkeypatch.setattr(fpi, "_check_planned_item_write_access", _noop_access)

    subsidy, cat = await _make_approved_subsidy_with_category(db_session, org_id=test_org.id)
    own_wish = await _make_wish(db_session, org_id=test_org.id, subsidy_id=subsidy.id)
    data = _planned_item_data(cat.id, name="Позиция из своей заявки")

    item = await fpi.create_planned_item(
        data=data, wish_id=own_wish.id, purchase_id=None,
        db=db_session, current_user=test_user,
    )
    assert item.id is not None
    assert item.feo_category_id == cat.id


@pytest.mark.asyncio
async def test_create_with_wish_id_other_subsidy_is_422(monkeypatch, db_session, test_user, test_org):
    """wish_id заявки ЧУЖОЙ субсидии — явная ошибка контекста (422), не
    молчаливое создание и не обход гейта подменой wish_id."""
    monkeypatch.setenv("SUBSIDY_REVISION_ENABLED", "1")

    from app.routers import feo_planned_items as fpi

    async def _noop_access(*a, **kw):
        return None
    monkeypatch.setattr(fpi, "_check_planned_item_write_access", _noop_access)

    subsidy, cat = await _make_approved_subsidy_with_category(db_session, org_id=test_org.id)
    other_subsidy, _other_cat = await _make_approved_subsidy_with_category(db_session, org_id=test_org.id)
    foreign_wish = await _make_wish(db_session, org_id=test_org.id, subsidy_id=other_subsidy.id)
    data = _planned_item_data(cat.id, name="Позиция через чужую заявку")

    with pytest.raises(HTTPException) as exc_info:
        await fpi.create_planned_item(
            data=data, wish_id=foreign_wish.id, purchase_id=None,
            db=db_session, current_user=test_user,
        )
    assert exc_info.value.status_code == 422
