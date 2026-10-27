"""Общая логика сборщиков каталогов (ПРАВИЛО №5 — один файл, одна ответственность):

  - gala_contracts.py — импорт format.py/stores.py/manufacturer_quality.py
    из backend/app/services/catalog_gala без тяги БД (ЕДИНСТВЕННОЕ место).
  - http.py           — HTTP-клиент: троттлинг по домену, backoff, журнал отказов.
  - checkpoint.py      — возобновление сбора (jsonl чекпоинт).
  - gala_writer.py     — сборка item формата gala-catalog без значений по умолчанию.
  - quality.py         — гейт качества перед записью файла.
  - runner.py          — общий цикл обхода разделов/товаров магазина.
"""
