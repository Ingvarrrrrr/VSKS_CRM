"""Тесты scripts/strip_ads_from_descriptions.py (владелец, 26.10.2026,
Задача 4). Юнит-часть — strip_ads_preserving_paragraphs — без БД: поабзацное
применение ЕДИНСТВЕННОГО фильтра strip_ad_sentences и склейка обратно через
"\n\n". DB-часть — process_rows (ядро run(), вынесено для тестируемости, как
_process_file у rebuild_descriptions_from_sources.py) — с реальной тестовой
БД (db_session/test_user из conftest.py): dry-run ничего не пишет, --apply
меняет Product.description через единственного писателя истории
set_product_description, повторный --apply не находит изменений."""
import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.product_description_history import ProductDescriptionHistory
from scripts.strip_ads_from_descriptions import (
    DEFAULT_SOURCE_FILES, _import_note_file, process_rows, source_file_allowed,
    strip_ads_preserving_paragraphs,
)

_FIRE_EQUIPMENT_NOTE = "Импорт каталога из файла «fire_equipment_nomenclature.json», Тест, 26.10.2026 12:00"


# --- strip_ads_preserving_paragraphs (без БД) -------------------------------

def test_owner_example_valve_ad_paragraph_removed_tech_paragraph_kept():
    """Пример владельца: «Широкий выбор запорно-регулирующей арматуры...
    \n\nДиаметр: 300 мм» -> «Диаметр: 300 мм» (первый абзац — целиком
    реклама, strip_ad_sentences даёт на нём None; второй — техданные,
    остаётся как есть)."""
    text = (
        "Широкий выбор запорно-регулирующей арматуры для систем водяного и "
        "пенного пожаротушения: противопожарные клапаны, задвижки, вентили, "
        "затворы.\n\nДиаметр: 300 мм"
    )
    assert strip_ads_preserving_paragraphs(text) == "Диаметр: 300 мм"


def test_non_ad_text_untouched():
    text = "Ластик фигурный «Панда». Сертифицированная продукция."
    assert strip_ads_preserving_paragraphs(text) == text


def test_non_ad_multi_paragraph_text_untouched():
    text = "Кружка чайная керамическая «Врач», 320 мл.\n\nСтрана-производитель: Китай\nВес брутто: 325 г"
    assert strip_ads_preserving_paragraphs(text) == text


def test_all_paragraphs_are_ads_gives_none():
    text = (
        "Купить с доставкой по России в компании Magazin01.\n\n"
        "Звоните, заказывайте по доступным ценам со скидками."
    )
    assert strip_ads_preserving_paragraphs(text) is None


def test_middle_paragraph_removed_order_preserved():
    text = "Первый абзац технический.\n\nКупить можно с доставкой по России.\n\nТретий абзац технический."
    assert strip_ads_preserving_paragraphs(text) == "Первый абзац технический.\n\nТретий абзац технический."


def test_empty_and_none_input():
    assert strip_ads_preserving_paragraphs(None) is None
    assert strip_ads_preserving_paragraphs("") is None
    assert strip_ads_preserving_paragraphs("   ") is None


# --- _import_note_file -------------------------------------------------------

def test_import_note_file_extracts_filename():
    note = "Импорт каталога из файла «fire_equipment_nomenclature.json», Иванов И.И., 26.10.2026 12:00"
    assert _import_note_file(note) == "fire_equipment_nomenclature.json"


def test_import_note_file_missing_note():
    assert _import_note_file(None) == "(без import_note)"
    assert _import_note_file("") == "(без import_note)"


def test_import_note_file_other_format():
    assert _import_note_file("Что-то другое") == "(прочий import_note)"


# --- source_file_allowed (владелец, 27.10.2026, обязательный фильтр по
# источнику — товары из «ТЗ для АПИ *.xlsx» и без import_note НЕ трогать
# никогда, независимо от --files) ---------------------------------------

def test_source_file_allowed_matches_exact_name():
    note = "Импорт каталога из файла «fire_equipment_nomenclature.json», Тест, 26.10.2026 12:00"
    assert source_file_allowed(note, DEFAULT_SOURCE_FILES) is True


def test_source_file_allowed_matches_glob_mask():
    note = "Импорт каталога из файла «electro_mpo_breakers_all.json», Тест, 26.10.2026 12:00"
    assert source_file_allowed(note, DEFAULT_SOURCE_FILES) is True


def test_source_file_allowed_rejects_tz_api_xlsx_even_with_wide_patterns():
    """«ТЗ для АПИ (8).xlsx» — тексты владельца, не каталог магазина; не
    трогаем ВСЕГДА, даже если кто-то по ошибке передаст маску, под которую
    это имя формально подходит ("*")."""
    note = "Импорт каталога из файла «ТЗ для АПИ (8).xlsx», Тест, 26.10.2026 12:00"
    assert source_file_allowed(note, DEFAULT_SOURCE_FILES) is False
    assert source_file_allowed(note, ["*"]) is False


def test_source_file_allowed_rejects_missing_import_note_even_with_wide_patterns():
    assert source_file_allowed(None, DEFAULT_SOURCE_FILES) is False
    assert source_file_allowed(None, ["*"]) is False
    assert source_file_allowed("Что-то другое", ["*"]) is False


# --- process_rows (с реальной тестовой БД) -----------------------------------

