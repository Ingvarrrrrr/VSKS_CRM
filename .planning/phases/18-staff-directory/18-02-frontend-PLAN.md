---
phase: 18
plan: 18-02
title: Frontend — StaffDirectoryView + mini-dialog + StaffView work_phone input
wave: 2
depends_on: [18-01]
autonomous: true
files_modified:
  - frontend/src/views/StaffDirectoryView.vue  # NEW
  - frontend/src/components/StaffMemberDialog.vue  # NEW
  - frontend/src/views/StaffView.vue  # ADD work_phone input
requirements: []
---

# 18-02: Frontend — StaffDirectoryView + Dialog

<objective>
1. Создать `views/StaffDirectoryView.vue` — read-only справочник сотрудников: grid карточек как в `StaffView`, live-search по всем полям, фильтр-`v-select` отделов и организаций (если ≥2 орг).
2. Создать `components/StaffMemberDialog.vue` — mini-dialog с расширенной read-only информацией и `tel:`/`mailto:` ссылками.
3. Расширить `views/StaffView.vue` editDialog: добавить input «Рабочий телефон» (work_phone) рядом с «Мобильный» (phone), с маской `formatPhoneRu`.
</objective>

<must_haves>
- `/directory` route возвращает компонент StaffDirectoryView (route добавляется в плане 18-03)
- Карточки показывают: фото 4:5 (через ProfilePhotoUpload format='rectangle' read-only), ФИО, должность · отдел, mobile + work_phone (отформатированы), email
- Live-search фильтрует по full_name, position, department, phone, work_phone, email (case-insensitive)
- v-select «Отдел» — multi-select из distinct departments
- v-select «Организация» — виден только если у current_user ≥2 орг
- Click по карточке → mini-dialog с расширенной информацией
- Mini-dialog: фото больше (320×400), `<a href="tel:+7...">` для phone/work_phone, `<a href="mailto:...">` для email, кнопка «Закрыть»
- Empty state: «Сотрудники не найдены» при пустом результате
- StaffView edit dialog: поле «Рабочий телефон» с маской `formatPhoneRu`, в БД записывается через `unformatPhone` только цифры (как `phone` в коммите `38ac526`)
- Build `cd frontend && npm run build` проходит чисто
</must_haves>

<tasks>

<task id="18-02-01" title="StaffMemberDialog.vue (mini-dialog)">
<read_first>
- frontend/src/components/ProfilePhotoUpload.vue — props `format='circle'|'rectangle'`, `userId?`
- frontend/src/utils/phoneFormat.ts — `formatPhoneRu()`, `unformatPhone()`
- frontend/src/views/StaffView.vue — паттерн отображения сотрудника (для референса дизайна)
</read_first>

<action>
Создать `frontend/src/components/StaffMemberDialog.vue`:

```vue
<template>
  <v-dialog v-model="open" max-width="540" scrollable>
    <v-card v-if="user">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-account-circle-outline" color="primary" class="mr-2" />
        Карточка сотрудника
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="open = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <div class="d-flex flex-column flex-sm-row ga-4">
          <!-- Фото 320×400 -->
          <div class="staff-photo-wrap">
            <img v-if="user.photo_url" :src="user.photo_url" alt="" class="staff-photo" />
            <div v-else class="staff-photo-placeholder">
              <v-icon icon="mdi-account" size="80" color="grey-lighten-1" />
            </div>
          </div>
          <!-- Контакты -->
          <div class="flex-grow-1">
            <div class="text-h6">{{ user.full_name }}</div>
            <div v-if="user.position" class="text-body-2 text-medium-emphasis mt-1">{{ user.position }}</div>
            <div v-if="user.department" class="text-caption text-medium-emphasis">{{ user.department }}</div>
            <div v-if="user.org_name" class="text-caption text-medium-emphasis mt-2">
              <v-icon icon="mdi-office-building" size="14" /> {{ user.org_name }}
            </div>

            <v-divider class="my-3" />

            <div v-if="user.phone" class="d-flex align-center mb-2">
              <v-icon icon="mdi-cellphone" color="primary" size="20" class="mr-2" />
              <a :href="`tel:${rawPhone(user.phone)}`" class="text-decoration-none">
                {{ formatPhoneRu(user.phone) }}
              </a>
              <span class="text-caption text-medium-emphasis ml-2">мобильный</span>
            </div>

            <div v-if="user.work_phone" class="d-flex align-center mb-2">
              <v-icon icon="mdi-phone-classic" color="indigo" size="20" class="mr-2" />
              <a :href="`tel:${rawPhone(user.work_phone)}`" class="text-decoration-none">
                {{ formatPhoneRu(user.work_phone) }}
              </a>
              <span class="text-caption text-medium-emphasis ml-2">рабочий</span>
            </div>

            <div v-if="user.email" class="d-flex align-center">
              <v-icon icon="mdi-email-outline" color="teal" size="20" class="mr-2" />
              <a :href="`mailto:${user.email}`" class="text-decoration-none">{{ user.email }}</a>
            </div>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatPhoneRu, unformatPhone } from '@/utils/phoneFormat'

interface DirectoryUser {
  id: number
  full_name: string
  position: string | null
  department: string | null
  phone: string | null
  work_phone: string | null
  email: string | null
  photo_url: string | null
  org_name: string | null
  org_id: number | null
}

const props = defineProps<{ modelValue: boolean; user: DirectoryUser | null }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean] }>()
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function rawPhone(s: string): string {
  return '+7' + unformatPhone(s).replace(/^[78]/, '')
}
</script>

<style scoped>
.staff-photo-wrap {
  flex-shrink: 0;
  width: 160px;
  height: 200px;
  border-radius: 12px;
  overflow: hidden;
  background: #f5f5f5;
}
.staff-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.staff-photo-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
```
</action>

