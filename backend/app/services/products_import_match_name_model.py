"""Критерий «название + индекс модели» сопоставления строки импорта каталога
с товаром (решение владельца, 27.10.2026, см. докстринг
app.services.product_name_signature и app/services/products_import_match.py,
критерий (0.75)). ЗАМЕНЯЕТ прежний критерий «ключ вида товара»
(product_type_keys.py, удалён — ПРАВИЛО №6: один механизм «тот же товар» по
названию, не два частных).

Применяется ТОЛЬКО когда у строки нет совпадения по store_article/штрихкоду/
бренду+артикулу производителя (критерии (0)/(0.25)/(0.5), приоритетнее) И у
строки есть хотя бы один цифро-буквенный токен названия (ProductSignature.
digit_tokens непуст — без него ключ ничего не отличает, см. докстринг
product_name_signature.py). Сравнение — ТОЛЬКО через
app.services.product_name_signature.match()/build_signature (ПРАВИЛО №6,
вторую «похожесть» здесь не пишем); срабатывает только decision == "auto" для
РОВНО ОДНОГО кандидата ДРУГОГО магазина — иначе критерий не сработал, строка
идёт дальше по приоритету к точному совпадению названия (а)/(б)/(в).

ПРЕДВЫБОРКА кандидатов каталога (на 250+ тыс. товаров тащить весь каталог в
память на один импорт нельзя, тот же принцип, что у store_article/barcode/
brand_article выше) — для каждой строки файла берётся САМЫЙ ДЛИННЫЙ (самый
редкий) цифро-буквенный токен названия (_search_token); по множеству таких
токенов со ВСЕГО файла каталог фильтруется запросами `Product.name ILIKE
'%токен%'`, порциями по NAME_ILIKE_CHUNK токенов (OR) в одном запросе —
`chunked`, ПРАВИЛО №6, тот же приём, что у остальных load_candidates_by_*.
Это скан по имени без триграммного индекса в БД — ценa: на файл с ~300-600
различимыми токенами это 15-25 запросов, каждый — последовательный скан по
Product.name (250 тыс. строк × ~20 ILIKE-сравнений в OR ≈ 5 млн сравнений на
запрос, ~100 млн на весь файл). Для РАЗОВОЙ операции на весь импорт (не на
строку) это приемлемо; если импорт большого файла станет ощутимо медленным —
завести GIN pg_trgm индекс на Product.name отдельной миграцией (вне этой
задачи). ILIKE — только сужение, финальное совпадение — точный
frozenset(digit_tokens) в Python."""
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.product_name_signature import ProductSignature, build_signature, match
from app.services.products_import_match import conflicts_with_row_store
from app.utils.chunking import chunked

# Размер порции токенов в одном ILIKE OR-запросе — небольшой (не 5000, как у
# `chunked` по умолчанию для IN(...)): каждый ILIKE — отдельное условие OR,
# слишком длинный список делает один запрос медленным без встречного выигрыша
# (в отличие от IN(...), где лимит — предел asyncpg на параметры, не стоимость
# плана).
NAME_ILIKE_CHUNK = 25

_ILIKE_ESCAPE_RE = re.compile(r"([%_\\])")


def _escape_ilike(token: str) -> str:
    return _ILIKE_ESCAPE_RE.sub(r"\\\1", token)


_DIGIT_RUN_RE = re.compile(r"\d+")


def _search_token(sig: ProductSignature) -> Optional[str]:
    """Ключ ILIKE-предвыборки — САМАЯ ДЛИННАЯ последовательность ЦИФР среди
    digit_tokens сигнатуры (не весь буквенно-цифровой токен целиком).

    Почему именно цифры, а не весь токен: digit_tokens построены из
    fold_brand_or_code()-свёрнутого названия (см. product_name_signature.
    _split_words), а свёртка гомоглифов МЕНЯЕТ буквы (например, латинское
    "M8701B" сворачивается в "м8701в" — кириллица) — значит, folded-токен
    почти никогда не встречается КАК ПОДСТРОКА в исходном Product.name,
    хранящемся в БД как есть (латиница). Цифры свёртка НЕ трогает (см.
    докстринг product_type_keys.py/brand_code_fold.py — 0/3/4 и остальные
    цифры исключены из таблицы гомоглифов именно поэтому), так что числовая
    часть токена ("8701" из "м8701в") гарантированно совпадает с исходным
    текстом независимо от регистра/гомоглифов букв вокруг неё. Короткие
    цифровые пробеги (1-2 цифры) слишком неселективны — сигнатура без хотя
    бы одного пробега ≥3 цифр в этом критерии не участвует (см. докстринг
    модуля — предвыборка имеет смысл только для достаточно редкого ключа)."""
    if not sig.digit_tokens:
        return None
    runs = [m for tok in sig.digit_tokens for m in _DIGIT_RUN_RE.findall(tok)]
    runs = [r for r in runs if len(r) >= 3]
    if not runs:
        return None
    return max(runs, key=len)


