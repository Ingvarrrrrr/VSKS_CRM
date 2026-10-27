"""Сборщик inari.pro. ⚠️ НУЖНА ДОРАБОТКА — за отведённые на эту задачу 3
живые страницы разметку разобрать НЕ удалось, см. причину ниже. Модуль
зарегистрирован в run.py по требованию задания, но parse_category_page()
сознательно возвращает [] — честный ноль, а не выдуманные товары (брак
старого harvest_inari_winders.py, который гнал regex по плоскому тексту
страницы и писал галлюцинированные "characteristics"/"article"/"country"
— ПРАВИЛО №8: не заполнять сидом то, чего на странице на самом деле нет).

Причина (проверено на живой фикстуре tools/harvest/tests/fixtures/
inari_category.html, 27.10.2026, 2 живых запроса — страница каталога
https://inari.pro/catalog/products/flagshtoki-parus/483 + 1 проверка
гипотетического REST-эндпойнта):
  - inari.pro — Angular SSR/CSR-приложение (`<script id="ng-state"
    type="application/json">` — служебный hydration-стейт Angular, НЕ
    данные товара: в блоке нет ни слова "флагшток", ни "price", ни
    "name" — проверено прямым поиском по декодированному JSON).
  - В отданном сервером HTML НЕТ ни одной читаемой пары цена/название
    (искали паттерн "<число> Р" — старый сборщик именно на нём строил
    весь разбор; на живой фикстуре совпадений 0). Значит каталог и цены
    подгружаются КЛИЕНТСКИМ JS уже в браузере — какой именно XHR/API он
    дёргает, по статическому HTML не видно.
  - Проверка одной правдоподобной догадки `/api/catalog/products/
    flagshtoki-parus/483` вернула 404 — реальный путь API не найден в
    пределах выделенного бюджета живых запросов.
  - Для настоящего сбора inari.pro нужен headless-браузер (Playwright/
    Selenium) с перехватом сетевых запросов страницы, чтобы найти
    реальный источник данных — это отдельная задача за пределами
    tools/harvest (текущее ядро работает только по "голым" HTTP-ответам,
    см. core/http.py), и не входит в эту задачу."""
from __future__ import annotations

from typing import Optional

from tools.harvest.core.runner import StoreSpec, harvest as _run_harvest

STORE_NAME = "inari"

CATEGORIES: list[tuple[str, str, list[str]]] = [
    (
        "https://inari.pro/catalog/products/flagshtoki-parus/483",
        "Флагштоки Парус",
        ["Рекламные конструкции", "Мобильные флагштоки"],
    ),
]


def page_url(category_url: str, page: int) -> str:
    return category_url


def parse_category_page(html: str) -> list[dict]:
    # Сознательно пусто — см. докстринг модуля: сервер не отдаёт данные
    # товара в статическом HTML (Angular CSR), выдумывать строки нельзя.
    return []


def needs_product_visit(candidate: dict) -> bool:
    return False


def parse_product_page(html: str, url: str) -> dict:  # pragma: no cover - не вызывается
    return {}


def build_item(candidate: dict, enrichment: dict, known_brands: set) -> Optional[dict]:  # pragma: no cover - нет кандидатов
    return None


SPEC = StoreSpec(
    name=STORE_NAME,
    categories=CATEGORIES,
    page_url=page_url,
    parse_category_page=parse_category_page,
    needs_product_visit=needs_product_visit,
    parse_product_page=parse_product_page,
    build_item=build_item,
    max_pages_per_category=1,
    concurrency=1,
    default_pause_per_domain=1.0,
    category_has_price=False,
)


def harvest(
    out_path: str,
    limit_categories: Optional[int] = None,
    resume: bool = False,
    pause_per_domain: Optional[float] = None,
    previous_items: Optional[list] = None,
    prices_only: bool = False,
    with_details: bool = False,
) -> dict:
    return _run_harvest(
        SPEC, out_path, limit_categories=limit_categories, resume=resume,
        pause_per_domain=pause_per_domain, previous_items=previous_items, prices_only=prices_only,
        with_details=with_details,
    )
