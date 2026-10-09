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


def _ho_row(l2=None, l3=None, l4=None, item_name=None, unit=None, qty=None, price=None, amount=None,
            fact_qty=None, fact_price=None, fact_amount=None, paid=None, contracted=None,
            status=None, status_raw=None, purchase_no=None, supplier=None):
    r = [None] * 28
    r[0] = "ХО_2026"
    r[4], r[5], r[6] = l2, l3, l4
    r[7] = item_name  # «Плановая позиция» — колонка H, см. _ho_header()
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


def test_ho_header_oplata_variants_mapped():
    """Повод: файл ЛНР МАО 07.10.2026, лист «Смета доходов и расходов 20 (3)»
    — колонка T «Оплата» (без «-но») не распознавалась как paid. «Оплата»/
    «Оплата факт» → paid, «Оплачено »/«Оплачено» (как в образце ХО) → paid,
    «Оплата труда» — НЕ paid (ФОТ, не платёж)."""
    header = _ho_header()
    header[21] = "Оплата"
    detected = {"format": "columns", "header_row": 1, "rows": [header], "header": header}
    cols = columns_mod.build_columns(detected)
    by_field = {c["field"]: c["letter"] for c in cols if c["field"]}
    assert by_field["paid"] == "V"

    header2 = _ho_header()
    header2[21] = "Оплата факт"
    detected2 = {"format": "columns", "header_row": 1, "rows": [header2], "header": header2}
    cols2 = columns_mod.build_columns(detected2)
    by_field2 = {c["field"]: c["letter"] for c in cols2 if c["field"]}
    assert by_field2["paid"] == "V"

    header3 = _ho_header()
    header3[21] = "Оплачено "
    detected3 = {"format": "columns", "header_row": 1, "rows": [header3], "header": header3}
    cols3 = columns_mod.build_columns(detected3)
    by_field3 = {c["field"]: c["letter"] for c in cols3 if c["field"]}
    assert by_field3["paid"] == "V"

    header4 = _ho_header()
    header4[21] = "Оплата труда"
    detected4 = {"format": "columns", "header_row": 1, "rows": [header4], "header": header4}
    cols4 = columns_mod.build_columns(detected4)
    assert "paid" not in {c["field"] for c in cols4}

    # Значение из колонки «Оплата» действительно попадает в row["paid"].
    row = _ho_row(
        l3="Заработная плата работников", unit="усл", qty=1, price=18492000, amount=18492000,
        fact_price=18492000, fact_amount=18492000, paid=171159, status="Оплачено", status_raw="Оплачено",
    )
    detected5 = {"format": "columns", "header_row": 1, "rows": [header, row], "header": header}
    parsed = rows_mod.parse_rows(detected5, cols, 1)
    assert len(parsed) == 1
    assert float(parsed[0]["paid"]) == 171159


def test_ho_total_row_without_leaf_name_is_skipped():
    """🟢 Правка (план lazy-swimming-hollerith.md): раньше `path` переносил
    Уровень 2 из строки-итога выше (`carry`) — перенос между строками убран
    целиком (искать позицию/уровень только в своей строке), остался только
    перенос значения ОДНОЙ объединённой Excel-ячейки (не этот случай:
    total_row и leaf_row — разные ячейки). `leaf_row` не задаёт свой Уровень 2
    — `path` у позиции теперь пуст, а не `["Заработная плата и иные выплаты"]»."""
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
    assert parsed[0]["path"] == []


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
    """🟢 Та же правка, что у `test_ho_total_row_without_leaf_name_is_skipped`
    (owner: пример — это класс проблемы, искать все такие же, не только
    названный) — `leaf_row` своего Уровня 2 не задаёт, перенос из total_row
    убран, `path` пуст, а не `["Оплата труда"]`."""
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
    assert parsed[0]["path"] == []
    assert parsed[0]["status_raw"] == "Оплачено"


# ── 🔵 Правка (план lazy-swimming-hollerith.md): правило «строка без своей
# «Плановой позиции» — категория, не позиция» ─────────────────────────────


