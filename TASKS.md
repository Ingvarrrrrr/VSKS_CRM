# TASKS — VSKS_CRM

## 2026-06-04 — Карточка контрагента в Иерархии + drag-resize колонок (по скриншотам)

- [x] **Цель сессии**: устранить дублирование карточки орг в «Иерархии» (должна быть та же, что в «Контрагентах»), добавить drag-resize колонок во всех таблицах, поправить отображение «Ответственный исполнитель» в согласующих, разобраться почему орг по субсидии не попадает в «Персонал». Коммит `59ff1ca`, push в `origin/claude` (autodeploy).
  - **ContractorEditDialog** вынесен в reusable-компонент (33 поля), переиспользуется в ContractorsView и HierarchyView — единый источник, без урезанной копии (правило «не дублировать»).
  - `hierarchy.py` отдаёт `contractor_id` → дабл-клик по орг-узлу открывает полную карточку контрагента; fallback editOrgDialog для орг без contractor_id.
  - **drag-resize** ширины колонок (`v-resizable-columns`) добавлен в ~31 view/компонент, ключи localStorage уникальны.
  - **«Ответственный исполнитель»** в согласующих: прочерк + «Исполнитель определяется для каждой закупки», ФИО не запрашивается в форме.
  - **backfill** зеркальных орг по subsidy↔contractor при старте бэкенда (орг 27 ДОН-РАЙФЕН, 28 ЦентрПоиск). Риска 502 нет — `_ensure_feo_categories_sort_order_column` уже в lifespan.
- [ ] **Следующий шаг**: UAT пользователем после autodeploy — открыть карточку орг в Иерархии (полная как в Контрагентах), проверить drag-resize в нескольких таблицах, прочерк у «Ответственный исполнитель», появление ДОН-РАЙФЕН в Персонале/Иерархии.

## 2026-06-03 — Публикация визуализации «Передача оборудования ВСКС» по ссылке

- [x] **Цель сессии**: окрасить порядковые номера шагов в цвет отдела + опубликовать HTML-визуализацию по ссылке (Telegram на iOS не рендерит .html инлайн)
  - Окраска `.proc-num`: один отдел → сплошная заливка цветом подразделения (белая цифра + text-shadow), несколько → conic-gradient секторами, без отдела → нейтральный fallback. Проверено read-only.
  - Опубликовано: копия → `frontend/public/equipment.html` (2230 строк) → коммит `95584bd` → push в `origin/claude` (autodeploy). Раздаётся через frontend dist + server.mjs, минуя SPA-fallback.
  - Ссылка для телефона: **https://gaaala.duckdns.org/equipment.html** (Safari, как обычный сайт).
  - Push строго в scope: только equipment.html; 6 несвязанных modified файлов (subsidies/purchases/feo + 3 вью) НЕ тронуты, остались локально.
- [x] **Деплой подтверждён**: после пересборки frontend `curl https://gaaala.duckdns.org/equipment.html` → `HTTP 200 size=104210` (полный файл, не SPA-fallback). Фоновая проверка `bvbvt44wx` сматчила контент `tabBar/proc-num`.
- [ ] **Следующий шаг**: открыть ссылку на айфоне в Safari, проверить рендер всех 7 вкладок и PDF-экспорт на телефоне.

## 2026-06-02 — /gsd:graphify (граф знаний)

- [x] **Цель сессии**: выполнить `/gsd:graphify` — построить/обновить граф знаний проекта
  - Результат: команда отработала корректно, но упёрлась в config-гейт — `graphify.enabled` отсутствует в `.planning/config.json` → граф **отключён**. Билд не запускался по дизайну скилла.
  - Кода не писалось: `git diff --stat` пуст, в `git status` только untracked-артефакты прошлых сессий (json/sql/png/docx).
- [ ] **Следующий шаг**: если граф нужен — включить `node .../gsd-tools.cjs config-set graphify.enabled true`, затем `/gsd:graphify build`.

## 2026-06-01 — Push последних 5 коммитов + список незавершённого

