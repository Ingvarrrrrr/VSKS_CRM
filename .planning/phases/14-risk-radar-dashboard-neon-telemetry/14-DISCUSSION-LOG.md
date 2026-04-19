# Phase 14: Risk Radar (Neon Telemetry) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-19
**Phase:** 14-risk-radar-dashboard-neon-telemetry
**Areas discussed:** Neon Telemetry — палитра/эффекты/API (единственная выбранная область)

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Метрики рисков и формулы (Рек) | Что такое 'риск'? Какие именно метрики входят в radar и как считается скор. | |
| Визуальная композиция (Рек) | Единый radar + панели? Много radar-карточек? Heatmap субсидий? Gauge-колонны? | |
| Toggle classic/radar + роутинг (Рек) | Отдельный /dashboard/radar? In-page tab? Toggle в AppBar? Где хранится выбор. | |
| Neon Telemetry — палитра/эффекты/API (Рек) | Цвета, фон, эффекты, dark-only/адаптивно, источник данных. | ✓ |

**User's choice:** Только "Neon Telemetry — палитра/эффекты/API". Остальные области оставлены на усмотрение Claude.

---

## Neon Telemetry — палитра/эффекты/API

### Question 1: Палитра Neon Telemetry

| Option | Description | Selected |
|--------|-------------|----------|
| Cyan/Magenta/Amber/Lime (Рек) | #06B6D4/#EC4899/#F59E0B/#EF4444 — 4 уровня риска | |
| Cyan/Violet/Amber (3-тон) | #22D3EE/#8B5CF6/#FBBF24 — ok/warn/critical | |
| Monochrome green (классика radar) | #10B981 + красный на critical. Минимализм. | |
| Claude решает | Выбор по ходу реализации в стиле существующего glassmorphism. | ✓ |

**User's choice:** Claude решает
**Notes:** Палитра должна сочетаться с existing glassmorphism и поддерживать 3-4 уровня severity.

### Question 2: Фон и визуальные эффекты

| Option | Description | Selected |
|--------|-------------|----------|
| Deep navy + dot-grid + glow + sweep (Рек) | #0B1220, dot-grid bg, glow, вращающийся radar sweep | |
| Pure black + scan-line + chromatic | Максимальный sci-fi: CRT scan-line, chromatic aberration, pulse | |
| Адаптивно под Vuetify тему | Neon только в dark, light — спокойный вариант | ✓ |
| Только чёрный, без эффектов (минимализм) | Plain dark, аскетично | |

**User's choice:** Адаптивно под Vuetify тему
**Notes:** Neon должен модулироваться темой — в dark полноценно, в light приглушённо.

### Question 3: Dark-only или адаптивно

| Option | Description | Selected |
|--------|-------------|----------|
| Dark-only (Рек) | Radar всегда в dark вне зависимости от Vuetify темы. Проще. | |
| Адаптивно | Light-вариант с приглушённым neon; dark-вариант full neon. Два сета стилей. | ✓ |
| Только dark, авто-переключает тему при входе | Vuetify dark при входе, возврат на выходе. | |

**User's choice:** Адаптивно
**Notes:** Подтверждение что обе темы — first-class.

### Question 4: API для риск-данных

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse /api/dashboard/charts + счёт на фронте (Рек) | Composable useRiskScores() на клиенте | |
| Новый /api/dashboard/risks endpoint | Backend отдаёт готовые risk scores | |
| Гибрид: фронт сейчас, /risks потом | MVP на фронте, извлечь в backend в Phase 14.1 | |

**User's choice:** Other (free-text): "Тут вообще ничего не понял. И должна быть возможность переключаться между текущей стилистикой и той что сейчас делается. Тёмная и светлая тема — это по умолчанию в обоих реализациях."
**Notes:** Пользователь не понял API-вопрос → Claude's Discretion. Главное для пользователя:
1. Toggle между classic стилистикой и новой Neon Telemetry должен существовать
2. Dark и light тема должны работать в ОБЕИХ реализациях (classic + radar)

### Confirm: writing CONTEXT.md

**User's choice:** "Всё верно, пиши CONTEXT.md (Рек)"

---

## Claude's Discretion

Пользователь явно делегировал Claude следующие решения:

- Выбор цветовой палитры Neon Telemetry (hex-коды, число уровней severity)
- Выбор визуальной композиции (radar + панели / множество radar-карточек / heatmap / и т.п.)
- Выбор механики toggle (AppBar / tab / button / route)
- Выбор набора risk metrics (какие именно показываем)
- Выбор формул risk-скоров
- Выбор API стратегии (фронт-calc vs backend endpoint)
- Выбор визуальных эффектов (glow, sweep, scan-line, pulse и т.п.)
- Детали интеракции (hover / drill-down / alerts ticker)

---

## Deferred Ideas

Не обсуждались, но зафиксированы в CONTEXT.md `<deferred>` как возможные будущие фазы:
- Drill-down от риска к конкретной закупке (если потребует >1 плана → Phase 14.1)
- Web Push при критических рисках
- Исторический тренд риск-скоров
- Customizable risk weights per-user
- Мобильная оптимизация Risk Radar
- Экспорт Risk Radar в PDF/PNG
