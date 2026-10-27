"""Тест дефекта регистра в fold_brand_or_code (владелец, 27.10.2026):
гомоглифы сворачивались ДО регистра, а таблица гомоглифов задумано
несимметрична по регистру исходных букв (строчные в/к/м/н/т не входят в
общий _HOMOGLYPH_MAP) — "MAKITA" и "Makita" давали разные fold-строки.
Починено порядком операций (регистр СНАЧАЛА) + строчными парами тех же
букв ТОЛЬКО в _BRAND_CODE_FOLD_MAP (brand_code_fold.py), общий
_HOMOGLYPH_MAP не трогаем (другой потребитель, другое назначение)."""
from app.services.brand_code_fold import fold_brand_or_code


def test_makita_case_insensitive_including_cyrillic_m():
    variants = ["MAKITA", "Makita", "makita", "МAKITA"]  # последний — кириллическая "М"
    folded = {fold_brand_or_code(v) for v in variants}
    assert len(folded) == 1, folded


def test_zubr_case_insensitive():
    assert fold_brand_or_code("ЗУБР") == fold_brand_or_code("Зубр")


def test_code_with_cyrillic_homoglyph_letter():
    # DHR242RT (латиница) / dhr242rt (нижний регистр) / DНR242RT (кириллическая Н)
    a = fold_brand_or_code("DHR242RT")
    b = fold_brand_or_code("dhr242rt")
    c = fold_brand_or_code("DНR242RT")
    assert a == b == c, (a, b, c)


def test_digits_not_folded_into_letters():
    # Цифро-буквенные пары (0/О, 3/З, 4/Ч) здесь ИСКЛЮЧЕНЫ намеренно — иначе
    # "ОП-10"/"ОП-100" слипаются (см. docstring модуля) — регрессия не должна
    # появиться при фиксе регистра.
    assert fold_brand_or_code("ОП-10") != fold_brand_or_code("ОП-100")
