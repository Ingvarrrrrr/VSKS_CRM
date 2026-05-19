# Phase 29: Vehicle Fleet — Discussion Log

**Date:** 2026-05-19
**Mode:** default (4 AskUserQuestion batches, 4 questions each = 16 decisions + 4 pre-locked from initial AskUserQuestion = 20 total)
**Status:** Complete

---

## Pre-locked decisions (from initial AskUserQuestion before /gsd:discuss-phase)

User triggered `/gsd:plan-phase` for a brand-new vehicle fleet module. Claude redirected to `/gsd:discuss-phase 29` via 4-question opener AskUserQuestion (memory rule `feedback_use_askuserquestion`):

| Question | Options presented | User pick | D-num |
|---|---|---|---|
| Как запускаем Phase 29? | discuss→plan / plan-phase сразу / 2 подфазы | **discuss-phase → plan** (Recommended) | D-01 |
| Где живёт раздел «Имущество»? | Новая вкладка AppBar / прямая `Автотранспорт` / в карточке организации | **Новая вкладка AppBar «Имущество»** (Recommended) | D-02 |
| Глубина учёта топлива и путёвок? | Полный учёт / только путёвки+пробег / MVP без топлива | **Полный учёт** (Recommended) | D-03 |
| Водители — кто и откуда? | User.can_drive flag / отдельный Driver / привязка только при путёвке | **User.can_drive flag** (Recommended) | D-04 |

---

## Batch 1 — Permissions / Visibility / Storage / Schema

Domain probe: «Что-то для УЧЁТА» — модель + storage + multi-tenancy + permissions критичны.

| Question | Options presented | User pick | D-num | Notes |
|---|---|---|---|---|
| Кто видит и редактирует `/property/vehicles`? | tab `vehicles` + actions / всем authenticated / только admin | **tab + actions, default-матрица** (Recommended) | D-05 | Через Phase 17 матрицу. Actions: vehicle.edit/delete/import/odometer.write/repair.write/trip.create |
| Visibility ТС по орг? | owner + assigned / все всё видят / строго owner_org | **owner_org + assigned_org** (Recommended) | D-06 | Сотрудник видит ТС если owner ИЛИ assigned в его org_ids |
| Где хранить фото/сканы? | bytea / filesystem / гибрид | **PostgreSQL bytea** (Recommended) | D-07 | Паттерн Phase 3 PurchaseFile, SHA-256 dedup |
| Как хранить 24 поля состояния? | смешанно ENUM+text+JSONB / всё колонки / только JSONB | **Смешанно ENUM + текст + JSONB props** (Recommended) | D-08 | Канонические колонки + bool слоты + JSONB для редко меняющихся |

---

## Batch 2 — Import / Field history / Document slots / Repairs

| Question | Options presented | User pick | D-num | Notes |
|---|---|---|---|---|
| Импорт 51 ТС из xlsx? | seed + UI / только UI / ручной ввод | **Seed при старте + UI Excel** (Recommended) | D-09 | Idempotent по (vin, plate). Paттерн OrdersView import dialog |
| Облачка-комментарии — история полей? | VehicleFieldHistory таблица / JSONB / только общий коммент | **VehicleFieldHistory** (Recommended) | D-10 | Авто-запись при PATCH. UI: popover с timeline |
| Слоты документов ТС? | типизированные + Прочее / свободные типы / только 3 (VIN/СТС/ПТС) | **Типизированные + «Прочее»** (Recommended) | D-11 | СТС, ПТС, ОСАГО, КАСКО, ДК, Разрешение ТО, Прочее. Доп. поля даты для ОСАГО/КАСКО/ДК |
| Ремонты — отдельная сущность? | VehicleRepair + RepairAttachment / variant of VehicleAttachment / только Purchase 28-05 | **VehicleRepair + RepairAttachment** (Recommended) | D-12 | Отдельная таб «Ремонты» в карточке. status enum + связь с Purchase см. D-18 |

---

## Batch 3 — Mileage / Trip docs / External drivers / Dashboard

