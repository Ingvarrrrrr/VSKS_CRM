"""Поиск похожих карточек каталога — пилот (владелец, 27.10.2026): один и тот
же товар лежит разными карточками у разных магазинов (у каждого магазина своё
название). products_import_match.py сопоставляет СТРОГО по точному имени (это
НЕ меняется — норм. сопоставление для импорта/создания позиции), а это —
отдельная, более грубая подсказка «эти карточки, возможно, один товар»,
которую человек проверяет глазами перед POST /api/products/merge
(app/routers/products_merge.py). Автоматически НИЧЕГО не объединяет.

similarity_key раскладывает нормализованное имя на (brand, base_model,
rest_tokens) — см. докстринг самой функции.

find_similar_groups группирует карточки, чьё имя содержит запрос, ЧЕТЫРЬМЯ
ключами, по убыванию надёжности (владелец, 27.10.2026):
  - общий штрихкод (product_barcodes) — confidence='уверенно',
    match_key='barcode' — ПЕРВЫЙ, самый надёжный (решение владельца,
    27.10.2026: штрихкод — главный ключ сведения карточки);
  - название + индекс модели (ЕДИНОЕ правило «тот же товар», владелец,
    27.10.2026, app.services.product_name_signature — заменяет прежнюю
    группировку «ключ вида товара», ПРАВИЛО №6: один механизм) — ВТОРОЙ:
    карточки с одинаковым набором цифро-буквенных токенов названия
    (ProductSignature.digit_tokens), сравненные через match() с winner'ом —
    decision=="auto" у всех → confidence='уверенно', match_key='name_model';
    хоть одна "проверить" → confidence='проверить', diff каждой такой
    карточки — match()["reason"] по-русски; decision=="no" (другой бренд/вид/
    свойство) — карточка исключается из группы целиком, это другой товар;
  - (brand, manufacturer_code) — confidence='уверенно' — артикул
    производителя (Product.article у магазинов с article_is_manufacturer=True,
    иначе код вида "DHP482Z"/"14054DEK" из названия) строго совпадает у
    разных магазинов для инструмента/электрики/техники;
  - (brand, base_model) среди карточек, НЕ попавших в группу по артикулу —
    confidence='проверить' — код модели (ОП-2, ОУ-5) совпадает, но это не
    настолько надёжно, как совпадение артикула производителя.
Группа показывается ТОЛЬКО если в ней ≥2 РАЗНЫХ магазина (price_source_
contractor_id; NULL — «без магазина», отдельный источник) — иначе это просто
несколько карточек одного магазина, которые САМИ ПО СЕБЕ всегда разные товары
(магазин не продаёт одно и то же дважды), слиянию предлагать нечего."""
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contractor import Contractor
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_photo import ProductPhoto
from app.models.product_price_history import ProductPriceHistory
from app.services.brand_code_fold import fold_brand_or_code
from app.services.catalog_gala.stores import article_is_manufacturer_for_inn
from app.services.product_catalog_match import _HOMOGLYPH_MAP, _WS_RE
from app.services.product_name_signature import build_signature as _build_name_signature
from app.services.product_name_signature import match as _name_signature_match

MIN_QUERY_LEN = 3
DEFAULT_LIMIT_GROUPS = 50
SQL_SCAN_LIMIT = 5000
MIN_BRAND_LEN = 3
MIN_MANUFACTURER_CODE_LEN = 5

# Сентинел "без магазина" для подсчёта РАЗНЫХ источников группы (владелец,
# 27.10.2026, п.3) — NULL contractor_id считается ОДНИМ отдельным источником,
# не "любым количеством разных", поэтому обычный None как ключ set() уже даёт
# ровно нужное поведение (все NULL схлопываются в одно значение) — сентинел
# только для читаемости кода/отчёта, по значению эквивалентен None.
_NO_STORE = "__no_store__"

# Город в скобках после названия — «(г. Ярославль)» — не несёт отличительной
# информации о самом товаре, убирается целиком.
_CITY_PAREN_RE = re.compile(r"\(\s*г\.?\s*[^)]*\)")

