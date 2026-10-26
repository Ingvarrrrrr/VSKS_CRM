"""Единственный механизм сопоставления строки импорта каталога с уже
известным товаром (ПРАВИЛО №6) — используется ТОЛЬКО
`app.services.products_import_apply.apply_products_import`, вторую функцию
поиска совпадения не писать.

Повод (владелец, 2026-10-26): раньше товар искался по ключу
name+description — при совпадении названия, но другом/пустом описании,
создавался ДУБЛЬ (на боевом файле это дало бы 260 лишних товаров). Новое
правило — явный приоритет совпадения:
  (а) точное совпадение «название+описание» после нормализации;
  (б) совпадение по названию, когда описание у кандидата из БД ИЛИ у строки
      файла — пустое (тогда это точно тот же товар, которому донаполняется
      описание);
  (в) совпадение по названию с ДРУГИМ непустым описанием — владелец прямо
      подтвердил: это тоже тот же товар (а не похожий), описание не
      создаёт второй карточки.
Fuzzy/похожие названия НЕ сопоставляются — только точное совпадение после
нормализации (schлопывание пробелов, ё→е, регистр).

Если одному названию в БД соответствует несколько товаров (дубли уже
существуют из прошлых импортов) — выбор кандидата:
  точное совпадение по описанию → кандидат с пустым описанием → наименьший
  id. Такая многозначность возвращается вызывающему через `reason`, чтобы
  попасть в построчный отчёт импорта.
"""
from typing import Optional

from app.models.product import Product


def norm_key(s) -> str:
    """Нормализация строки для сравнения названия/описания: без \\r,
    регистронезависимо, ё→е, один пробел между словами вместо любых
    повторов/переводов строк по краям. Та же нормализация для названия и
    для описания — один источник (ПРАВИЛО №6), раньше в
    products_import_apply._norm_key не было ё→е и схлопывания пробелов."""
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n").strip().lower()
    s = s.replace("ё", "е")
    s = " ".join(s.split())
    return s


def _sort_key(p: Product):
    # Ещё не сохранённый (id=None) товар этого же прогона импорта —
    # приоритетнее любого товара с настоящим id (наименьший сначала).
    return (p.id is not None, p.id if p.id is not None else -1)


class ProductMatchIndex:
    """Индекс существующих товаров каталога для поиска совпадения строки
    импорта. Пополняется НОВЫМИ товарами сразу после их создания в рамках
    того же прогона импорта (см. apply_products_import) — чтобы повтор
    позиции внутри одного файла находил товар, созданный предыдущей строкой,
    а не создавал второй created."""

    def __init__(self, products=()):
        self._by_name_desc: dict[tuple[str, str], Product] = {}
        self._by_name: dict[str, list[Product]] = {}
        for p in products:
            self.add(p)

    def add(self, product: Product) -> None:
        name_key = norm_key(product.name)
        desc_key = norm_key(product.description)
        # Первый встреченный экземпляр при точном совпадении name+description
        # выигрывает (при настоящих дублях в БД — порядок обхода выборки;
        # для товара, созданного в этом же прогоне, add() вызывается сразу
        # после создания и имеет приоритет для последующих строк файла, т.к.
        # пары name+description идентичных товаров — явный повтор строки).
        self._by_name_desc.setdefault((name_key, desc_key), product)
        self._by_name.setdefault(name_key, []).append(product)

    def find(self, name: str, description) -> dict:
        """Возвращает {"product": Product|None, "reason": str|None}.
        `reason` заполнен, когда по названию в БД найдено НЕСКОЛЬКО товаров
        (многозначность уже существующих дублей) — независимо от того, какой
        из них в итоге выбран."""
        name_key = norm_key(name)
        desc_key = norm_key(description)

        exact = self._by_name_desc.get((name_key, desc_key))
        if exact is not None:
            return {"product": exact, "reason": None}

        candidates = self._by_name.get(name_key) or []
        if not candidates:
            return {"product": None, "reason": None}

        reason: Optional[str] = None
        if len(candidates) > 1:
            ids = ",".join(
                str(c.id) if c.id is not None else "новый"
                for c in sorted(candidates, key=_sort_key)
            )
            reason = f"в БД несколько товаров с этим названием (id: {ids})"

        # Приоритет при нескольких одноимённых: кандидат с пустым описанием
        # (правило (б)) — иначе любой (правило (в), владелец подтвердил, что
        # это тот же товар), наименьший id первым.
        empty_desc_candidates = [c for c in candidates if not norm_key(c.description)]
        pool = empty_desc_candidates if empty_desc_candidates else candidates
        chosen = min(pool, key=_sort_key)
        return {"product": chosen, "reason": reason}
