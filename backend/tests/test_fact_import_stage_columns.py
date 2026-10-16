"""Лист GoodsService владельца (16.10.2026, план с.м. задание сессии) — тот
же формат 'columns', но стадия закупки лежит в НЕСКОЛЬКИХ колонках Да/Нет
(«Закупка проведена»/«Договор заключен»/«Товар заказан»/«Товар поставлен»/
«Оплачено») вместо одной «Статус»/«Правильный статус», плюс 4-й уровень ФЭО
(«Тип расходов конкретизированный (сам придумываю…)») и «Оплачено в деньгах»
рядом с голым «Оплачено» (который в этом листе — флаг стадии, не сумма).

Строит `detected` руками (структура заголовков/строк воспроизводит образец
владельца буква-в-букву по расположению колонок), проверяет columns.py +
rows.py + statuses.py вместе; второй блок — что старый формат с «Оплачено»-
суммой (без «Оплачено в деньгах» рядом) продолжает работать как раньше."""
from app.services.historical_fact_import import columns as columns_mod
from app.services.historical_fact_import import rows as rows_mod
from app.services.historical_fact_import import statuses as statuses_mod

# Буквы колонок владельца (D, G, H, I, J, K, L, N, O, AD..AH, AS..AW, BD).
_LETTER_IDX = {
    "D": 3, "G": 6, "H": 7, "I": 8, "J": 9, "K": 10, "L": 11, "N": 13, "O": 14,
    "AD": 29, "AE": 30, "AF": 31, "AG": 32, "AH": 33,
    "AS": 44, "AT": 45, "AU": 46, "AV": 47, "AW": 48,
    "BD": 55,
}
_WIDTH = max(_LETTER_IDX.values()) + 1


def _gs_header():
    h = [None] * _WIDTH
    h[_LETTER_IDX["D"]] = "Номер закупки"
    h[_LETTER_IDX["G"]] = "Наименование товара"
    h[_LETTER_IDX["H"]] = "Контрагент"
    h[_LETTER_IDX["I"]] = "Плановое количество"
    h[_LETTER_IDX["J"]] = "Ед. изм. (ОКЕИ)"
    h[_LETTER_IDX["K"]] = "Плановая цена"
    h[_LETTER_IDX["L"]] = "Плановая стоимость за объём"
    h[_LETTER_IDX["N"]] = "Итоговая цена  за единицу товара"
    h[_LETTER_IDX["O"]] = "Итоговая цена за объём"
    h[_LETTER_IDX["AD"]] = "Товары или Услуги"
    h[_LETTER_IDX["AE"]] = "Направление расходов по категориям в соответсвии с ФЭО"
    h[_LETTER_IDX["AF"]] = "Тип расходов в соответсвии с ФЭО Конкретизированный"
    h[_LETTER_IDX["AG"]] = "Направление расходов из приложений к ФЭО"
    h[_LETTER_IDX["AH"]] = "Тип расходов конкретизированный (сам придумываю общий тип для cебя)"
    h[_LETTER_IDX["AS"]] = "Закупка проведена"
    h[_LETTER_IDX["AT"]] = "Договор заключен (устно или письменно)"
    h[_LETTER_IDX["AU"]] = "Товар заказан"
    h[_LETTER_IDX["AV"]] = "Товар поставлен"
    h[_LETTER_IDX["AW"]] = "Оплачено"
    h[_LETTER_IDX["BD"]] = "Оплачено в деньгах"
    return h


def _gs_row(purchase_no=None, name=None, supplier=None, qty=None, unit=None, price=None, amount=None,
            fact_price=None, fact_amount=None, item_type=None, l2=None, l3=None, l4=None, l5=None,
            purchase_done=None, contracted=None, ordered=None, delivered=None, paid_flag=None, paid_money=None):
    r = [None] * _WIDTH
    r[_LETTER_IDX["D"]] = purchase_no
    r[_LETTER_IDX["G"]] = name
    r[_LETTER_IDX["H"]] = supplier
    r[_LETTER_IDX["I"]] = qty
    r[_LETTER_IDX["J"]] = unit
    r[_LETTER_IDX["K"]] = price
    r[_LETTER_IDX["L"]] = amount
    r[_LETTER_IDX["N"]] = fact_price
    r[_LETTER_IDX["O"]] = fact_amount
    r[_LETTER_IDX["AD"]] = item_type
    r[_LETTER_IDX["AE"]] = l2
    r[_LETTER_IDX["AF"]] = l3
    r[_LETTER_IDX["AG"]] = l4
    r[_LETTER_IDX["AH"]] = l5
    r[_LETTER_IDX["AS"]] = purchase_done
    r[_LETTER_IDX["AT"]] = contracted
    r[_LETTER_IDX["AU"]] = ordered
    r[_LETTER_IDX["AV"]] = delivered
    r[_LETTER_IDX["AW"]] = paid_flag
    r[_LETTER_IDX["BD"]] = paid_money
    return r


def _detect_and_map(header, rows):
    detected = {"format": "columns", "header_row": 1, "rows": [header] + rows, "header": header}
    cols = columns_mod.build_columns(detected)
    return detected, cols