# Токен вида "буквы[-]цифры" — код модели (ОП-2, ОУ-5, СВ-100), с НЕОБЯЗАТЕЛЬНЫМ
# скобочным суффиксом ("ОП-2(з)", "ОП-2(3)" — группа 1 захватывает ТОЛЬКО
# "оп-2", суффикс в скобках и всё, что после него, отрезается целиком и не
# участвует в base_model (см. докстринг модуля — не угадываем смысл "(3)" vs
# "(з)", опечатка магазина не должна разваливать группу на две). `\d+`
# захватывает ВСЕ цифры подряд — "оп-10" ≠ "оп-1" ≠ "оп-100" (владелец,
# 27.10.2026 — на проде эти три слиплись из-за цифро-буквенного фолда выше,
# без него regex сам по себе корректен).
_MODEL_TOKEN_RE = re.compile(r"^([a-zа-я]+-?\d+)(?:[a-zа-я0-9]*)?(?:\([^)]*\))?$", re.IGNORECASE)
_MODEL_STRIP_RE = re.compile(r"[^a-zа-я0-9]", re.IGNORECASE)

# Общие слова категории (первое существительное/прилагательные-типа товара) —
# не отличают один товар от другого внутри одной категории, в rest_tokens не
# попадают. Включены частые опечатки магазинов того же слова (владелец,
# 27.10.2026: «Огнетушитель поршковый» — пропущена буква) — опечатка типа
# товара не должна считаться отличием карточек. Список сознательно
# небольшой — расширять по мере пилота, не угадывать все случаи сразу.
_CATEGORY_STOPWORDS = {
    "огнетушитель", "огнетушители",
    "порошковый", "поршковый",  # опечатка магазина (пропущена "о")
    "углекислотный", "воздушно-пенный",
    "воздушно", "пенный", "передвижной", "ручной",
}

_PUNCT_RE = re.compile(r"[,.;:!?\"'«»]+")

# Шаблоны "размер/стандарт", которые ВИЗУАЛЬНО похожи на артикул
# производителя (буквы+цифры), но артикулом не являются — владелец,
# 27.10.2026: CR2016/LR03 — стандартные типоразмеры батареек (одинаковы у
# Philips и Kodak — РАЗНЫЕ товары, не группировать только по этому коду).
# Список намеренно короткий, с комментарием у каждого шаблона — расширять по
# мере пилота, не пытаться угадать все стандарты сразу.
_SIZE_STANDARD_PATTERNS = (
    re.compile(r"^\d+x\d+$", re.IGNORECASE),     # "15x15" — размер в мм/см
    re.compile(r"^\d+p$", re.IGNORECASE),        # "1080p" — разрешение видео
    re.compile(r"^ral\d+$", re.IGNORECASE),       # "RAL7035" — цвет по каталогу RAL
    re.compile(r"^dvb-?t\d*$", re.IGNORECASE),    # "DVB-T2" — стандарт телевещания
    re.compile(r"^cr\d+$", re.IGNORECASE),        # "CR2016" — типоразмер батарейки
    re.compile(r"^lr\d+$", re.IGNORECASE),        # "LR03" — типоразмер батарейки (AAA)
)

# Обратная карта кириллица→латиница (владелец, 27.10.2026, разбор «почему
# GA5090X01 не нашёлся»): источник данных иногда печатает код производителя
# с КИРИЛЛИЧЕСКИМ гомоглифом вместо латинской буквы (та же путаница, что и
# normalize_product_name чинит в другую сторону — см. _HOMOGLYPH_MAP в
# product_catalog_match.py, ПРАВИЛО №6, строим обратную карту из ТОЙ ЖЕ
# таблицы, не завели вторую). "Х01" с кириллической «Х» — тот же символ на
# глаз, что латинская "X01", но _CODE_TOKEN_RE (чисто ASCII) его не пускал.
_REVERSE_HOMOGLYPH_FOR_CODE = {cyr: lat.lower() for lat, cyr in _HOMOGLYPH_MAP.items()}


