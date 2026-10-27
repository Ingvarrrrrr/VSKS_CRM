"""normalize_barcode (владелец, 27.10.2026, app/services/barcodes.py) —
проверка контрольной цифры GS1 и свёртка UPC-12/GTIN-14 в EAN-13, на
реальных валидных штрихкодах (не придуманных числах)."""
from app.services.barcodes import normalize_barcode


def test_valid_ean13_kept_as_is():
    # Реальный валидный EAN-13 (общеизвестный пример Kellogg's Nutri-Grain).
    assert normalize_barcode("4006381333931") == "4006381333931"


def test_valid_ean13_with_separators_stripped():
    assert normalize_barcode("400-6381-333931") == "4006381333931"
    assert normalize_barcode(" 4006381333931 ") == "4006381333931"


def test_invalid_check_digit_rejected():
    # Последняя цифра правильного кода заменена — контрольная цифра не совпадёт.
    assert normalize_barcode("4006381333930") is None


def test_valid_ean8_kept_as_is():
    # Реальный валидный EAN-8 (пример GS1): "96385074".
    assert normalize_barcode("96385074") == "96385074"


def test_invalid_ean8_rejected():
    assert normalize_barcode("96385075") is None


def test_upc12_converted_to_ean13_with_leading_zero():
    # UPC-A валидный пример: "036000291452" (Pringles).
    upc = "036000291452"
    result = normalize_barcode(upc)
    assert result == "0" + upc
    assert len(result) == 13


def test_upc12_and_its_ean13_form_give_same_key():
    """Решение владельца 27.10.2026: UPC-12 и EAN-13 того же товара должны
    дать ОДИН ключ — свёртка UPC-12 → '0'+digits должна совпасть с тем, как
    магазин, использующий EAN-13, естественно записал бы тот же товар."""
    upc = "036000291452"
    ean13_equivalent = "0" + upc
    assert normalize_barcode(upc) == normalize_barcode(ean13_equivalent) == ean13_equivalent


def test_invalid_upc12_rejected():
    assert normalize_barcode("036000291453") is None


def test_gtin14_with_leading_zero_converted_to_ean13():
    ean13 = "4006381333931"
    gtin14 = "0" + ean13
    assert normalize_barcode(gtin14) == ean13


def test_gtin14_without_leading_zero_kept_as_14():
    # GTIN-14 валидный пример: индикатор упаковки 1 перед EAN-13 данными
    # (тот же алгоритм проверки, просто другая длина) — должен остаться
    # 14-значным (другая единица учёта, не сворачивается в EAN-13).
    # Строим валидный код: 13 цифр данных (без контрольной) + считаем
    # контрольную по общему алгоритму.
    from app.services.barcodes import _check_digit_valid
    data13 = "1400638133393"  # индикатор '1' + 12 цифр из примера выше
    for d in range(10):
        candidate = data13 + str(d)
        if _check_digit_valid(candidate):
            assert normalize_barcode(candidate) == candidate
            assert len(normalize_barcode(candidate)) == 14
            break
    else:
        raise AssertionError("не нашли валидную контрольную цифру — ошибка в тесте")


def test_wrong_length_rejected():
    assert normalize_barcode("12345") is None
    assert normalize_barcode("123456789012345") is None


def test_non_numeric_input_rejected():
    assert normalize_barcode("не штрихкод") is None
    assert normalize_barcode("") is None
    assert normalize_barcode(None) is None
