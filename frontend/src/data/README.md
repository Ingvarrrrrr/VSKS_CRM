Генерируется из `backend/app/data/ru_regions.json` скриптом `frontend/scripts/sync-ru-regions.mjs`.
Руками не править — правки перезатрёт `npm run sync:regions` / `prebuild`.

`dictionaries.json` — генерируется из `backend/app/services/dictionaries.py` +
`backend/app/routers/purchases.py` (STATUS_ORDER) + `backend/app/startup/permission_seeds.py`
скриптом `python backend/scripts/export_dictionaries.py` (`--check` — в CI). Руками не
править — источник бэкенд (Правило №6).