def _latinize_code_candidate(word: str) -> Optional[str]:
    """Заменяет кириллические гомоглифы на латинский эквивалент посимвольно;
    любой символ ВНЕ (ASCII-буква/цифра ∪ известный гомоглиф) — слово не код
    производителя, возвращает None (не угадываем произвольную кириллицу)."""
    out = []
    for ch in word:
        if ch.isascii() and (ch.isalpha() or ch.isdigit()):
            out.append(ch)
        elif ch.lower() in _REVERSE_HOMOGLYPH_FOR_CODE:
            # _HOMOGLYPH_MAP хранит только СТРОЧНУЮ кириллицу как цель
            # (регистр снимается финальным lower() там же) — заглавный
            # гомоглиф ("Х" вместо "х") ищем по ch.lower().
            out.append(_REVERSE_HOMOGLYPH_FOR_CODE[ch.lower()])
        else:
            return None
    return "".join(out)


# _fold — алиас на единственную нормализацию бренда/кода (ПРАВИЛО №6,
# app.services.brand_code_fold.fold_brand_or_code; раньше была своя копия
# таблицы здесь — вынесена в общий модуль при появлении второго потребителя,
# products_import_match.py).
_fold = fold_brand_or_code


def _clean_word(word: str) -> str:
    w = _PUNCT_RE.sub("", word).strip("-")
    # Скобка "(ЗПУ латунь)" режется пробелом на два слова — "(зпу" и
    # "латунь)" — без своей пары каждая половинка несёт только шум, не код
    # модели (тот всегда один токен без внутреннего пробела, "оп-2(з)").
    if w.startswith("(") and ")" not in w:
        w = w[1:]
    if w.endswith(")") and "(" not in w:
        w = w[:-1]
    return w


def manufacturer_code_from_name(name: Optional[str]) -> Optional[str]:
    """Код производителя из названия — токен "латиница+цифры" длиной ≥5
    символов ПОСЛЕ удаления "-./" и пробелов (владелец, 27.10.2026, пример
    "DHP482Z", "14054DEK", "MVA20-1-016-C"), кроме типоразмеров/стандартов
    (_SIZE_STANDARD_PATTERNS). Первый подходящий токен исходного (НЕ
    гомоглиф-свёрнутого — важно сохранить исходную латиницу/цифры как есть)
    названия, разбитого по пробелам; нет подходящего — None."""
    if not name:
        return None
    for raw_word in name.split():
        cleaned = re.sub(r"[-./]", "", raw_word)
        if len(cleaned) < MIN_MANUFACTURER_CODE_LEN:
            continue
        latinized = _latinize_code_candidate(cleaned)
        if latinized is None:
            continue
        if not any(c.isdigit() for c in latinized) or not any(c.isalpha() for c in latinized):
            continue
        if any(p.fullmatch(latinized) for p in _SIZE_STANDARD_PATTERNS):
            continue
        return latinized.lower()
    return None


def _manufacturer_code_display_from_name(name: Optional[str], manufacturer_code: str) -> str:
    """Исходное написание кода производителя для показа человеку (владелец,
    27.10.2026, п.1 приёмки) — "DF332DWME", не свёрнутое/латинизированное
    значение manufacturer_code. Повторяет РАЗБОР manufacturer_code_from_name
    (ПРАВИЛО №6 — не вторая формула кода, только возвращает СЫРОЕ слово
    вместо приведённого), ищет слово, чей тот же разбор даёт manufacturer_code."""
    if not name:
        return ""
    for raw_word in name.split():
        cleaned = re.sub(r"[-./]", "", raw_word)
        if len(cleaned) < MIN_MANUFACTURER_CODE_LEN:
            continue
        latinized = _latinize_code_candidate(cleaned)
        if latinized is None:
            continue
        if not any(c.isdigit() for c in latinized) or not any(c.isalpha() for c in latinized):
            continue
        if any(p.fullmatch(latinized) for p in _SIZE_STANDARD_PATTERNS):
            continue
        if latinized.lower() == manufacturer_code:
            return raw_word
    return ""


