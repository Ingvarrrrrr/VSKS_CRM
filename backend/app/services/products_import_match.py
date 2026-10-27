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
  (0.25) (РЕШЕНИЕ ВЛАДЕЛЬЦА, 27.10.2026, штрихкод — ГЛАВНЫЙ ключ сведения
      одной карточки товара из разных магазинов) — если у строки есть хоть
      один валидный штрихкод (app.services.barcodes.normalize_barcode,
      проверяет и приводит EAN-13/EAN-8/UPC-12/GTIN-14 к одному ключу) и он
      уже записан за какой-то карточкой (product_barcodes,
      app/models/product_barcode.py) — это тот же товар, даже у другого
      магазина, с другим названием, брендом или артикулом. Проверяется
      ПЕРЕД (0.5) (штрихкод надёжнее бренда+артикула), ПОСЛЕ (0)
      (store_article самого магазина строки — ещё надёжнее). «Один магазин
      не продаёт товар дважды» действует и здесь (products_import_match_
      barcode.BarcodeCandidate.conflicts_with_row_store, та же единственная
      реализация правила, что у (0.5) — conflicts_with_row_store, вынесена
      в module-level функцию). Кандидаты — одним запросом на весь файл
      (products_import_match_barcode.load_candidates_by_barcode, ПРАВИЛО №5
      — отдельный файл, не разрастающий этот модуль).
  (0.5) (РЕШЕНИЕ ВЛАДЕЛЬЦА, 27.10.2026, товар новой выгрузки, совпавший по
      бренду+артикулу производителя с товаром ДРУГОГО магазина — сразу в ту
      же карточку) — если у строки есть непустой manufacturer (не «брак»,
      is_bogus_manufacturer решает ТОЛЬКО вызывающий load_gala_catalog.
      item_to_row/конвертер — этот модуль просто использует переданное
      значение) и manufacturer_article, и в каталоге уже есть товар с тем же
      fold(manufacturer)+fold(article) (app.services.brand_code_fold.
      fold_brand_or_code — ПРАВИЛО №6, та же нормализация, что у
      product_similar.py, вторая не завелась) — это тот же товар. Проверяется
      ПОСЛЕ (0) (store_article надёжнее), ДО (а)/(б)/(в) по названию (артикул
      производителя надёжнее названия). «Один магазин не продаёт товар
      дважды»: кандидат с историей ЭТОГО ЖЕ магазина (contractor_id строки) и
      ДРУГИМ store_article — не тот же товар, пропускается. Несколько
      оставшихся кандидатов — выбирается с наибольшим числом строк истории,
      затем с наименьшим id; многозначность — в reason. Кандидаты грузятся
      ОДНИМ запросом на весь файл (load_candidates_by_brand_article), не
      запрос на каждую строку.
  (0.75) (РЕШЕНИЕ ВЛАДЕЛЬЦА, 27.10.2026, название + индекс модели —
      app.services.product_name_signature, ЗАМЕНЯЕТ прежний критерий «ключ
      вида товара», ПРАВИЛО №6: один механизм «тот же товар» по названию) —
      если у строки есть хотя бы один цифро-буквенный токен названия
      (ProductSignature.digit_tokens непуст) и в каталоге есть РОВНО ОДНА
      карточка ДРУГОГО магазина, для которой product_name_signature.match()
      даёт decision == "auto" (бренд, вид товара, цифровые токены и свойства
      совпадают, однозначность внутри каждого магазина проверена самим
      match() через peers) — это тот же товар. Проверяется ПОСЛЕ (0.5)
      (бренд+артикул производителя надёжнее — если он есть, этот критерий не
      нужен), ДО (а)/(б)/(в) по названию. Кандидаты и сравнение —
      services/products_import_match_name_model.py (ПРАВИЛО №5, отдельный
      файл — предвыборка кандидатов объёмная).
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
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.brand_code_fold import fold_brand_or_code
from app.services.catalog_gala.store_article_split import pending_split_product_ids
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


