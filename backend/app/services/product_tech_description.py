"""Сборка технического описания товара из характеристик каталога (владелец, 26.10).

ЕДИНСТВЕННОЕ место в проекте, где текст описания собирается из структурированных
характеристик (ПРАВИЛО №6) — всё, что хочет показать читаемый текст «описание
поставщика + список характеристик», вызывает build_tech_description(), а не
собирает строки вручную. Не путать с app/services/product_description_history.py
и product_description_proposals.py — те про историю правок уже готового текстового
Product.description/description_44fz, другая задача.

Правила сборки:
  - base_text (вольный текст поставщика), если не пуст после strip() — первый
    абзац; HTML-переносы "<br>"/"<br/>"/"<br />" внутри него заменяются на "\n"
    (встречаются в выгрузках вроде VkusVill properties).
  - Для каждой характеристики (в порядке списка) с непустыми name и value —
    строка "Название: значение ед." (unit добавляется через пробел только если
    задан и непустой после strip()). Характеристики без value или без name
    пропускаются.
  - Характеристика с "in_description": False (владелец, 2026-10-26, Задача 2
    — служебные поля упаковки поставщика типа "Номер по прайс-листу") в
    описание НЕ попадает, хотя в карточке товара (Product.characteristics)
    хранится полностью.
  - Абзацы разделяются "\n\n": первый — base_text, второй — все строки
    характеристик, склеенные через "\n".
  - Если обеих частей нет — None. Если есть только одна — возвращается она.
"""
from typing import Optional

_BR_VARIANTS = ("<br/>", "<br />", "<br>")


def _normalize_base_text(base_text: Optional[str]) -> Optional[str]:
    if base_text is None:
        return None
    text = base_text
    for br in _BR_VARIANTS:
        text = text.replace(br, "\n")
    text = text.strip()
    return text or None


def _characteristic_line(item: dict) -> Optional[str]:
    if isinstance(item, dict) and item.get("in_description") is False:
        return None
    name = (item.get("name") or "").strip() if isinstance(item, dict) else ""
    value = (item.get("value") or "").strip() if isinstance(item, dict) else ""
    if not name or not value:
        return None
    unit = (item.get("unit") or "").strip() if isinstance(item, dict) else ""
    line = f"{name}: {value}"
    if unit:
        line += f" {unit}"
    return line


def build_tech_description(
    characteristics: Optional[list] = None,
    base_text: Optional[str] = None,
) -> Optional[str]:
    """Собирает текст описания из текста поставщика (base_text) и списка
    характеристик [{"name","value","unit"}]. Возвращает None, если собирать
    не из чего. См. докстринг модуля — единственная такая функция в проекте."""
    paragraph_base = _normalize_base_text(base_text)

    lines = []
    for item in (characteristics or []):
        line = _characteristic_line(item)
        if line:
            lines.append(line)
    paragraph_characteristics = "\n".join(lines) if lines else None

    parts = [p for p in (paragraph_base, paragraph_characteristics) if p]
    if not parts:
        return None
    return "\n\n".join(parts)
