# Phase 29 — Plan Review

**Reviewer:** gsd-plan-checker (Opus 4.7, 1M context)
**Date:** 2026-05-19
**Verdict:** PASS WITH NOTES

## Summary

21 планов покрывают все 20 решений D-01..D-20, wave-структура корректна и ацикличная, паттерны из 29-PATTERNS.md мапятся на конкретные планы, риск-зоны (check_schema, smoke-render, _coerce_patch_value, FastAPI routing) явно вызваны в Gotchas. Найден 1 серьёзный пробел в плане 29-13 (Task.status SAEnum(TaskStatus), idempotency-WHERE содержит несуществующий enum planned и теряет TaskStatus.review). Остальные 6 WARNING мелкие. Фаза готова к выполнению.

## Per-plan scoring

| Plan | Goal | Files | Tasks | Deps | Risks | Verif | Total /12 | Verdict |
|------|------|-------|-------|------|-------|-------|-----------|---------|
| 29-01 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-02 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-03 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-04 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-05 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-06 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-07 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-08 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-09 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-10 | 2 | 2 | 2 | 2 | 2 | 1 | 11/12 | OK |
| 29-11 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-12 | 2 | 2 | 2 | 2 | 1 | 1 | 10/12 | OK |
| 29-13 | 2 | 2 | 1 | 2 | 1 | 1 | 9/12 | NOTE |
| 29-14 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-15 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-16 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-17 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-18 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-19 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-20 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |
| 29-21 | 2 | 2 | 2 | 2 | 2 | 2 | 12/12 | OK |

**Среднее:** 11.71/12. Все >= 9/12 — плохих планов нет.

## Cross-plan checks

- [PASS] **Decision coverage:** все 20 D-01..D-20 покрыты. Spot-check 5 случайных:
  - D-04 (can_drive): 29-01 (model), 29-02 (ALTER), 29-09 (PATCH whitelist), 29-15 (UI).
  - D-06 (visibility): 29-01, 29-04, 29-11, 29-12, 29-16.
  - D-13 (mileage UNIQUE + monotonic): 29-01, 29-02, 29-07, 29-18.
  - D-17 (alerts): 29-02, 29-10, 29-13.
  - D-20 (fuel summer/winter): 29-01, 29-07.

- [PASS] **Wave acyclic:** граф зависимостей валидный.
  - W0: 29-01 -> 29-02 -> 29-03
  - W1: 29-04..29-10 depend on (29-02, 29-03)
  - W1.5: 29-11 -> 29-02; 29-12 -> (29-04, 29-11); 29-13 -> 29-02
  - W2..W5 монотонны.

- [PASS] **File ownership unique (Create):**
  - 29 уникальных backend/frontend файлов, без двойного Create.
  - trip_*.docx: 29-08 (stubs) -> 29-20 (replace) — корректный hand-off через Modify.
  - VehicleListView/DetailView/Dashboard: Create stub в 29-14, Replace в 29-16/17/19.
  - Modify-overlap (backend/app/__init__.py) в 29-02..29-13 — все добавляют разные блоки.

- [PASS] **Verification feasibility** без docker/build/test:
  - 21/21 планов используют grep / git log / ls / wc -l / curl — executor-friendly.
  - 100% >= 80% target.

- [PASS] **Pattern reuse:** все 35 файлов из 29-PATTERNS.md Create list мапятся на планы.

- [PASS] **Boilerplate present:** все 21 планов содержат Executor boilerplate (no-verification-loops, git log check, dict-detail, pre-push grep let/const, smoke-render). Universal boilerplate в PLAN.md — 9 пунктов.

## Risk hot-spots

### 29-02 (check_schema)

- 9 новых таблиц + ALTER на purchases/users/tasks.
- vehicle_odometer: UNIQUE(vehicle_id, date) в DDL.
- trips: CHECK XOR constraint в DDL.
- 7 ALTER COLUMN для users (can_drive + 6 license_*/med).
- system_tag ALTER + partial index для tasks.
- Порядок зависимостей явно объявлен.

**Вердикт:** OK.

### 29-04 (vehicles router)

- _DATE_FIELDS = {registered_at, insurance_until} — корректно.
- _TRACKED_FIELDS_FOR_HISTORY — 15 полей.
- History hook: snapshot old_val до setattr — корректный порядок.
- flag_modified(vehicle, props) в Gotchas.
- _visibility_q использует or_(owner_org_id.in_, assigned_org_id.in_) — D-06.
- FastAPI routing: отдельные prefix /api/vehicle-attachments — самое чистое.

**Вердикт:** OK.

### 29-08 + 29-20 (trips + docx)

- 29-08: boot-time smoke-render блок в lifespan, цикл по 3 шаблонам, fake_ctx, DocxTemplate.render в try/except.
- Lesson 2026-05-15 (tr запрещён) явно цитируется в обоих планах.
- 29-20 в DoD: unzip -p ... | grep -c tr = 0.
- render endpoint в 29-08 ловит exception → возвращает error_class/error_raw/traceback/hint.

**Вердикт:** OK.

### 29-13 (lifespan cron) — WARNING