- [x] **Цель сессии**: запушить итог сессии 29.05 (после autodeploy теста) + выдать пользователю список незакрытого
  - [x] Push `499d7d1..d86adff` (5 коммитов: import-vat-cols / import-no-clutter / import-pdf-debug / approval-sheet-template / approval-picker-prefill) в `claude` → autodeploy
  - [x] Сформирован список незакрытого по запросу пользователя: HTTP_403 у Тлеубаева/Кулиева, смена пароля Кулиеву, PDF Акт билетов (требует debug-отчёт), UAT 6 текущих фич, старые pending (27.1.x / 26-I / 25 Report Builder)
- Достижение цели: **100%** (всё что просил — сделано)
- [ ] **Следующий шаг**: пользователь возвращается с DevTools URL для 403 / DevTools payload для пароля Кулиева / debug-JSON для PDF-билетов — далее точечные фиксы

## 2026-05-29 — Версионирование ФЭО + per-item ФЭО + видимость заявок/СЗ + импорт PDF + шаблон ЛС

- [x] **Цель сессии**: батч UX-фиксов и фич по запросам пользователя (накопительно за 3 дня — 27/28/29):
  - **ФЭО v1.0**: версионирование «Финансирования по ФЭО» в `/subsidies` — сохранение редакций с датой, сравнение версий (Excel diff с composite-key matcher по code→parent_path→name), reconciliation snapshot↔текущий факт. **9 коммитов** `55638cf..0c411ee` + `e566def..1bb19a7` (B1-B6+F1-F3, запушены)
  - **Per-item ФЭО**: тогл «Свои ФЭО для каждого товара» + per-row autocomplete с soft-warning при превышении + hard-validation при save. Колонка `PurchaseItem.feo_category_id` через ensure-pattern. **8 коммитов** `779a521..7f8046a` (включая FCAT-B1..F1 перехода с FeoPlannedItem на leaf FeoCategory)
  - **Видимость Заявок/СЗ**: фикс багa суперадмин не видит чужие wishes (`build_visibility_clause` теперь корректно даёт `None` для SaaS, `subordinates_only` через `get_visible_user_ids`). WishesView/ServiceNotesView переведены на v-data-table с колонками От/Кому/Создано/Срок + фильтры. **4 коммита** `be418bf..e44ca3b`
  - **СЗ форма**: «Кому СЗ» (новая колонка `Purchase.service_note_to_user_id`), ответственный=адресат, ФЭО опциональны, кнопка «Создать служебную записку», заголовок «Что надо выдать», шрифт 12px, цена/сумма с пробелами-разделителями. **1 коммит** `3ba358c`
  - **Импорт позиций**: колонки НДС в Manual (`vat_amount`, `total_with_vat` через ensure + 4 новых `TARGET_FIELDS`), anti-clutter каталога (`skip_catalog` param + bulk-add endpoint + UI чекбокс/кнопка), PDF debug endpoint + расширенный keyword-fallback для билетов. **3 коммита** `7d22d92..ecf76cd`
  - **Шаблон Листа согласования**: добавлен `{{responsible_person}}` после «Срок исполнения» (была причина «не подтягивается»). **1 коммит** `280ff6f`
