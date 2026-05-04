# Phase 18: Staff Directory — Context

**Gathered:** 2026-05-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Read-only справочник «Сотрудники» — отдельная вкладка в AppBar (`/directory`), доступная всем ролям (employee+). Показывает коллег внутри своих организаций (`get_org_filter`): ФИО, должность, отдел, мобильный телефон, рабочий (стационарный) телефон, email, фото. Сотрудник может быть скрыт через флаг `exclude_from_directory` (поле уже добавлено коммитом `38ac526`). Редактирование сотрудников — НЕ в этой фазе (остаётся в админской `/staff`).

</domain>

<decisions>
## Implementation Decisions

### Поля и модель данных
- **D-01:** Поля карточки: `full_name`, `position`, `department`, `phone` (мобильный), `work_phone` (стационарный, **новое поле**), `email`, `profile_photo` (data URL из `User.profile_photo`).
- **D-02:** Добавить колонку `User.work_phone = Column(String(30), nullable=True)`. Schemas (`UserCreate`/`UserUpdate`/`UserOut`) расширить поле `work_phone: Optional[str]`. SQLAlchemy `Base.metadata.create_all` создаст колонку при старте backend (alembic chain сломан — паттерн уже использован для `exclude_from_directory`).
- **D-03:** В **карточке сотрудника (StaffView edit dialog)** — добавить второй input «Рабочий телефон» рядом с «Мобильный». Иконки: `mdi-cellphone` для phone, `mdi-phone-classic` для work_phone. Маска `1-111-111-11-11` (та же `formatPhoneRu` из `frontend/src/utils/phoneFormat.ts`, коммит `38ac526`).

### Layout и UX
- **D-04:** Плоский grid карточек (как в `StaffView`) — `v-row` с `v-col cols=12 md=6 lg=4`. На каждой карточке сразу видно: фото слева вертикальный прямоугольник 4:5 (как в коммите `4df1a86`), справа ФИО (text-h6), должность + отдел (text-caption), список контактов (телефоны кликабельны `tel:`, email кликабелен `mailto:`).
- **D-05:** Click по карточке → `v-dialog` mini-dialog с расширенным read-only видом: фото больше (320×400), все контакты крупно, отдел/организация. Без перехода на отдельную страницу.
- **D-06:** Live-search по любому полю (full_name, position, department, phone, work_phone, email) — `v-text-field` сверху + `computed filteredUsers` фильтрует все поля через `.toLowerCase().includes(query)`. Debounce не нужен (массив всегда в памяти).
- **D-07:** Дополнительный фильтр-`v-select` «Отдел» — multi-select, options = distinct departments из загруженного списка. Применяется после search.
- **D-08:** Дополнительный фильтр-`v-select` «Организация» — если у пользователя ≥2 орг (видны через `get_org_filter`). Скрывать если орг одна.

### Видимость и фильтрация (backend)
- **D-09:** Endpoint `GET /api/staff-directory` — возвращает `[{id, full_name, position, department, phone, work_phone, email, photo_url, org_name}]`.
- **D-10:** Фильтр через `get_org_filter(current_user)` — пользователь видит только сотрудников из своих организаций (`User.org_id` ИЛИ `user_org_access.org_id` ∈ my_org_ids).
- **D-11:** Carry-forward из Phase 17 (D-09): superadmin полностью невидим всем кроме других superadmin'ов (`User.role != 'superadmin' OR current_user.role == 'superadmin'`).
- **D-12:** Скрывать пользователей с `exclude_from_directory=true` ВСЕГДА (никто не видит, кроме них самих если хотят редактировать в `/staff`). Superadmin тоже не видит.
- **D-13:** `photo_url` в API — base64 data URL из `User.profile_photo` (та же стратегия что и в карточке сотрудника). Если пусто — отдаётся `null`, frontend показывает initials или placeholder.

### Permission и навигация
- **D-14:** Новый tab_key `staff_directory` в permissions matrix. Seed: разрешён всем 5 ролям (`superadmin/admin/org_admin/manager/employee`). Migration через `Base.metadata.create_all` + idempotent INSERT в migration функции (паттерн из Phase 17).
- **D-15:** Маршрут `/directory` с `meta.tab_key='staff_directory'`. Роутер-guard через `authStore.hasTab()` (Phase 17, D-09).
- **D-16:** Новый пункт меню «Справочник» в AppBar (`mdi-account-multiple-outline`) — между «Персонал» и «Чат» / другим логичным местом. Видим если `authStore.hasTab('staff_directory')`.

