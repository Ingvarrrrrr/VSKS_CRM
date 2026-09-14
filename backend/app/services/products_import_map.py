"""Подсказка соответствия колонок Excel-файла товарного справочника полям
`Product`. ТОЛЬКО точное совпадение нормализованного заголовка с `COLUMN_MAP`
(плюс распознавание пронумерованных «Ссылка N» / «Цена ссылки N») — никакой
фаззи-цепочки по подстрокам и никакой пост-эвристики «в колонке name одни
числа — возьмём другую колонку».

Обе убранные ветки — ровно то, что на боевом файле владельца
(«ТЗ для АПИ (4).xlsx», лист «ТЗ») превратило колонку «Категория товара» в
`name`: строка `'категор' in h` фаззи-цепочки матчила «Категория товара» на
`category`, но перед этим `any(x in h for x in ('наименован', ...))` тоже
матчила её на `name`, потому что порядок elif решал первым делом `name`, и то,
что «Категория товара» физически СОДЕРЖИТ подстроку из списка совпадений
`name` в конкретной комбинации заголовков файла, забирало колонку раньше,
чем реальный заголовок «Наименование». Итог — 1022 товара с именами-категориями
в БД (план dreamy-booping-piglet.md, задача B, дефект №2).

Подсказка — это ТОЛЬКО подсказка: возвращается клиенту для проверки/правки в
мастере маппинга и не применяется сама по себе (см.
routers/products_import.py::products_import_preview /
products_import_mapped — реальные индексы колонок передаёт клиент явно).

Второй проход (`suggest_products_column_mapping_with_hints`, только для
/import-preview — не для старого /import, чтобы там сохранялось поведение
чистого точного совпадения): владелец 2026-09-09 указал, что после первого
исправления подсказка перестала предлагать ОЧЕВИДНЫЕ колонки («Категория
товара», «Ед. изм.», «Цена за ед.») просто потому, что их заголовок не
СОВПАДАЕТ буквально с ключом COLUMN_MAP — они лежали в «Не определилось», и
пользователь рисковал случайно оставить категорию пустой (снова эффект
дефекта №2, только зеркальный — не подмена name, а бесполезная подсказка).
Второй проход — узкий и безопасный: заголовок подходит полю, только если
нормализованное имя поля — префикс заголовка ИЛИ отдельное слово в нём;
колонка занимается не больше одного раза; несколько кандидатов на одно поле
— берём самый короткий заголовок, при равенстве длин не предлагаем ничего.
Поле «name» второй проход не получает вовсе, если заголовок похож на
категорию/вид/тип/описание (`_NAME_FORBIDDEN_SUBSTR`) — жёсткий бэкстоп
против исходного бага, даже если алгоритм совпадения когда-нибудь изменится.

Третье правило (`_pick_best_exact_candidate`, только для /import-preview,
2026-09-15): на боевом файле владельца («ТЗ для АПИ (4).xlsx») ОБА
заголовка «фото» и «Ссылка на фото» точно совпадают с ключами COLUMN_MAP
на `photo_link` — «фото» стоит в файле раньше и пустой во всех строках,
реальные адреса лежат в «Ссылка на фото». Правило не «переставить фото
выше ссылки в словаре» (в чужом файле порядок и сами названия будут
другими), а общее: если на одно поле нашлось НЕСКОЛЬКО точных совпадений,
берём то, у которого в образце строк (`sample`, те же данные, что клиент
и так видит в предпросмотре) есть хоть одно непустое значение; без образца
— прежнее поведение (первый по порядку).
"""
import re as _re

# Дословно перенесено из routers/products_import.py:136-166 (до правки) —
# единственный источник соответствия «заголовок → поле Product» для подсказки.
COLUMN_MAP = {
    "наименование": "name",
    "название": "name",
    "наименование товара": "name",
    "товар": "name",
    "name": "name",
    "описание": "description",
    "description": "description",
    "категория": "category",
    "category": "category",
    "вид": "product_type",
    "тип": "product_type",
    "type": "product_type",
    "цена": "price",
    "цена, руб": "price",
    "цена, ₽": "price",
    "цена (руб)": "price",
    "стоимость": "price",
    "price": "price",
    "фото (url)": "photo_link",
    "фото": "photo_link",
    "photo": "photo_link",
    "ссылка на фото": "photo_link",
    "многоразовое": "is_reusable",
    "активен": "is_active",
    "активна": "is_active",
    "active": "is_active",
    "категория фэо": "feo_category_name",
    "фэо": "feo_category_name",
    "направление фэо": "feo_category_name",
}

_LINK_URL_RE = _re.compile(r"ссылка (\d+)$")
_LINK_PRICE_RE = _re.compile(r"цена ссылки (\d+)$")