<acceptance_criteria>
- Файл `frontend/src/components/StaffMemberDialog.vue` существует
- `grep -n "tel:" frontend/src/components/StaffMemberDialog.vue` возвращает 1+ совпадение
- `grep -n "mailto:" frontend/src/components/StaffMemberDialog.vue` возвращает 1+ совпадение
- `grep -n "formatPhoneRu" frontend/src/components/StaffMemberDialog.vue` возвращает 1+ совпадение
</acceptance_criteria>
</task>

<task id="18-02-02" title="StaffDirectoryView.vue (grid + search + filters)">
<read_first>
- frontend/src/views/StaffView.vue — структура карточек, паттерны loadUsers, фильтрации (computed), org filter
- frontend/src/api.ts — `apiFetch<T>` сигнатура
- frontend/src/utils/phoneFormat.ts — formatPhoneRu
</read_first>

<action>
Создать `frontend/src/views/StaffDirectoryView.vue`:

```vue
<template>
  <v-container fluid class="pa-4">
    <h1 class="text-h5 mb-4 d-flex align-center">
      <v-icon icon="mdi-account-multiple-outline" class="mr-2" />
      Справочник сотрудников
      <v-chip v-if="!loading" size="small" variant="tonal" class="ml-3">{{ filtered.length }}</v-chip>
    </h1>

    <!-- Поиск + фильтры -->
    <v-row class="mb-2" dense>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          label="Поиск по любому полю"
          variant="outlined"
          density="compact"
          hide-details
          clearable
        />
      </v-col>
      <v-col cols="12" md="3">
        <v-select
          v-model="filterDepts"
          :items="departments"
          label="Отдел"
          variant="outlined"
          density="compact"
          hide-details
          multiple
          chips
          closable-chips
          clearable
        />
      </v-col>
      <v-col v-if="orgs.length >= 2" cols="12" md="3">
        <v-select
          v-model="filterOrgs"
          :items="orgs"
          item-title="name"
          item-value="id"
          label="Организация"
          variant="outlined"
          density="compact"
          hide-details
          multiple
          chips
          closable-chips
          clearable
        />
      </v-col>
    </v-row>

    <!-- Grid карточек -->
    <v-row v-if="loading">
      <v-col cols="12" class="text-center pa-8">
        <v-progress-circular indeterminate color="primary" />
      </v-col>
    </v-row>

    <v-row v-else-if="filtered.length === 0">
      <v-col cols="12" class="text-center pa-8 text-medium-emphasis">
        <v-icon icon="mdi-account-search-outline" size="64" class="mb-2 d-block mx-auto" />
        Сотрудники не найдены
      </v-col>
    </v-row>

    <v-row v-else dense>
      <v-col v-for="u in filtered" :key="u.id" cols="12" md="6" lg="4">
        <v-card variant="outlined" class="pa-3 staff-card cursor-pointer" @click="openCard(u)">
          <div class="d-flex ga-3">
            <!-- Фото 4:5 — 80×100 -->
            <div class="staff-card-photo">
              <img v-if="u.photo_url" :src="u.photo_url" alt="" />
              <div v-else class="staff-card-photo-placeholder">
                <v-icon icon="mdi-account" size="40" color="grey-lighten-1" />
              </div>
            </div>
            <!-- Инфо -->
            <div class="flex-grow-1 staff-card-info">
              <div class="text-subtitle-2 font-weight-bold">{{ u.full_name }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ u.position || '—' }}<span v-if="u.department"> · {{ u.department }}</span>
              </div>
              <div v-if="u.phone" class="text-caption mt-1">
                <v-icon icon="mdi-cellphone" size="12" /> {{ formatPhoneRu(u.phone) }}
              </div>
              <div v-if="u.work_phone" class="text-caption">
                <v-icon icon="mdi-phone-classic" size="12" /> {{ formatPhoneRu(u.work_phone) }}
              </div>
              <div v-if="u.email" class="text-caption text-truncate">
                <v-icon icon="mdi-email-outline" size="12" /> {{ u.email }}
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <StaffMemberDialog v-model="dialogOpen" :user="selectedUser" />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { formatPhoneRu } from '@/utils/phoneFormat'
import StaffMemberDialog from '@/components/StaffMemberDialog.vue'

interface DirectoryUser {
  id: number
  full_name: string
  position: string | null
  department: string | null
  phone: string | null
  work_phone: string | null
  email: string | null
  photo_url: string | null
  org_name: string | null
  org_id: number | null
}

const users = ref<DirectoryUser[]>([])
const loading = ref(true)
const search = ref('')
const filterDepts = ref<string[]>([])
const filterOrgs = ref<number[]>([])
const dialogOpen = ref(false)
const selectedUser = ref<DirectoryUser | null>(null)

const departments = computed(() => {
  const set = new Set<string>()
  for (const u of users.value) if (u.department) set.add(u.department)
  return Array.from(set).sort()
})

const orgs = computed(() => {
  const map = new Map<number, string>()
  for (const u of users.value) if (u.org_id && u.org_name) map.set(u.org_id, u.org_name)
  return Array.from(map.entries()).map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return users.value.filter((u) => {
    if (filterDepts.value.length && !filterDepts.value.includes(u.department || '')) return false
    if (filterOrgs.value.length && !filterOrgs.value.includes(u.org_id || -1)) return false
    if (!q) return true
    const haystack = [u.full_name, u.position, u.department, u.phone, u.work_phone, u.email]
      .filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(q)
  })
})

function openCard(u: DirectoryUser) {
  selectedUser.value = u
  dialogOpen.value = true
}

onMounted(async () => {
  try {
    users.value = await apiFetch<DirectoryUser[]>('/staff-directory/')
  } catch (e) {
    console.error('staff directory load failed', e)
    users.value = []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.staff-card { transition: box-shadow 0.15s; }
.staff-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.cursor-pointer { cursor: pointer; }
.staff-card-photo {
  width: 80px;
  height: 100px;
  border-radius: 8px;
  overflow: hidden;
  background: #f5f5f5;
  flex-shrink: 0;
}
.staff-card-photo img { width: 100%; height: 100%; object-fit: cover; }
.staff-card-photo-placeholder {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
}
.staff-card-info { min-width: 0; }
</style>
```
</action>

