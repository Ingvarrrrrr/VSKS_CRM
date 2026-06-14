<template>
  <v-dialog v-model="show" max-width="600" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="teal">mdi-link-variant-plus</v-icon>
        Изменить привязку к каталогу
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="show = false" />
      </v-card-title>
      <v-card-text class="pa-4">
        <div v-if="itemName" class="text-caption text-medium-emphasis mb-3">
          Позиция: <strong>{{ itemName }}</strong>
        </div>
        <v-autocomplete
          v-model="selected"
          v-model:search="searchQuery"
          :items="searchResults"
          item-title="name"
          item-value="product_id"
          return-object
          density="compact"
          variant="outlined"
          clearable
          autofocus
          :loading="loading"
          placeholder="Введите название товара..."
          prepend-inner-icon="mdi-magnify"
          no-data-text="Начните вводить название (мин. 2 символа)"
          @update:search="onSearch"
        >
          <template #item="{ item: it, props: ip }">
            <v-list-item v-bind="ip">
              <template #subtitle>
                <span v-if="it.raw.category" class="text-caption text-medium-emphasis">
                  {{ it.raw.category }}
                  <span v-if="it.raw.item_type"> · {{ it.raw.item_type }}</span>
                </span>
                <span v-if="it.raw.price" class="text-caption ml-2">
                  {{ Number(it.raw.price).toLocaleString('ru-RU') }} ₽
                </span>
              </template>
            </v-list-item>
          </template>
        </v-autocomplete>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="teal" variant="elevated" :disabled="!selected" @click="apply">
          Применить привязку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

const { mobile } = useDisplay()

interface CatalogCandidate {
  product_id: number
  name: string
  price: number | null
  description?: string | null
  photo_url?: string | null
  item_type?: string | null
  category?: string | null
}

const props = defineProps<{
  modelValue: boolean
  itemName?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'pick', candidate: CatalogCandidate): void
}>()

const show = computed({ get: () => props.modelValue, set: v => emit('update:modelValue', v) })

const searchQuery = ref('')
const searchResults = ref<CatalogCandidate[]>([])
const selected = ref<CatalogCandidate | null>(null)
const loading = ref(false)

// Pre-fill search with item name
watch(() => props.modelValue, (v) => {
  if (v) {
    searchQuery.value = props.itemName || ''
    selected.value = null
    if (searchQuery.value.length >= 2) onSearch(searchQuery.value)
  }
})

let _debounceTimer: ReturnType<typeof setTimeout> | null = null

function onSearch(query: string) {
  searchQuery.value = query
  if (_debounceTimer) clearTimeout(_debounceTimer)
  if (!query || query.length < 2) {
    searchResults.value = []
    return
  }
  _debounceTimer = setTimeout(() => fetchResults(query), 300)
}

async function fetchResults(query: string) {
  loading.value = true
  try {
    const data = await apiFetch<any>(`/products/?search=${encodeURIComponent(query)}&limit=20`)
    const items: any[] = Array.isArray(data) ? data : (data.results ?? [])
    searchResults.value = items.map(p => ({
      product_id: p.id,
      name: p.name,
      price: p.price ?? p.contract_price ?? null,
      description: p.description ?? null,
      photo_url: p.photo_url ?? p.photo_link ?? null,
      item_type: p.product_type ?? null,
      category: p.category ?? null,
    }))
  } catch {
    searchResults.value = []
  } finally {
    loading.value = false
  }
}

function apply() {
  if (!selected.value) return
  emit('pick', selected.value)
}
</script>
