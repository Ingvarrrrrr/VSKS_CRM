# -*- coding: utf-8 -*-
"""Общий бонус ранжирования «целое слово / первое слово» (владелец,
29.10.2026, см. app/services/product_search_rank.py, Правило №6) —
покрывает ДВЕ жалобы владельца на реальном каталоге:

  - «масло 2х» находил первым кабель «Кабель силовой гибкий КГН 2х1,0 ...
    маслостойкий» (слово «масло»/«2х» совпало только ПОДСТРОКОЙ внутри
    «маслостойкий»/«2х1,0»);
  - «вода» находил «Кондиционер для аквариумной воды»/«Водовозка» выше
    настоящей «Воды ...» (FTS-префикс «вод:*» матчит любое слово на «вод»,
    без бонуса за совпадение ЦЕЛОГО первого слова).

Регрессионные случаи прошлой сессии (болгарка/Makita/огнетушитель/
«масло лукойл 5w40 4л»/пускатель/ОП-4) — покрыты test_product_search.py,
здесь НЕ дублируются, только прогоняются вместе (см. отчёт задания)."""
import pytest

from app.services.product_search import ProductSearchFilters, search_products
from app.models.product import Product


def _mk(db_session, **kwargs):
    p = Product(name=kwargs.pop("name"), category=kwargs.pop("category", "Прочее"), **kwargs)
    db_session.add(p)
    return p


@pytest.mark.asyncio
async def test_vода_ranks_real_water_above_prefix_matches(db_session):
    water = _mk(db_session, name="Вода питьевая 5 л")
    conditioner = _mk(db_session, name="Кондиционер для аквариумной воды")
    waterwagon = _mk(db_session, name="Водовозка")
    matches = _mk(db_session, name="Водо-ветроустойчивые спички")
    await db_session.commit()

    filters = ProductSearchFilters(search="вода")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids_in_order = [p.id for p in items if p.id in {water.id, conditioner.id, waterwagon.id, matches.id}]
    assert ids_in_order, "вода должна находить хотя бы один из товаров"
    assert ids_in_order[0] == water.id, (
        f"«Вода питьевая 5 л» должна быть первой, получили порядок {ids_in_order}"
    )


@pytest.mark.asyncio
async def test_maslo_2h_ranks_oils_above_cable(db_session):
    oil_hyphen = _mk(db_session, name="Масло моторное 2-х тактное")
    oil_plain = _mk(db_session, name="Масло моторное 2х тактное")
    cable = _mk(
        db_session,
        name="Кабель силовой гибкий КГН 2х1,0 маслостойкий",
    )
    await db_session.commit()

    filters = ProductSearchFilters(search="масло 2х")
    items, total, capped = await search_products(db_session, filters, limit=50, offset=0)
    ids_in_order = [p.id for p in items]

    # Кабель — либо не находится вовсе, либо находится НИЖЕ обоих масел
    # (задание: «либо не находится, либо ниже масел»).
    oil_positions = [ids_in_order.index(i) for i in (oil_hyphen.id, oil_plain.id) if i in ids_in_order]
    assert oil_positions, "хотя бы одно из масел должно находиться по «масло 2х»"
    if cable.id in ids_in_order:
        cable_pos = ids_in_order.index(cable.id)
        assert all(cable_pos > p for p in oil_positions), (
            f"кабель (поз. {cable_pos}) должен быть ниже масел (поз. {oil_positions}), "
            f"порядок: {ids_in_order}"
        )
