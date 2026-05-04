# Phase 18: Staff Directory — Discussion Log

> **Audit trail only.** Decisions captured in CONTEXT.md.

**Date:** 2026-05-04
**Phase:** 18-staff-directory
**Areas discussed:** Поля и лейаут, Поиск и фильтрация, Группировка и видимость, Доступ и навигация, Стационарный телефон, Группировка карточек, Click на карточку

---

## Round 1 — Gray areas (multiSelect)

| Option | Description | Selected |
|--------|-------------|----------|
| Поля и лейаут | ФИО + должность + отдел + телефон (стац+моб) + email + фото; layout — таблица/карточки/список | ✓ |
| Поиск и фильтрация | Live-search; фильтры по орг и отделу | ✓ |
| Группировка и видимость | Плоский / collapsible по отделам; superadmin скрытие | ✓ |
| Доступ и навигация | Новый AppBar пункт; route /directory; tab_key 'staff_directory' | ✓ |

**User's choice:** «Отдельная вкладка "Справочник сотрудников". Суперадмин не виден. Поиск возможен по любому из полей. Карточки как в Персонале, на ней сразу фото фио должность контакты»

---

## Round 2 — Стационарный телефон

| Option | Description | Selected |
|--------|-------------|----------|
| Отдельное поле User.work_phone | Новая колонка String(30). 2 поля в карточке. Иконки cellphone + phone-classic | ✓ |
| Одно User.phone через запятую | Без миграции. Хуже для сортировки/поиска | |

**User's choice:** Отдельное поле User.work_phone

---

## Round 3 — Группировка

| Option | Description | Selected |
|--------|-------------|----------|
| Плоский grid + фильтр отделов | Все карточки сразу, v-select «Отдел» | ✓ |
| Collapsible секции по отделам | Каждый отдел — раскрывающийся блок | |

**User's choice:** Плоский grid + фильтр

---

## Round 4 — Click на карточку

| Option | Description | Selected |
|--------|-------------|----------|
| Mini-dialog с расширенными данными | Попап с read-only details, tel:/mailto: | ✓ |
| Inline expansion карточки | Раскрытие в grid'е | |
| Переход на /directory/{id} | Отдельная страница профиля | |

**User's choice:** Mini-dialog

---

## Claude's Discretion

- Точная анимация открытия mini-dialog
- Точные grid breakpoints (md=6 lg=4 vs md=4 lg=3)
- Цветовые токены empty-state
- Цвет/иконка пункта AppBar (предложение: mdi-account-multiple-outline)

## Deferred Ideas

- Per-org override exclude_from_directory
- Кнопки «Позвонить»/«Написать в TG» прямо из карточки
- Excel/CSV экспорт
- Right-side А-Я навигация
- Сам сотрудник может скрыть себя
