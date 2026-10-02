"""Разбор строк «Импорта факта» — оба формата (ХО 'columns', ЛНР 'sections').

Строит `detected`-словарь руками (без реального xlsx — только структура
заголовков/строк, воспроизводящая образцы владельца буква-в-букву по
расположению колонок) и проверяет columns.py + rows.py вместе: что заголовок
распознаётся в нужные field, что иерархия «заливается вниз» правильно, что
итоговая/категорийная строка без листового имени пропускается, и что
количество факта в ХО пересчитывается из сумма/цена (владелец: колонка S
бывает испорчена порядковыми номерами).
"""
from app.services.historical_fact_import import columns as columns_mod
from app.services.historical_fact_import import rows as rows_mod


def _ho_header():
    h = [None] * 28
    h[0] = "Субсидия"
    h[4] = "Уровень 2 (Направление расходов по ФЭО)"
    h[5] = "Уровень 3 (Тип расходов по ФЭО)"
    h[6] = "Уровень 4 (Конкретизированный)"
    h[7] = "Плановая позиция (папка НЕ создаётся)"
    h[8] = "Товар/услуга/работа"
    h[9] = "Комментарий"
    h[10] = "План 2026"
    h[14] = "Ед. изм. плана"
    h[15] = "Плановое количество"
    h[16] = "Плановая цена за единицу"
    h[17] = "Сумма плана"
    h[18] = "Факт"
    h[21] = "Оплачено "
    h[22] = "Законтрактовано"
    h[23] = "Статус"
    h[24] = "Правильный статус"
    h[25] = "№ Закупки"
    h[26] = "№ Заявки"
    h[27] = "Поставщик "
    return h


def _ho_row(l2=None, l3=None, l4=None, unit=None, qty=None, price=None, amount=None,
            fact_qty=None, fact_price=None, fact_amount=None, paid=None, contracted=None,
            status=None, status_raw=None, purchase_no=None, supplier=None):
    r = [None] * 28
    r[0] = "ХО_2026"
    r[4], r[5], r[6] = l2, l3, l4
    r[14], r[15], r[16], r[17] = unit, qty, price, amount
    r[18], r[19], r[20] = fact_qty, fact_price, fact_amount
    r[21], r[22] = paid, contracted
    r[23], r[24] = status, status_raw
    r[25], r[27] = purchase_no, supplier
    return r


def test_ho_columns_format_detected_and_mapped():
    header = _ho_header()
    detected = {"format": "columns", "header_row": 1, "rows": [header], "header": header}
    cols = columns_mod.build_columns(detected)
    by_field = {c["field"]: c["letter"] for c in cols if c["field"]}
    assert by_field["path_l2"] == "E"
    assert by_field["path_l3"] == "F"
    assert by_field["path_l4"] == "G"
    assert by_field["plan_item_name"] == "H"
    assert by_field["fact_qty"] == "S"
    assert by_field["fact_price"] == "T"
    assert by_field["fact_amount"] == "U"
    assert by_field["paid"] == "V"
    assert by_field["contracted"] == "W"
    assert by_field["status_raw"] == "Y"
    assert by_field["purchase_no"] == "Z"
    assert by_field["supplier"] == "AB"


def test_ho_total_row_without_leaf_name_is_skipped():
    header = _ho_header()
    total_row = _ho_row(l2="Заработная плата и иные выплаты", amount=14359242.42, fact_amount=14359242.42)
    leaf_row = _ho_row(
        l3="Заработная плата работников", unit="усл", qty=1, price=18492000, amount=13277966.84,
        fact_price=18492000, fact_amount=8235337.78, status="В работе", status_raw="В работе",
    )
    detected = {"format": "columns", "header_row": 1, "rows": [header, total_row, leaf_row], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Заработная плата работников"
    assert parsed[0]["path"] == ["Заработная плата и иные выплаты"]


def test_ho_fact_quantity_recomputed_from_amount_over_price():
    """Владелец: колонка S (факт кол-во) в ХО местами испорчена порядковыми
    номерами — реальное количество = сумма / цена, сырое значение S не
    читается напрямую."""
    header = _ho_header()
    # fact_qty (S) = 999 — заведомо «мусорное» порядковое значение, не 8235337.78/18492000.
    row = _ho_row(
        l3="Заработная плата работников", unit="усл", qty=1, price=18492000, amount=13277966.84,
        fact_qty=999, fact_price=18492000, fact_amount=8235337.78,
        status_raw="В работе",
    )
    detected = {"format": "columns", "header_row": 1, "rows": [header, row], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 1
    expected_qty = 8235337.78 / 18492000
    assert abs(float(parsed[0]["fact"]["qty"]) - expected_qty) < 1e-6


def _lnr_group_row():
    g = [None] * 17
    g[6] = "ПЛАН"
    g[9] = "ФАКТ"
    g[12] = "Оплата"
    g[13] = "Законтрактовано"
    g[14] = "Экономия"
    g[15] = "Правильный статус"
    g[16] = "Поставщик"
    return g


def _lnr_sub_row():
    s = [None] * 17
    s[0] = "№ п/п"
    s[2] = "Наименование статей затрат"
    s[4] = "Подкатегория"
    s[5] = "Ед. изм."
    s[6] = "Количество, ед."
    s[7] = "Сумма за ед., руб."
    s[8] = "Всего, руб"
    s[9] = "Количество, ед."
    s[10] = "Сумма за ед., руб."
    s[11] = "Всего, руб"
    return s


def _lnr_level1_row(seq, name, amount, paid, contracted):
    r = [None] * 17
    r[0], r[2], r[8] = seq, name, amount
    r[12], r[13] = paid, contracted
    return r


def _lnr_leaf_row(name, unit, qty, price, amount, fact_qty, fact_price, fact_amount, paid, contracted, status):
    r = [None] * 17
    r[4], r[5], r[6], r[7], r[8] = name, unit, qty, price, amount
    r[9], r[10], r[11] = fact_qty, fact_price, fact_amount
    r[12], r[13] = paid, contracted
    r[15] = status
    return r


def test_lnr_sections_format_detected_and_mapped():
    group_row = _lnr_group_row()
    sub_row = _lnr_sub_row()
    detected = {"format": "sections", "header_row": 3, "rows": [group_row, sub_row],
                "group_row": group_row, "sub_row": sub_row}
    cols = columns_mod.build_columns(detected)
    by_field = {c["field"]: c["letter"] for c in cols if c["field"]}
    assert by_field["path_l2"] == "C"
    assert by_field["plan_item_name"] == "E"
    assert by_field["fact_qty"] == "J"
    assert by_field["fact_price"] == "K"
    assert by_field["fact_amount"] == "L"
    assert by_field["paid"] == "M"
    assert by_field["contracted"] == "N"
    assert by_field["status_raw"] == "P"
    assert by_field["supplier"] == "Q"


def test_lnr_level1_total_row_skipped_leaf_kept():
    group_row = _lnr_group_row()
    sub_row = _lnr_sub_row()
    total_row = _lnr_level1_row(1, "Оплата труда", 32296800, 18549309.98, 18549309.98)
    leaf_row = _lnr_leaf_row(
        "Заработная плата работников", "мес", 12, 2691400, 32296800,
        None, None, 18549309.98, 18549309.98, 18549309.98, "Оплачено",
    )
    detected = {"format": "sections", "header_row": 2, "rows": [group_row, sub_row, total_row, leaf_row],
                "group_row": group_row, "sub_row": sub_row}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 2)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Заработная плата работников"
    assert parsed[0]["path"] == ["Оплата труда"]
    assert parsed[0]["status_raw"] == "Оплачено"
