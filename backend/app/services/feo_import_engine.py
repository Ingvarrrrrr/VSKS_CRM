"""Фасад: ядро импорта ФЭО (`_do_feo_import`) переехало в feo_import_core.py.

Правило №5 (модульность): `_do_feo_import` — одна неделимая функция
(~1230 строк, единственный `def` в исходном модуле, без внутренних
вложенных функций-этапов) — состояние (cat_cache, collected_plan,
existing_cats, warnings и т.д.) переплетено общим циклом по строкам и
последующими фазами (снимок дерева, применение плана, отчёт
"несопоставленные узлы", переезд/удаление). Резать на отдельные файлы по
«разбор/матчинг/запись/превью» означало бы придумывать новые границы
функций, которых в оригинале не было — без возможности проверить
AST-эквивалентность (в отличие от feo_plan, где резались уже
существующие top-level функции). По прецеденту feo_plan_tree.py
(758 строк, тоже неделимая функция) оставлена целиком, но в СВОЁМ
модуле — feo_import_core.py; здесь остаётся только фасад-реэкспорт.

Явный список ре-экспорта (dir() фасада не уже, чем был у исходного
модуля до переноса — там были не только `_do_feo_import`, но и его
собственные top-level импорты, которые оставлены как проекции для
обратной совместимости):
    Decimal, HTTPException, select, AsyncSession, FeoCategory,
    normalize_feo_name, fc, _do_feo_import

`app.routers.feo_import` импортирует `_do_feo_import` ИЗ ЭТОГО модуля на
уровне модуля (для /import, /import-mapped); `app.routers.feo_categories`
ре-экспортирует `_do_feo_import` лениво (PEP 562 `__getattr__`) по
строковому пути `"app.services.feo_import_engine"` — оба места продолжают
работать без изменений, т.к. имя остаётся здесь же (просто определено не
локально, а импортом).
"""
from app.services.feo_import_core import (
    AsyncSession,
    Decimal,
    FeoCategory,
    HTTPException,
    _do_feo_import,
    fc,
    normalize_feo_name,
    select,
)

__all__ = [
    "Decimal",
    "HTTPException",
    "select",
    "AsyncSession",
    "FeoCategory",
    "normalize_feo_name",
    "fc",
    "_do_feo_import",
]