def suggest_products_column_mapping(headers: list) -> dict:
    """headers — заголовки КАК ЕСТЬ (регистр/пробелы неважны, нормализуются
    внутри). Возвращает {field: column_index} — только точные совпадения из
    `COLUMN_MAP` (первое вхождение поля побеждает при дублирующихся
    заголовках) плюс динамические `link_url_N` / `link_price_N` для колонок
    «Ссылка N» / «Цена ссылки N». Никакой догадки сверх этого."""
    col_idx: dict = {}
    for i, h in enumerate(headers):
        norm = str(h).strip().lower() if h is not None else ""
        if not norm:
            continue
        field = COLUMN_MAP.get(norm)
        if field and field not in col_idx:
            col_idx[field] = i
        m = _LINK_URL_RE.match(norm)
        if m:
            col_idx[f"link_url_{m.group(1)}"] = i
        m2 = _LINK_PRICE_RE.match(norm)
        if m2:
            col_idx[f"link_price_{m2.group(1)}"] = i
    return col_idx


def _exact_match_candidates(headers: list) -> dict:
    """Как `suggest_products_column_mapping`, но БЕЗ правила «первый победил»
    — возвращает {field: [все индексы заголовков, точно совпавших с полем]}.
    На чужих файлах одно поле нередко имеет два точных синонима в
    COLUMN_MAP разом (пример: «фото» и «Ссылка на фото» — оба ключа на
    `photo_link`); который из двух реальный, решает не порядок колонок в
    файле, а `_pick_best_exact_candidate` (см. ниже)."""
    by_field: dict = {}
    for i, h in enumerate(headers):
        norm = str(h).strip().lower() if h is not None else ""
        if not norm:
            continue
        field = COLUMN_MAP.get(norm)
        if field:
            by_field.setdefault(field, []).append(i)
    return by_field


# Значения, которые Excel сам подставляет при битой формуле/ссылке — считать
# их «есть данные» нельзя: на боевом файле владельца колонка «фото» (пустая
# почти везде) в одной строке образца содержала не URL, а буквально `#REF!` —
# при подсчёте «есть хоть одно непустое значение» ЭТО единственное значение
# перевешивало и снова выбирало пустую колонку вместо «Ссылка на фото»
# (там реальные адреса в 5 строках из 5, но простое «хоть одна непустая
# ячейка» не отличает частый мусор от редкого).
_EXCEL_ERROR_TOKENS = {"#ref!", "#n/a", "#value!", "#div/0!", "#name?", "#null!", "#num!"}


def _sample_fill_count(sample: list, col_idx: int) -> int:
    """Сколько строк образца в этой колонке реально заполнены — ячейки с
    Excel-ошибкой (#REF! и т.п.) не считаются, все остальные непустые
    значения считаются (включая текстовый мусор вроде «НЕ смог найти» —
    отличать текст от настоящего URL это правило не пытается, оно только
    выбирает, у какого из двух ЗАГОЛОВКОВ данные заполнены гуще)."""
    count = 0
    for row in sample or ():
        if col_idx < len(row):
            val = row[col_idx]
            if val is None:
                continue
            s = str(val).strip()
            if s and s.lower() not in _EXCEL_ERROR_TOKENS:
                count += 1
    return count


def _pick_best_exact_candidate(candidates: list, sample: list) -> int:
    """Несколько заголовков точно совпали с одним полем — правило не «кто
    первый встретился», а «у кого в образце строк реально ГУЩЕ заполнены
    данные» (побеждает наибольшее число непустых строк образца, а не факт
    «хоть одна непустая ячейка» — единичный мусор в редко используемой
    колонке иначе перевешивал бы стабильно заполненную). При равенстве —
    первый по порядку в файле. Без образца (sample пуст/не передан)
    откатываемся на прежнее поведение — первый по порядку, чтобы не ломать
    вызовы без sample."""
    if not sample:
        return candidates[0]
    counts = [(i, _sample_fill_count(sample, i)) for i in candidates]
    best_count = max(cnt for _, cnt in counts)
    if best_count == 0:
        return candidates[0]
    for i, cnt in counts:
        if cnt == best_count:
            return i
    return candidates[0]


# ── Второй проход (только для /import-preview) ──────────────────────────
# Канонический русский термин на поле — используется как префикс/отдельное
# слово, НЕ как точное совпадение (точное совпадение уже покрыто COLUMN_MAP
# выше). "ед" — намеренно короткий префикс: покрывает и «Ед. изм.», и
# «Единица измерения» одним правилом.
_FUZZY_FIELD_TERMS = {
    "name": "наименование",
    "description": "описание",
    "category": "категория",
    "product_type": "вид",
    "unit": "ед",
    "price": "цена",
    "photo_link": "фото",
    "is_reusable": "многоразовое",
    "is_active": "активен",
    "feo_category_name": "категория фэо",
}

