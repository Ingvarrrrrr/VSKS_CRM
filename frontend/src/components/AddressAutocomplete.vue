<template>
  <v-combobox
    :model-value="modelValue"
    @update:model-value="onUpdate"
    :items="combinedItems"
    :label="label"
    variant="outlined" density="compact"
    clearable
    :hint="hint"
    :persistent-hint="persistentHint"
    @blur="onBlur"
  >
    <template #item="{ props: itemProps, item }">
      <v-list-item v-bind="itemProps" :title="item.raw">
        <template #prepend>
          <v-icon v-if="defaultAddresses.includes(item.raw)" icon="mdi-star-outline" size="14" color="primary" />
          <v-icon v-else icon="mdi-history" size="14" color="grey" />
        </template>
      </v-list-item>
    </template>
  </v-combobox>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

const props = defineProps<{
  modelValue: string | null
  label?: string
  hint?: string
  persistentHint?: boolean
  customerAddress?: string  // юр.адрес организации Заказчика
  ownOrgAddress?: string    // юр.адрес собственной организации пользователя
}>()
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

const userAddresses = ref<{id: number; address: string}[]>([])

const defaultAddresses = computed(() => {
  // Доработка 5 мая: формулировка из ТЗ заказчика — «По месту нахождения подрядчика»
  // (плюс юр.адрес заказчика и юр.адрес собственной организации сотрудника).
  const arr = ['По месту нахождения подрядчика']
  if (props.ownOrgAddress?.trim() && !arr.includes(props.ownOrgAddress)) {
    arr.push(props.ownOrgAddress)
  }
  if (props.customerAddress?.trim() && !arr.includes(props.customerAddress)) {
    arr.push(props.customerAddress)
  }
  return arr
})

const combinedItems = computed(() => {
  const all = [
    ...defaultAddresses.value,
    ...userAddresses.value.map(a => a.address).filter(a => !defaultAddresses.value.includes(a)),
  ]
  return all
})

async function load() {
  try {
    userAddresses.value = await apiFetch<any[]>('/user-addresses/')
  } catch { userAddresses.value = [] }
}
onMounted(load)

function onUpdate(v: string | null) {
  emit('update:modelValue', v ?? '')
}

async function onBlur() {
  const v = (props.modelValue || '').trim()
  if (v && v.length >= 3 && !defaultAddresses.value.includes(v)) {
    try { await apiFetch('/user-addresses/', { method: 'POST', body: { address: v } }) } catch {}
  }
}
</script>
