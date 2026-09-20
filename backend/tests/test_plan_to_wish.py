"""«Из плана — в заявку» (plan-to-wish, сессия 2026-09-20).

Кандидаты (POST /feo-planned-items/plan-to-wish/candidates) и создание заявки
(POST /feo-planned-items/plan-to-wish/create) — тестируются через прямой вызов
сервисных функций app.services.plan_to_wish (по образцу
test_feo_product_hint_category_match.py — прямой вызов роутер-функции с
db_session/test_user, без HTTP-клиента), т.к. вся интересующая логика лежит в
сервисном слое, а роутер — тонкая обёртка (Правило №5).
"""
from decimal import Decimal

import pytest

from app.models.feo_category import FeoCategory
from app.models.feo_planned_item import FeoPlannedItem
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.services.plan_to_wish import (
    PlanToWishItemInput,
    build_plan_to_wish_candidates,
    create_wish_from_plan,
)


async def _make_subsidy_with_leaf(db_session, name: str) -> tuple[Subsidy, FeoCategory]:
    """Утверждённая (status='approved') субсидия с одной листовой категорией ФЭО —
    create_wish (вызывается изнутри create_wish_from_plan) отклоняет привязку к
    черновой субсидии (assert_subsidy_approved_for_binding), поэтому тестовая
    субсидия обязана быть 'approved', а не полагаться на server_default='draft'."""
    subsidy = Subsidy(name=name, year=2026, budget=0, status="approved", require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    cat = FeoCategory(subsidy_id=subsidy.id, level=3, name="Прочее")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(subsidy)
    await db_session.refresh(cat)
    return subsidy, cat


async def _make_planned_item(db_session, cat: FeoCategory, name: str, quantity=None, unit_price=None, amount=None, unit="шт") -> FeoPlannedItem:
    item = FeoPlannedItem(
        feo_category_id=cat.id, name=name, quantity=quantity, unit_price=unit_price,
        amount=amount, unit=unit, is_active=True,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_candidates_exact_name_match(db_session, test_user):
    """Тесты гоняются на общем dev-каталоге (products — единый справочник, см.
    память проекта) — имя намеренно с уникальным суффиксом (uuid), чтобы
    случайно не столкнуться по стемам с реальным товаром из живой БД (иначе
    'exact' может уйти чужому кандидату с тем же совпадением по одному слову)."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Огнетушитель ОП-5 тест-{suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-exact")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("10"), unit_price=Decimal("1000"), amount=Decimal("10000"))

    product = Product(name=name, category="Прочее", price=Decimal("950"), is_active=True)
    db_session.add(product)
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)

    assert len(result) == 1
    row = result[0]
    assert row["planned_item_id"] == planned.id
    assert row["feo_category_id"] == cat.id
    assert row["exact"] is not None, f"expected exact match, got: {row}"
    assert row["exact"]["product_id"] == product.id
    assert row["exact"]["score"] >= 0.95
    assert row["exact"]["product_type"] == product.product_type  # None here, field present
    assert row["exact"]["unit"] == product.unit


@pytest.mark.asyncio
async def test_candidates_single_word_full_coverage_not_exact(db_session, test_user):
    """Владелец, приёмка в браузере 2026-09-21: однословная плановая позиция
    «Экипировка» подхватила товар «Тренажёры для работы в экипировке в воде
    (например, с грузом, в гидрокостюме)» как exact (100%) только потому, что
    единственное слово запроса входит в название товара (coverage=1.0).
    text_match.is_exact_match теперь требует >=3 значимых токенов запроса для
    score-based exact (или полное normalize-равенство имён) — однословный
    запрос с частичным совпадением уходит в by_name, выбор за пользователем.

    Слово намеренно бессмысленное+uuid (не «экипировка»), чтобы не зависеть от
    того, что реально лежит в общем dev-каталоге — изолирует тест от чужих
    товаров с похожим словом, сохраняя тот же механизм дефекта (один токен
    запроса, длинное название товара с этим токеном внутри)."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    word = f"жгутик{suffix}"
    name = word  # плановая позиция — одно слово, как в реальном дефекте
    product_name = f"Тренажёры для работы с приспособлением {word} в воде (например, с грузом, в гидрокостюме)"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-singleword")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"))

    product = Product(name=product_name, category="Прочее", price=Decimal("900"), is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["exact"] is None, f"expected NOT exact for single-word query, got: {row['exact']}"
    by_name_ids = {c["product_id"] for c in row["by_name"]}
    assert product.id in by_name_ids, f"expected product to land in by_name, got: {row['by_name']}"


@pytest.mark.asyncio
async def test_candidates_exact_full_name_match_stays_exact(db_session, test_user):
    """«Принтер epson l100» против товара с точно таким же именем — остаётся
    exact (normalize(query) == normalize(product.name)), это ровно случай,
    который владелец назвал «100% совпадение названия — именно этот товар»."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Принтер epson l100 {suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-exact-fullname")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("1"), unit_price=Decimal("15000"), amount=Decimal("15000"))

    product = Product(name=name, category="Оргтехника", price=Decimal("14500"), is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["exact"] is not None, f"expected exact match, got: {row}"
    assert row["exact"]["product_id"] == product.id


@pytest.mark.asyncio
async def test_candidates_exact_match_collapses_double_spaces(db_session, test_user):
    """«Шнур Vento Высота 6 цветной (200 м)» против того же имени, но с
    двойным пробелом в имени товара — text_match.normalize схлопывает пробелы,
    имена совпадают после нормализации → остаётся exact."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Шнур Vento Высота 6 цветной (200 м) {suffix}"
    product_name = f"Шнур Vento  Высота 6 цветной (200 м)  {suffix}"  # двойные пробелы

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-exact-doublespace")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("10"), unit_price=Decimal("500"), amount=Decimal("5000"))

    product = Product(name=product_name, category="Электрика", price=Decimal("480"), is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["exact"] is not None, f"expected exact match despite double spaces, got: {row}"
    assert row["exact"]["product_id"] == product.id


@pytest.mark.asyncio
async def test_candidates_by_type_match(db_session, test_user):
    """«Принтер» при товарах с product_type «принтер» (разные названия) —
    обнаруживаются через product_type, а не по имени (имена совсем другие).

    Владелец, 2026-09-21 (живая проверка, субсидия 46): пул by_name и пул
    by_type теперь ОБЪЕДИНЯЮТСЯ и ранжируются одним similarity ДО раздачи по
    двум спискам (см. build_plan_to_wish_candidates) — какая из товарных
    находок попадёт в by_name, а какая в by_type, зависит от того, сколько
    ещё конкурентов у неё по similarity (a не от жёсткого «type-match всегда
    в by_type», как было раньше). Поэтому тест проверяет ОБЪЕДИНЕНИЕ
    (by_name ∪ by_type) — сам факт, что product_type-совпадение нашло HP/Canon
    несмотря на совсем другие имена, а «Сканер» (другой product_type) не
    попал никуда.

    Имя плановой позиции — «Принтер тест-{uuid}» (не голое «Принтер»): общий
    dev-каталог реально содержит десятки товаров со словом «принтер»/«принтера»
    в названии (расходники/запчасти) — однословный запрос совпадает с ЛЮБЫМ из
    них по стему с coverage=1.0 и мог случайно попасть в exact. Второе слово с
    уникальным суффиксом гарантирует, что ни один реальный товар не наберёт
    полное покрытие по НАЗВАНИЮ — но word-токен «принтер» (>=4 симв.) всё
    равно попадает в match_targets для type-match (см. build_plan_to_wish_candidates)."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    name = f"Принтер тест-{suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-type")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("2"), unit_price=Decimal("15000"), amount=Decimal("30000"))

    p1 = Product(name=f"HP LaserJet M140w {suffix}", product_type="Принтер", category="Оргтехника", price=Decimal("14000"), is_active=True)
    p2 = Product(name=f"Canon i-SENSYS LBP6030 {suffix}", product_type="принтер", category="Оргтехника", price=Decimal("13000"), is_active=True)
    unrelated = Product(name=f"Сканер Epson {suffix}", product_type="Сканер", category="Оргтехника", price=Decimal("9000"), is_active=True)
    db_session.add_all([p1, p2, unrelated])
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["exact"] is None
    surfaced_ids = {c["product_id"] for c in row["by_name"]} | {c["product_id"] for c in row["by_type"]}
    assert p1.id in surfaced_ids and p2.id in surfaced_ids, (
        f"expected both printers to surface (by_name or by_type), got by_name={row['by_name']}, by_type={row['by_type']}"
    )
    assert unrelated.id not in surfaced_ids


@pytest.mark.asyncio
async def test_candidates_by_name_ranked_by_similarity_not_100_percent(db_session, test_user):
    """Владелец, приёмка 2026-09-21: подбор товара для плановой позиции
    «Перчатки» показывал «Перчатки латексные» и длинное чужое описание ОБА
    как 100% (одностороннее покрытие токенов text_match.score у однословного
    запроса — 1.0 любому названию, куда слово входит целиком). Теперь score
    кандидатов by_name = text_match.similarity (симметричный Jaccard по
    стемам), и by_name отсортирован по нему по убыванию — короткое близкое
    название выше длинного описания с кучей посторонних слов.

    Выдуманное слово-основа (не «Перчатки») — общий dev-каталог реально
    содержит десятки живых перчаточных товаров (та же субсидия 46, на которой
    владелец нашёл баг), которые иначе конкурировали бы за топ-8 наравне с
    тестовыми и делали бы сравнение score недетерминированным."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    base = "жбурзик"  # выдуманное слово — гарантированно отсутствует в реальном каталоге
    name = f"{base} {suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-glove-rank")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("10"), unit_price=Decimal("100"), amount=Decimal("1000"))

    p_close1 = Product(name=f"{base} {suffix} латексные", category="Прочее", price=Decimal("50"), is_active=True)
    p_close2 = Product(name=f"Защитные {base} {suffix}", category="Прочее", price=Decimal("60"), is_active=True)
    p_long = Product(
        name=(
            f"{base} {suffix} цельноспилковые Master-Pro ПРОФИ (ДРАЙВЕР) / "
            "водительские, размер 10,5 XL, 20 пар 9080-GSD-10"
        ),
        category="Прочее", price=Decimal("900"), is_active=True,
    )
    db_session.add_all([p_close1, p_close2, p_long])
    await db_session.commit()
    await db_session.refresh(p_close1)
    await db_session.refresh(p_close2)
    await db_session.refresh(p_long)

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["exact"] is None, f"однословный запрос не должен давать exact/100%, got: {row['exact']}"

    by_name = row["by_name"]
    ids_present = {c["product_id"] for c in by_name}
    assert {p_close1.id, p_close2.id, p_long.id} <= ids_present, by_name

    for c in by_name:
        assert c["score"] < 1.0, f"ни один кандидат не должен показывать 100%, got: {c}"

    # порядок by_name — по убыванию score (similarity); длинное описание с кучей
    # посторонних слов (артикул/размер/бренд/количество) ранжируется НИЖЕ
    # коротких близких названий (точные числа 0.5/0.5/<0.2 на голом «Перчатки»
    # без изолирующей приставки — отдельно в test_text_match_similarity.py).
    scores_by_id = {c["product_id"]: c["score"] for c in by_name}
    assert scores_by_id[p_long.id] < scores_by_id[p_close1.id]
    assert scores_by_id[p_long.id] < scores_by_id[p_close2.id]
    assert scores_by_id[p_long.id] < 0.2, scores_by_id

    ordered_scores = [c["score"] for c in by_name]
    assert ordered_scores == sorted(ordered_scores, reverse=True), by_name