# Заголовки с этими подстроками никогда не становятся `name` вторым проходом
# — ровно то, что на боевом файле владельца («ТЗ для АПИ (4).xlsx») привело
# к 1022 товарам-категориям (план dreamy-booping-piglet.md, задача B).
_NAME_FORBIDDEN_SUBSTR = ("категор", "вид", "тип", "описан")

_FUZZY_PUNCT_RE = _re.compile(r'["\'()«»,.]')


def _fuzzy_normalize(h) -> str:
    """Нормализация ТОЛЬКО для второго прохода — в отличие от точного
    совпадения (пункт 1, ключи COLUMN_MAP сами содержат запятые/скобки),
    здесь пунктуация схлопывается в пробел, чтобы «Цена за ед.» и «ед.изм.»
    сравнивались по словам, а не по буквальной строке."""
    s = str(h).strip().lower() if h is not None else ""
    s = _FUZZY_PUNCT_RE.sub(" ", s)
    return _re.sub(r"\s+", " ", s).strip()


def _apply_fuzzy_pass(col_idx: dict, headers: list) -> list:
    """Мутирует `col_idx` (добавляет поля, для которых нашёлся безопасный
    кандидат), возвращает список имён полей, подставленных этим проходом —
    его кладут в `mapping_hint_fuzzy`, чтобы фронт пометил такие карточки
    «предположительно» (пользователь всё равно подтверждает вручную)."""
    used = set(col_idx.values())
    norm_headers = [_fuzzy_normalize(h) for h in headers]
    fuzzy_fields: list = []
    for field, term in _FUZZY_FIELD_TERMS.items():
        if field in col_idx:
            continue
        candidates = []
        for i, norm_h in enumerate(norm_headers):
            if i in used or not norm_h:
                continue
            if field == "name" and any(bad in norm_h for bad in _NAME_FORBIDDEN_SUBSTR):
                continue
            if norm_h.startswith(term) or term in norm_h.split():
                candidates.append(i)
        if not candidates:
            continue
        # Ранжируем: сначала заголовки БЕЗ цифры (перечисление вроде «Цена 1
        # (руб)», «Цена 2 (руб)» — это альтернативные цены по ссылкам, а не
        # основная цена товара), затем по длине. На боевом файле владельца
        # «Цена за ед.» (10 симв., без цифры) иначе давала точную ничью по
        # длине с «Цена 1 (руб)»/«Цена 2 (руб)»/«Цена 3 (руб)» (тоже 10 симв.,
        # но с цифрой) — без этого правила подсказка отказывалась бы от
        # «Цена за ед.» вовсе, хотя одна из четырёх колонок явно основная.
        def _rank(i: int) -> tuple:
            h = norm_headers[i]
            return (any(ch.isdigit() for ch in h), len(h))
        candidates.sort(key=_rank)
        if len(candidates) > 1 and _rank(candidates[0]) == _rank(candidates[1]):
            continue  # неоднозначно даже с учётом цифр — лучше ничего не предлагать
        chosen = candidates[0]
        col_idx[field] = chosen
        used.add(chosen)
        fuzzy_fields.append(field)
    return fuzzy_fields


def suggest_products_column_mapping_with_hints(headers: list, sample: list = None) -> dict:
    """Для POST /import-preview: точное совпадение
    (`suggest_products_column_mapping`) + пересмотр полей с НЕСКОЛЬКИМИ
    точно совпавшими заголовками по данным образца (`sample` — те же
    строки-примеры, что /import-preview и так возвращает клиенту, см.
    `_pick_best_exact_candidate`) + второй, узкий проход (`_apply_fuzzy_pass`).
    Возвращает тот же {field: column_index}, плюс ключ `mapping_hint_fuzzy`
    — список полей, подставленных вторым проходом (см. модуль docstring).
    `sample` необязателен (по умолчанию None) — без него поведение как
    раньше, «первый точно совпавший заголовок побеждает». Старый POST
    /import НЕ использует эту функцию — он по-прежнему зовёт
    `suggest_products_column_mapping` напрямую, только точное совпадение,
    без второго прохода и без пересмотра по образцу."""
    col_idx = suggest_products_column_mapping(headers)
    if sample:
        for field, candidates in _exact_match_candidates(headers).items():
            if len(candidates) > 1:
                col_idx[field] = _pick_best_exact_candidate(candidates, sample)
    fuzzy_fields = _apply_fuzzy_pass(col_idx, headers)
    col_idx["mapping_hint_fuzzy"] = fuzzy_fields
    return col_idx
