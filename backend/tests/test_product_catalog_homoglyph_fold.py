"""Гомоглифы кириллица/латиница в normalize_product_name (владелец, 2026-09-15).

ПРИЧИНА: «"Топор колун для дров FISKARS X17 M 1,55 кг с чехлом 122463" — этот
топор есть в БД, есть фото, но в закупке 914, в которую я данные импортировал
из Excel, не подтянулось ни ТЗ, ни фото». В каталоге (id 2693, боевая база)
X/M — ЛАТИНСКИЕ, в позиции закупки (id 3028) те же X/M — КИРИЛЛИЧЕСКИЕ. Строки
визуально неразличимы, но normalize_product_name (до фикса) сравнивал их как
разные имена → product_id остался пустым, ТЗ/фото подтянуть было неоткуда.

Замер по боевой базе: 93 позиции закупок без product_id, у 44 из них в
названии смешаны кириллица и латиница, 25 из 93 нашли бы свой товар только
за счёт приведения гомоглифов.

Единая точка входа (Правило №6) — app/services/product_catalog_match.py:
normalize_product_name теперь ПЕРЕД схлопыванием пробелов приводит явно
проверенный список визуально идентичных пар кириллица/латиница к КИРИЛЛИЦЕ,
плюс попутно ё→е, варианты пробела/дефиса/кавычек, невидимые артефакты
копипаста — см. докстринг модуля с полным обоснованием. SQL-сторона
(find_exact_product) применяет ТУ ЖЕ таблицу через Postgres translate(),
построенную из ОДНОГО словаря — здесь это тоже проверяется, чтобы Python- и
SQL-нормализация не разошлись по-тихому.

Гоняется ПО ОДНОМУ УЗЛУ за вызов pytest (флейк pytest-asyncio «different
loop» при параллельном запуске, см. project_pytest_asyncio_loop_flake).
Тестовые данные живут внутри db_session/outer-transaction (conftest.py) и
откатываются автоматически.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.services.items_import_catalog import _upsert_product_to_catalog
from app.services.product_catalog_match import (
    find_exact_product,
    normalize_product_name,
)

# Уникальный префикс на файл — исключает коллизию с реальными товарами на
# локальной dev-БД (стенд — копия боевой базы).
_UNIQ = "ТестГомоглифКаталога_20260915"


def test_fiskars_latin_and_cyrillic_names_normalize_equal():
    """Ядро дефекта: то же название FISKARS X17 M — латинскими и
    кириллическими X/M — после нормализации становится одной строкой."""
    latin = "Топор колун для дров FISKARS X17 M 1,55 кг с чехлом 122463"
    cyrillic = "Топор колун для дров FISKARS Х17 М 1,55 кг с чехлом 122463"
    assert latin != cyrillic, "тестовые строки должны различаться байтово (иначе тест ничего не проверяет)"
    assert normalize_product_name(latin) == normalize_product_name(cyrillic)


@pytest.mark.asyncio
async def test_find_exact_product_matches_cyrillic_variant_via_sql(db_session):
    """SQL-сторона (Postgres translate()) находит товар, заведённый с
    ЛАТИНСКИМИ X/M, по имени с КИРИЛЛИЧЕСКИМИ Х/М — воспроизводит закупку 914
    из боевого инцидента."""
    latin_name = f"{_UNIQ} Топор FISKARS X17 M"
    cyrillic_query = f"{_UNIQ} Топор FISKARS Х17 М"
    p = Product(name=latin_name, category="Прочее", description="ТЗ товара", price=Decimal("100"))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    found = await find_exact_product(db_session, cyrillic_query)
    assert found is not None, "гомоглиф-приведение не сработало на SQL-стороне"
    assert found.id == p.id


@pytest.mark.asyncio
async def test_import_row_with_cyrillic_letters_links_to_latin_catalog_product(db_session):
    """Тот же сценарий целиком через _upsert_product_to_catalog (реальный
    путь импорта позиций закупки) — строка с кириллическими буквами ДОПОЛНЯЕТ
    существующий товар, а не заводит второй."""
    latin_name = f"{_UNIQ} Бензорез Champion X17"
    cyrillic_name = f"{_UNIQ} Бензорез Champion Х17"
    p = Product(name=latin_name, category="Прочее", description="Полное ТЗ", price=Decimal("50"))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    pid = await _upsert_product_to_catalog(db_session, cyrillic_name, "товар", Decimal("55"))
    assert pid == p.id, "строка с гомоглифом должна была найти существующий товар, а не завести новый"

    rows = (await db_session.execute(
        select(Product).where(Product.name.in_([latin_name, cyrillic_name]))
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_different_products_are_not_merged_by_homoglyph_fold(db_session):
    """Гомоглиф-приведение не должно склеивать РАЗНЫЕ товары: два реально
    разных названия (просто оба содержат confusable-буквы) остаются
    раздельными и в normalize_product_name, и через upsert-путь."""
    name_a = f"{_UNIQ} Ручка дверная модель А"
    name_b = f"{_UNIQ} Ручка дверная модель Б"
    assert normalize_product_name(name_a) != normalize_product_name(name_b)

    pid_a = await _upsert_product_to_catalog(db_session, name_a, "товар", Decimal("5"))
    pid_b = await _upsert_product_to_catalog(db_session, name_b, "товар", Decimal("6"))
    assert pid_a != pid_b

    rows = (await db_session.execute(
        select(Product).where(Product.name.in_([name_a, name_b]))
    )).scalars().all()
    assert {r.id for r in rows} == {pid_a, pid_b}


def test_homoglyph_fold_is_letter_specific_not_full_transliteration():
    """Приведение точечное — только явно заданный список пар (А В Е К М Н О
    Р С Т У Х / a e o p c y x), а не полный транслит слова целиком."""
    # F, L, U, I, D — ни одна буква не входит в список гомоглифов: слово
    # остаётся латиницей без изменений.
    assert normalize_product_name("FLUID") == "fluid"
    # S, T, U, D — единственная confusable-буква здесь "T" (T -> т):
    # заменяется ТОЛЬКО она, S/U/D латиницей.
    assert normalize_product_name("STUD") == "sтud"
    # Кириллическая "о" вместо латинской в середине слова — не мешает
    # сравнению именно потому, что латинская "o" точно так же складывается в
    # "о"; остальные буквы слова (I, N, S, P, R) в списке нет и не трогаются.
    assert normalize_product_name("Inspiron") == normalize_product_name("Inspirоn")


def test_double_space_still_collapses():
    """Регресс уже починенного дефекта (владелец, 2026-09-14): двойной пробел
    внутри имени по-прежнему схлопывается."""
    assert normalize_product_name("Бензорез Champion  3.5 кВт") == normalize_product_name("Бензорез Champion 3.5 кВт")


def test_yo_e_equivalence():
    """ё/Е считаются эквивалентными для точного сопоставления (та же пара,
    что уже принята в app/product_matcher.py для fuzzy-пути)."""
    assert normalize_product_name("Тренажёр силовой") == normalize_product_name("Тренажер силовой")


def test_dash_variants_unified():
    """En dash / em dash / minus sign схлопываются к обычному дефису — сам
    дефис не добавляется и не убирается, меняется только символ."""
    base = "Топор-колун FISKARS"
    for dash in ("‐", "–", "—", "−"):
        variant = base.replace("-", dash)
        assert normalize_product_name(variant) == normalize_product_name(base), f"дефис {dash!r} не унифицирован"


def test_quote_variants_unified():
    """Ёлочки/лапки/апостроф/обратная кавычка сводятся к одному символу."""
    assert normalize_product_name('Дрель "Bosch"') == normalize_product_name("Дрель «Bosch»")
    assert normalize_product_name('Дрель "Bosch"') == normalize_product_name("Дрель “Bosch”")


def test_nbsp_and_zero_width_stripped():
    """Неразрывный пробел (NBSP) вместо обычного не создаёт ложных различий
    (приводится к ' ' перед схлопыванием); невидимый артефакт копипаста
    (zero-width space), затесавшийся ВНУТРЬ слова, удаляется целиком, не
    оставляя невидимого разрыва в сравнении."""
    plain = "FISKARS X17 M"
    with_nbsp = plain.replace(" ", " ")
    with_zwsp_inside_word = "FISKA​RS X17 M"  # ZWSP затесался внутри слова, пробелы на месте
    assert normalize_product_name(plain) == normalize_product_name(with_nbsp)
    assert normalize_product_name(plain) == normalize_product_name(with_zwsp_inside_word)


def test_digit_letter_confusables_folded():
    """Владелец, 2026-09-16: «надо сравнивать ещё и З и 3». Три пары
    цифра↔буква (0/О, 3/З, 4/Ч) — «ОУ-2» (аббревиатура огнетушителя) с
    буквой О и с нулём считаются одним названием."""
    assert normalize_product_name("ОУ-2") == normalize_product_name("0У-2")
    assert normalize_product_name("Аптечка 3") == normalize_product_name("Аптечка З")
    assert normalize_product_name("Топор-колун 4мм") == normalize_product_name("Топор-колун Чмм")


def test_different_digit_counts_never_merge():
    """КРИТИЧНО (владелец, 2026-09-16): цифро-буквенное приведение не смеет
    склеивать РАЗНЫЕ количества/размеры — «Лестница 3 секции» и «Лестница 4
    секции» остаются разными названиями ни при каких условиях, как и другие
    пары, различающиеся только значащей цифрой."""
    assert normalize_product_name("Лестница 3 секции") != normalize_product_name("Лестница 4 секции")
    assert normalize_product_name("Набор 3 предмета") != normalize_product_name("Набор 4 предметов")
    assert normalize_product_name("Стремянка 10 ступеней") != normalize_product_name("Стремянка 11 ступеней")
    assert normalize_product_name("Трос 1,3 мм") != normalize_product_name("Трос 1,4 мм")


@pytest.mark.asyncio
async def test_existing_exact_matches_still_work(db_session):
    """Плоское точное совпадение без каких-либо гомоглифов/юникод-мусора
    по-прежнему находит существующий товар (не ломаем базовый случай)."""
    name = f"{_UNIQ} Простой товар без сюрпризов"
    p = Product(name=name, category="Прочее", price=Decimal("10"))
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    found = await find_exact_product(db_session, f"  {name}  ")  # с обрамляющими пробелами
    assert found is not None
    assert found.id == p.id