| Question | Options presented | User pick | D-num | Notes |
|---|---|---|---|---|
| Ежедневный пробег — формат ввода? | абсолют одометр / delta / только через путёвку | **Одометр на конец дня (абсолют)** (Recommended) | D-13 | VehicleOdometer UNIQUE(vehicle_id, date). delta вычисляется на чтении |
| Шаблоны путевых листов? | 3 раздельных .docx / 1 универсальный / per-org через БД | **3 раздельных .docx** (Recommended) | D-14 | trip_light / trip_truck / trip_special. Выбор по vehicle.type |
| Наёмные водители? | ExternalDriver сущность / Trip.driver_user_id OR text / только User с can_drive | **ExternalDriver сущность** (Recommended) | D-15 | Накапливает историю. В путёвке список = User ∪ ExternalDriver |
| Дашборд виджеты? | 8 + draggable / 5 статичных / через Phase 25 | **8 + draggable + кастомные креативы** (user_custom note) | D-16 | KPI / Канистра-анимация / ТО-warning / в ремонте / bar по орг / line расход / donut состояние / TOP-10. Фильтры регион+орг |

**D-16 user expansion:** «крутые визуализации, переключатели по регионам/организациям, бензин плещется в канистре, машины с ТО <1000 км должны светиться, виджет с машинами в ремонте». Custom SVG-канистра анимация, pulsing glow на карточках с просрочкой/ТО.

---

## Batch 4 — Alerts / Purchase integration / Output format / Fuel norms

| Question | Options presented | User pick | D-num | Notes |
|---|---|---|---|---|
| Уведомления о просрочке? | баннер + auto-Task / только баннер / + email | **Баннер + auto-Task** (Recommended) | D-17 | Cron в lifespan создаёт Task за 30 дней. system_tag для идемпотентности |
| Связь ремонта/заправки с Purchase? | Purchase.vehicle_id + UI селект / без связи / VehicleRepair.purchase_id | **Optional FK Purchase.vehicle_id + UI** (Recommended) | D-18 | Двусторонняя ссылка (Purchase.vehicle_id + VehicleRepair.purchase_id) для удобства резолва |
| Формат путёвки? | .docx через docxtpl / .docx + .pdf / PDF через reportlab | **.docx через docxtpl** (Recommended) | D-19 | Без PDF. Паттерн Phase 19/27.5/28 |
| Норма расхода + цена бензина? | норма в карточке + цена из последней заправки / летняя/зимняя norms / без расчёта | **Отдельные norms по сезону** (user pick) | D-20 | fuel_norm_summer (May-Sep) + fuel_norm_winter (Oct-Apr). Минтранс РФ. Цена — из последней FuelLog |

---

## Deferred Ideas (captured during discussion)

- GPS-трекеры в реальном времени (отдельная фаза 30+)
- OCR ПТС/СТС/чеков (отдельная фаза 31+)
- Маршруты на карте Yandex/2GIS (отдельная фаза)
- Имущество → Оборудование / Прочее (заглушки в нав, отдельные фазы)
- PDF-экспорт путёвок (только .docx сейчас)
- Кастомизация шаблонов путёвок по орг (паттерн Phase 19, deferred)
- QR-парсинг чеков заправки (паттерн Phase 21-08, отдельная мини-фаза)
- Reports через Phase 25 для vehicle/fuel/repair sources (опционально в плане 29-XX)
- Email уведомления (D-17 пока только in-app)
- Роль «Ответственный за автопарк» (флаг user_organizations пока, full-fledged role позже)
- Шиномонтажный календарь

---

## Claude's Discretion (areas where user didn't lock specifics)

- Точный layout карточки ТС и порядок табов
- Конкретная SVG-анимация «канистры»
- Цвета и иконки виджетов
- ENUM-значения для type/state
- Шаблоны путевых листов (формы Минтранса)
- Mapping регионов xlsx → org_id (полу-ручной диалог при импорте)

---

## Process notes

- **Memory rule respected:** `feedback_use_askuserquestion` → 5 AskUserQuestion batches вместо текстовых списков. Всего 20 вопросов в опросниках.
- **Memory rule respected:** `feedback_no_verification_loops` → discuss phase не запускает builds/migrations.
- **ROADMAP.md edit:** Phase 29 entry added (lines после Phase 27.1) с D-01..D-04 locked decisions, scope, success criteria.
- **GSD workflow:** check_blocking_antipatterns skipped (нет `.continue-here.md`). check_spec skipped (нет SPEC.md). check_existing — no CONTEXT.md, no checkpoint, no plans. load_prior_context — приоры загружены в начале сессии. scout_codebase — известные паттерны из контекста сессии (Phase 3/14/17/19/25). analyze_phase — gray areas сгенерированы phase-specific. discuss_areas — 4 batches × 4 questions = 16 + 4 pre-locked = 20 decisions.

---

*Discussion completed: 2026-05-19*