@dataclass
class SimilarityKey:
    brand: str
    base_model: str
    rest_tokens: tuple
    manufacturer_code: Optional[str] = None
    # Бренд в ИСХОДНОМ написании — для показа человеку (владелец, 27.10.2026:
    # свёрнутый `brand` в выдаче читался как «маkitа» — гомоглифы кириллица/
    # латиница годятся для СРАВНЕНИЯ ключей, но не для отображения). `brand`
    # выше остаётся свёрнутым — это ключ группировки, не трогаем.
    brand_display: str = ""
    # base_model/manufacturer_code — ТО ЖЕ самое (владелец, 27.10.2026, п.1
    # приёмки): заголовок группы показывал свёрнутое «оп2»/«df332dwme» вместо
    # исходного «ОП-2»/«DF332DWME». ПРАВИЛО №6 — тот же приём raw_words/
    # _raw_at, что уже дал brand_display, вторую реализацию не заводим.
    base_model_display: str = ""
    manufacturer_code_display: str = ""

    @property
    def group_key(self) -> Optional[tuple]:
        if not self.brand or not self.base_model:
            return None
        return (self.brand, self.base_model)

    @property
    def article_group_key(self) -> Optional[tuple]:
        # «Код без бренда группу не образует» (владелец, 27.10.2026) — CR2016
        # у Philips/Kodak и так отсеян шаблоном выше, но и прочий код без
        # известного бренда ничего не группирует.
        if not self.brand or not self.manufacturer_code:
            return None
        return (self.brand, self.manufacturer_code)


def similarity_key(
    name: Optional[str],
    manufacturer: Optional[str],
    known_brands: set[str],
    *,
    article: Optional[str] = None,
    article_is_manufacturer: bool = False,
) -> SimilarityKey:
    """brand — Product.manufacturer, если заполнен; иначе первое вхождение
    известного производителя (known_brands) в названии. base_model — первый
    токен вида "буквы[-]цифры" (ОП-2, ОУ-5, СВ-100). rest_tokens — значимые
    слова названия без brand/base_model/стоп-слов/городов в скобках/
    пунктуации. manufacturer_code (владелец, 27.10.2026, п.4) — `article`,
    если магазин карточки передаёт в нём артикул ПРОИЗВОДИТЕЛЯ
    (article_is_manufacturer=True, см. app.services.catalog_gala.stores),
    иначе код, извлечённый из названия (manufacturer_code_from_name) —
    артикул магазина (Сима-ленд/Бауцентр) НИКОГДА не используется как код
    производителя."""
    name_no_city = _CITY_PAREN_RE.sub(" ", name or "")
    norm = _fold(name_no_city)
    words = [w for w in (_clean_word(w) for w in norm.split(" ")) if w]
    # raw_words — ИСХОДНОЕ написание слов (для brand_display, владелец,
    # 27.10.2026 — свёрнутый `brand` в выдаче читался как «маkitа»), в ТОМ ЖЕ
    # порядке, что и folded `words` выше (фолд/strip — посимвольные операции,
    # границы слов не двигаются). Расхождение в счётчике слов — редкий
    # крайний случай (слово из одних невидимых символов) — тогда просто нет
    # соответствующего raw-слова по индексу, brand_display откатывается на
    # свёрнутое значение (см. ниже), не на 500.
    raw_words = [w for w in (_clean_word(w) for w in _WS_RE.sub(" ", name_no_city.strip()).split(" ")) if w]

    def _raw_at(idx: Optional[int], fallback: str) -> str:
        if idx is not None and 0 <= idx < len(raw_words):
            return raw_words[idx]
        return fallback

    brand = _fold(manufacturer) if manufacturer else ""
    brand_display = (manufacturer or "").strip()
    brand_word_idx: Optional[int] = None
    if brand:
        for i, w in enumerate(words):
            if w == brand or brand in w or w in brand:
                brand_word_idx = i
                break
    else:
        # Производитель не указан на карточке — ищем известный бренд как
        # отдельное слово названия (самое длинное совпадение сначала, чтобы
        # "ярпожинвест" не терялся за частью другого слова).
        for i, w in enumerate(words):
            if w in known_brands and len(w) >= MIN_BRAND_LEN:
                brand = w
                brand_display = _raw_at(i, w)
                brand_word_idx = i
                break

    base_model = ""
    base_model_display = ""
    model_word_idx: Optional[int] = None
    for i, w in enumerate(words):
        if i == brand_word_idx:
            continue
        m = _MODEL_TOKEN_RE.match(w)
        if m:
            base_model = _MODEL_STRIP_RE.sub("", m.group(1))
            model_word_idx = i
            # raw_w и w совпадают по длине посимвольно (_fold — таблица
            # символ-в-символ, см. докстринг _SIMILAR_FOLD_TABLE) — префикс
            # той же длины, что m.group(1), даёт исходное написание "ОП-2" без
            # отрезанного скобочного суффикса "(з)".
            raw_w = _raw_at(i, w)
            base_model_display = raw_w[:len(m.group(1))] if raw_w else base_model
            break

    rest = []
    for i, w in enumerate(words):
        if i in (brand_word_idx, model_word_idx):
            continue
        if w in _CATEGORY_STOPWORDS:
            continue
        if not w:
            continue
        rest.append(w)

    manufacturer_code_display = ""
    if article_is_manufacturer and (article or "").strip():
        manufacturer_code = article.strip().lower()
        manufacturer_code_display = article.strip()
    else:
        manufacturer_code = manufacturer_code_from_name(name)
        if manufacturer_code:
            manufacturer_code_display = _manufacturer_code_display_from_name(name, manufacturer_code)

    return SimilarityKey(
        brand=brand, base_model=base_model, rest_tokens=tuple(rest),
        manufacturer_code=manufacturer_code, brand_display=brand_display or brand,
        base_model_display=base_model_display or base_model,
        manufacturer_code_display=manufacturer_code_display or (manufacturer_code or ""),
    )


