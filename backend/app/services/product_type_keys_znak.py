"""Ключ вида товара — знак безопасности, ГОСТ 12.4.026/Р 12.4.026 (владелец,
27.10.2026). Разбор ТОЛЬКО этого вида — общие helpers живут в
app.services.product_type_keys (ПРАВИЛО №5).

Бренд у знака — НЕ часть ключа (в отличие от огнетушителя/рукава/шкафа):
тот же код+размер+материал от разных производителей — это один и тот же
стандартный предмет, а не два разных товара (владелец, см. докстринг
product_type_keys.py) — бренд попадает только в extra как мягкая проверка."""
import re

from app.services.product_type_keys import TypeKeyResult, blob as _blob, fold as _fold, find_brand as _find_brand

# Код знака — одна буква (f/e/w/p/m/t, после fold часть латиницы ушла в
# кириллицу по brand_code_fold._HOMOGLYPH_MAP: E->е, P->р, остальные (f/w)
# остаются латиницей) + 1-2 цифры, сразу после слова "знак".
_SIGN_CODE_RE = re.compile(r"знак\s+([a-zа-я])\s*-?\s*(\d{1,2})\b")

# Размер — "200х200", "150x300", с опциональным "мм" — обе цифры попадают в
# key КАК ПАРА (не отсортированы — 200х300 и 300х200 разные таблички).
_SIGN_SIZE_RE = re.compile(r"(\d{2,4})\s*[xх×]\s*(\d{2,4})")
# Диаметр "Ø200"/"d200" — отдельный вид размера.
_SIGN_DIAMETER_RE = re.compile(r"[øo]\s?-?\s?(\d{2,4})")

_MATERIAL_WORDS = {
    "плёнка": ("плен", "пленк"),
    "пластик": ("пластик", "пвх"),
    "металл": ("металл",),
    "фотолюминесцентный": ("фотолюминесц",),
}


def _material(text: str) -> tuple:
    flags = []
    for label, stems in _MATERIAL_WORDS.items():
        if any(stem in text for stem in stems):
            flags.append(label)
    return tuple(sorted(flags))


def znak_key(name, characteristics, manufacturer, category_path) -> TypeKeyResult:
    text = _blob(name, characteristics, category_path)
    missing = []

    code_match = _SIGN_CODE_RE.search(text)
    code = None
    if code_match:
        code = code_match.group(1) + code_match.group(2)
    else:
        missing.append("код знака")

    size = None
    size_match = _SIGN_SIZE_RE.search(text)
    if size_match:
        size = (size_match.group(1), size_match.group(2))
    else:
        diameter_match = _SIGN_DIAMETER_RE.search(text)
        if diameter_match:
            size = ("d", diameter_match.group(1))
    if size is None:
        missing.append("размер")

    material = _material(text)
    if not material:
        missing.append("материал")

    # Бренд у знака — ТОЛЬКО мягкий признак (см. докстринг модуля), никогда
    # не входит в key/partial.
    brand = _find_brand(text, manufacturer, name)

    partial = (code,) if code else None
    key = (code, size, material) if (code and size and material) else None

    extra = {}
    if brand:
        extra["бренд"] = _fold(brand)

    return TypeKeyResult(kind="знак", key=key, partial=partial, missing=missing, extra=extra)
