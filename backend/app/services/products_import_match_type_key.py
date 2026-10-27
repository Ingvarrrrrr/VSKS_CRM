"""Критерий ключа вида товара (пожарная безопасность: огнетушитель/знак/
рукав/шкаф, app/services/product_type_keys.py) сопоставления строки импорта
каталога с товаром — решение владельца, 27.10.2026, см. докстринг
app/services/products_import_match.py (этот критерий — ПОСЛЕ бренда+артикула
производителя (0.5) и ПЕРЕД совпадениями по названию (а)/(б)/(в)).

Применяется ТОЛЬКО когда у строки нет совпадения по store_article/штрихкоду/
бренд+артикулу (выше по приоритету), есть распознанный вид товара
(product_type_keys.type_key вернул непустой kind+key) и в каталоге уже есть
РОВНО ОДНА карточка ДРУГОГО магазина с ТЕМ ЖЕ ключом, а в самом файле под
этот же ключ — РОВНО ОДНА строка (правило однозначности,
product_type_keys.keys_match_unique — ЕДИНСТВЕННОЕ место этой логики,
ПРАВИЛО №6, вторую проверку однозначности здесь не пишем).

ЭТОТ файл — только загрузка кандидатов (ПРАВИЛО №5, не разрастающий
products_import_match.py) + вызов keys_match_unique; собственной логики
сравнения ключей не содержит."""
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_price_history import ProductPriceHistory
from app.services.product_type_keys import TypeKeyResult, keys_match_unique, type_key
from app.services.products_import_match import conflicts_with_row_store
from app.utils.chunking import chunked

# Первое слово названия (см. докстринг product_type_keys.py — вид товара
# определяется ИМ) для каждого распознаваемого вида — та же загрузка
# кандидатов одним SQL-запросом на весь файл, что у критериев (0)/(0.25)/(0.5)
# выше в products_import_match.py. ILIKE с "%" в конце — только сравнение по
# первому слову, второй разбор здесь не ведём (type_key сам решает дальше).
_KIND_NAME_PATTERNS = ("огнетуш%", "знак%", "рукав%", "шкаф%")

# Человекочитаемый состав ключа — только для построчного отчёта импорта
# (владелец, 27.10.2026: «сведено с №… по ключу вида товара (огнетушитель:
# бренд, модель, класс пожара…)»); НЕ участвует в сравнении — чистый текст.
KIND_KEY_LABELS = {
    "огнетушитель": "бренд, модель, класс пожара, ЗПУ, исполнение, закачной, тип/сборка баллона",
    "знак": "код знака, размер, материал",
    "рукав": "бренд, диаметр, длина, тип, головки, ствол",
    "шкаф": "бренд, модель, способ установки, дверца, цвет",
}


@dataclass
class TypeKeyCandidate:
    """Товар-кандидат этого критерия + его TypeKeyResult и строки истории
    цены (для «один магазин не продаёт товар дважды» и исключения карточек
    СВОЕГО ЖЕ магазина строки — см. докстринг модуля)."""
    product: Product
    result: TypeKeyResult
    history_count: int = 0
    store_pairs: set = field(default_factory=set)  # {(contractor_id, store_article), ...}

    def contractor_ids(self) -> set:
        return {cid for cid, _sa in self.store_pairs}

    def conflicts_with_row_store(self, contractor_id, store_article) -> bool:
        return conflicts_with_row_store(self.store_pairs, contractor_id, store_article)


async def load_type_key_candidates(db: AsyncSession) -> dict:
    """{(kind, key): [TypeKeyCandidate, ...]} — ОДИН запрос на весь файл
    (владелец, 27.10.2026): карточки распознанных видов товара грузятся по
    ILIKE первого слова названия (_KIND_NAME_PATTERNS), type_key() считается
    в Python по каждой. Кандидаты без полного key (только partial/ничего) не
    попадают в индекс — для этого критерия нужен ИМЕННО полный ключ."""
    conditions = [Product.name.ilike(p) for p in _KIND_NAME_PATTERNS]
    rows = (await db.execute(select(Product).where(or_(*conditions)))).scalars().all()
    if not rows:
        return {}

    ids = [p.id for p in rows]
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

    result: dict[tuple, list] = {}
    for p in rows:
        r = type_key(p.name, p.characteristics, p.manufacturer, None)
        if r is None or r.key is None:
            continue
        result.setdefault((r.kind, r.key), []).append(TypeKeyCandidate(
            product=p, result=r,
            history_count=history_count_by_id.get(p.id, 0),
            store_pairs=store_pairs_by_id.get(p.id, set()),
        ))
    return result


def find_type_key_match(
    candidates: dict,
    row_result: Optional[TypeKeyResult],
    file_peers_same_kind: list,
    *,
    contractor_id: Optional[int],
) -> Optional[TypeKeyCandidate]:
    """Возвращает ЕДИНСТВЕННОГО подходящего TypeKeyCandidate («уверенно»,
    ПРАВИЛО однозначности keys_match_unique) или None. `candidates` —
    результат load_type_key_candidates(); `file_peers_same_kind` — ВСЕ
    TypeKeyResult строк ЭТОГО ЖЕ файла того же kind, что и row_result
    (считается один раз на весь файл вызывающим кодом, ПРАВИЛО №6 — не
    второй проход). Кандидаты СВОЕГО ЖЕ магазина строки (contractor_id
    совпадает с одним из contractor_ids() кандидата) исключаются ЦЕЛИКОМ —
    этот критерий сводит только с ДРУГИМ магазином (владелец, 27.10.2026;
    строже, чем «conflicts_with_row_store» у соседних критериев — там
    исключается только РАЗНЫЙ store_article, здесь — любое совпадение
    магазина, т.к. цель критерия — именно МЕЖмагазинное сведение)."""
    if row_result is None or row_result.key is None:
        return None
    group = candidates.get((row_result.kind, row_result.key)) or []
    if not group:
        return None
    if contractor_id is not None:
        group = [c for c in group if contractor_id not in c.contractor_ids()]
    if not group:
        return None
    # Группа уже отфильтрована по ТОЧНО тому же key, что и у строки — если
    # в ней больше одного кандидата, keys_match_unique понизит до
    # "проверить" для любого из них (count_b > 1), поэтому достаточно
    # проверить единственного оставшегося.
    if len(group) > 1:
        return None
    candidate = group[0]
    verdict = keys_match_unique(
        row_result, candidate.result,
        file_peers_same_kind, [c.result for c in group],
    )
    if verdict != "уверенно":
        return None
    return candidate