@pytest.mark.asyncio
async def test_process_rows_dry_run_writes_nothing(db_session, test_user):
    product = Product(
        name="Арматура запорно-регулирующая",
        category="Пожарное оборудование",
        description=(
            "Широкий выбор запорно-регулирующей арматуры для систем водяного "
            "и пенного пожаротушения: противопожарные клапаны, задвижки, "
            "вентили, затворы.\n\nДиаметр: 300 мм"
        ),
        import_note=_FIRE_EQUIPMENT_NOTE,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    old_description = product.description

    report = await process_rows(db_session, [product], apply=False, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)
    await db_session.commit()

    assert report["will_change"] == 1
    assert report["by_file"] == {"fire_equipment_nomenclature.json": 1}
    assert report["samples"][0]["new"] == "Диаметр: 300 мм"

    # dry-run: Product.description и история не тронуты.
    await db_session.refresh(product)
    assert product.description == old_description
    history_rows = (await db_session.execute(
        select(ProductDescriptionHistory).where(
            ProductDescriptionHistory.product_id == product.id
        )
    )).scalars().all()
    assert history_rows == []


@pytest.mark.asyncio
async def test_process_rows_untouched_product_not_counted(db_session, test_user):
    product = Product(
        name="Ластик фигурный «Панда»",
        category="Канцтовары",
        description="Ластик фигурный «Панда». Сертифицированная продукция.",
        import_note="Импорт каталога из файла «sima_land_catalog_all.json», Тест, 26.10.2026 12:00",
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    report = await process_rows(db_session, [product], apply=False, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)

    assert report["will_change"] == 0
    assert report["processed"] == 1
    assert report["samples"] == []


@pytest.mark.asyncio
async def test_process_rows_apply_writes_through_history_then_repeat_apply_finds_nothing(
    db_session, test_user,
):
    product = Product(
        name="Арматура запорно-регулирующая",
        category="Пожарное оборудование",
        description=(
            "Широкий выбор запорно-регулирующей арматуры для систем водяного "
            "и пенного пожаротушения: противопожарные клапаны, задвижки, "
            "вентили, затворы.\n\nДиаметр: 300 мм"
        ),
        import_note=_FIRE_EQUIPMENT_NOTE,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    report = await process_rows(db_session, [product], apply=True, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)
    await db_session.commit()

    assert report["will_change"] == 1
    await db_session.refresh(product)
    assert product.description == "Диаметр: 300 мм"

    history_rows = (await db_session.execute(
        select(ProductDescriptionHistory).where(
            ProductDescriptionHistory.product_id == product.id
        )
    )).scalars().all()
    assert len(history_rows) == 1
    assert history_rows[0].source == "import"
    assert history_rows[0].field == "description"
    assert "Широкий выбор" in history_rows[0].old_value

    # Повторный --apply на уже очищенном описании — 0 изменений.
    second_report = await process_rows(db_session, [product], apply=True, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)
    await db_session.commit()
    assert second_report["will_change"] == 0

    history_rows_after = (await db_session.execute(
        select(ProductDescriptionHistory).where(
            ProductDescriptionHistory.product_id == product.id
        )
    )).scalars().all()
    assert len(history_rows_after) == 1  # вторая запись истории не появилась


@pytest.mark.asyncio
async def test_process_rows_empty_result_not_touched(db_session, test_user):
    """Описание целиком реклама (new пуст) — product.description НЕ
    трогается, считается в became_empty, а не will_change."""
    product = Product(
        name="Гидроэлеватор пожарный Г-600",
        category="Пожарное оборудование",
        description=(
            "Гидроэлеватор пожарный Г-600 по низким ценам в Москве в "
            "компании Magazin01. На нашем сайте большой выбор пожарного "
            "оборудования, у нас вы можете купить гидроэлеватор Г-600 с "
            "доставкой по России."
        ),
        import_note=_FIRE_EQUIPMENT_NOTE,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    old_description = product.description

    report = await process_rows(db_session, [product], apply=True, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)
    await db_session.commit()

    assert report["became_empty"] == 1
    assert report["will_change"] == 0
    await db_session.refresh(product)
    assert product.description == old_description


# --- обязательный фильтр по источнику на уровне process_rows (владелец,
# 27.10.2026): товар с рекламным описанием, но import_note «ТЗ для АПИ
# *.xlsx» или вовсе без import_note — НЕ трогается, даже с --apply. ------

@pytest.mark.asyncio
async def test_process_rows_skips_tz_api_xlsx_source_even_with_ad_text(db_session, test_user):
    product = Product(
        name="Текст владельца из ТЗ",
        category="Прочее",
        description=(
            "Широкий выбор запорно-регулирующей арматуры для систем водяного "
            "и пенного пожаротушения: противопожарные клапаны, задвижки, "
            "вентили, затворы."
        ),
        import_note="Импорт каталога из файла «ТЗ для АПИ (8).xlsx», Тест, 26.10.2026 12:00",
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    old_description = product.description

    report = await process_rows(db_session, [product], apply=True, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)
    await db_session.commit()

    assert report["will_change"] == 0
    assert report["became_empty"] == 0
    await db_session.refresh(product)
    assert product.description == old_description


@pytest.mark.asyncio
async def test_process_rows_skips_product_without_import_note_even_with_ad_text(db_session, test_user):
    product = Product(
        name="Товар без import_note",
        category="Прочее",
        description="Купить с доставкой по России в компании Magazin01.",
        import_note=None,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    old_description = product.description

    report = await process_rows(db_session, [product], apply=True, user=test_user, file_patterns=DEFAULT_SOURCE_FILES)
    await db_session.commit()

    assert report["will_change"] == 0
    assert report["became_empty"] == 0
    await db_session.refresh(product)
    assert product.description == old_description
