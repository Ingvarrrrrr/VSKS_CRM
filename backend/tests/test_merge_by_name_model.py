"""Юнит-тесты scripts/merge_by_name_model.py (владелец, доп. дефект пробного
прогона на проде 27.10.2026 — см. докстринг модуля) — без реальной БД:
только чистые функции _store_key/_has_duplicate_store_cards/_has_store_
conflict/_is_group_unique, которые _plan_batch вызывает на уже загруженных
данных (ПРАВИЛО №6 — тест того же механизма, что реально исполняется).

Сценарий 1 («один магазин не продаёт товар дважды»): «Огнетушитель
углекислотный Ярпожинвест ОУ-50 ВСЕ разобран.(эл./сварная труба)» — скрипт
слил ТРИ варианта магазина «Спасатель» (разные исполнения — эл./сварная
труба, одобрение МРС, 00-00002864) с ОДНОЙ карточкой другого магазина в одну
карточку. Правило: группа мержится ТОЛЬКО если в ней не больше одной
карточки на каждый магазин.

Сценарий 2: «Знак P04 'Запрещается тушить водой'» ← «Знак P04 ... FL» — две
карточки ОДНОГО магазина (P04 и P04 FL, FL = фотолюминесцентный, другой
товар) под одним цифровым ключом ("p04")."""
from scripts.merge_by_name_model import (
    _has_duplicate_store_cards, _has_store_conflict, _is_group_unique,
    _store_key,
)
from app.services.product_name_signature import build_signature


def _sig(name, manufacturer=None):
    return build_signature({"name": name, "manufacturer": manufacturer, "characteristics": []})


# ---------------------------------------------------------------------------
# _store_key
# ---------------------------------------------------------------------------

def test_store_key_prefers_price_source_contractor_id():
    assert _store_key(1, 42, (("99", "art"),)) == ("csrc", 42)


def test_store_key_falls_back_to_single_history_contractor():
    assert _store_key(1, None, ((7, "art1"), (7, "art2"))) == ("hist", 7)


def test_store_key_multiple_history_contractors_is_undetermined():
    # История называет НЕСКОЛЬКО разных магазинов — у карточки нет
    # определённого ОДНОГО магазина, не повод считать это одним "hist".
    assert _store_key(1, None, ((7, "a"), (8, "b"))) == ("none",)


def test_store_key_no_history_is_undetermined():
    assert _store_key(1, None, ()) == ("none",)


# ---------------------------------------------------------------------------
# _has_duplicate_store_cards — сценарий ОУ-50 (владелец, 27.10.2026)
# ---------------------------------------------------------------------------

def test_ou50_three_cards_one_store_plus_one_other_store_is_duplicate():
    # 3 карточки магазина "Спасатель" (contractor_id=1) + 1 карточка другого
    # магазина (contractor_id=2) под одним цифровым ключом названия ОУ-50 —
    # ОДНОЗНАЧНО нельзя сливать: 3 варианта одного магазина — РАЗНЫЕ товары.
    price_source_by_id = {101: 1, 102: 1, 103: 1, 104: 2}
    history_pairs_by_id = {101: [], 102: [], 103: [], 104: []}
    assert _has_duplicate_store_cards([101, 102, 103, 104], price_source_by_id, history_pairs_by_id) is True


def test_two_cards_two_different_stores_is_not_duplicate():
    # Обычный «правильный» случай 1-к-1 — ровно по одной карточке на
    # магазин, не конфликт этой проверки (дальше решает match()).
    price_source_by_id = {201: 1, 202: 2}
    history_pairs_by_id = {201: [], 202: []}
    assert _has_duplicate_store_cards([201, 202], price_source_by_id, history_pairs_by_id) is False