@pytest.mark.asyncio
async def test_candidates_type_matched_product_merged_into_by_name_ranking(db_session, test_user):
    """Живая проверка владельца (2026-09-21, субсидия 46, «Перчатки»): товары,
    совпавшие ТОЛЬКО по product_type («Защитные перчатки SBARCO MAGNUM...»,
    «ВСВ Премиум...» — их имена не содержат искомого слова целиком, текстовый
    поиск _score_product_candidates их не находит НИКАКИМ лимитом), но при
    этом реально похожие по similarity — оставались в by_type, хотя по
    подобию названия должны попасть в by_name (там были кандидаты с более
    низким similarity, просто найденные текстовым поиском). Пул по имени и
    пул по типу теперь объединяются ДО сортировки по similarity — единое
    ранжирование, best-8 к пользователю независимо от того, каким путём
    товар был найден."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    base = "мурзаклей"  # выдуманное слово — гарантированно отсутствует в реальном каталоге
    name = f"{base} {suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-glove-typemerge")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("10"), unit_price=Decimal("100"), amount=Decimal("1000"))

    # Совпадает ТОЛЬКО по типу — имя не содержит выдуманного слова вовсе,
    # прогрессивное сужение по первому токену query его отсекает ещё до
    # формирования пула по имени, независимо от ширины лимита.
    p_type_only = Product(
        name=f"SBARCO MAGNUM {suffix}", product_type=base,
        category="Прочее", price=Decimal("300"), is_active=True,
    )
    # Проходит через пул по имени (содержит base+suffix — полное покрытие),
    # но длинное описание с кучей посторонних слов — низкий similarity, ниже,
    # чем у p_type_only (общий стем — только suffix).
    p_long_name_match = Product(
        name=(
            f"{base} {suffix} цельноспилковые Master-Pro ПРОФИ (ДРАЙВЕР) / "
            "водительские, размер 10,5 XL, 20 пар 9080-GSD-10"
        ),
        category="Прочее", price=Decimal("900"), is_active=True,
    )
    db_session.add_all([p_type_only, p_long_name_match])
    await db_session.commit()
    await db_session.refresh(p_type_only)
    await db_session.refresh(p_long_name_match)

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    by_name_ids = {c["product_id"] for c in row["by_name"]}
    by_type_ids = {c["product_id"] for c in row["by_type"]}

    assert p_type_only.id in by_name_ids, (
        f"товар, совпавший только по типу, но более похожий по имени, должен "
        f"попасть в by_name, а не остаться в by_type: by_name={row['by_name']}, "
        f"by_type={row['by_type']}"
    )
    assert p_type_only.id not in by_type_ids, "не должен дублироваться в by_type после попадания в by_name"

    scores_by_id = {c["product_id"]: c["score"] for c in row["by_name"]}
    assert scores_by_id[p_type_only.id] > scores_by_id[p_long_name_match.id], scores_by_id


@pytest.mark.asyncio
async def test_candidates_by_name_limit_is_8(db_session, test_user):
    """limit by_name поднят до 8 (было завязано на общий `limit` параметр,
    обычно 6) — владелец, 2026-09-21."""
    import uuid
    suffix = uuid.uuid4().hex[:8]
    base = "фыркотяп"  # выдуманное слово — гарантированно отсутствует в реальном каталоге
    name = f"{base} {suffix}"

    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-glove-limit")
    planned = await _make_planned_item(db_session, cat, name, quantity=Decimal("10"), unit_price=Decimal("100"), amount=Decimal("1000"))

    products = [
        Product(name=f"{base} {suffix} вариант {i}", category="Прочее", price=Decimal("50"), is_active=True)
        for i in range(10)
    ]
    db_session.add_all(products)
    await db_session.commit()

    # limit=6 передан в функцию (как и раньше для by_type), но by_name всегда до 8
    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]
    assert len(row["by_name"]) == 8, row["by_name"]


@pytest.mark.asyncio
async def test_candidates_residual_excludes_draft_wish_but_not_plan_schedule_purchase(db_session, test_user, test_org):
    """Остаток плановой позиции (used_quantity/residual_quantity) учитывает
    PurchaseItem, привязанный к закупке в plan_schedule, но НЕ учитывает
    черновую заявку (WishItem с тем же feo_planned_item_id, без закупки) —
    ровно правило planned_item_consumption (owner, 2026-08-17)."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-residual")
    planned = await _make_planned_item(db_session, cat, "Бумага А4", quantity=Decimal("10"), unit_price=Decimal("300"), amount=Decimal("3000"), unit="упак")

    purchase = Purchase(status="plan_schedule", item_type="товар", item_name="Бумага")
    db_session.add(purchase)
    await db_session.flush()
    pi = PurchaseItem(
        purchase_id=purchase.id, item_name="Бумага А4", quantity=Decimal("3"), unit="упак",
        unit_price=Decimal("300"), total_price=Decimal("900"), feo_planned_item_id=planned.id,
    )
    db_session.add(pi)

    # Черновая заявка на ту же плановую позицию — НЕ должна уменьшать остаток.
    draft_wish = Wish(org_id=test_org.id, title="Черновик", status="draft", created_by=test_user.id)
    db_session.add(draft_wish)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=draft_wish.id, item_name="Бумага А4", quantity=Decimal("5"), unit="упак",
        unit_price=Decimal("300"), total_price=Decimal("1500"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    row = result[0]

    assert row["used_quantity"] == Decimal("3"), f"expected used_quantity=3 (only the purchase), got {row['used_quantity']}"
    assert row["residual_quantity"] == Decimal("7"), f"expected residual=10-3=7, got {row['residual_quantity']}"
    assert len(row["linked_purchases"]) == 1
    assert row["linked_purchases"][0]["purchase_id"] == purchase.id
    assert row["linked_purchases"][0]["status"] == "plan_schedule"
    assert row["linked_purchases"][0]["quantity"] == 3.0


@pytest.mark.asyncio
async def test_candidates_linked_purchase_initiator_name(db_session, test_admin_user):
    """linked_purchases[].initiator_name — service_note_by, если задан, иначе assigned_user_id."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-initiator")
    planned = await _make_planned_item(db_session, cat, "Стулья офисные", quantity=Decimal("5"), unit_price=Decimal("2000"), amount=Decimal("10000"))

    purchase = Purchase(
        status="plan_schedule", item_type="товар", item_name="Стулья",
        service_note_by=test_admin_user.id,
    )
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Стулья офисные", quantity=Decimal("2"), unit="шт",
        unit_price=Decimal("2000"), total_price=Decimal("4000"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    result = await build_plan_to_wish_candidates(db_session, [planned.id], limit=6)
    linked = result[0]["linked_purchases"]
    assert len(linked) == 1
    assert linked[0]["initiator_user_id"] == test_admin_user.id
    assert linked[0]["initiator_name"] == test_admin_user.full_name


@pytest.mark.asyncio
async def test_create_wish_two_items_catalog_and_manual(db_session, test_user):
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-create")
    planned1 = await _make_planned_item(db_session, cat, "Мышь компьютерная", quantity=Decimal("10"), unit_price=Decimal("500"), amount=Decimal("5000"))
    planned2 = await _make_planned_item(db_session, cat, "Клавиатура", quantity=Decimal("10"), unit_price=Decimal("1500"), amount=Decimal("15000"))

    product = Product(name="Мышь компьютерная Logitech", category="Оргтехника", price=Decimal("450"), unit="шт", is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    items = [
        PlanToWishItemInput(feo_planned_item_id=planned1.id, quantity=Decimal("2"), product_id=product.id, price_source="catalog"),
        PlanToWishItemInput(feo_planned_item_id=planned2.id, quantity=Decimal("1"), item_name="Клавиатура механическая", price_source="plan"),
    ]

    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, None, items)

    assert result["items_count"] == 2
    assert _subsidy.name in result["title"]
    assert result["warnings"] == []

    from sqlalchemy import select
    wish = (await db_session.execute(select(Wish).where(Wish.id == result["wish_id"]))).scalar_one()
    assert wish.status == "draft"
    assert wish.subsidy_id == _subsidy.id

    wish_items = (await db_session.execute(select(WishItem).where(WishItem.wish_id == wish.id).order_by(WishItem.id))).scalars().all()
    assert len(wish_items) == 2

    mouse_item = next(wi for wi in wish_items if wi.feo_planned_item_id == planned1.id)
    assert mouse_item.product_id == product.id
    assert mouse_item.item_name == "Мышь компьютерная Logitech"
    assert mouse_item.unit_price == Decimal("450.00")  # цена из каталога
    assert mouse_item.total_price == Decimal("900.00")  # 2 x 450
    assert mouse_item.feo_category_id == cat.id

    kb_item = next(wi for wi in wish_items if wi.feo_planned_item_id == planned2.id)
    assert kb_item.product_id is None
    assert kb_item.item_name == "Клавиатура механическая"
    assert kb_item.unit_price == Decimal("1500.00")  # плановая цена (price_source='plan')
    assert kb_item.total_price == Decimal("1500.00")

    # Обе позиции — одна и та же категория → wish.feo_category_id проставлена
    assert wish.feo_category_id == cat.id


@pytest.mark.asyncio
async def test_create_wish_price_fallback_when_catalog_price_missing(db_session, test_user):
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-fallback")
    planned = await _make_planned_item(db_session, cat, "Флешка USB", quantity=Decimal("20"), unit_price=Decimal("400"), amount=Decimal("8000"))

    product = Product(name="Флешка USB Kingston 32GB", category="Оргтехника", price=None, is_active=True)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("3"), product_id=product.id, price_source="catalog")]
    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, "Тест fallback", items)

    assert any("плановая цена" in w for w in result["warnings"]), result["warnings"]

    from sqlalchemy import select
    wi = (await db_session.execute(select(WishItem).where(WishItem.wish_id == result["wish_id"]))).scalars().first()
    assert wi.unit_price == Decimal("400.00")  # плановая цена как fallback
    assert wi.total_price == Decimal("1200.00")  # 3 x 400


@pytest.mark.asyncio
async def test_create_wish_warns_when_over_residual(db_session, test_user):
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-overresidual")
    planned = await _make_planned_item(db_session, cat, "Тонер для принтера", quantity=Decimal("5"), unit_price=Decimal("2000"), amount=Decimal("10000"))

    purchase = Purchase(status="plan_schedule", item_type="товар", item_name="Тонер", purchase_number=777)
    db_session.add(purchase)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=purchase.id, item_name="Тонер для принтера", quantity=Decimal("4"), unit="шт",
        unit_price=Decimal("2000"), total_price=Decimal("8000"), feo_planned_item_id=planned.id,
    ))
    await db_session.commit()

    # residual = 5 - 4 = 1; запрашиваем 3 → предупреждение
    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("3"), item_name="Тонер для принтера", price_source="plan")]
    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, "Тест превышения", items)

    assert result["items_count"] == 1
    assert any("остаток 1" in w and "запрошено 3" in w for w in result["warnings"]), result["warnings"]
    assert any("777" in w for w in result["warnings"]), result["warnings"]


@pytest.mark.asyncio
async def test_create_wish_multi_category_sets_feo_per_item(db_session, test_user):
    """Блокер владельца (2026-09-20): позиции из ДВУХ категорий ФЭО → заявка
    заводится с feo_per_item=True (режим «своя категория у каждого товара»),
    а не с обнулённой шапочной feo_category_id без объяснения. У каждой
    позиции при этом свой feo_category_id (её плановой позиции)."""
    subsidy, cat_a = await _make_subsidy_with_leaf(db_session, "Subsidy-multicat")
    cat_b = FeoCategory(subsidy_id=subsidy.id, level=3, name="Прочее-Б")
    db_session.add(cat_b)
    await db_session.commit()
    await db_session.refresh(cat_b)

    planned_a = await _make_planned_item(db_session, cat_a, "Позиция А", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"))
    planned_b = await _make_planned_item(db_session, cat_b, "Позиция Б", quantity=Decimal("5"), unit_price=Decimal("200"), amount=Decimal("1000"))

    items = [
        PlanToWishItemInput(feo_planned_item_id=planned_a.id, quantity=Decimal("1"), item_name="Позиция А", price_source="plan"),
        PlanToWishItemInput(feo_planned_item_id=planned_b.id, quantity=Decimal("1"), item_name="Позиция Б", price_source="plan"),
    ]

    result = await create_wish_from_plan(db_session, test_user, subsidy.id, None, items)

    from sqlalchemy import select
    wish = (await db_session.execute(select(Wish).where(Wish.id == result["wish_id"]))).scalar_one()
    assert wish.feo_per_item is True
    assert wish.feo_category_id is None

    wish_items = (await db_session.execute(select(WishItem).where(WishItem.wish_id == wish.id))).scalars().all()
    assert len(wish_items) == 2
    item_a = next(wi for wi in wish_items if wi.feo_planned_item_id == planned_a.id)
    item_b = next(wi for wi in wish_items if wi.feo_planned_item_id == planned_b.id)
    assert item_a.feo_category_id == cat_a.id
    assert item_b.feo_category_id == cat_b.id


@pytest.mark.asyncio
async def test_create_wish_single_category_no_feo_per_item(db_session, test_user):
    """Позиции из ОДНОЙ категории → feo_category_id заявки = эта категория,
    feo_per_item остаётся False (обычный режим, без изменений поведения)."""
    _subsidy, cat = await _make_subsidy_with_leaf(db_session, "Subsidy-singlecat")
    planned1 = await _make_planned_item(db_session, cat, "Позиция 1", quantity=Decimal("5"), unit_price=Decimal("100"), amount=Decimal("500"))
    planned2 = await _make_planned_item(db_session, cat, "Позиция 2", quantity=Decimal("5"), unit_price=Decimal("200"), amount=Decimal("1000"))

    items = [
        PlanToWishItemInput(feo_planned_item_id=planned1.id, quantity=Decimal("1"), item_name="Позиция 1", price_source="plan"),
        PlanToWishItemInput(feo_planned_item_id=planned2.id, quantity=Decimal("1"), item_name="Позиция 2", price_source="plan"),
    ]

    result = await create_wish_from_plan(db_session, test_user, _subsidy.id, None, items)

    from sqlalchemy import select
    wish = (await db_session.execute(select(Wish).where(Wish.id == result["wish_id"]))).scalar_one()
    assert wish.feo_category_id == cat.id
    assert wish.feo_per_item is False


@pytest.mark.asyncio
async def test_create_wish_422_foreign_subsidy(db_session, test_user):
    _subsidy_a, cat_a = await _make_subsidy_with_leaf(db_session, "Subsidy-A")
    _subsidy_b, _cat_b = await _make_subsidy_with_leaf(db_session, "Subsidy-B")
    planned = await _make_planned_item(db_session, cat_a, "Позиция субсидии A", quantity=Decimal("1"), unit_price=Decimal("100"), amount=Decimal("100"))

    items = [PlanToWishItemInput(feo_planned_item_id=planned.id, quantity=Decimal("1"), item_name="Позиция субсидии A", price_source="plan")]

    with pytest.raises(Exception) as exc_info:
        await create_wish_from_plan(db_session, test_user, _subsidy_b.id, None, items)

    from fastapi import HTTPException
    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 422
