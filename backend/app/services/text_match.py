"""Общий движок нечёткого сопоставления по имени (Step 4, план
zany-fluttering-mountain.md, шаг 4: «не заводить пятую копию нормализации»).

Вынесено из app.services.product_matcher (единственная существующая реализация,
которая уже была общей по форме — параметризована произвольным каталогом
`(id, name, ...)`, просто жила под именем "product"). normalize/tokenize/stem/
score/generic_progressive_match — единственный источник для ВСЕХ доменов, которым
нужно «похожее по имени» сопоставление с прогрессивным сужением по словам:
  - товары каталога (app.services.product_matcher — тонкая обёртка над этим модулем,
    сохраняет прежний публичный API CandidateResult/MatchResult/progressive_match/
    bulk_match для products.py и purchase_items_import.py, которые НЕ трогаем);
  - плановые позиции ФЭО (app.routers.feo_planned_items — POST /match).

Домен строит свой candidate-объект (свои поля: product_id vs planned-item id/kind/
category_id/...) поверх `generic_progressive_match` — сама механика узнавания и
сужения по словам не дублируется.

Алгоритм (как и раньше):
1. normalize(s) — lower + strip punctuation + collapse spaces
2. tokenize(s) — split by whitespace, keep tokens with len>=2, drop NOISE_TOKENS
3. stem(t) — t[:6] if len(t)>6 (примитивный стемминг русских суффиксов)
4. score(query, name) — взвешенное покрытие токенов + SequenceMatcher ratio
5. generic_progressive_match(query, indexed) — прогрессивное сужение по словам
   (пользовательская бизнес-логика: «вводит слова — из БД вылезают совпадения как
   интерактивный фильтр»), см. docstring ниже.
"""
import re
from difflib import SequenceMatcher
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------

SCORE_AUTO = 0.95     # auto-accept: no human review needed
SCORE_SUGGEST = 0.60  # suggest: show candidates to user for review
SCORE_DIFFERENT = 0.40  # ниже этого — почти наверняка другой объект, не предлагаем вовсе

# ---------------------------------------------------------------------------
# Noise tokens stripped before scoring
# ---------------------------------------------------------------------------

NOISE_TOKENS = {
    'кг', 'шт', 'мл', 'л', 'см', 'мм', 'м', 'упак', 'пач', 'кор',
    'пара', 'и', 'в', 'на', 'для', 'с', 'из', 'от', 'по', 'за',
    'или', 'а', 'но', 'к', 'до', 'над', 'под',
}

_RE_PUNCT = re.compile(r'[^\w\s\d]')
_RE_WS = re.compile(r'\s+')


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not s:
        return ''
    s = s.lower()
    s = _RE_PUNCT.sub(' ', s)
    s = _RE_WS.sub(' ', s).strip()
    return s


def tokenize(s: str) -> list[str]:
    """Split normalized string into meaningful tokens (len>=2, not noise)."""
    return [t for t in normalize(s).split() if len(t) >= 2 and t not in NOISE_TOKENS]


def stem(t: str) -> str:
    """Primitive 6-char prefix stem for Russian suffix handling."""
    return t[:6] if len(t) > 6 else t


def score(query: str, catalog_name: str) -> float:
    """Compute similarity score between query and one catalog entry name.

    Returns float in [0.0, 1.0].
    """
    q_tokens = {stem(t) for t in tokenize(query)}
    c_tokens = {stem(t) for t in tokenize(catalog_name)}

    if not q_tokens:
        return 0.0

    intersection = q_tokens & c_tokens
    coverage = len(intersection) / len(q_tokens)

    seq = SequenceMatcher(None, normalize(query), normalize(catalog_name)).ratio()

    combined = 0.7 * coverage + 0.3 * seq

    # Boost: full query coverage with at least 2 meaningful tokens
    if coverage == 1.0 and len(q_tokens) >= 2:
        combined = max(combined, 0.95)

    return combined


