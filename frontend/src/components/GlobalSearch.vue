<template>
  <div>
    <v-btn
      variant="outlined"
      prepend-icon="mdi-magnify"
      size="small"
      color="grey"
      @click="open = true"
      class="global-search-btn"
    >
      Поиск...
      <v-chip size="x-small" variant="text" class="ml-1 text-grey">Ctrl+K</v-chip>
    </v-btn>

    <v-dialog v-model="open" max-width="600" :retain-focus="false">
      <v-card>
        <v-text-field
          v-model="query"
          placeholder="Поиск закупок, контрагентов, договоров..."
          variant="solo"
          flat
          hide-details
          prepend-inner-icon="mdi-magnify"
          clearable
          autofocus
          @keyup.esc="open = false"
          class="search-input"
        />
        <v-divider />
        <div v-if="loading" class="d-flex justify-center pa-6">
          <v-progress-circular indeterminate size="24" />
        </div>
        <div v-else-if="query.length > 1 && results.length === 0" class="pa-4 text-center text-medium-emphasis text-caption">
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
        <div v-else-if="query.length === 0" class="pa-4 text-caption text-medium-emphasis text-center">
          Введите запрос (минимум 2 символа)
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const router = useRouter()
const open = ref(false)
const query = ref('')
const loading = ref(false)

interface SearchResult { id: number; title: string; subtitle?: string }
interface ResultGroup { type: string; label: string; icon: string; items: SearchResult[] }

const purchases = ref<SearchResult[]>([])
const contractors = ref<SearchResult[]>([])

// Keyboard shortcut Ctrl+K
const handleKeydown = (e: KeyboardEvent) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    open.value = true
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handleKeydown)
}

let searchTimeout: ReturnType<typeof setTimeout> | null = null

watch(query, (q) => {
  if (q.length < 2) {
    purchases.value = []
    contractors.value = []
    return
  }
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => doSearch(q), 300)
})

watch(open, (v) => {
  if (!v) {
    query.value = ''
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
      subtitle: [x.subsidy_name, x.contractor_name, x.status ? x.status : ''].filter(Boolean).join(' · '),
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
  open.value = false
  if (type === 'purchase') router.push(`/orders/${item.id}`)
  else if (type === 'contractor') router.push(`/contractors`)
}
</script>

<style scoped>
.global-search-btn { min-width: 180px; justify-content: flex-start; }
.search-input :deep(.v-field__input) { font-size: 16px; }
.search-result-item { cursor: pointer; }
.search-result-item:hover { background: var(--crm-surface-hover); }
</style>