### Чекбокс «Не включать в справочник»
- **D-17:** Уже сделано коммитом `38ac526` (B6/F3-чекбокс): `User.exclude_from_directory: bool` колонка + чекбокс в StaffView edit dialog «Не включать в справочник сотрудников». Эта фаза только потребляет флаг (D-12 фильтр).
- **D-18:** Сотрудник может **сам себя** скрыть из справочника? **Нет** — флаг ставит только тот кто редактирует карточку (admin/manager). В Phase 18 — только просмотр.

### Claude's Discretion
- Точная анимация открытия mini-dialog
- Цвет/градиент пустого state (когда нет сотрудников после фильтра)
- Dark/light mode цветовые токены
- Точный grid breakpoints (`md=6 lg=4` или `md=4 lg=3` — выбрать после first-build prototype)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Permission system (carry-forward Phase 17)
- `.planning/phases/17-permission-system-override/17-CONTEXT.md` — D-09 superadmin invisibility, tab_key system
- `backend/app/auth/permissions.py` — `require_tab`, `get_org_filter`, `_get_effective`
- `backend/app/routers/permissions.py` — admin endpoints для матрицы (как seed нового tab_key)

### Existing components (reuse)
- `frontend/src/views/StaffView.vue` — паттерн карточек сотрудников (для grid layout, ProfilePhotoUpload integration)
- `frontend/src/components/ProfilePhotoUpload.vue` — фото компонент (Phase post-2026-05 уже поддерживает `format='rectangle'`)
- `frontend/src/utils/phoneFormat.ts` — маска телефона `formatPhoneRu` (коммит `38ac526`)
- `backend/app/models/user.py` — `exclude_from_directory` колонка (уже есть, нужно только добавить `work_phone`)

### Backend filters
- `backend/app/auth/jwt.py:get_org_filter` — фильтр организаций для current_user

### Roadmap entry
- `.planning/ROADMAP.md` Phase 18 — formal scope (read-only directory, отдельная от админского /staff)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **ProfilePhotoUpload.vue** (props `format='circle'|'rectangle'` + `userId?`) — для отображения фото в карточке справочника (read-only режим: `:editable="false"` если такой проп есть, иначе через CSS `pointer-events: none`).
- **utils/phoneFormat.ts** — `formatPhoneRu()` для отображения телефонов в формате `1-111-111-11-11`.
- **AppBar.vue tab_key system** — добавить пункт меню по паттерну `{ icon, title, to, tab_key }` (как другие пункты Phase 17).
- **StaffView.vue carousel** — там есть `<v-row>` с `<v-col>` для карточек сотрудников; можно скопировать структуру и упростить (без edit dialog, только показ).

### Established Patterns
- **`Base.metadata.create_all`** — для добавления новой колонки `User.work_phone` без alembic (как `exclude_from_directory`).
- **`get_org_filter(current_user)`** — стандартный фильтр всех list endpoints.
- **`require_tab('staff_directory')` + `meta.tab_key` на route** — стандартная схема Phase 17.
- **D-09 superadmin filter** — `_get_visible_user_ids` или прямой `WHERE u.role != 'superadmin' OR cu.role = 'superadmin'`.

### Integration Points
- `backend/app/routers/users.py` — расширить schemas + добавить новый endpoint `/api/staff-directory` (или новый router-файл `staff_directory.py` для чистоты).
- `frontend/src/router/index.ts` — добавить route `/directory`.
- `frontend/src/components/AppBar.vue` — пункт меню «Справочник».
- `backend/alembic/versions/` — seed migration для `staff_directory` tab_key (или INSERT в существующий permission_seed_hotfix).

</code_context>

<specifics>
## Specific Ideas

- «Карточки как в Персонале, на ней сразу фото фио должность контакты» — пользователь явно ссылается на текущий UX `/staff`. Layout заимствуется отсюда.
- Из docx (фидбек 2026-05-04): «телефон стационарный и мобильный» — отсюда выбор отдельного `work_phone` поля.
- Из docx: «отдельное поле его не включалось в справочник» — флаг `exclude_from_directory` уже добавлен коммитом `38ac526` (B6).

</specifics>

<deferred>
## Deferred Ideas

- **Per-org override exclude** — сейчас `exclude_from_directory` глобальный (все орг). Если потребуется «скрыть в АНО, показать в ВСКС» — отдельная задача (новая таблица `user_directory_visibility` per-org).
- **Кнопка «Позвонить»/«Написать в Telegram» прямо из карточки** — отдельная фича, требует интеграции с уже работающим TG-bot (Phase 8).
- **Экспорт справочника в Excel/CSV** — отдельная задача.
- **Right-side панель с быстрым переходом по алфавиту (А-Я)** — UX улучшение, не блокер.
- **Сам сотрудник может скрыть себя** — отложено (только admin/manager сейчас, D-18).

</deferred>

---

*Phase: 18-staff-directory*
*Context gathered: 2026-05-04*