def test_total_row_above_two_same_named_positions_is_skipped():
    """Итог Уровня 3 без своей «Плановой позиции», под ним 2 позиции с тем же
    названием (владелец, боевой файл: 146 «Расходы на приобретение ГСМ» —
    итог 700 000, 147/148 — по 413 050,66 и 286 949,34) → итог пропущен
    молча, 2 отдельные строки-позиции остаются."""
    header = _ho_header()
    total_row = _ho_row(l3="Расходы на приобретение ГСМ", amount=700000, fact_amount=700000)
    pos1 = _ho_row(l3="Расходы на приобретение ГСМ", item_name="Расходы на приобретение ГСМ",
                    amount=413050.66, fact_amount=413050.66, status_raw="Оплачено")
    pos2 = _ho_row(l3="Расходы на приобретение ГСМ", item_name="Расходы на приобретение ГСМ",
                    amount=286949.34, fact_amount=286949.34, status_raw="Оплачено")
    detected = {"format": "columns", "header_row": 1, "rows": [header, total_row, pos1, pos2], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 2
    assert [float(p["fact"]["amount"]) for p in parsed] == [413050.66, 286949.34]
    assert all(p["name"] == "Расходы на приобретение ГСМ" for p in parsed)


def test_two_nested_total_rows_above_twelve_positions_without_l4():
    """Два вложенных итога (Уровень 3, затем Уровень 4 с тем же названием,
    что и у позиций) + 12 позиций без заполненного Уровня 4, но со своей
    «Плановой позицией» (боевой файл ДНРР: 99 — итог Ур.3, 100 — итог Ур.4,
    101–112 — 12 позиций «Услуги по проведению предрейсовых…») → оба итога
    пропущены молча, 12 строк-позиций остаются."""
    header = _ho_header()
    title = "Услуги по проведению предрейсовых медицинских осмотров"
    total_lvl3 = _ho_row(l2="Прочие расходы", l3=title, amount=1200000, fact_amount=1200000)
    total_lvl4 = _ho_row(l2="Прочие расходы", l3=title, l4=title, amount=1200000, fact_amount=1200000)
    positions = [
        _ho_row(l2="Прочие расходы", l3=title, item_name=title, amount=100000, fact_amount=100000,
                status_raw="Оплачено")
        for _ in range(12)
    ]
    rows = [header, total_lvl3, total_lvl4, *positions]
    detected = {"format": "columns", "header_row": 1, "rows": rows, "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 12
    assert all(p["name"] == title for p in parsed)


def test_category_without_position_with_paid_status_gets_no_item_name_flag():
    """Категория без своей «Плановой позиции», но со статусом «Оплачено»
    (боевой файл ДНРР, строки 150–152 «Проезд, проживание, питание») — не
    пропуск молча, а строка с `no_item_name=True` (preview.py превращает её в
    уведомление владельцу, см. test_fact_import_commit.py)."""
    header = _ho_header()
    other_row = _ho_row(l4="Другая статья", item_name="Другая статья", amount=1, fact_amount=1)
    category_row = _ho_row(l4="Проезд, проживание, питание", amount=50000, fact_amount=50000,
                            status_raw="Оплачено")
    detected = {"format": "columns", "header_row": 1, "rows": [header, category_row, other_row], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 2
    cat = next(p for p in parsed if p["name"] == "Проезд, проживание, питание")
    assert cat["no_item_name"] is True
    assert cat["status_raw"] == "Оплачено"


def test_category_without_position_with_plan_schedule_status_gets_no_item_name_flag():
    """Координатор, повторная правка 10.10: статус «План закупок» (ДНРР 152)
    — тоже данные, не «ничего не написано»; категория всё равно получает
    `no_item_name=True`, не тихий пропуск, как при пустом статусе."""
    header = _ho_header()
    other_row = _ho_row(l4="Другая статья", item_name="Другая статья", amount=1, fact_amount=1)
    category_row = _ho_row(l4="Проезд, проживание, питание", status_raw="План закупок")
    detected = {"format": "columns", "header_row": 1, "rows": [header, category_row, other_row], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 2
    cat = next(p for p in parsed if p["name"] == "Проезд, проживание, питание")
    assert cat["no_item_name"] is True
    assert cat["status_raw"] == "План закупок"


def test_category_without_position_and_without_data_is_dropped():
    """Та же категория, но без статуса/факта/оплаты — пропуск молча, строки
    в разборе нет вовсе (ничего показать владельцу)."""
    header = _ho_header()
    other_row = _ho_row(l4="Другая статья", item_name="Другая статья", amount=1, fact_amount=1)
    category_row = _ho_row(l4="Проезд, проживание, питание")
    detected = {"format": "columns", "header_row": 1, "rows": [header, category_row, other_row], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Другая статья"


def test_empty_level_not_carried_from_row_above():
    """🟢 Строка без своего Уровня 2 — путь пуст, значение из строки выше НЕ
    подставляется (раньше — `carry`)."""
    header = _ho_header()
    row1 = _ho_row(l2="Направление А", item_name="Позиция 1", amount=1, fact_amount=1)
    row2 = _ho_row(item_name="Позиция 2", amount=2, fact_amount=2)  # свои l2/l3 не заданы
    detected = {"format": "columns", "header_row": 1, "rows": [header, row1, row2], "header": header}
    cols = columns_mod.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 2
    assert parsed[0]["path"] == ["Направление А"]
    assert parsed[1]["path"] == []  # без переноса l2 строки выше


def test_file_without_item_name_column_keeps_old_fallback_behavior():
    """Файл без колонки «Плановая позиция» вообще (старое устройство) —
    имя строки берётся из самого глубокого заполненного уровня СВОЕЙ строки
    (без carry), категорийная/no_item_name-логика не включается."""
    header = _ho_header()
    header[7] = None  # «Плановая позиция (папка НЕ создаётся)» — колонки нет
    total_row = _ho_row(l2="Направление", amount=100000, fact_amount=100000)  # нет листового имени — пропуск
    leaf_row = _ho_row(l3="Статья расходов", amount=50000, fact_amount=50000, status_raw="В работе")
    detected = {"format": "columns", "header_row": 1, "rows": [header, total_row, leaf_row], "header": header}
    cols = columns_mod.build_columns(detected)
    assert "plan_item_name" not in {c["field"] for c in cols}
    parsed = rows_mod.parse_rows(detected, cols, 1)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "Статья расходов"
    assert parsed[0]["no_item_name"] is False


def test_merged_level_cell_is_filled_across_rows():
    """Исключение из «ничего не переносится между строками» — ячейка,
    физически объединённая в Excel на несколько строк (одна ячейка). Проверка
    через настоящий .xlsx (openpyxl) и `detect_format_and_header`, который
    теперь вызывает `read_full_sheet_rows(..., fill_merged=True)` для импорта
    факта."""
    from io import BytesIO

    from openpyxl import Workbook

    from app.services.historical_fact_import import columns as columns_mod2

    wb = Workbook()
    ws = wb.active
    header = _ho_header()
    ws.append(header)
    ws.append(_ho_row(l2="Направление (объединено)", l3="Статья", item_name="Позиция 1", amount=1, fact_amount=1))
    ws.append(_ho_row(l3="Статья", item_name="Позиция 2", amount=2, fact_amount=2))  # своего l2 нет
    # Объединяем E2:E3 (Уровень 2, строки 2-3, 1-based Excel) — одна ячейка на обе строки данных.
    ws.merge_cells(start_row=2, start_column=5, end_row=3, end_column=5)
    buf = BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    detected = columns_mod2.detect_format_and_header(content, "test.xlsx", None)
    cols = columns_mod2.build_columns(detected)
    parsed = rows_mod.parse_rows(detected, cols, detected["header_row"])
    assert len(parsed) == 2
    # Объединённая ячейка «Направление (объединено)» — честно повторена во
    # второй строке диапазона (НЕ carry: это та же физическая Excel-ячейка);
    # «Статья» — собственный Уровень 3 второй строки, не из merge.
    assert parsed[1]["path"] == ["Направление (объединено)", "Статья"]


def test_ambiguous_message_uses_plural_and_row_ranges():
    """Текст «позиции нет в плане GALA» — число позиций с окончанием,
    диапазон строк без повторного независимого форматтера (ПРАВИЛО №6,
    `feo_import_common.format_rows`)."""
    from app.services.historical_fact_import.preview import _row_ranges_only, _ru_plural_position

    assert _ru_plural_position(1) == "позиция"
    assert _ru_plural_position(2) == "позиции"
    assert _ru_plural_position(5) == "позиций"
    assert _ru_plural_position(11) == "позиций"
    assert _ru_plural_position(111) == "позиций"
    assert _row_ranges_only([99, 100, 101, 103]) == "99–101, 103"
    assert _row_ranges_only([144]) == "144"
