<template>
  <div>
    <!-- Владелец, 2026-09-03: раньше здесь ещё был переключатель «по странице/по всей БД» —
         корневой div нёс d-flex, чтобы уложить поле и переключатель в ряд. Переключатель убрали
         (режим «по странице» нигде толком не работал), остался один child — flex больше не нужен.
         Важно: d-flex было утилитой !important и конфликтовало с d-none/d-sm-flex, которые
         AppBar.vue вешает на этот же корневой элемент, чтобы скрывать поиск на мобильных — из-за
         одинаковой специфичности побеждал тот класс, что ниже в CSS, и поле вылезало на мобильном
         поверх шапки независимо от viewport. Без d-flex это больше не проблема. -->
    <v-text-field
      v-model="appSearch"
      prepend-inner-icon="mdi-magnify"
      placeholder="Поиск по всей базе..."
      variant="outlined"
      density="compact"
      hide-details
      clearable
      bg-color="white"
      style="width: 260px"
      @keydown.ctrl.k.prevent
    />

    <!-- Global search results dialog -->
    <v-dialog v-model="globalDialog" max-width="600" :retain-focus="false" :fullscreen="mobile">
      <v-card>
        <v-card-text class="pa-2 pb-0">
          <v-text-field
            v-model="appSearch"
            placeholder="Поиск закупок, контрагентов, договоров..."
            variant="solo"
            flat
            hide-details
            prepend-inner-icon="mdi-magnify"
            clearable
            autofocus
            @keyup.esc="globalDialog = false"
            class="search-input"
          />
        </v-card-text>
        <v-divider />
        <div v-if="loading" class="d-flex justify-center pa-6">
          <v-progress-circular indeterminate size="24" />
        </div>
        <div v-else-if="appSearch.length > 1 && results.length === 0" class="pa-4 text-center text-medium-emphasis text-caption">
          Ничего не найдено
        </div>
        <v-list v-else-if="results.length > 0" density="compact" style="max-height:400px; overflow-y:auto">
          <template v-for="group in groupedResults" :key="group.type">
            <v-list-subheader>{{ group.label }}</v-list-subheader>
            <v-list-item
              v-for="item in group.items"
              :key="item.id + group.type"
              :title="item.title"
              :subtitle="item.subtitle"
              :prepend-icon="group.icon"
              @click="navigate(item, group.type)"
              class="search-result-item"
            />
          </template>
        </v-list>
        <div v-else-if="appSearch.length === 0" class="pa-4 text-caption text-medium-emphasis text-center">
          Введите запрос (минимум 2 символа)
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useAppSearch } from '@/composables/useAppSearch'
import { purchaseStatusLabel } from '@/constants/purchaseStatus'

const router = useRouter()
const { mobile } = useDisplay()
const { appSearch } = useAppSearch()
const globalDialog = ref(false)
const loading = ref(false)

interface SearchResult { id: number; title: string; subtitle?: string }
interface ResultGroup { type: string; label: string; icon: string; items: SearchResult[] }

const purchases = ref<SearchResult[]>([])
const contractors = ref<SearchResult[]>([])

// Ctrl+K shortcut
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault()
      globalDialog.value = true
    }
  })
}

let searchTimeout: ReturnType<typeof setTimeout> | null = null

// Open the results dialog as soon as the query is long enough
watch(appSearch, (q) => {
  if (q.length >= 2) {
    globalDialog.value = true
    if (searchTimeout) clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => doSearch(q), 300)
  } else {
    globalDialog.value = false
  }
})

watch(globalDialog, (v) => {
  if (!v) {
    purchases.value = []
    contractors.value = []
  }
})

async function doSearch(q: string) {
  loading.value = true
  try {
    // Владелец 15.10.2026: вводил последние цифры номера («767») и не видел
    // РЕЕ-2026-00767 — в выдаче не было номера, а 8 случайных совпадений по
    // всем полям вытесняли нужную. Цифры (до 5) ищем ещё и как номер реестра
    // с ведущими нулями и ставим эти совпадения первыми.
    const trimmed = q.trim()
    const numberQuery = /^\d{1,5}$/.test(trimmed) ? trimmed.padStart(5, '0') : null
    const [p, byNumber, c] = await Promise.all([
      apiFetch<any[]>(`/purchases/?search=${encodeURIComponent(q)}&limit=20`).catch(() => []),
      numberQuery
        ? apiFetch<any[]>(`/purchases/?search=${encodeURIComponent('-' + numberQuery)}&limit=20`).catch(() => [])
        : Promise.resolve([] as any[]),
      apiFetch<any[]>(`/contractors/?search=${encodeURIComponent(q)}`).catch(() => []),
    ])
    const exact = (byNumber || []).filter(x => numberQuery && String(x.registry_number || '').endsWith(numberQuery))
    const seen = new Set<number>()
    const ordered = [...exact, ...(byNumber || []), ...(p || [])]
      .filter(x => (seen.has(x.id) ? false : (seen.add(x.id), true)))
    purchases.value = ordered.slice(0, 20).map(x => ({
      id: x.id,
      title: [x.registry_number, x.subject || x.item_name].filter(Boolean).join(' · ') || `Закупка #${x.id}`,
      subtitle: [purchaseStatusLabel(x.status), x.subsidy_name, x.contractor_name].filter(Boolean).join(' · '),
    }))
    contractors.value = (c || []).slice(0, 5).map(x => ({
      id: x.id,
      title: x.name,
      subtitle: x.inn ? `ИНН: ${x.inn}` : '',
    }))
  } finally {
    loading.value = false
  }
}

const results = computed(() => [...purchases.value, ...contractors.value])

const groupedResults = computed((): ResultGroup[] => {
  const groups: ResultGroup[] = []
  if (purchases.value.length) {
    groups.push({ type: 'purchase', label: 'Закупки', icon: 'mdi-clipboard-list', items: purchases.value })
  }
  if (contractors.value.length) {
    groups.push({ type: 'contractor', label: 'Контрагенты', icon: 'mdi-account-group', items: contractors.value })
  }
  return groups
})

function navigate(item: SearchResult, type: string) {
  globalDialog.value = false
  if (type === 'purchase') router.push(`/orders/${item.id}`)
  else if (type === 'contractor') router.push(`/contractors`)
}
</script>

<style scoped>
.search-input :deep(.v-field__input) { font-size: 16px; }
.search-result-item { cursor: pointer; }
.search-result-item:hover { background: var(--crm-surface-hover); }
</style>