_EXACT_MIN_QUERY_TOKENS = 3   # ниже — однословные/двусловные запросы слишком общие
_EXACT_NAME_LEN_RATIO = 1.5   # имя товара не длиннее query больше чем в столько раз


def is_exact_match(query: str, product_name: str, score_value: float) -> bool:
    """Строгое правило автоподстановки «exact» (владелец, 2026-09-21, приёмка
    в браузере): однословная плановая позиция «Экипировка» подхватила товар
    «Тренажёры для работы в экипировке в воде (например, с грузом, в
    гидрокостюме)» как 100%-совпадение — coverage=1.0 (все токены query нашлись
    в имени товара) при SCORE_AUTO=0.95 пропускает случайные товары для
    коротких запросов. Владелец: «если 100% совпадение названия в плане и в
    БД — именно этот товар»; иначе высокий score — это ПОДСКАЗКА пользователю
    (by_name), не решение за него.

    Используется ТОЛЬКО app.services.plan_to_wish (single source — не копия
    во app.routers.products_match, у POST /products/match своё поведение
    'auto'/score>=SCORE_AUTO не меняется).

    True, если:
      - normalize(query) == normalize(product_name) — полное совпадение
        нормализованных имён (пробелы/пунктуация/регистр не считаются), ЛИБО
      - score_value >= SCORE_AUTO И у query >= 3 значимых токенов (защита от
        1-2-словных запросов, которые совпадают с чем угодно по coverage) И
        число токенов имени товара не превышает токены query больше чем в 1.5
        раза (защита от длинного названия товара, зацепившегося одним-двумя
        общими словами).
    """
    if normalize(query) == normalize(product_name):
        return True
    if score_value < SCORE_AUTO:
        return False
    q_tokens = tokenize(query)
    if len(q_tokens) < _EXACT_MIN_QUERY_TOKENS:
        return False
    c_tokens = tokenize(product_name)
    if not c_tokens:
        return False
    return len(c_tokens) <= len(q_tokens) * _EXACT_NAME_LEN_RATIO


# ---------------------------------------------------------------------------
# Generic progressive narrowing (domain-agnostic — works on any payload)
# ---------------------------------------------------------------------------

def _stem_hits(q_stem: str, c_stems: set[str], prefix_match: bool) -> bool:
    """Совпал ли стем запроса `q_stem` с каким-то стемом каталожной записи `c_stems`.

    `prefix_match=False` (по умолчанию) — прежнее строгое поведение: точное
    равенство стемов (`q_stem in c_stems`). Используется в пакетном
    сопоставлении/дедупе — там расширять правила совпадения нельзя (владелец
    явно требовал не делать матчинг нечётким по умолчанию).

    `prefix_match=True` — для интерактивного набора с клавиатуры: `stem()`
    обрезает токен до 6 символов, поэтому слово длиннее 6 букв (например,
    «огнетушитель» → стем «огнету») не совпадает с своими же префиксами
    короче 6 символов («ог», «огн», «огне», «огнет») при точном сравнении —
    подсказки появляются только с 6-го введённого символа, хотя UI обещает
    «минимум 2». При этом флаге совпадением считается ЛИБО точное равенство,
    ЛИБО когда какой-то стем записи НАЧИНАЕТСЯ с q_stem (пользователь печатает
    начало слова слева направо, а не наоборот).
    """
    if q_stem in c_stems:
        return True
    if prefix_match:
        return any(c.startswith(q_stem) for c in c_stems)
    return False


