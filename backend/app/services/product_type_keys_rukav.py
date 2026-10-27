"""Ключ вида товара — пожарный рукав (владелец, 27.10.2026). Разбор ТОЛЬКО
этого вида — общие helpers живут в app.services.product_type_keys
(ПРАВИЛО №5)."""
import re

from app.services.product_type_keys import TypeKeyResult, blob as _blob, fold as _fold, find_brand as _find_brand

# Диаметр/условный проход — слова "ду "/"диаметр " в тексте, либо цифры
# сразу после буквенного кода рукава (РПМ(Д)-65-..., РПК(В) 50-...).
_DIAMETER_WORD_RE = re.compile(r"(?:ду|диаметр)\D{0,4}(\d{2,3})\b")
# Буквенный код рукава — "рп" + ОДНА буква (м/д/п/в — тип покрытия, но
# встречается и "к" — "РПК" у k_spasatel, владелец, 27.10.2026, см. отчёт
# eval_type_keys.py) + опциональная скобка "(В)"/"(Д)" + диаметр (с
# опциональным пробелом/дефисом между скобкой и цифрами — обе выгрузки
# пишут по-разному: "РПК(В) 50-1,0" у k_spasatel, "РПК(В)-50-1,0" у
# Магазин 01).
_CODE_DIAMETER_RE = re.compile(r"рп[а-я]\([^)]*\)[\s-]*(\d{2,3})\b")

_LENGTH_RE = re.compile(r"(\d{1,3})\s*(?:±\s*\d+\s*)?м\b")

_TYPE_WORDS = {
    "напорный": ("напорн",),
    "латексированный": ("латексир",),
    "с пвх-покрытием": ("пвх",),
    "термостойкий": ("термостойк",),
    "морозостойкий": ("морозостойк",),
    "износостойкий": ("износостойк",),
}


def _rukav_type(text: str) -> tuple:
    flags = []
    for label, stems in _TYPE_WORDS.items():
        if any(stem in text for stem in stems):
            flags.append(label)
    return tuple(sorted(flags))


# Тип головки (ГР/ГМ/ГЦ) + номер + материал, прилепленный к номеру БЕЗ
# пробела ("ГР-65А" — "а" = алюминиевая; "ГР-50ал"/"ГР-50пл"/"ГР-50а-пл" —
# владелец, 27.10.2026, правка после обзора: материал головки — ДРУГОЙ
# товар, не вариант написания того же. Альтернативы по убыванию длины,
# чтобы "а-пл" не обрезалось до "а".
_HEAD_CODE_RE = re.compile(r"(гр|гм|гц)-?(\d{2,3})(а-пл|ал|пл|а)?\b")

# "Ствол" — комплектация РС-NN(.NN) — владелец, 27.10.2026: "с головками
# ГР-50" и "с головкой ГР-50 и стволом РС-50.01" — ДРУГОЙ товар (другая
# комплектация), не просто другая запись одного и того же.
_STVOL_WORD_RE = re.compile(r"ствол")
_STVOL_CODE_RE = re.compile(r"рс-?(\d{2,3}(?:[.,]\d{1,2})?)")


def _heads(text: str) -> tuple:
    codes = sorted(set(_HEAD_CODE_RE.findall(text)))
    with_heads = "с головк" in text
    without_heads = "без головк" in text
    return (tuple(codes), with_heads, without_heads)


def _stvol(text: str) -> tuple:
    has_stvol = bool(_STVOL_WORD_RE.search(text))
    code_match = _STVOL_CODE_RE.search(text)
    code = code_match.group(1) if code_match else None
    return (has_stvol, code)


def rukav_key(name, characteristics, manufacturer, category_path) -> TypeKeyResult:
    text = _blob(name, characteristics, category_path)
    missing = []

    diameter = None
    diam_match = _DIAMETER_WORD_RE.search(text)
    if diam_match:
        diameter = diam_match.group(1)
    else:
        code_diam_match = _CODE_DIAMETER_RE.search(text)
        if code_diam_match:
            diameter = code_diam_match.group(1)
    if diameter is None:
        missing.append("диаметр")

    length = None
    length_match = _LENGTH_RE.search(text)
    if length_match:
        length = length_match.group(1)
    else:
        missing.append("длина")

    rukav_type = _rukav_type(text)  # пустой tuple легитимен
    heads = _heads(text)
    stvol = _stvol(text)

    brand = _find_brand(text, manufacturer, name)
    if brand is None:
        missing.append("бренд")

    folded_brand = _fold(brand) if brand else None
    partial = (folded_brand, diameter) if (brand and diameter) else None
    key = None
    if brand and diameter and length:
        key = (folded_brand, diameter, length, rukav_type, heads, stvol)

    return TypeKeyResult(kind="рукав", key=key, partial=partial, missing=missing, extra={})
