"""Ключ вида товара — пожарный шкаф (владелец, 27.10.2026). Разбор ТОЛЬКО
этого вида — общие helpers живут в app.services.product_type_keys
(ПРАВИЛО №5)."""
import re

from app.services.product_type_keys import TypeKeyResult, blob as _blob, fold as _fold, find_brand as _find_brand

# "шпк" допускает дефис/пробел между буквами (Магазин 01 пишет "ШП-К-310") —
# модель — 2-3 цифры сразу после.
_MODEL_RE = re.compile(r"ш[\s-]?п[\s-]?к[\s-]?(\d{2,3})\b")

# 3-буквенный код исполнения сразу после модели у k_spasatel (нет отдельных
# characteristics): позиция 1 — способ установки (н/в), позиция 2 — дверца
# (о/з), позиция 3 — цвет (б/к/н-нержавейка). У Магазин 01 то же самое ЧАЩЕ
# написано словами в скобках в конце названия — разбираем оба варианта и
# берём словесный, если он есть (надёжнее кода).
_SUFFIX_CODE_RE = re.compile(r"\b([нв])([оз])([бкн])\b")

_INSTALL_WORDS = {"навесной": "навесной", "встроенный": "встроенный"}
_DOOR_WORDS = {"открытый": "открытый", "закрытый": "закрытый"}
_COLOR_WORDS = {
    "белый": "белый", "красный": "красный",
    "нержавеющ": "нержавеющая сталь", "сталь": "нержавеющая сталь",
}

_SUFFIX_DECODE_INSTALL = {"н": "навесной", "в": "встроенный"}
_SUFFIX_DECODE_DOOR = {"о": "открытый", "з": "закрытый"}
_SUFFIX_DECODE_COLOR = {"б": "белый", "к": "красный", "н": "нержавеющая сталь"}


def _word_in_text(text, words_map):
    for stem, canonical in words_map.items():
        if stem in text:
            return canonical
    return None


def shkaf_key(name, characteristics, manufacturer, category_path) -> TypeKeyResult:
    text = _blob(name, characteristics, category_path)
    missing = []

    model_match = _MODEL_RE.search(text)
    model = model_match.group(1) if model_match else None
    if model is None:
        missing.append("модель")

    install = _word_in_text(text, _INSTALL_WORDS)
    door = _word_in_text(text, _DOOR_WORDS)
    color = _word_in_text(text, _COLOR_WORDS)

    if install is None or door is None or color is None:
        # Фолбэк — 3-буквенный код сразу после модели (k_spasatel).
        window_start = model_match.end() if model_match else 0
        suffix_match = _SUFFIX_CODE_RE.search(text, window_start, window_start + 15)
        if suffix_match:
            if install is None:
                install = _SUFFIX_DECODE_INSTALL.get(suffix_match.group(1))
            if door is None:
                door = _SUFFIX_DECODE_DOOR.get(suffix_match.group(2))
            if color is None:
                color = _SUFFIX_DECODE_COLOR.get(suffix_match.group(3))

    if install is None:
        missing.append("способ установки")
    if door is None:
        missing.append("дверца")
    if color is None:
        missing.append("цвет")

    brand = _find_brand(text, manufacturer, name)
    # Бренд у шкафов в обеих выгрузках почти всегда отсутствует (manufacturer
    # null, в названии бренд не пишут) — требуем его так же строго, как у
    # огнетушителя/рукава (владелец, см. докстринг product_type_keys.py);
    # отсутствие просто означает, что для этого товара автосведения не
    # будет — учитывается в отчёте eval_type_keys.py как отдельная причина
    # "нет бренда", не как брак разбора.
    if brand is None:
        missing.append("бренд")

    folded_brand = _fold(brand) if brand else None
    partial = (folded_brand, model) if (brand and model) else None
    key = None
    if brand and model and install and door and color:
        key = (folded_brand, model, install, door, color)

    return TypeKeyResult(kind="шкаф", key=key, partial=partial, missing=missing, extra={})
