"""Тесты интеллектуального Subset-Sum подбора позиций под платёж/расхождение и ранжирования по категориям."""

from decimal import Decimal

from app.services.payment_smart_combo_matcher import (
    CandidateUnit,
    detect_semantic_cluster,
    evaluate_combo_coherence,
    find_sign_error_candidates,
    find_subset_sum_combinations,
)


def _make_unit(
    purchase_id: int,
    name: str,
    amount: float,
    *,
    item_type: str = "товар",
    feo_category_id: int | None = None,
    feo_parent_id: int | None = None,
    product_category: str | None = None,
    contractor_id: int | None = None,
    contractor_inn: str | None = None,
) -> CandidateUnit:
    return CandidateUnit(
        purchase_id=purchase_id,
        registry_number=str(purchase_id),
        subject=name,
        amount=Decimal(str(amount)),
        contractor_id=contractor_id,
        contractor_name=None,
        contractor_inn=contractor_inn,
        feo_category_id=feo_category_id,
        feo_category_name=None,
        feo_parent_id=feo_parent_id,
        product_category=product_category,
        item_type=item_type,
        item_names=[name],
    )


def test_fire_extinguisher_hose_vs_bread_800_rubles():
    """Платёж на 800 ₽ без найденного исполнителя и три закупки без контрагента:
    - Огнетушитель — 500 ₽
    - Рукав пожарный — 300 ₽
    - Батон хлеба — 300 ₽

    Ожидается:
    1) Оба варианта на 800 ₽ найдены (500 + 300).
    2) Вариант «Огнетушитель + Рукав пожарный» идёт первым с вероятностью 'high' («Очень вероятно»),
       т.к. обе позиции относятся к одной тематической группе (Пожарная безопасность / СИЗ).
    3) Вариант «Огнетушитель + Батон хлеба» идёт вторым с вероятностью 'low' («Маловероятно»),
       т.к. позиции из несовместимых категорий (Пожарная безопасность vs Продукты питания).
    """
    u_ext = _make_unit(10, "Огнетушитель ОП-4", 500)
    u_hose = _make_unit(11, "Рукав пожарный Д51", 300)
    u_bread = _make_unit(25, "Батон хлеба нарезной", 300)

    assert detect_semantic_cluster("Огнетушитель ОП-4") == "Пожарно-спасательное имущество и СИЗ"
    assert detect_semantic_cluster("Рукав пожарный Д51") == "Пожарно-спасательное имущество и СИЗ"
    assert detect_semantic_cluster("Батон хлеба нарезной") == "Продукты питания и вода"

    combos = find_subset_sum_combinations(
        [u_ext, u_hose, u_bread],
        Decimal("800"),
    )

    assert len(combos) == 2

    best = combos[0]
    second = combos[1]

    best_ids = {it["purchase_id"] for it in best["items"]}
    second_ids = {it["purchase_id"] for it in second["items"]}

    assert best_ids == {10, 11}
    assert best["probability"] == "high"
    assert best["probability_label"] == "Очень вероятно"
    assert best["can_merge"] is True

    assert second_ids == {10, 25}
    assert second["probability"] == "low"
    assert second["probability_label"] == "Маловероятно"


def test_discrepancy_28000_subset_sum_and_sign_error_14000():
    """Поиск расхождения на 28 000 ₽:
    - находит составную сумму из 3 позиций (12 000 + 9 500 + 6 500 = 28 000 ₽);
    - одновременно проверяет классическую бухгалтерскую ловушку ошибки знака ÷2 (14 000 ₽).
    """
    units = [
        _make_unit(101, "Каска защитная пожарная", 12000, feo_category_id=5),
        _make_unit(102, "Боевая одежда пожарного (БОП)", 9500, feo_category_id=5),
        _make_unit(103, "Краги пожарные пятипалые", 6500, feo_category_id=5),
        _make_unit(104, "Ноутбук офисный", 45000, feo_category_id=8),
        _make_unit(105, "Генератор бензиновый", 14000, feo_category_id=9),
    ]

    combos = find_subset_sum_combinations(units, Decimal("28000"))
    assert len(combos) >= 1
    top = combos[0]
    assert top["total_amount"] == 28000.0
    assert {it["purchase_id"] for it in top["items"]} == {101, 102, 103}
    assert top["probability"] == "high"

    sign_hints = find_sign_error_candidates(units, Decimal("28000"))
    assert len(sign_hints) == 1
    assert sign_hints[0]["purchase_id"] == 105
    assert sign_hints[0]["amount"] == 14000.0
    assert "14 000" in sign_hints[0]["reason"]