async def _load_known_brands(db: AsyncSession) -> set[str]:
    rows = (await db.execute(
        select(Product.manufacturer).where(Product.manufacturer.isnot(None)).distinct()
    )).scalars().all()
    return {_fold(r) for r in rows if r and len(_fold(r)) >= MIN_BRAND_LEN}


async def _load_article_is_manufacturer_by_contractor(
    db: AsyncSession, contractor_ids: set[int],
) -> dict[int, bool]:
    """contractor_id → article_is_manufacturer (app.services.catalog_gala.
    stores, по ИНН контрагента) — одним запросом на ВСЕ контрагенты
    карточек этого прогона, не по одному на карточку."""
    ids = [cid for cid in contractor_ids if cid is not None]
    if not ids:
        return {}
    rows = (await db.execute(
        select(Contractor.id, Contractor.inn).where(Contractor.id.in_(ids))
    )).all()
    return {cid: article_is_manufacturer_for_inn(inn) for cid, inn in rows}


@dataclass
class SimilarCard:
    id: int
    name: str
    manufacturer: Optional[str]
    price: Optional[float]
    contractor_id: Optional[int]
    source_ref: Optional[str]
    history_count: int
    has_photo: bool
    has_description: bool
    diff_tokens: tuple = field(default_factory=tuple)
    same_store_as_winner: bool = False


@dataclass
class SimilarGroup:
    brand: str
    base_model: str
    confidence: str
    match_key: str  # 'article' | 'model' — чем именно сгруппировано
    suggested_winner_id: Optional[int]
    cards: list
    # Исходное написание модели/артикула winner'а для заголовка группы
    # (владелец, 27.10.2026, п.1 приёмки) — «ОП-2»/«DF332DWME», не свёрнутое
    # «оп2»/«df332dwme» (base_model/код остаются ключом группировки, их не
    # трогаем). Пусто только если разбор не нашёл исходное слово — тогда
    # фронт сам подставляет base_model (см. роутер/сборку группы ниже).
    model_display: str = ""


def _store_source(contractor_id: Optional[int]):
    """Ключ "магазина" для подсчёта разных источников группы (владелец,
    27.10.2026, п.3) — NULL сворачивается в ОДИН сентинел '__no_store__',
    поэтому «2 карточки без магазина» считаются ОДНИМ источником, не двумя
    разными (как и обычные set() с None — сентинел только для читаемости)."""
    return contractor_id if contractor_id is not None else _NO_STORE