@dataclass
class NameModelCandidate:
    """Товар-кандидат этого критерия + его сигнатура и строки истории цены
    (для «один магазин не продаёт товар дважды» и собственного набора
    магазинов карточки)."""
    product: Product
    signature: ProductSignature
    history_count: int = 0
    store_pairs: set = field(default_factory=set)  # {(contractor_id, store_article), ...}

    def store_ids(self) -> set:
        ids = {cid for cid, _sa in self.store_pairs}
        if self.product.price_source_contractor_id is not None:
            ids.add(self.product.price_source_contractor_id)
        return ids

    def conflicts_with_row_store(self, contractor_id, store_article) -> bool:
        return conflicts_with_row_store(self.store_pairs, contractor_id, store_article)


async def load_name_model_candidates(
    db: AsyncSession, row_signatures: Iterable[ProductSignature],
) -> dict:
    """{frozenset(digit_tokens): [NameModelCandidate, ...]} — ОДИН проход на
    весь файл (см. докстринг модуля). `row_signatures` — ProductSignature
    КАЖДОЙ строки файла (уже посчитанные вызывающим кодом, ПРАВИЛО №6 — не
    второй разбор названия)."""
    tokens = {_search_token(sig) for sig in row_signatures}
    tokens.discard(None)
    if not tokens:
        return {}

    candidates_by_id: dict[int, Product] = {}
    token_list = list(tokens)
    for i in range(0, len(token_list), NAME_ILIKE_CHUNK):
        chunk = token_list[i:i + NAME_ILIKE_CHUNK]
        conditions = [Product.name.ilike(f"%{_escape_ilike(t)}%") for t in chunk]
        rows = (await db.execute(select(Product).where(or_(*conditions)))).scalars().all()
        for p in rows:
            candidates_by_id[p.id] = p
    if not candidates_by_id:
        return {}

    ids = list(candidates_by_id.keys())
    history_count_by_id: dict[int, int] = {}
    store_pairs_by_id: dict[int, set] = {}
    for chunk in chunked(ids):
        hist_rows = (await db.execute(
            select(
                ProductPriceHistory.product_id,
                ProductPriceHistory.contractor_id,
                ProductPriceHistory.store_article,
            ).where(ProductPriceHistory.product_id.in_(chunk))
        )).all()
        for product_id, contractor_id, store_article in hist_rows:
            history_count_by_id[product_id] = history_count_by_id.get(product_id, 0) + 1
            if contractor_id is not None and store_article:
                store_pairs_by_id.setdefault(product_id, set()).add((contractor_id, store_article))

    result: dict = {}
    for p in candidates_by_id.values():
        sig = build_signature({
            "name": p.name, "manufacturer": p.manufacturer,
            "characteristics": p.characteristics or [],
        })
        if not sig.digit_tokens:
            continue
        result.setdefault(sig.digit_tokens, []).append(NameModelCandidate(
            product=p, signature=sig,
            history_count=history_count_by_id.get(p.id, 0),
            store_pairs=store_pairs_by_id.get(p.id, set()),
        ))
    return result


def find_name_model_match(
    candidates: dict,
    row_signature: ProductSignature,
    file_peers_same_key: list,
    *,
    contractor_id: Optional[int],
    store_article: Optional[str],
) -> Optional[NameModelCandidate]:
    """Возвращает ЕДИНСТВЕННОГО подходящего NameModelCandidate (decision ==
    "auto" у product_name_signature.match(), и РОВНО ОДИН такой кандидат) или
    None. `candidates` — результат load_name_model_candidates();
    `file_peers_same_key` — ВСЕ ProductSignature строк ЭТОГО ЖЕ файла с тем же
    digit_tokens (считается один раз на весь файл вызывающим кодом, ПРАВИЛО
    №6 — не второй проход).

    Кандидаты СВОЕГО ЖЕ магазина строки (contractor_id входит в
    candidate.store_ids()) исключаются целиком — этот критерий сводит только
    с ДРУГИМ магазином (как и прежний критерий ключа вида товара). Для
    каждого оставшегося кандидата peers_b — другие карточки ТОГО ЖЕ магазина,
    что и кандидат, под тем же ключом (однозначность с b-стороны); peers_a —
    остальные строки файла под тем же ключом (однозначность с a-стороны,
    product_name_signature.match сам решает, конфликтует ли это с «уверенно»
    — см. `_ambiguity_reason`)."""
    if not row_signature.digit_tokens:
        return None
    group = candidates.get(row_signature.digit_tokens) or []
    if not group:
        return None

    eligible = [c for c in group if contractor_id not in c.store_ids()]
    if not eligible:
        return None

    peers_a = tuple(s for s in file_peers_same_key if s is not row_signature)

    auto_matches = []
    for cand in eligible:
        cand_stores = cand.store_ids()
        peers_b = tuple(
            other.signature for other in group
            if other is not cand and (other.store_ids() & cand_stores)
        )
        verdict = match(row_signature, cand.signature, peers_a=peers_a, peers_b=peers_b)
        if verdict["decision"] == "auto":
            auto_matches.append(cand)

    if len(auto_matches) != 1:
        return None
    return auto_matches[0]