def conflicts_with_row_store(
    store_pairs, contractor_id: Optional[int], store_article: Optional[str],
) -> bool:
    """«Один магазин не продаёт товар дважды» (владелец, 27.10.2026) — True,
    если среди `store_pairs` ({(contractor_id, store_article), ...} строк
    истории товара-кандидата) есть строка ЭТОГО ЖЕ магазина (contractor_id),
    но с ДРУГИМ store_article: значит кандидат — действительно РАЗНЫЙ товар,
    сводить нельзя. ЕДИНСТВЕННАЯ реализация правила (ПРАВИЛО №6) —
    используется и критерием (0.5, бренд+артикул производителя, ниже), и
    критерием (0.25, штрихкод, products_import_match_barcode.py)."""
    if contractor_id is None:
        return False
    for cid, sa in store_pairs:
        if cid == contractor_id and sa != store_article:
            return True
    return False


@dataclass
class _BrandArticleCandidate:
    """Товар-кандидат критерия (0.5) + его строки истории цены, нужные для
    правила «один магазин не продаёт товар дважды» и выбора при нескольких
    кандидатах (владелец, 27.10.2026)."""
    product: Product
    history_count: int = 0
    store_pairs: set = field(default_factory=set)  # {(contractor_id, store_article), ...}

    def conflicts_with_row_store(self, contractor_id: Optional[int], store_article: Optional[str]) -> bool:
        return conflicts_with_row_store(self.store_pairs, contractor_id, store_article)