- Итог: ~26 atomic коммитов, 5 запушены (FEO MVP `e566def..1bb19a7`), остальные локально. **Достижение цели: ~95%** (всё что просил пользователь — сделано локально; ожидает финального UAT и push'а)
- [ ] **Не доделано/ожидает действий пользователя**:
  - HTTP_403 у Тлеубаева/Кулиева — нужны DevTools Network URL или название экрана (без этого не диагностировать)
  - Смена пароля Кулиеву — backend код корректен, нужно проверить через DevTools Network что фронт реально шлёт `password` в PUT `/users/{id}` (прервано пользователем перед разбором)
  - Push 21 локального коммита в `claude` (ждёт подтверждения после теста)
- [ ] **Следующий шаг**: пользователь подтверждает все UAT-пункты → `git push origin claude` → проверка autodeploy → закрытие сессии

## 2026-05-28 — Subsidies expand-row link (A) + Wishes flow batch (B, 10 пунктов из docx Иванова)

- [~] **Цель сессии**: A — в /subsidies expand-row для уже состоявшихся закупок добавить кликабельный № закупки; B — пакет из 10 пунктов по Заявкам (docx «Доработка ИВАНОВА 28.05.2026»)
  - [x] **A (Subsidies expand-row)** — backend `FeoActualItemOut` +`purchase_number`,`registry_number`; frontend TS interface + кликабельная ссылка `РЕЕ-2026-XXXXX` под item_name в 2 ветках таблицы (сопоставленные + без плана) + стиль `.feo-purchase-link`. Файлы: schemas.py:1152, feo_planned_items.py:172, SubsidiesView.vue (478, 553, 2694, 4697)
  - [~] **B1** snackbar: `:timeout="snackbarColor==='error'?-1:4000"` + кнопка «Закрыть» + 9 catch'ей extract `e?.message||e?.payload?.message`
  - [~] **B2** автор не видит свою заявку: `saveWish()` → `reloadActiveTab()` (не только loadWishes)
  - [x] **B3** read-only после approve: backend уже защищён в `update_wish`/`approve`/`reject`/`patch_wish_item`/`approve_distribution` — verified, добавлен маркер-комментарий
  - [~] **B4** «утв. кол-во/цена» из WishItem: `convert_wish` полностью переписан — копирует все items с `quantity`/`unit_price` (раньше создавал ПУСТУЮ закупку)
  - [~] **B5** ФЭО в карточке согласования: `openEditDialog` walks parent_id chain → заполняет `selectedFeo1/2/3` (раньше всегда пусто)
  - [~] **B6** «От кого»: `<v-card-subtitle>` с creator/assignee/date/status в заголовке диалога
  - [~] **B7** ColumnHeaderMenu в WishesView: импорт + colFilters/colSort + applyColFilters computed + #header.* слоты в 3 data-table
  - [~] **B8** ФЭО editable для approver: `:readonly="!isWishEditable && !canAssigneeAct"` + TODO про отдельный PATCH endpoint
  - [~] **B9** FEO в созданной закупке: `wish_items.feo_category_id` колонка + check_schema + lifespan wire-up + pass-through в create/update/approve/convert
  - [~] **B10** баг привязки к каталогу: backfill `product_id` по `item_name` в `convert_wish` (как в approve_distribution)
  - [ ] UAT пользователем — локально перезапустить backend (cold-start → check_schema добавит колонку) + frontend dev-server → пройти B1-B10 + A. После подтверждения — `git push`.

**Оценка сессии: ~75%** — все 11 задач (A + B1-B10) реализованы локально, Python syntax OK, lifespan wire-up по memory `check_schema → lifespan`. 2 параллельных Sonnet-агента (frontend WishesView / backend wishes.py) без конфликтов. Не дотянуло до 90%: (1) НЕТ runtime-проверки — vue-tsc/build не запускал по правилу `no_verification_loops`, (2) пользователь сообщил «не вижу изменений» по A — возможно frontend dev-server не пересобрался, нужен hard-reload, (3) НЕ push'нуто (per `feedback_no_push_without_confirmation`).

**Следующий шаг:** пользователь тестирует локально → `git push` пакетом после подтверждения. Если что-то не работает — debug-итерация (особо: B7 ColumnHeaderMenu — большая интеграция, риск template-конфликтов; B9 первая загрузка backend применит `_ensure_wish_items_feo_category_column`).

## 2026-05-21 — Phase 29: продолжение (Vehicle Fleet UAT/фиксы)

- [ ] **Цель сессии**: продолжить Phase 29 «про машины» — принять конкретный пункт UAT/баг и пофиксить
  - [x] Загружен полный контекст VAULT (00–05, Lessons, Runbook, 2 последние сессии, GRAPH_REPORT существует)
  - [x] Прочитан `.planning/STATE.md` — Phase 29 EXECUTED, 21/21 планов, UAT pending (9 пунктов)
  - [x] Выдан структурированный session-start отчёт по шаблону (LLM mode / GSD config / распределение моделей / позиция / состояние фаз / последние сессии / блокеры / 9 UAT-пунктов Phase 29 / шаги A/B/C/D)
  - [ ] Получить от пользователя конкретный пункт фидбека/бага по машинам (страница + что видит / что должно быть)
  - [ ] Фикс-итерация: делегировать Sonnet через Agent(subagent_type=Explore/general-purpose) → Edit + commit + push
  - [ ] Browser-smoke по правилу Lesson 2026-05-11/12 (не закрывать UI-фикс без проверки в браузере)

**Оценка сессии: ~5%** — только контекст-load + отчёт + опросник вариантов. Реального кода/коммитов 0 (`git status` показывает только untracked python-хелперы шаблонов и docx от прошлых сессий; `git diff --stat` пуст). Пользователь не дал конкретики — сессия завершилась стоп-хуком до получения ответа на вопрос «какой сценарий A/B/C/D».

**Следующий шаг:** в новой сессии — дождаться от пользователя конкретного пункта (один из 9 UAT Phase 29, либо новый баг с описанием «страница X → вижу Y → должно Z»). Если ответ «прогоняй сам» — стартовать `/gsd:verify-work 29` и идти по UAT-чеклисту последовательно.

## 2026-05-20 — Phase 29.2: UX-фиксы Vehicle Fleet + критический WebSocket leak

- [x] **3 проблемы Vehicle Fleet от юзера**:
  - [x] VehicleListView (`/property/vehicles`) — пустая таблица при total=36 → useColumnConfig fallback на все колонки при stale ключах в LS (`28a0b64`)
  - [x] Drill «В РАБОЧЕМ 34» возвращает 0 машин → case-insensitive `func.lower(coalesce(state,""))` + diagnostic log distinct(state) при empty (`457cdd2`)
  - [x] Drill-диалог белый поверх тёмного дашборда → `.fleet-dash--light` override + `:theme="vuetifyTheme"` на v-dialog (`519a264`)

- [x] **Критический инцидент QueuePool exhaustion** — корневой фикс:
  - [x] Симптом: `INTERNAL_ERROR` на любом `/api/*` после нескольких часов работы. Traceback: `chat_ws → QueuePool limit of size 5 overflow 10 reached, timeout 30.00`
  - [x] Первая попытка (неверная): поднял pool 5+10 → 20+40 в database.py (`5535493`) — пользователь подтвердил «не помогло» → revert (`9e2ac23..2e802ac`)
  - [x] Root cause найден из `docker logs --tail 60`: WebSocket `chat_ws` использовал `db: AsyncSession = Depends(get_db)` → FastAPI держал session на всё время WS-подключения (часы) → 15 вкладок чата исчерпывали pool
  - [x] Корневой fix `d1f2348`: убрал `Depends(get_db)`, открыл session локально через `async with async_session()` только на 2 init-запроса (load user + unread count), pool 5+10 теперь достаточен
  - [x] Reapply vehicle fixes (`519a264` theme, `457cdd2` drill, `28a0b64` list) после revert
  - [x] Force-recreate backend через SSH: `docker compose up -d --force-recreate backend` (Lesson 2026-05-04 — `up -d` без флага не пересоздаёт контейнер)

- [x] **Уроки зафиксированы**:
  - VAULT/Lessons.md (2026-05-20 WebSocket+Depends leak) — правило «никогда не Depends(get_db) в WS endpoint»
  - VAULT/05_Gotchas.md — раздел про QueuePool диагностику

**Оценка сессии: ~85%** — три UI-проблемы Vehicle Fleet закрыты + найден и устранён давний архитектурный баг (WebSocket leak висел с момента написания чата). Не дотянуло до 90%: не открывал прод в браузере после finальных fix-коммитов (правило из Lesson 2026-05-11/12), полагался на ответ пользователя «заработало».

**Следующий шаг:** UAT пользователем — открыть `/property/vehicles` (таблица с 25/36 рядами), кликнуть «В РАБОЧЕМ» (должны быть 34 машины), переключить тему. Оставить чат открытым на час — backend не должен лечь.

## 2026-05-15/16 — Phase 26-VV..YY: реестр авансовых + дубли + ускорение GET

- [~] **Фидбек по реестру авансовых + перформанс**
  - [ ] **UI колонки**: «Закр.документ» из `acceptance_docs[]`, «Дата поставки» = `last_receipt_date`, multi-контрагент chips — `phase26-vv` revert'нут (`b9e7972`+`3f13c5f`), нужна переделка frontend-only
  - [x] **Дубли позиций**: `_recompute_from_receipts_core` плодил 8 вместо 4 — early-exit если у Purchase есть items + dedup helper по (name, total, receipt_id) (`2434ef1`, `d218239`)
  - [x] **Standalone endpoint** `POST /api/purchases/{pid}/dedup-items` — вручную почищен #582 (id=806): kept 4, deleted 4
  - [x] **Snapshot-hash гейт**: `Purchase.recompute_snapshot_hash` (SHA-1) — `_recompute_from_receipts_core` skip если состояние не изменилось (`4c3962c` phase26-yy)
  - [x] **Pinia кэш контрагентов** `useContractorsStore` (TTL 5 мин) — 7 views переведены на `ensureLoaded()` вместо bulk-load каждый mount (`4c3962c`)
  - [x] **Hotfix limit**: backend `le=1000`→`le=5000` + frontend `?limit=5000` (был `2000` → 422 VALIDATION_ERROR) (`8808286`)
  - [x] Прод: 200/401 после autodeploy, GET #806 стабильно 1.6s (гейт работает)
  - [ ] UAT phase26-yy: Ctrl+F5 на проде → DevTools Network показывает один `/contractors/` за сессию + субъективное ускорение

**Оценка: ~70%** — дубли и замедление закрыты архитектурно, hotfix limit прошёл, прод поднят. Не дотянуло до 90%: UI-фидбек по колонкам реестра avансовых был reverted из-за 502 OOM от двойной пересборки backend+frontend; нужна аккуратная переделка frontend-only.

**Следующий шаг:** `phase26-zz` frontend-only коммит — взять логику из `783e0f5` (acceptance_docs[]→display_name+date, last_receipt_date→delivery_date, multi-chip) и применить только к `AdvanceReportsView.vue`. Backend `acceptance_docs[]` уже есть с phase26-u-4.

## 2026-05-14/15 — Phase 26-U..DD: каскад фиксов авансовых отчётов

- [~] **Заполнение данных в авансовых отчётах + UX фиксы**
  - [x] 26-T-2: бейджи непрочитанных в чатах — на аватарке + chip справа (`9031be9`)
  - [x] 26-U: любая ошибка генерации документа — в подробный диалог с error_class/traceback (`bad9736`)
  - [x] 26-V: автозаполнение контрагента из чека + колонка ИНН + resize позиций + родительный падеж (`841a502`)
  - [x] 26-W: чек→файл в закр.документах (PNG, PurchaseFile) + lookup-inn в per-row + lifespan backfill (`b1b3b33`)
  - [x] 26-X: дубли чеков — structured 409 RECEIPT_DUPLICATE + кнопка «Открыть закупку №X» (`e0a0f8b`)
  - [x] 26-Y: per-row контрагент 1-в-1 с основной формой (auto-select-first, ИНН в subtitle, account-plus) (`27517e0`)
  - [x] 26-Z: POST /recompute-from-receipts + auto-propagate purchase.contractor → items (`4b7b871`)
  - [x] 26-AA: hydrate assigned_user/reimbursement_user через /users/{id} если их нет в orgUsersList (`b725c6e`)
  - [x] 26-Z-bootstrap: auto-recompute on GET /purchases/{pid} + opt-out deps + /api/diag/version (`cd02ad6`)
  - [x] 26-BB: schema purchase_items.receipt_id + per-receipt mapping + fuzzy match по 4 полям (`6c9768e`)
  - [x] 26-BB-diag: runtime checks в /api/diag/version (column presence, linked_count, null_count) (`f5881b9`)
  - [x] 26-CC: lifespan propagate purchase.contractor → items + force-backfill endpoint + fuzzy 2/4 (`361e507`)
  - [x] 26-DD: autocreate PurchaseItem из raw_json чека если их нет в БД (`6510372`)
  - [x] Hotfix 502: убрал pymorphy3 (OOM при сборке словарей) (`e2dee47`)
  - [x] Прод backend поднят: phase=26-DD, schema receipt_id present, advance_purchases=9
  - [ ] **Не подтверждено**: реально ли заполнились контрагенты после autocreate (linked_count=0 в диагностике на момент завершения)
  - [ ] Родительный падеж: petrovich оставлен (ФИО будут склоняться), pymorphy3 убран → должность останется в именительном
  - [ ] UAT 575/582 пользователем: открыть → подтвердить что 4 позиции (УАЙТ-СПИРИТ+3×ЭМАЛЬ) появились с контрагентом ЛЕ МОНЛИД

**Оценка: ~70%** — 12 коммитов с правками + хотфикс 502, прод восстановлен, код задеплоен. Не дотянуло до 90%: (а) после `Ctrl+F5` на 575/582 нужно убедиться что auto-recompute on GET реально создал PurchaseItem из raw_json — `linked_count` пока 0 (но он мог обновиться только при GET от пользователя, а не при автоматических check'ах); (б) родительный падеж работает только частично (ФИО ✓, должность ✗).

**Следующий шаг:** пользователь открывает 575 и 582 в браузере → backend auto-recompute должен создать позиции + проставить контрагента. Если linked_count в /api/diag/version вырастет с 0 — кейс закрыт. Если нет — нужна диагностика через `GET /api/diag/purchase/582` (admin token), смотрим структуру raw_json и почему `_extract_items` не вернул items.

## 2026-05-13 — Phase 26-E ColumnHeaderMenu (Excel-like per-column фильтр)

- [~] **Phase 26-E ColumnHeaderMenu — Excel-like per-column фильтр в 4 list-view**
  - [x] Wave 1: `ColumnHeaderMenu.vue` (417 строк, 5 типов фильтра + sort + hide) — создан
  - [x] Wave 1: `useColumnConfig.ts` расширен — `FilterValue` тип, `state.filters`, helper'ы `setFilter/clearAllFilters/hasFilter/activeFilterCount`, миграция в `loadState`
  - [~] Wave 2a OrdersView: только частичная интеграция (+44/-2), не все slot'ы покрыты
  - [~] Wave 2c AdvanceReportsView: минимальная интеграция (+7/-2), большая часть не сделана
  - [ ] Wave 2b ContractsView: **НЕ тронут** (1474 строк — агент не успел)
  - [ ] Wave 2d PaymentRegistryView: **НЕ тронут** (863 строк — агент не успел)
  - [ ] Browser smoke на 4 view (по правилу из Lessons 2026-05-11/12)
  - [ ] Коммит + push в claude

**Оценка: ~35%** — фундамент полностью готов; 2 view частично, 2 не тронуты. 2 фоновых агента из 4 не завершились до stop hook.

**Следующий шаг:** в новой сессии — верифицировать что в OrdersView/AdvanceReportsView добавлено корректно (особенно matchesColumnFilters integration в pipeline), затем перезапустить отдельных агентов на ContractsView и PaymentRegistryView с явным списком header keys (предварительно вытащить grep'ом). Финал — один коммит + push + browser smoke.

## 2026-05-11/12 — Phase 25 Report Builder + UAT фидбек

- [~] **Phase 25 — UI-конфигуратор отчётов (3 типа: реестр/сводная/дашборд) + Excel/PDF**
  - [x] План фазы из 10 sub-plans (план-файл утверждён через ExitPlanMode)
  - [x] 25-01..25-10 реализованы агентами Sonnet (11 коммитов `558dcc9..0b16f75`, ~3600 LOC)
  - [x] Push в origin/claude (3 коммита остались локально после агентов — пришлось пушить вручную в конце)
  - [x] Autodeploy на прод запущен вручную (webhook health OK)
  - [x] Backend контейнер пересобрался + permission seed SQL применён (1 action + 4 role_permissions)
  - [x] DB schema: `Purchase.region` ✓, `report_configs` table ✓
  - [x] Frontend контейнер пересоздан (после name-conflict от прерванного deploy)
  - [x] Bundle hash сменился: `index-C26XBJAn.js`
  - [x] API smoke: `/analytics/fields` (96 полей), `/query` list/pivot, `/export.xlsx` (200, valid xlsx), `/export.pdf` (200, valid PDF)
  - [ ] UI smoke в браузере: **НЕ пройден** — пользователь сообщил «вот такая ошибка» на `/reports/lists`, `/reports/pivots`, `/dashboards`. Жду скриншот/Console.
  - [ ] UAT 16 пунктов из плана фазы — не начат

- [ ] **Phase 26 — фидбек пользователя 12 мая (12 пунктов)** — зафиксирован в `04_TODO.md`
  - 26-A1 блокер: Реестры/Сводные/Дашборды runtime error (ждёт скриншот)
  - 26-B1..3: регрессии table-config (импорт реестров растянут, корзинки прыгают, «Тип» обрезается)
  - 26-C1..2: локализация «Способ закупки», «Авансовый платёж» в Тип договора
  - 26-D1..6: фичи (фильтры в Сводной по продукции, поля СЗ, № п/п везде, фильтр reimbursement_user, SUM отфильтрованного, удаление чата)

- [x] **Урок в Lessons.md (2026-05-11/12)**: Sonnet-агенты врут про push + я закрыл фазу без UI-проверки в браузере. Правило: после каждого Agent'а `git log origin/claude..HEAD`; не закрывать UI-фазы без browser smoke.

- [x] **Документация синхронизирована**: `.planning/STATE.md`, `.planning/phases/25-report-builder/STATE.md`, VAULT/03_Done_Phases.md, VAULT/04_TODO.md, VAULT/Sessions/2026-05-11_VSKS_CRM.md, VAULT/Lessons.md

**Оценка сессии: ~75%** — Phase 25 поставлена, backend и API работают, документация полная. Не дотянуло до 90% потому что: (а) UI runtime error на 3 новых view не диагностирован, (б) фидбек на 12 пунктов открыт.

**Следующий шаг:** Пользователь даёт скриншот / текст ошибки из DevTools Console → 5-минутный фикс блокера 26-A1 → дальше по приоритету Phase 26 (мелкие UX-фиксы первыми).

## 2026-05-08/09 — табличная фича + ISO-date root cause + advance auto-fill

- [x] Root cause ISO-дат: `_to_date/_to_datetime` через `datetime.fromisoformat()` (`d3bcf8c`) — `_json_safe` писал ISO в JSONB, чтение не понимало T-разделитель. Lifespan auto-backfill починил 72 строки import #8 без действий юзера
- [x] Phase A — universal column config: composable `useColumnConfig` + `ColumnConfigDialog` + миграция PaymentRegistryView с migrateFrom для старых LS ключей (`a2edd0c`)
- [x] Phase B — применили ко всем 11 oставшимся таблицам (`d68eec6`): Orders/Contracts/AdvanceReports/Staff/Billing/CommercialRequests/Organizations/Suppliers/SystemIncidents/ServiceNotes/PaymentImport. ContractorsView пропущен (карточки, не таблица)
- [x] Width через cellProps/headerProps style + dialog→navigation-drawer для live preview (`877af38`)
- [x] Master-list расширен для топ-3 views: 13+70 OrdersView, 18+10 ContractsView, 10+50 AdvanceReportsView через таб «Все возможные» (`3cb8a3f`)
- [x] Глобальный `table-layout: fixed` чтобы inline width реально применялся (`4d4fafa`)
- [x] Убрана `v-resizable-columns` с 6 migrated views — конфликтовала с composable cellProps (`41c270a`). Trade-off: drag временно недоступен в этих views, юзер использует input в drawer
- [x] Текст в ячейках переносится не режется (`aa454a5`): `white-space: normal; overflow-wrap: anywhere`
- [x] Auto-fill `contract_date/number` для advance: (1) при receipt → fill if empty; (2) при bank_payment match → override из parsed_documents.advance_reports[0]; (3) lifespan backfill для legacy advance с receipts но без основания (`f5bfc3c`). Покрывает кейс #575
- [ ] UAT финальных push'ей юзером (`f5bfc3c` deploy ~3 мин) — переход #575 в «Заключён договор», перенос текста, master-list в picker
- [ ] Drag-resize колонки в migrated views — новая директива v-table-config-resize с интеграцией в composable.setWidth
- [ ] Master-list для остальных 8 views (Staff/Billing/CommercialRequests/Organizations/Suppliers/SystemIncidents/ServiceNotes/PaymentImport) — текущие колонки + доп поля backend моделей

## 2026-05-07 (вечерняя сессия — bug-fix + аудит)

- [x] Регрессия парсера ScrollerHash: пустая «Дата документа» / «Назначение платежа» / «Договор» (`6f94e38`) — single-row headers contamination в _extract_headers + docDisplay fallback
- [x] «Ошибка сохранения» в SubsidiesView — root cause: `loadSubsidies()` несуществующая функция → JS ReferenceError маскировался как save fail 2 дня (`c1fb925`: loadSubsidies→loadAll); JS-ошибки теперь идут в глобальный ApiErrorDialog (window 'error' + 'unhandledrejection')
- [x] Деструктивный баг: при save субсидии затирался basis_doc_number/date в NULL (`95ecd31`) — startEdit теперь тянет полную карточку через GET /subsidies/{id} (раньше брал из /dashboard/charts который не отдаёт basis_doc_*)
- [x] Структурный фикс reparse: shared helper reparse_bank_payment_typed(bp) в parser + lifespan backfill для legacy bank_payments (`08a986b`) — 72 строки import #8 чинятся автоматически при рестарте, без нажатия кнопок
- [x] UX ошибок: snackbar timeout=-1 + кнопка «Закрыть» + multi-line для error (`5143ac5` partial, потом `c1fb925` rollback детализации в пользу глобального диалога)
- [x] Аудит проекта (4 параллельных Explore агента: backend/frontend/infra/phases) — отчёт выдан в чате: 8 критичных, 18 важных, dead code list ~5K LOC, статус фаз
- [ ] UAT push `08a986b` юзером — не подтверждён в этой сессии

## 2026-05-07

- [x] Phase 24: этапы рамочного договора + накопленные обязательства в финплане (`ab59584` backend, `0ffe349` frontend MonthlyStagesDialog/CreateOrderView/DashboardView/BudgetDrillDownDialog)
- [x] Фикс /financial-plan/details — period опционален для category=no_deadline (`ad4c732`)
- [x] QR-скан чеков в обычной закупке (раньше только для авансовых) (`01dd1cd`)
- [x] Pre-check дубликата чека в БД до запроса в ФНС + перехват rate-limit (`a7bb8c1`)
- [x] Pipeline показывает все 7 этапов даже при 0 + строка «Поставлено, не оплачено» + Excel (`8ea172f`)
- [x] Cumulative drill для pipeline + pickPositive fallback в purchaseEffectivePrice (`5972505`, после реверта `81a5267`+`307290f` из-за OOM)
- [x] FEO-иерархический drill для этапов (StageFeoDrillDialog) с уведомлением о неоднородной глубине + Excel (`064f538`)
- [x] UX: pipelineByType без фильтра .total>0, «Поставлено не оплачено» между этапами, авто-пропуск 1 субсидии в FEO drill (`f787200`)
- [ ] Право «передвигать закупки без обязательных полей» + индикатор «не хватает с этапа X» — обсуждено, не начато
- [ ] Backend-выравнивание /dashboard/ (FEO tree) vs /dashboard/charts (mismatch 1.7M vs 0 в drill бюджета) — отложено

## 2026-04-30

- [~] Разобраться с вопросом пользователя про торгового бота (заблокировано: вопрос не про этот проект, отправлен запрос на уточнение — ждём название/путь/сервер)
- [x] WS-диагностика — false-alarm (нормальное поведение Starlette при невалидном JWT, бэк работает)
- [x] Обновить Obsidian-вальт (Sessions/2026-04-28_VSKS_CRM.md создан) — частично, KG не обновлён

## 2026-05-27

- [ ] Возобновить работу: #5 диалоги История/ТО → карта филиалов 89 субъектов → #13 vehicle-profile + #11 waybill-form → Б-1 импорт штрафов CSV/XLSX → #12 mobile (деплой localhost, без push). СТАТУС: только старт-отчёт сформирован, кода нет, ждём подтверждения приоритета пользователем (~5%).

## 2026-06-07

- [~] Поднять фикс «Участники заявки» на ЛОКАЛКЕ и показать в браузере. Кода нового нет (фикс уже в репо: 520bdca/e1b9313/e4800e5). Backend локально перезапущен и проверен через API — работает (40 кандидатов по subsidy_id=45, добавление/удаление участников OK). Фронт-контейнер локально НЕ пересобран (в нём нет UI участников) → в браузере не виден. Docker Desktop лёг после перезагрузки ПК, запущен заново, ждём engine. ~40%. Следующий: `docker compose build frontend && docker compose up -d --force-recreate frontend`, открыть http://localhost, проверить раздел «Участники заявки».