- Идемпотентность через Task.system_tag — формат [VEHICLE:{id}:OSAGO_EXPIRY].
- SYSTEM_USER_ID = 1 объявлена + Gotcha упоминает альтернативу.
- **WARNING:** план строит Task.status=todo как строку. backend/app/models/task.py:30 — status = Column(SAEnum(TaskStatus)). SQLAlchemy примет str, но в WHERE план указывает status.in_([todo, in_progress, planned]) — planned НЕ в TaskStatus enum (только todo/in_progress/review/done/cancelled). Запрос не упадёт, но при Task в review создастся дубль.
- **WARNING:** due_date = DateTime(timezone=True), не Date. План присваивает Date — SQLAlchemy auto-coerce, безопасно.
- Task.assigned_user_id Column есть (task.py:33), но UI обычно читает из TaskAssignee m2m. План пишет напрямую Task(assigned_user_id=u.id) — сработает на DB, но не создаст TaskAssignee.

**Вердикт:** WARNING. Не блокер.

### 29-19 (dashboard) — 11 widgets

- R-7 перечисляет 11 layout-items.
- 29-19 Task 1 объявляет DEFAULT_LAYOUT с 11 элементами.
- D-16 текстуально 8 виджетов, но перечисление даёт 11 (4 KPI + canister + repairs + maintenance + bar + line + donut + table). Defensible.
- localStorage key vehicle_dashboard_layout_u${userId} совпадает с R-7.
- clampScore-pattern для SVG в Gotchas (Lesson 2026-04-19).

**Вердикт:** OK.

### 29-11 (seed)

- ON CONFLICT (plate) DO NOTHING — соответствует R-5 (vin часто NULL).
- 29-02 устанавливает UNIQUE на plate в DDL.
- assigned_text mapping: row[7] -> assigned_text. owner_org_id с fallback на ВСКС id=1.
- TYPE_MAP, STATE_MAP, FUEL_MAP, bool_from_cell — всё явно прописано.
- xlsx файл существует по абсолютному пути.

**Вердикт:** OK.

## Concerns

### WARNING (фиксятся при выполнении):

**W1. План 29-13 — несуществующий enum value planned в idempotency WHERE**
- Severity: WARNING
- Plan: 29-13
- Описание: TaskStatus enum имеет todo/in_progress/review/done/cancelled. planned нет. Запрос не упадёт, но при Task в review создастся дубль.
- Fix: заменить planned на TaskStatus.review (либо использовать [TaskStatus.todo, TaskStatus.in_progress, TaskStatus.review]).

**W2. План 29-13 — TaskStatus используется как строки**
- Severity: WARNING
- Plan: 29-13
- Описание: Task.status = SAEnum(TaskStatus). Лучше быть явным: status=TaskStatus.todo.
- Fix: импортировать TaskStatus + использовать enum везде.

**W3. План 29-13 — TaskAssignee vs Task.assigned_user_id**
- Severity: WARNING (info)
- Plan: 29-13
- Описание: TaskAssignee — отдельная m2m таблица. UI может читать из assignees relationship.
- Fix: executor до выполнения 29-13 — grep как UI читает свои задачи. Если из TaskAssignee — добавить db.add(TaskAssignee(task=task, user_id=u.id)).

**W4. План 29-10 (dashboard) — verification слаб**
- Severity: WARNING
- Plan: 29-10
- Описание: grep -c @router. = 8+ не подтверждает форму данных. Curl smoke только на 2 endpoint.
- Fix: добавить в DoD curl каждый из 8 endpoint.

**W5. План 29-12 — in-memory sessions при autodeploy сбрасываются**
- Severity: WARNING
- Plan: 29-12
- Описание: in-memory _IMPORT_SESSIONS теряется при каждом autodeploy.
- Fix: добавить warning в UI диалог импорта.

**W6. План 29-19 — 8 vs 11 widgets интерпретация**
- Severity: WARNING (scope clarification)
- Plan: 29-19
- Описание: D-16 текст 8 виджетов. План + R-7 — 11. Defensible.
- Fix: подтвердить с пользователем интерпретацию.

**W7. План 29-18 — может выйти за context budget**
- Severity: WARNING
- Plan: 29-18
- Описание: 8 tab-компонентов ~1500 LOC. План это acknowledgeит.
- Fix: executor разбить на 2 коммита если context >40%.

### BLOCKERS
Нет.

## Recommendation

**PASS WITH NOTES** — фаза готова к /gsd:execute-phase 29.

Notes — баклог:
1. **W1+W2+W3 (29-13):** ДО выполнения 29-13 — открыть backend/app/models/task.py, использовать TaskStatus.todo вместо строк, убрать несуществующий planned, проверить TaskAssignee.
2. **W4 (29-10):** добавить 6 curl smoke verifications в DoD.
3. **W5 (29-12):** warning в UI диалог импорта.
4. **W6 (29-19):** подтвердить с пользователем 11 vs 8 widgets.
5. **W7 (29-18):** разбить на 2 коммита если context >40%.

Все 7 WARNING — не блокеры. Ни одного BLOCKER не обнаружено.

## Дополнительные замечания (info)

- **CLAUDE.md/Lessons.md compliance:** все 21 плана используют абсолютные Windows-пути, упоминают memory rules, явно цитируют Lessons.md (tr 2026-05-15, smoke-render 2026-05-18, dict-detail 2026-05-04, duplicate let/const 2026-05-05, clampScore 2026-04-19). Compliance отличная.
- **Universal boilerplate** в PLAN.md — 9 пунктов.
- **PATTERNS.md coverage:** 35/45 паттернов имеют аналоги, 3 NEW (SVG canister, pulse-glow, daily cron) распланированы.
- **xlsx файл verifiable** существует по абсолютному пути.
- **Backend 502 window** между 29-01 и 29-02 явно прописан в обоих планах.

---

**Готово к выполнению.** Запустить /gsd:execute-phase 29 с balanced profile.
