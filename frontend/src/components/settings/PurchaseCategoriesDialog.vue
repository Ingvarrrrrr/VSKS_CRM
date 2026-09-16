<template>
  <v-dialog :model-value="modelValue" max-width="560" scrollable :fullscreen="mobile" @update:model-value="onDialogModel">
    <v-card>
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-tag-multiple-outline" color="teal" class="mr-2" />
        Справочник категорий закупки
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="$emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="text-caption text-medium-emphasis mb-3">
          По этим категориям товар выставляется в закупку.
        </div>

        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />

        <div v-if="!loading && categories.length === 0" class="text-center text-medium-emphasis py-6">
          Категорий пока нет — добавьте первую ниже.
        </div>

        <div v-for="cat in categories" :key="cat.id" class="pcat-row">
          <template v-if="editingId === cat.id">
            <v-text-field
              v-model="editName"
              density="compact" variant="outlined" hide-details
              class="flex-grow-1"
              autofocus
              @keydown.enter="saveRename(cat.id)"
              @keydown.esc="editingId = null"
            />
            <v-btn icon="mdi-check" variant="text" size="small" color="primary" :loading="savingId === cat.id" @click="saveRename(cat.id)" />
            <v-btn icon="mdi-close" variant="text" size="small" @click="editingId = null" />
          </template>
          <template v-else>
            <span class="flex-grow-1 pcat-name" :class="{ 'text-medium-emphasis': !cat.is_active }">{{ cat.name }}</span>
            <v-chip v-if="!cat.is_active" size="x-small" color="grey" variant="tonal" class="mr-1">выключена</v-chip>
            <v-switch
              :model-value="cat.is_active"
              density="compact" hide-details color="success" class="pcat-switch"
              @update:model-value="v => toggleActive(cat.id, !!v)"
            />
            <v-btn icon="mdi-pencil-outline" variant="text" size="small" @click="startRename(cat)" />
            <template v-if="pendingDeleteId === cat.id">
              <v-btn size="small" variant="tonal" color="error" :loading="savingId === cat.id" @click="doDelete(cat.id)">Точно удалить?</v-btn>
              <v-btn icon="mdi-close" variant="text" size="small" @click="pendingDeleteId = null" />
            </template>
            <v-btn v-else icon="mdi-delete-outline" variant="text" size="small" color="error" @click="pendingDeleteId = cat.id; deleteError = ''" />
          </template>
        </div>

        <v-alert v-if="deleteError" type="error" density="compact" variant="tonal" class="mt-2">
          {{ deleteError }}
        </v-alert>

        <v-divider class="my-4" />

        <div class="d-flex gap-2 align-start">
          <v-text-field
            v-model="newName"
            label="Новая категория"
            variant="outlined" density="compact" hide-details
            class="flex-grow-1"
            @keydown.enter="addNew"
          />
          <v-btn color="primary" prepend-icon="mdi-plus" :loading="adding" :disabled="!newName.trim()" @click="addNew">
            Добавить
          </v-btn>
        </div>
        <v-alert v-if="addError" type="error" density="compact" variant="tonal" class="mt-2">{{ addError }}</v-alert>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePurchaseCategories } from '@/composables/products/usePurchaseCategories'
import type { PurchaseCategory } from '@/composables/products/productsTypes'

const props = defineProps<{
  modelValue: boolean
  mobile: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

// Destructured (не единым объектом) — top-level refs, возвращённые из setup(),
// авто-разворачиваются в шаблоне без `.value` (тот же приём, что и у
// useProductsForm/useProductsData в ProductsView.vue).
const { categories, loading, load, createCategory, updateCategory, removeCategory } = usePurchaseCategories()

watch(() => props.modelValue, (v) => { if (v) load() })

function onDialogModel(v: boolean) {
  emit('update:modelValue', v)
}

const editingId = ref<number | null>(null)
const editName = ref('')
const savingId = ref<number | null>(null)

function startRename(cat: PurchaseCategory) {
  editingId.value = cat.id
  editName.value = cat.name
}

async function saveRename(id: number) {
  const name = editName.value.trim()
  if (!name) return
  savingId.value = id
  const res = await updateCategory(id, { name })
  savingId.value = null
  if (res.ok) editingId.value = null
}

async function toggleActive(id: number, isActive: boolean) {
  await updateCategory(id, { is_active: isActive })
}

const pendingDeleteId = ref<number | null>(null)
const deleteError = ref('')

async function doDelete(id: number) {
  savingId.value = id
  deleteError.value = ''
  const res = await removeCategory(id)
  savingId.value = null
  pendingDeleteId.value = null
  if (!res.ok) deleteError.value = res.error
}

const newName = ref('')
const adding = ref(false)
const addError = ref('')

async function addNew() {
  const name = newName.value.trim()
  if (!name) return
  adding.value = true
  addError.value = ''
  const res = await createCategory(name)
  adding.value = false
  if (res.ok) newName.value = ''
  else addError.value = res.error
}
</script>

<style scoped>
.dialog-title {
  display: flex;
  align-items: center;
  font-size: 16px !important;
  font-weight: 600 !important;
  padding: 16px 20px !important;
}
.pcat-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.pcat-name { word-break: break-word; }
.pcat-switch :deep(.v-selection-control) { min-height: unset; }
</style>