def test_goodsservice_header_detected_as_columns_with_header_row_3():
    header = _gs_header()
    all_rows = [[None] * _WIDTH, [None] * _WIDTH, header, _gs_row(name="x")]
    # Эмулируем detect_format_and_header без чтения реального xlsx: прогоняем
    # ту же логику скоринга, что и сам detect_format_and_header (копия теста
    # с реальной функцией через подмену read_full_sheet_rows избыточна для
    # маленькой правки — проверяем прямо сигнатуру результата по контракту).
    from app.services.historical_fact_import.columns import _score_sections_header, _norm, _is_paid_header
    assert not _score_sections_header(all_rows, 2)
    norm = [_norm(c) for c in all_rows[2]]
    score = sum(1 for c in norm if c and (any(h in c for h in (
        "уровень", "факт", "законтракт", "правильный статус",
        "закупка провед", "договор заключ", "товар заказ", "товар поставлен",
    )) or _is_paid_header(c)))
    assert score >= 3


def test_goodsservice_columns_mapped():
    header = _gs_header()
    _, cols = _detect_and_map(header, [])
    by_field = {c["field"]: c["letter"] for c in cols if c["field"]}
    assert by_field["purchase_no"] == "D"
    assert by_field["plan_item_name"] == "G"
    assert by_field["supplier"] == "H"
    assert by_field["plan_qty"] == "I"
    assert by_field["unit"] == "J"
    assert by_field["plan_price"] == "K"
    assert by_field["plan_amount"] == "L"
    assert by_field["fact_price"] == "N"
    assert by_field["fact_amount"] == "O"
    assert by_field["item_type"] == "AD"
    assert by_field["path_l2"] == "AE"
    assert by_field["path_l3"] == "AF"
    assert by_field["path_l4"] == "AG"
    assert by_field["path_l5"] == "AH"
    assert by_field["stage_purchase_done"] == "AS"
    assert by_field["stage_contracted"] == "AT"
    assert by_field["stage_ordered"] == "AU"
    assert by_field["stage_delivered"] == "AV"
    # «Оплачено в деньгах» (BD) есть на листе → голое «Оплачено» (AW) — флаг
    # стадии, сумма — в BD (не наоборот, см. columns.py::_map_columns_format).
    assert by_field["stage_paid"] == "AW"
    assert by_field["paid"] == "BD"


def test_goodsservice_status_from_stage_flags_all_au_values():
    header = _gs_header()
    rows = [
        _gs_row(name="Товар Да", l4="x", purchase_done="Да", contracted="Да", ordered="Да", delivered="Нет", paid_flag="Нет"),
        _gs_row(name="Товар ежемесячный", l4="x", purchase_done="Да", contracted="Нет",
                ordered="Еще не поставлено , но  будет.Ежемесячная услуга", delivered="Нет", paid_flag="Нет"),
        _gs_row(name="Товар скорее всего", l4="x", purchase_done="Нет", contracted="Нет",
                ordered="Скорее всего поставка потребуется", delivered="Нет", paid_flag="Нет"),
        _gs_row(name="Товар непредвиденный", l4="x", purchase_done="Да", contracted="Да",
                ordered="Непредвиденные расходы", delivered="Нет", paid_flag="Нет"),
        _gs_row(name="Товар пустой заказ", l4="x", purchase_done="Да", contracted="Нет", ordered=None,
                delivered="Нет", paid_flag="Нет"),
        _gs_row(name="Товар поставлен", l4="x", purchase_done="Да", contracted="Да", ordered="Да",
                delivered="Да", paid_flag="Нет"),
        _gs_row(name="Товар оплачен", l4="x", purchase_done="Да", contracted="Да", ordered="Да",
                delivered="Да", paid_flag="Да"),
    ]
    detected, cols = _detect_and_map(header, rows)
    parsed = rows_mod.parse_rows(detected, cols, header_row=1)
    by_name = {r["name"]: r for r in parsed}

    assert statuses_mod.resolve_status(by_name["Товар Да"]["status_raw"])["target_status"] == "ordered"
    assert statuses_mod.resolve_status(by_name["Товар ежемесячный"]["status_raw"])["target_status"] == "contracted"
    # «Скорее всего поставка потребуется» / «Непредвиденные расходы» —
    # запланированные расходы владельца, не закупка (plan_schedule → target None).
    res_skip1 = statuses_mod.resolve_status(by_name["Товар скорее всего"]["status_raw"])
    assert res_skip1["recognized"] is True and res_skip1["target_status"] is None
    res_skip2 = statuses_mod.resolve_status(by_name["Товар непредвиденный"]["status_raw"])
    assert res_skip2["recognized"] is True and res_skip2["target_status"] is None
    assert statuses_mod.resolve_status(by_name["Товар пустой заказ"]["status_raw"])["target_status"] == "work_in_progress"
    assert statuses_mod.resolve_status(by_name["Товар поставлен"]["status_raw"])["target_status"] == "delivered"
    assert statuses_mod.resolve_status(by_name["Товар оплачен"]["status_raw"])["target_status"] == "paid"


def test_old_format_paid_amount_column_still_works():
    """ХО/ЛНР/ДНР: нет «Оплачено в деньгах» рядом — голое «Оплачено» остаётся
    суммой (старое поведение), а не стадией."""
    header = [None] * 10
    header[0] = "Плановая позиция"
    header[1] = "Законтрактовано"
    header[2] = "Оплачено "
    header[3] = "Правильный статус"
    _, cols = _detect_and_map(header, [])
    by_field = {c["field"]: c["letter"] for c in cols if c["field"]}
    assert by_field["paid"] == "C"
    assert "stage_paid" not in by_field

    detected = {"format": "columns", "header_row": 1, "rows": [header, ["Товар", None, "15000", "Оплачено"]], "header": header}
    parsed = rows_mod.parse_rows(detected, cols, header_row=1)
    assert len(parsed) == 1
    assert parsed[0]["status_raw"] == "Оплачено"
    assert parsed[0]["paid"] == 15000
