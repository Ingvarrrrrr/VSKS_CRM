<template>
  <div>
    <v-autocomplete
      :model-value="modelValue"
      :items="contractors"
      item-title="name"
      item-value="id"
      :label="label"
      variant="outlined"
      density="compact"
      clearable
      auto-select-first
      :custom-filter="contractorFilter"
      :loading="contractorSearchLoading"
      :no-data-text="noDataText"
      :menu-props="{ maxWidth: 500 }"
      :hint="hint"
      persistent-hint
      @update:model-value="onSelect"
      @update:search="onContractorSearch"
      @update:focused="onFocused"
      @click:clear="$emit('clear')"
    >
      <template #item="{ item, props: itemProps }">
        <v-list-item v-bind="itemProps" :title="undefined">
          <template #title>
            <span style="white-space:normal;word-break:break-word;line-height:1.4">{{ item.raw.name }}</span>
          </template>
          <template #subtitle>
            <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
          </template>
        </v-list-item>
      </template>
      <template #append-inner>
        <v-btn icon="mdi-account-plus" size="x-small" variant="text" color="teal"
          title="Добавить контрагента" @click.stop="openAddContractor" />
      </template>
    </v-autocomplete>

    <!-- Add contractor dialog (shared full create/edit dialog) -->
    <ContractorEditDialog v-model="addContractorDialog" :contractor-id="null" @saved="onContractorCreated" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useContractorsStore } from '@/stores/contractors'
import ContractorEditDialog from '@/components/ContractorEditDialog.vue'
import { useToast, type ToastType } from '@/composables/useToast'

interface Contractor { id: number; name: string; inn?: string }

const props = defineProps<{
  modelValue: number | null
  label?: string
  hint?: string
  initialContractor?: Contractor | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: number | null): void
  (e: 'select', c: Contractor | null): void
  (e: 'clear'): void
}>()

const label = computed(() => props.label || 'Контрагент')
const hint = computed(() => props.hint || 'Поставщик/исполнитель. Поиск по названию или ИНН')

const contractorsStore = useContractorsStore()
const contractors = ref<Contractor[]>([])

watch(() => props.initialContractor, (c) => {
  if (c && c.id && !contractors.value.find(x => x.id === c.id)) contractors.value.push({ ...c })
}, { immediate: true })

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') { toast.addToast(text, color) }

const contractorFilter = (value: string, query: string, item?: any): boolean => {
  const q = query.toLowerCase()
  const name = (item?.raw?.name || '').toLowerCase()
  const inn = (item?.raw?.inn || '').toLowerCase()
  return name.includes(q) || inn.includes(q)
}

// Жалоба владельца (2026-08-21): пустой список при открытии поля показывал
// английскую заглушку Vuetify "No data available". Подгружаем первую страницу
// контрагентов заранее (без ввода), серверный поиск при вводе не трогаем.
const initialLoading = ref(false)
const initialLoaded = ref(false)
async function loadInitialContractors() {
  if (initialLoaded.value || initialLoading.value) return
  initialLoading.value = true
  try {
    const list = await contractorsStore.search('', 50)
    const existing = new Set(contractors.value.map(c => c.id))
    for (const c of list) if (!existing.has(c.id)) contractors.value.push(c as Contractor)
  } finally {
    initialLoading.value = false
    initialLoaded.value = true
  }
}
onMounted(loadInitialContractors)
function onFocused(focused: boolean) {
  if (focused) loadInitialContractors()
}

const contractorSearchLoading = computed(() => contractorsStore.searching || initialLoading.value)
const noDataText = computed(() => {
  if (contractorSearchLoading.value) return 'Загрузка…'
  if (contractors.value.length === 0) {
    return 'В справочнике пока нет контрагентов — начните вводить название или ИНН, либо добавьте нового'
  }
  return 'Ничего не найдено'
})

let _searchTimeout: any = null
function onContractorSearch(query: string) {
  clearTimeout(_searchTimeout)
  if (!query || query.length < 2) return
  _searchTimeout = setTimeout(async () => {
    const list = await contractorsStore.search(query, 50)
    const existing = new Set(contractors.value.map(c => c.id))
    for (const c of list) if (!existing.has(c.id)) contractors.value.push(c as Contractor)
  }, 300)
}
function onSelect(id: number | null) {
  emit('update:modelValue', id)
  emit('select', contractors.value.find(c => c.id === id) || null)
}

const addContractorDialog = ref(false)

function openAddContractor() {
  addContractorDialog.value = true
}

function onContractorCreated(c: any) {
  if (c && c.id && !contractors.value.find(x => x.id === c.id)) {
    contractors.value.push(c as Contractor)
  }
  contractorsStore.putToCache(c)
  emit('update:modelValue', c.id)
  emit('select', c)
  addContractorDialog.value = false
  showSnack('Контрагент добавлен')
}
</script>