def test_coherence_goods_vs_services_penalty():
    """Смешивание товаров и услуг без общей категории понижает вероятность."""
    u_good = _make_unit(1, "Шкаф металлический", 5000, item_type="товар")
    u_srv = _make_unit(50, "Услуги по организации кофе-брейка", 3000, item_type="услуга")

    res = evaluate_combo_coherence([u_good, u_srv])
    assert res["probability"] == "low"
    assert res["probability_label"] == "Маловероятно"


def test_contractor_isolation_predreysovy_vs_afinets():
    """Закупка с именем 'ПРЕДРЕЙСОВЫЙ' не может быть сопоставлена с платежом ИП Афинец."""
    u_pred = _make_unit(
        10,
        'Заказ 4 — ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРЕДРЕЙСОВЫЙ"',
        17000,
        contractor_inn="7704351079",
        item_type="услуга",
    )
    u_tea1 = _make_unit(20, "Чайник электрический", 8500, item_type="товар")
    u_tea2 = _make_unit(21, "Чайник электрический", 8500, item_type="товар")

    # 1. Поиск для Афинца (ИНН 619500069708) на 17 000 ₽:
    # Закупка Предрейсового должна быть отфильтрована!
    combos_afinets = find_subset_sum_combinations(
        [u_pred, u_tea1, u_tea2],
        Decimal("17000"),
        payee_name="Индивидуальный Предприниматель Афинец Александр Александрович",
        payee_inn="619500069708",
    )
    # Закупка Предрейсового не должна быть взята Афинцем!
    for c in combos_afinets:
        pids = [it["purchase_id"] for it in c["items"]]
        assert 10 not in pids

    # 2. Поиск для ООО "ПРЕДРЕЙСОВЫЙ" (ИНН 7704351079) на 17 000 ₽:
    # Должна быть выбрана родная закупка Предрейсового (id=10), а НЕ два чайника!
    combos_pred = find_subset_sum_combinations(
        [u_pred, u_tea1, u_tea2],
        Decimal("17000"),
        payee_name='ООО "ПРЕДРЕЙСОВЫЙ"',
        payee_inn="7704351079",
        purpose_text="Закупка услуг.: по пров.предр.медосмотра водит.",
    )
    assert len(combos_pred) >= 1
    top = combos_pred[0]
    assert top["items"][0]["purchase_id"] == 10
    assert top["probability"] == "high"
    assert top["probability_label"] == "Очень вероятно"


def test_kettles_disqualified_for_service_payment():
    """Когда все родные закупки Предрейсового исчерпаны, чайники не должны предлагаться с вероятностью 'Вероятно'."""
    u_tea1 = _make_unit(20, "Чайник электрический", 8500, item_type="товар")
    u_tea2 = _make_unit(21, "Чайник электрический", 8500, item_type="товар")

    combos = find_subset_sum_combinations(
        [u_tea1, u_tea2],
        Decimal("17000"),
        payee_name='ООО "ПРЕДРЕЙСОВЫЙ"',
        payee_inn="7704351079",
        purpose_text="Закупка услуг.: по пров.предр.медосмотра водит. 02.2026",
    )
    # Чайники под платежом за медосмотр получают вероятность 'low' (Маловероятно),
    # поэтому они не будут навязаны в окне пакетного подбора!
    assert len(combos) == 1
    assert combos[0]["probability"] == "low"
    assert combos[0]["probability_label"] == "Маловероятно"