<acceptance_criteria>
- Файл `frontend/src/views/StaffDirectoryView.vue` существует
- `grep -n "/staff-directory/" frontend/src/views/StaffDirectoryView.vue` возвращает 1+ совпадение
- `grep -n "filterDepts\|filterOrgs\|search.value" frontend/src/views/StaffDirectoryView.vue` возвращает совпадения для всех 3
- `grep -n "StaffMemberDialog" frontend/src/views/StaffDirectoryView.vue` возвращает 2+ совпадения (import + usage)
</acceptance_criteria>
</task>

<task id="18-02-03" title="Добавить work_phone input в StaffView edit dialog">
<read_first>
- frontend/src/views/StaffView.vue — найти `phone` input в editDialog и createDialog (около строки 380-400 и 490+); прочитать паттерн использования `formatPhoneRu` / `unformatPhone` (если уже есть)
- frontend/src/utils/phoneFormat.ts
</read_first>

<action>
В `frontend/src/views/StaffView.vue`:

1. Расширить интерфейс / тип формы добавив `work_phone: string` поле (рядом с `phone`).

2. После `<v-text-field>` для `phone` (мобильный) в **createDialog** и **editDialog** добавить аналогичный input для `work_phone`:

```vue
<v-text-field
  :model-value="formatPhoneRu(form.work_phone || '')"
  @update:model-value="form.work_phone = unformatPhone($event)"
  prepend-inner-icon="mdi-phone-classic"
  label="Рабочий телефон"
  variant="outlined" density="compact" hide-details
  class="mb-3"
/>
```

(Заменить `form` на корректное имя ref'а — `createDialog` / `editDialog` / общая структура. Если в проекте `phone` использует только `formatPhoneRu` для отображения и `unformatPhone` при сохранении — повторить тот же паттерн.)

3. В функции `saveUser` / `createUser` (POST/PATCH body) — убедиться что `work_phone` включается в payload (если используется generic `{...form}` spread — автоматически).

4. Если в `StaffMember` интерфейсе на уровне TypeScript есть поле `phone`, добавить рядом `work_phone: string | null`.
</action>

<acceptance_criteria>
- `grep -c "work_phone" frontend/src/views/StaffView.vue` ≥ 4 (interface + createDialog + editDialog + payload, минимум)
- `grep -n "mdi-phone-classic" frontend/src/views/StaffView.vue` возвращает 1+ совпадение
- `cd frontend && npm run build` завершается успешно (проверить вручную после трёх tasks)
</acceptance_criteria>
</task>

</tasks>

<verification>
- `cd frontend && npm run build` → ✓ success
- После autodeploy зайти на http://85.239.53.155/directory (после регистрации route в плане 18-03) → должна загрузиться страница с grid карточек
- Live-search и фильтры работают локально (computed)
- Click на карточку открывает mini-dialog с tel:/mailto: ссылками
- В StaffView edit dialog появилось поле «Рабочий телефон» с маской
</verification>