def _pick_winner(products: list, history_count_by_id: dict, photo_ids: set) -> Product:
    """Приоритет (владелец, 27.10.2026, прогон на проде — побеждала карточка
    без магазина и без истории): больше строк истории цен → есть магазин
    (contractor_id не NULL) → есть фото → длиннее описание → меньший id."""
    def _priority(p: Product) -> tuple:
        return (
            history_count_by_id.get(p.id, 0),
            p.price_source_contractor_id is not None,
            p.id in photo_ids,
            len((p.description or "").strip()),
            -p.id,
        )
    return max(products, key=_priority)


def _build_cards(products: list, keys_by_id: dict, winner: Product, confidence: str, photo_ids: set, history_count_by_id: dict) -> list:
    # diff_tokens (владелец, 27.10.2026, правка): «общие» слова — токены,
    # присутствующие у ВСЕХ карточек группы; diff карточки = её токены МИНУС
    # общие. Раньше "others" был объединением (union) токенов ВСЕХ прочих
    # карточек — на группах из 3+ карточек это почти всегда покрывало любое
    # слово (оно встречалось хоть у одной другой карточки) и diff всегда
    # получался пустым даже там, где два конкретных названия отличались
    # («Китай» vs «Россия разборное»).
    all_rest_sets = [set(keys_by_id[p.id].rest_tokens) for p in products]
    common_tokens = set.intersection(*all_rest_sets) if all_rest_sets else set()

    cards = []
    for p in products:
        own_tokens = set(keys_by_id[p.id].rest_tokens)
        diff = tuple(sorted(own_tokens - common_tokens)) if confidence != "уверенно" else tuple()
        # «Тот же магазин, что winner» (владелец, 27.10.2026) — ТОЛЬКО когда
        # у ОБОИХ contractor_id реально совпадает и НЕ NULL; NULL — отдельный
        # источник у КАЖДОЙ карточки (как и в группировке), два NULL — это
        # НЕ "тот же магазин", не помечаем.
        same_store = (
            p.id != winner.id
            and p.price_source_contractor_id is not None
            and winner.price_source_contractor_id is not None
            and p.price_source_contractor_id == winner.price_source_contractor_id
        )
        cards.append(SimilarCard(
            id=p.id,
            name=p.name,
            manufacturer=p.manufacturer,
            price=float(p.price) if p.price is not None else None,
            contractor_id=p.price_source_contractor_id,
            source_ref=p.price_source_ref,
            history_count=history_count_by_id.get(p.id, 0),
            has_photo=p.id in photo_ids,
            has_description=bool((p.description or "").strip()),
            diff_tokens=diff,
            same_store_as_winner=same_store,
        ))
    cards.sort(key=lambda c: c.id)
    return cards


