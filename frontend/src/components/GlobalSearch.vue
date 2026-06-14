<template>
  <div class="d-flex align-center gap-2">
    <v-text-field
      v-model="appSearch"
      prepend-inner-icon="mdi-magnify"
      :placeholder="appSearchScope === 'page' ? 'Поиск по странице...' : 'Поиск по всей базе...'"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      bg-color="white"
      style="width: 260px"
      @keydown.ctrl.k.prevent
    />
    <v-btn-toggle
      v-model="appSearchScope"
      density="compact"
      variant="outlined"
      mandatory
      rounded="lg"
      class="search-scope-toggle"
    >
      <v-btn value="page" size="small">По странице</v-btn>
      <v-btn value="global" size="small">По всей БД</v-btn>
    </v-btn-toggle>

    <!-- Global search results dialog (only when scope=global) -->
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

const router = useRouter()
const { mobile } = useDisplay()
const { appSearch, appSearchScope } = useAppSearch()
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
      appSearchScope.value = 'global'
      globalDialog.value = true
    }
  })
}

let searchTimeout: ReturnType<typeof setTimeout> | null = null

// Open global dialog when switching to global scope with existing query
watch([appSearch, appSearchScope], ([q, scope]) => {
  if (scope === 'global' && (q as string).length >= 2) {
    globalDialog.value = true
    if (searchTimeout) clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => doSearch(q as string), 300)
  }
  if (scope === 'page') {
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
    const [p, c] = await Promise.all([
      apiFetch<any[]>(`/purchases/?search=${encodeURIComponent(q)}&limit=8`).catch(() => []),
      apiFetch<any[]>(`/contractors/?search=${encodeURIComponent(q)}`).catch(() => []),
    ])
    purchases.value = (p || []).slice(0, 8).map(x => ({
      id: x.id,
      title: x.item_name || x.subject || `Закупка #${x.purchase_number || x.id}`,
      subtitle: [x.subsidy_name, x.contractor_name, x.status].filter(Boolean).join(' · '),
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
.search-scope-toggle :deep(.v-btn) {
  color: white !important;
  border-color: rgba(255,255,255,0.5) !important;
  font-size: 12px;
}
.search-scope-toggle :deep(.v-btn--active) {
  background: rgba(255,255,255,0.25) !important;
  color: white !important;
}
.search-input :deep(.v-field__input) { font-size: 16px; }
.search-result-item { cursor: pointer; }
.search-result-item:hover { background: var(--crm-surface-hover); }
</style>