def generic_progressive_match(
    query: str,
    indexed: list[tuple[Any, set[str]]],
    prefix_match: bool = False,
    tie_breaker: Optional[Callable[[Any], Any]] = None,
) -> tuple[str, list[tuple[Any, float]]]:
    """Прогрессивное сужение по словам — domain-agnostic ядро (см. модуль docstring).

    `indexed` — список пар (payload, stem_set), где payload — произвольный объект
    домена (кортеж/словарь/ORM-строка — что угодно, движок его не трогает, только
    возвращает обратно), stem_set — {stem(t) for t in tokenize(payload_name)},
    посчитанный домном заранее (чтобы не токенизировать каталог на каждый query).

    Алгоритм (пользовательское требование): «Не брать всю фразу сразу. Вводит
    слова — из БД вылезают совпадения как интерактивный фильтр. Если по первому
    слову 0 — товара/позиции нет, добавлять. Если несколько — следующие слова,
    пока не останется один похожий.»

    `prefix_match` (по умолчанию False) — включает префиксное сопоставление стемов
    через `_stem_hits` (см. её docstring за подробным обоснованием: `stem()` режет
    по 6 символам, из-за чего интерактивный набор слова длиннее 6 букв не даёт
    подсказок до 6-го символа, хотя UI обещает «минимум 2»). Флаг по умолчанию
    выключен и должен явно включаться только вызывающей стороной, отвечающей за
    интерактивный ввод (инлайновый подбор товара в строке позиции) — пакетное
    сопоставление при импорте/дедупе товаров обязано оставаться строгим, чтобы не
    расширять его поведение по умолчанию.

    `tie_breaker` (опционально) — вторичный ключ сортировки ПРИ РАВНОМ score
    (владелец, 2026-09-14: «сопоставление предпочитает запись с ТЗ» — пока в
    каталоге ещё есть дубли по имени, кандидат с более «истинным» payload'ом
    должен идти выше среди равных по покрытию). Домен передаёт функцию
    payload → сравнимое значение (например, 1, если у товара заполнено
    описание, иначе 0); большее значение — выше в списке. По умолчанию None —
    прежний порядок (стабильная сортировка Python сохраняет порядок `indexed`).

    Возвращает (status, [(payload, coverage_score), ...]) — score в [0, 1],
    отсортировано по (score, tie_breaker(payload)) desc, отфильтровано по
    SCORE_DIFFERENT (заведомо чужие — не зашумляем выбор пользователя).

    status:
      - 'create'  — даже первый токен query ни у одного payload не встречается
                    (либо после фильтра SCORE_DIFFERENT кандидатов не осталось)
      - 'auto'    — единственный payload покрывает ВСЕ токены query (score==1.0)
      - 'suggest' — иначе (несколько кандидатов, либо один с неполным покрытием)
    """
    q_tokens = tokenize(query)
    if not q_tokens:
        return 'create', []

    q_stems = [stem(t) for t in q_tokens]

    pool = indexed
    matched_stem_count = 0
    for q_stem in q_stems:
        next_pool = [entry for entry in pool if _stem_hits(q_stem, entry[1], prefix_match)]
        if not next_pool:
            if matched_stem_count == 0:
                # Даже первый токен query ни у кого из каталога не встречается
                return 'create', []
            # Часть токенов матчила; остановиться на предыдущем pool
            break
        pool = next_pool
        matched_stem_count += 1
        if len(pool) == 1:
            break

    results: list[tuple[Any, float]] = []
    for payload, c_stems in pool:
        coverage = len([s for s in q_stems if _stem_hits(s, c_stems, prefix_match)]) / len(q_stems)
        results.append((payload, round(coverage, 4)))

    if tie_breaker is not None:
        results.sort(key=lambda x: (x[1], tie_breaker(x[0])), reverse=True)
    else:
        results.sort(key=lambda x: x[1], reverse=True)

    # Отсекаем заведомо чужие объекты: при <40% покрытия это почти наверняка
    # совсем другая сущность — не зашумляем выбор пользователя ложными кандидатами.
    results = [r for r in results if r[1] >= SCORE_DIFFERENT]
    if not results:
        return 'create', []

    if len(results) == 1 and results[0][1] >= 1.0:
        return 'auto', results
    return 'suggest', results