async def find_similar_groups(
    db: AsyncSession, q: str, limit_groups: int = DEFAULT_LIMIT_GROUPS,
) -> list[SimilarGroup]:
    """Карточки, чьё имя (ILIKE) содержит `q`, группированные СНАЧАЛА по
    ОБЩЕМУ ШТРИХКОДУ (владелец, 27.10.2026, решение «штрихкод — главный
    ключ») — confidence='уверенно', match_key='barcode', ПЕРЕД артикулом и
    моделью (надёжнее обоих); ПОТОМ (среди карточек, не попавших в группу по
    штрихкоду) по (brand, артикул производителя) — confidence='уверенно',
    ПОТОМ (среди карточек, не попавших ни в штрихкод, ни в артикул) по
    (brand, base_model) — confidence='проверить'. Группа показывается только
    при ≥2 РАЗНЫХ магазинах внутри (владелец, 27.10.2026, п.3 — карточки
    одного магазина сами по себе всегда разные товары, слиянию нечего
    предложить). Ничего не меняет в БД — чистое чтение для ручной проверки
    (эндпоинт/CLI)."""
    q = (q or "").strip()
    if len(q) < MIN_QUERY_LEN:
        raise ValueError(f"q должен быть не короче {MIN_QUERY_LEN} символов")

    known_brands = await _load_known_brands(db)

    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (await db.execute(
        select(Product).where(Product.name.ilike(f"%{escaped}%")).limit(SQL_SCAN_LIMIT)
    )).scalars().all()
    if not rows:
        return []

    ids = [p.id for p in rows]
    history_count_by_id: dict[int, int] = {}
    for pid, _hid in (await db.execute(
        select(ProductPriceHistory.product_id, ProductPriceHistory.id)
        .where(ProductPriceHistory.product_id.in_(ids))
    )).all():
        history_count_by_id[pid] = history_count_by_id.get(pid, 0) + 1

    photo_ids = set((await db.execute(
        select(ProductPhoto.product_id).where(ProductPhoto.product_id.in_(ids))
    )).scalars().all())

    contractor_ids = {p.price_source_contractor_id for p in rows if p.price_source_contractor_id is not None}
    article_is_mfr_by_contractor = await _load_article_is_manufacturer_by_contractor(db, contractor_ids)

    keys_by_id: dict[int, SimilarityKey] = {}
    for p in rows:
        keys_by_id[p.id] = similarity_key(
            p.name, p.manufacturer, known_brands,
            article=p.article,
            article_is_manufacturer=article_is_mfr_by_contractor.get(p.price_source_contractor_id, False),
        )

    def _distinct_stores(products: list) -> set:
        return {_store_source(p.price_source_contractor_id) for p in products}

    result: list[SimilarGroup] = []
    claimed_ids: set[int] = set()

    # 0) Общий штрихкод — confidence='уверенно', match_key='barcode'
    # (владелец, 27.10.2026, решение «штрихкод — главный ключ») — ПЕРВОЙ,
    # до артикула и модели: совпадающий штрихкод надёжнее любого текстового
    # разбора названия.
    barcode_rows_by_product: dict[int, set] = {}
    for product_id, barcode in (await db.execute(
        select(ProductBarcode.product_id, ProductBarcode.barcode).where(ProductBarcode.product_id.in_(ids))
    )).all():
        barcode_rows_by_product.setdefault(product_id, set()).add(barcode)

    barcode_groups: dict[str, list] = {}
    for p in rows:
        for bc in barcode_rows_by_product.get(p.id, ()):
            barcode_groups.setdefault(bc, []).append(p)
    for barcode, products in barcode_groups.items():
        if len(products) < 2 or len(_distinct_stores(products)) < 2:
            continue
        winner = _pick_winner(products, history_count_by_id, photo_ids)
        cards = _build_cards(products, keys_by_id, winner, "уверенно", photo_ids, history_count_by_id)
        result.append(SimilarGroup(
            brand=keys_by_id[winner.id].brand_display or "", base_model=barcode,
            confidence="уверенно", match_key="barcode",
            suggested_winner_id=winner.id, cards=cards,
            model_display=barcode,
        ))
        claimed_ids.update(p.id for p in products)

    # 0.5) Название + индекс модели (ЕДИНОЕ правило «тот же товар», владелец,
    # 27.10.2026, app.services.product_name_signature — заменяет прежнюю
    # группировку «ключ вида товара», product_type_keys.py удалён, ПРАВИЛО
    # №6: один механизм) — ВТОРОЙ по надёжности, после штрихкода. Группа —
    # карточки (НЕ уже сгруппированные по штрихкоду выше) с ОДИНАКОВЫМ
    # набором цифро-буквенных токенов названия (ProductSignature.
    # digit_tokens — тот же жёсткий гейт, что у критерия (0.75) импорта,
    # services/products_import_match_name_model.py). winner — _pick_winner;
    # каждая другая карточка группы сравнивается с winner через match():
    # decision=="no" (бренд/вид товара/свойство расходится) — карточка явно
    # ДРУГОЙ товар, исключается из группы целиком; decision=="auto" у ВСЕХ
    # оставшихся → confidence='уверенно'; хоть одна "check" →
    # confidence='проверить', diff_tokens — match()["reason"] по-русски.
    rows_by_id = {p.id: p for p in rows}

    name_sig_by_id: dict = {}
    for p in rows:
        if p.id in claimed_ids:
            continue
        sig = _build_name_signature({
            "name": p.name, "manufacturer": p.manufacturer,
            "characteristics": p.characteristics or [],
        })
        if sig.digit_tokens:
            name_sig_by_id[p.id] = sig

    name_model_groups: dict = {}
    for pid, sig in name_sig_by_id.items():
        name_model_groups.setdefault(sig.digit_tokens, []).append(pid)

    for digit_key, pids in name_model_groups.items():
        products = [rows_by_id[pid] for pid in pids]
        if len(products) < 2 or len(_distinct_stores(products)) < 2:
            continue
        winner = _pick_winner(products, history_count_by_id, photo_ids)
        winner_sig = name_sig_by_id[winner.id]

        kept_pids = [winner.id]
        decisions: dict[int, dict] = {}
        for pid in pids:
            if pid == winner.id:
                continue
            other_sig = name_sig_by_id[pid]
            peers_a = tuple(name_sig_by_id[p2] for p2 in pids if p2 not in (winner.id, pid))
            peers_b = peers_a
            res = _name_signature_match(winner_sig, other_sig, peers_a=peers_a, peers_b=peers_b)
            if res["decision"] == "no":
                continue  # другой товар (бренд/вид/свойство разошлось) — не похожий, не в группу
            kept_pids.append(pid)
            decisions[pid] = res

        kept_products = [rows_by_id[pid] for pid in kept_pids]
        if len(kept_products) < 2 or len(_distinct_stores(kept_products)) < 2:
            continue
        confidence = "уверенно" if all(d["decision"] == "auto" for d in decisions.values()) else "проверить"
        cards = _build_cards(kept_products, keys_by_id, winner, confidence, photo_ids, history_count_by_id)
        if confidence == "проверить":
            for card in cards:
                if card.id == winner.id:
                    continue
                d = decisions.get(card.id)
                if d is not None and d["decision"] == "check":
                    card.diff_tokens = (d["reason"],)
        label = winner_sig.product_type or ", ".join(sorted(digit_key))
        result.append(SimilarGroup(
            brand=winner_sig.brand or keys_by_id[winner.id].brand_display or "",
            base_model=", ".join(sorted(digit_key)),
            confidence=confidence, match_key="name_model",
            suggested_winner_id=winner.id, cards=cards,
            model_display=label,
        ))
        claimed_ids.update(kept_pids)

    # 1) Артикул производителя + бренд — confidence='уверенно' (только
    # карточки, НЕ уже сгруппированные по штрихкоду выше).
    article_groups: dict[tuple, list] = {}
    for p in rows:
        if p.id in claimed_ids:
            continue
        gk = keys_by_id[p.id].article_group_key
        if gk is not None:
            article_groups.setdefault(gk, []).append(p)
    for (brand, code), products in article_groups.items():
        if len(products) < 2 or len(_distinct_stores(products)) < 2:
            continue
        winner = _pick_winner(products, history_count_by_id, photo_ids)
        cards = _build_cards(products, keys_by_id, winner, "уверенно", photo_ids, history_count_by_id)
        result.append(SimilarGroup(
            brand=keys_by_id[winner.id].brand_display or brand, base_model=code,
            confidence="уверенно", match_key="article",
            suggested_winner_id=winner.id, cards=cards,
            model_display=keys_by_id[winner.id].manufacturer_code_display or code,
        ))
        claimed_ids.update(p.id for p in products)

    # 2) Код модели + бренд — confidence='проверить' (только карточки, НЕ
    # уже сгруппированные по артикулу выше).
    model_groups: dict[tuple, list] = {}
    for p in rows:
        if p.id in claimed_ids:
            continue
        gk = keys_by_id[p.id].group_key
        if gk is not None:
            model_groups.setdefault(gk, []).append(p)
    for (brand, base_model), products in model_groups.items():
        if len(products) < 2 or len(_distinct_stores(products)) < 2:
            continue
        rest_sets = {keys_by_id[p.id].rest_tokens for p in products}
        confidence = "уверенно" if len(rest_sets) == 1 else "проверить"
        winner = _pick_winner(products, history_count_by_id, photo_ids)
        cards = _build_cards(products, keys_by_id, winner, confidence, photo_ids, history_count_by_id)
        result.append(SimilarGroup(
            brand=keys_by_id[winner.id].brand_display or brand, base_model=base_model,
            confidence=confidence, match_key="model",
            suggested_winner_id=winner.id, cards=cards,
            model_display=keys_by_id[winner.id].base_model_display or base_model,
        ))

    result.sort(key=lambda g: (g.confidence != "уверенно", -len(g.cards)))
    return result[:limit_groups]