async def load_candidates_by_brand_article(
    db: AsyncSession, pairs: Iterable[tuple]
) -> dict:
    """Критерий (0.5) модуля (владелец, 27.10.2026) — для набора СЫРЫХ пар
    (manufacturer, manufacturer_article) со всех строк файла (уже
    отфильтрованных от «брака» вызывающим — is_bogus_manufacturer, см.
    catalog_gala.manufacturer_quality — этот модуль только использует
    переданное значение, второй проверки брака здесь нет) возвращает
    {(fold(manufacturer), fold(manufacturer_article)): [_BrandArticleCandidate, ...]}.

    SQL сужает кандидатов по lower(Product.article) IN (сырые коды файла,
    порциями через `chunked`, ПРАВИЛО №6 — тот же приём, что у
    load_candidate_products/load_candidates_by_store_article) — это ТОЛЬКО
    предвыборка (убирает заведомо непохожие артикулы), финальное сравнение —
    точный fold(manufacturer)+fold(article) в Python, как и везде в этом
    модуле. Код, совпадающий с файлом ТОЛЬКО по гомоглифу/дефису (не по
    строчному значению) и ни разу — по `lower()`, предвыборкой не найдётся;
    на реальных данных магазины печатают один и тот же артикул производителя
    почти буквально одинаково (регистр — единственное частое отличие),
    этого достаточно без второй, дорогой нормализации в самом SQL.

    ГАРД (владелец, 27.10.2026, риск Сима-ленда/Бауцентра) — ДО переноса
    backend/scripts/split_store_articles.py --apply у ~174 тыс. товаров этих
    магазинов Product.article — НОМЕР МАГАЗИНА (старая трактовка поля), не
    артикул производителя; совпадение бренда с чужим артикулом производителя
    по ТАКОМУ "артиклю" было бы случайным и свело бы товар в чужую карточку.
    Кандидаты, чей id входит в app.services.catalog_gala.store_article_split.
    pending_split_product_ids (тот же отбор, что у самого скрипта переноса —
    ПРАВИЛО №6, не дублировать условие), исключаются из результата целиком —
    после переноса их Product.article становится NULL и они и так не попали
    бы в SQL-предвыборку ниже."""
    raw_pairs = [(m, a) for m, a in pairs if m and a]
    if not raw_pairs:
        return {}
    norm_keys = {(fold_brand_or_code(m), fold_brand_or_code(a)) for m, a in raw_pairs}
    norm_keys.discard(("", ""))
    norm_keys = {(m, a) for m, a in norm_keys if m and a}
    if not norm_keys:
        return {}

    raw_codes = list({a for _, a in raw_pairs})
    candidates: dict[int, Product] = {}
    for chunk in chunked(raw_codes):
        rows = (await db.execute(
            select(Product).where(
                Product.article.isnot(None),
                Product.manufacturer.isnot(None),
                func.lower(Product.article).in_([c.lower() for c in chunk]),
            )
        )).scalars().all()
        for p in rows:
            candidates[p.id] = p
    if not candidates:
        return {}

    pending_ids = await pending_split_product_ids(db)
    if pending_ids:
        candidates = {pid: p for pid, p in candidates.items() if pid not in pending_ids}
    if not candidates:
        return {}

    ids = list(candidates.keys())
    history_count_by_id: dict[int, int] = {}
    store_pairs_by_id: dict[int, set] = {}
    for chunk in chunked(ids):
        rows = (await db.execute(
            select(
                ProductPriceHistory.product_id,
                ProductPriceHistory.contractor_id,
                ProductPriceHistory.store_article,
            ).where(ProductPriceHistory.product_id.in_(chunk))
        )).all()
        for product_id, contractor_id, store_article in rows:
            history_count_by_id[product_id] = history_count_by_id.get(product_id, 0) + 1
            if contractor_id is not None and store_article:
                store_pairs_by_id.setdefault(product_id, set()).add((contractor_id, store_article))

    result: dict[tuple, list] = {}
    for p in candidates.values():
        key = (fold_brand_or_code(p.manufacturer), fold_brand_or_code(p.article))
        if key not in norm_keys:
            continue
        result.setdefault(key, []).append(_BrandArticleCandidate(
            product=p,
            history_count=history_count_by_id.get(p.id, 0),
            store_pairs=store_pairs_by_id.get(p.id, set()),
        ))
    return result


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

    def __init__(
        self, products=(), store_article_candidates: Optional[dict] = None,
        brand_article_candidates: Optional[dict] = None,
        barcode_candidates: Optional[dict] = None,
        name_model_candidates: Optional[dict] = None,
        name_model_file_peers: Optional[dict] = None,
    ):
        self._by_name_desc: dict[tuple[str, str], Product] = {}
        self._by_name: dict[str, list[Product]] = {}
        # Критерий (0) — {(contractor_id, store_article): Product}, см.
        # load_candidates_by_store_article выше (владелец, 27.10.2026).
        self._by_store_article: dict = dict(store_article_candidates or {})
        # Критерий (0.25) — {barcode: [BarcodeCandidate, ...]}, см.
        # app.services.products_import_match_barcode.load_candidates_by_barcode
        # (владелец, 27.10.2026, решение «штрихкод — главный ключ»).
        self._by_barcode: dict = dict(barcode_candidates or {})
        # Критерий (0.5) — {(fold_brand, fold_article): [_BrandArticleCandidate, ...]},
        # см. load_candidates_by_brand_article выше (владелец, 27.10.2026).
        self._by_brand_article: dict = dict(brand_article_candidates or {})
        # Критерий (0.75) — {frozenset(digit_tokens): [NameModelCandidate, ...]},
        # см. app.services.products_import_match_name_model.
        # load_name_model_candidates (владелец, 27.10.2026, название + индекс
        # модели). name_model_file_peers — {frozenset(digit_tokens):
        # [ProductSignature, ...]} ВСЕХ строк файла с тем же ключом, считается
        # вызывающим кодом один раз на весь файл (ПРАВИЛО №6 — не второй
        # проход по файлу).
        self._name_model_candidates: dict = dict(name_model_candidates or {})
        self._name_model_file_peers: dict = dict(name_model_file_peers or {})
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
        manufacturer: Optional[str] = None, manufacturer_article: Optional[str] = None,
        barcodes: Optional[Iterable[str]] = None,
        name_signature=None,
    ) -> dict:
        """Возвращает {"product": Product|None, "reason": str|None,
        "matched_by": str|None}. `reason` заполнен, когда найдено НЕСКОЛЬКО
        товаров (многозначность) — независимо от того, какой из них в итоге
        выбран. `matched_by` — 'store_article' | 'barcode' | 'brand_article' |
        'name_model' | None, для построчного отчёта импорта (апстрим пишет
        туда «сведено с №… по штрихкоду» / «по бренду и артикулу
        производителя» / «по названию и модели»).

        Критерий (0) (владелец, 27.10.2026) — ПЕРВЫЙ: contractor_id+
        store_article строки совпадает с уже известной строкой истории цены
        → тот же товар, даже если название в файле изменилось.

        Критерий (0.25) (РЕШЕНИЕ ВЛАДЕЛЬЦА, 27.10.2026, штрихкод — главный
        ключ) — ВТОРОЙ, до бренда+артикула и до названия: любой из
        `barcodes` строки уже записан (product_barcodes) за карточкой —
        тот же товар, даже у другого магазина. «Один магазин не продаёт
        товар дважды» (BarcodeCandidate.conflicts_with_row_store) исключает
        кандидатов с историей ЭТОГО ЖЕ магазина под другим store_article.
        Несколько штрихкодов строки указывают на РАЗНЫЕ карточки (редкий
        случай плохих данных) → каждая такая карточка отдельно проверяется
        на конфликт, из оставшихся — с наибольшим числом строк истории,
        затем с наименьшим id; многозначность — в reason.

        Критерий (0.5) (РЕШЕНИЕ ВЛАДЕЛЬЦА, 27.10.2026) — ТРЕТИЙ, до
        совпадений по названию: manufacturer+manufacturer_article строки
        совпадают (после fold_brand_or_code) с уже известным товаром ДРУГОГО
        магазина — тот же товар. «Один магазин не продаёт товар дважды»
        (_BrandArticleCandidate.conflicts_with_row_store) исключает
        кандидатов с историей ЭТОГО ЖЕ магазина под другим store_article.
        (а)/(б)/(в) по названию не проверяются вовсе, если сработал (0),
        (0.25) или (0.5)."""
        if contractor_id is not None and store_article:
            by_article = self._by_store_article.get((contractor_id, store_article))
            if by_article is not None:
                return {"product": by_article, "reason": None, "matched_by": "store_article"}

        if barcodes:
            eligible = []
            for bc in barcodes:
                for cand in (self._by_barcode.get(bc) or []):
                    if not cand.conflicts_with_row_store(contractor_id, store_article):
                        eligible.append(cand)
            if eligible:
                reason = None
                distinct_products = {c.product.id or id(c.product): c.product for c in eligible}
                if len(distinct_products) > 1:
                    ids = ",".join(
                        str(p.id) if p.id is not None else "новый"
                        for p in sorted(distinct_products.values(), key=_sort_key)
                    )
                    reason = f"несколько товаров с этим штрихкодом (id: {ids})"
                chosen = max(eligible, key=lambda c: (c.history_count, -(c.product.id or 0)))
                return {"product": chosen.product, "reason": reason, "matched_by": "barcode"}

        if manufacturer and manufacturer_article:
            key = (fold_brand_or_code(manufacturer), fold_brand_or_code(manufacturer_article))
            group = self._by_brand_article.get(key) or []
            eligible = [c for c in group if not c.conflicts_with_row_store(contractor_id, store_article)]
            if eligible:
                reason = None
                if len(eligible) > 1:
                    ids = ",".join(str(c.product.id) for c in sorted(eligible, key=lambda c: c.product.id or -1))
                    reason = f"несколько товаров с этим брендом и артикулом производителя (id: {ids})"
                chosen = max(eligible, key=lambda c: (c.history_count, -(c.product.id or 0)))
                return {"product": chosen.product, "reason": reason, "matched_by": "brand_article"}

        if name_signature is not None and name_signature.digit_tokens:
            from app.services.products_import_match_name_model import find_name_model_match
            file_peers = self._name_model_file_peers.get(name_signature.digit_tokens) or [name_signature]
            name_match = find_name_model_match(
                self._name_model_candidates, name_signature, file_peers,
                contractor_id=contractor_id, store_article=store_article,
            )
            if name_match is not None:
                return {"product": name_match.product, "reason": None, "matched_by": "name_model"}

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
