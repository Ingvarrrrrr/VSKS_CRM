# tools/harvest — сборщики каталогов GALA по магазинам

Собирает товары с сайта магазина в формат `gala-catalog` (см.
`backend/app/services/catalog_gala/format.py`) для последующей загрузки в
products через существующий загрузчик (вне этого пакета).

## Запуск сбора

```
python -m tools.harvest.run --store kuvalda --out "C:\path\to\kuvalda.json"
python -m tools.harvest.run --store regard --out "C:\path\to\regard.json" --pause-per-domain 1.5
```

Параметры:
- `--store {kuvalda,regard}` — какой магазин собирать (реестр — `STORES` в `run.py`).
- `--out <файл>` — куда писать итоговый `.json`.
- `--limit-categories N` — собрать только первые N разделов (для разработки/проверки,
  не для полного прогона).
- `--resume` — продолжить прерванный сбор (см. ниже).
- `--pause-per-domain 1.0` — пауза между запросами к одному домену, секунды.

## Чекпоинт и `--resume`

Во время сбора рядом с `--out` пишется `<файл>.checkpoint.jsonl` — построчно
`{"url", "kind", "status"}` для каждого обработанного раздела/товара. Если
прогон прервался (упал процесс, Ctrl+C, `StoreAbortedError` после 20 подряд
отказов) — повторный запуск с `--resume`:
1. читает чекпоинт и пропускает уже встреченные URL;
2. читает уже накопленные `items` из самого `--out` (если файл существует)
   и продолжает дописывать к ним.

Чекпоинт не удаляется автоматически — если нужен полностью чистый прогон,
удалите `<файл>.checkpoint.jsonl` и `--out` вручную перед запуском без `--resume`.

## `<файл>.rejected.json`

Перед записью `run.py` прогоняет собранный каталог через гейт качества
(`tools/harvest/core/quality.py`). Если метрики хуже порогов (слишком много
мусорных брендов / невалидных ИНН / характеристик-заглушек "Параметр N" /
строк без цены и без ссылки, либо каталог не проходит схему `format.py`) —
результат пишется в `<файл с заменой .json на .rejected.json>`, а не под
основным именем, и в консоль печатаются причины. Файл `.rejected.json` —
сигнал остановиться и разобраться в парсере магазина, а не загружать его как
есть. После исправления парсера — удалить `.rejected.json` и повторить сбор
(с `--resume`, если чекпоинт ещё актуален, или с нуля).

## Структура

```
tools/harvest/
  core/
    gala_contracts.py  — единственный импорт format.py/stores.py/manufacturer_quality.py
                          из backend/app без тяги БД
    http.py            — HttpClient: троттлинг по домену, backoff, журнал отказов
    checkpoint.py       — jsonl чекпоинт для --resume
    gala_writer.py      — resolve_manufacturer(), build_item() без значений по умолчанию
    quality.py           — quality_report()/write_catalog() — гейт перед записью файла
    runner.py            — общий цикл обхода разделов/товаров (StoreSpec)
  stores/
    kuvalda.py            — парсинг kuvalda.ru (JSON-LD раздела/товара, характеристики)
    regard.py             — парсинг regard.ru (JSON-LD раздела/товара, характеристики)
  tests/
    fixtures/             — сохранённые страницы (1 раздел + 2 товара на магазин)
    test_*.py
  run.py                  — CLI
```

## Добавление нового магазина

1. Создать `tools/harvest/stores/<store>.py` по шаблону `kuvalda.py`/`regard.py`:
   реализовать функции `page_url(category_url, page)`, `parse_category_page(html)`,
   `needs_product_visit(candidate)`, `parse_product_page(html, url)`,
   `build_item(candidate, enrichment, known_brands)` и собрать их в `StoreSpec`
   (`tools/harvest/core/runner.py`). `build_item` обязан вызывать
   `gala_writer.resolve_manufacturer()` для бренда и `gala_writer.seller_inn_for()`
   для ИНН — не писать свою версию этих правил (ПРАВИЛО №6).
2. Зарегистрировать `harvest()` нового модуля в `STORES` в `run.py`.
3. Скачать РОВНО 3 страницы (1 раздел + 2 товара) в `tools/harvest/tests/fixtures/`
   и написать `tools/harvest/tests/test_stores_<store>.py` по образцу существующих —
   без живых запросов в тестах, только парсинг сохранённых фикстур.
4. Прогнать `pytest -q tools/harvest/tests` перед первым реальным сбором.

Для переноса оставшихся ~10 магазинов (sima-land.ru, baucenter.ru, electro-mpo.ru,
vkusvill.ru, k-spasatel.ru, magazin01.ru, medtehno.ru, ice-age.ru, kns.ru, safe.ru,
promalper.com — все уже в справочнике `catalog_gala/stores.py`) — повторить шаги
1-4 для каждого, разметка страниц (JSON-LD/HTML-классы характеристик) у каждого
магазина своя и должна быть проверена на живых страницах перед написанием парсера.
