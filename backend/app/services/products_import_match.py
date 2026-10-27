"""Единственный механизм сопоставления строки импорта каталога с уже
известным товаром (ПРАВИЛО №6) — используется ТОЛЬКО
`app.services.products_import_apply.apply_products_import`, вторую функцию
поиска совпадения не писать.

Повод (владелец, 2026-10-26): раньше товар искался по ключу
name+description — при совпадении названия, но другом/пустом описании,
создавался ДУБЛЬ (на боевом файле это дало бы 260 лишних товаров). Новое
правило — явный приоритет совпадения:
  (0) (владелец, 27.10.2026, manufacturer_article/store_article) — если у
      строки импорта есть contractor_id магазина (по seller_inn строки) и
      store_article, и в product_price_history уже существует строка с тем
      же (contractor_id, store_article) — это ТОТ ЖЕ товар, даже если
      название в файле изменилось (магазин переименовал товар). Проверяется
      ПЕРВЫМ, раньше правил (а)/(б)/(в) ниже — совпадение по "железному"
      идентификатору магазина надёжнее совпадения по названию. Кандидаты
      грузятся ОДНИМ запросом на весь файл (load_candidate_products_by_
      store_article, порциями через app.utils.chunking.chunked), не запрос
      на каждую строку.
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
from typing import Iterable, Optional

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.utils.chunking import chunked


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


def _sql_norm_key_expr():
    """SQL-эквивалент norm_key() выше — но, в отличие от неё, работает
    только на Product.name (однострочное поле: \\r/\\n в товарных названиях
    практически не встречаются, а regexp '\\s+' ниже и так схлопывает ЛЮБОЙ
    whitespace, включая переводы строк, так что ограничение не меняет
    результат на реальных данных). Используется ТОЛЬКО для сужения
    кандидатов в `load_candidate_products` — финальное точное сравнение
    name+description остаётся в Python (ProductMatchIndex.find), это SQL —
    предвыборка, а не замена сравнения."""
    collapsed = func.regexp_replace(func.trim(Product.name), r"\s+", " ", "g")
    return func.replace(func.lower(collapsed), "ё", "е")


async def load_candidate_products(db: AsyncSession, file_names: Iterable[str]) -> list[Product]:
    """Сужение кандидатов ProductMatchIndex (владелец, 2026-10-26): раньше
    apply_products_import грузил select(Product) БЕЗ ЛИМИТА — весь каталог
    (в проде 53 797+ строк, растёт к 250+ тыс.) в память на один импорт.
    Совпасть с товаром из `file_names` (правила (а)/(б)/(в) модуля) может
    ТОЛЬКО товар, чьё norm_key(name) равно norm_key одного из имён САМОГО
    ФАЙЛА — остальной каталог заведомо не участвует в сопоставлении, сужение
    безопасно (не меняет найденные пары, только убирает то, что гарантированно
    не совпадёт). `chunked` (app/utils/chunking.py, Правило №6) бьёт список
    ключей на порции ≤5000 — тот же лимит asyncpg на параметры запроса."""
    keys = {norm_key(n) for n in file_names}
    keys.discard("")
    if not keys:
        return []
    norm_expr = _sql_norm_key_expr()
    out: list[Product] = []
    for chunk in chunked(list(keys)):
        rows = (await db.execute(
            select(Product).where(norm_expr.in_(chunk))
        )).scalars().all()
        out.extend(rows)
    return out


async def load_candidates_by_store_article(
    db: AsyncSession, pairs: Iterable[tuple]
) -> dict:
    """Критерий (0) модуля — для набора пар (contractor_id, store_article)
    собранных со ВСЕХ строк файла (владелец, 27.10.2026), возвращает
    {(contractor_id, store_article): Product} — товар, у которого УЖЕ есть
    строка product_price_history с тем же магазином и тем же store_article
    (не важно, что название в файле могло измениться). Один проход на весь
    файл, порциями через `chunked` (ПРАВИЛО №6, та же защита от лимита
    asyncpg, что у load_candidate_products). Несколько строк истории с одним
    и тем же (contractor_id, store_article), но разными product_id
    (теоретически, задвоение данных) — выбирается товар с наименьшим id,
    тот же принцип, что и `_sort_key` для совпадений по названию ниже."""
    valid_pairs = {(cid, sa) for cid, sa in pairs if cid is not None and sa}
    if not valid_pairs:
        return {}

    pair_to_product_id: dict = {}
    for chunk in chunked(list(valid_pairs)):
        rows = (await db.execute(
            select(
                ProductPriceHistory.contractor_id,
                ProductPriceHistory.store_article,
                ProductPriceHistory.product_id,
            ).where(
                tuple_(ProductPriceHistory.contractor_id, ProductPriceHistory.store_article).in_(chunk)
            )
        )).all()
        for contractor_id, store_article, product_id in rows:
            key = (contractor_id, store_article)
            if key not in pair_to_product_id or product_id < pair_to_product_id[key]:
                pair_to_product_id[key] = product_id

    product_ids = set(pair_to_product_id.values())
    if not product_ids:
        return {}
    products_by_id: dict = {}
    for chunk in chunked(list(product_ids)):
        rows = (await db.execute(select(Product).where(Product.id.in_(chunk)))).scalars().all()
        for p in rows:
            products_by_id[p.id] = p

    return {
        key: products_by_id[pid]
        for key, pid in pair_to_product_id.items()
        if pid in products_by_id
    }


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

    def __init__(self, products=(), store_article_candidates: Optional[dict] = None):
        self._by_name_desc: dict[tuple[str, str], Product] = {}
        self._by_name: dict[str, list[Product]] = {}
        # Критерий (0) — {(contractor_id, store_article): Product}, см.
        # load_candidates_by_store_article выше (владелец, 27.10.2026).
        self._by_store_article: dict = dict(store_article_candidates or {})
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

    def find(
        self, name: str, description, *,
        contractor_id: Optional[int] = None, store_article: Optional[str] = None,
    ) -> dict:
        """Возвращает {"product": Product|None, "reason": str|None}.
        `reason` заполнен, когда по названию в БД найдено НЕСКОЛЬКО товаров
        (многозначность уже существующих дублей) — независимо от того, какой
        из них в итоге выбран.

        Критерий (0) (владелец, 27.10.2026) — ПЕРВЫЙ: contractor_id+
        store_article строки совпадает с уже известной строкой истории цены
        → тот же товар, даже если название в файле изменилось; (а)/(б)/(в)
        по названию не проверяются вовсе в этом случае."""
        if contractor_id is not None and store_article:
            by_article = self._by_store_article.get((contractor_id, store_article))
            if by_article is not None:
                return {"product": by_article, "reason": None}

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