def test_p04_fl_two_cards_same_store_is_duplicate():
    # «Знак P04» и «Знак P04 FL» (фотолюминесцентный — другой товар) у
    # ОДНОГО и того же магазина (один и тот же contractor_id, определённый
    # через историю цен, price_source_contractor_id не задан).
    price_source_by_id = {301: None, 302: None}
    history_pairs_by_id = {301: [(9, "p04")], 302: [(9, "p04-fl")]}
    assert _has_duplicate_store_cards([301, 302], price_source_by_id, history_pairs_by_id) is True


def test_two_cards_without_determined_store_is_duplicate():
    # Обе карточки без определённого магазина ("свой источник" по одной, но
    # ДВЕ такие в одной группе — тоже неоднозначно, владелец, п.1).
    price_source_by_id = {401: None, 402: None}
    history_pairs_by_id = {401: [], 402: []}
    assert _has_duplicate_store_cards([401, 402], price_source_by_id, history_pairs_by_id) is True


def test_single_card_without_determined_store_is_not_duplicate_by_itself():
    price_source_by_id = {501: None}
    history_pairs_by_id = {501: []}
    assert _has_duplicate_store_cards([501], price_source_by_id, history_pairs_by_id) is False


# ---------------------------------------------------------------------------
# Пары того же ревью (владелец), которые ДОЛЖНЫ остаться auto/1-к-1 —
# контроль, что _is_group_unique не стал строже, чем нужно.
# ---------------------------------------------------------------------------

def test_known_good_makita_pair_still_unique():
    ids = [1, 2]
    signatures_by_id = {
        1: _sig("Перфоратор MAKITA M8701B", manufacturer="MAKITA"),
        2: _sig("Перфоратор 800 Вт 2,3 Дж SDS-Plus Makita M8701B", manufacturer="Makita"),
    }
    assert _is_group_unique(ids, signatures_by_id) is True


def test_known_good_ibp_cbr_pair_still_unique():
    ids = [1, 2]
    signatures_by_id = {
        1: _sig("ИБП CBR ESN-1KT-4I-LCHERSC"),
        2: _sig("ИБП CBR Essence Online Tower ESN-1KT-4I-LCHERSC"),
    }
    assert _is_group_unique(ids, signatures_by_id) is True


def test_known_good_hp_computer_pair_still_unique():
    ids = [1, 2]
    signatures_by_id = {
        1: _sig("Компьютер HP Z2 G9 TWR 4N3U8AV"),
        2: _sig("Настольный компьютер HP Z2 Tower G9 Workstation (4N3U8AV)"),
    }
    assert _is_group_unique(ids, signatures_by_id) is True


def test_known_good_piroplate_pair_still_unique():
    ids = [1, 2]
    signatures_by_id = {
        1: _sig("ПироПластина Ф-30 автономное устройство пожаротушения"),
        2: _sig("ПироПластина Ф-30"),
    }
    assert _is_group_unique(ids, signatures_by_id) is True


def test_delta_security_force_bt_trio_is_not_unique():
    # Та же тройка, что в test_product_name_signature.py — без проверки
    # "не больше одной карточки на магазин" (у них УЖЕ разные магазины в
    # этом сценарии) _is_group_unique сам обязан вернуть False, раз match()
    # теперь видит "вероятно разные бренды" для каждой пары.
    ids = [1, 2, 3]
    signatures_by_id = {
        1: _sig("Аккумуляторная батарея Delta DT 1240 198х166х170 мм"),
        2: _sig("Аккумуляторная батарея Security Force SF 1240 195х165х170 мм"),
        3: _sig("Аккумуляторная батарея BT 1240 195х165х170 мм"),
    }
    assert _is_group_unique(ids, signatures_by_id) is False


# ---------------------------------------------------------------------------
# _has_store_conflict — не трогали, но проверяем, что до нашей новой
# проверки группа всё равно не проходит (разные store_article у одного
# contractor_id — тот же магазин под разными артикулами).
# ---------------------------------------------------------------------------

def test_store_article_conflict_still_detected():
    history_pairs_by_id = {1: [(9, "art-a")], 2: [(9, "art-b")]}
    assert _has_store_conflict([1, 2], history_pairs_by_id) is True
