<template>
  <!-- Drawer справа — таблица остаётся видимой для live preview изменений колонок -->
  <v-navigation-drawer
    v-model="dialog"
    location="right"
    temporary
    :scrim="false"
    width="520"
    class="column-config-drawer"
  >
    <div class="d-flex align-center pa-3" style="border-bottom: 1px solid rgba(0,0,0,0.08);">
      <v-icon icon="mdi-view-column" class="mr-2" />
      <span class="text-subtitle-1 font-weight-medium">Настройка колонок</span>
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="dialog = false" />
    </div>

    <v-tabs v-if="hasGroups" v-model="tab" color="primary" density="compact" grow>
      <v-tab v-for="g in groups" :key="g.key" :value="g.key">{{ g.label }}</v-tab>
    </v-tabs>

    <div class="pa-3" style="overflow-y: auto; height: calc(100% - 130px);">
      <div v-for="col in displayedColumns" :key="col.key" class="d-flex align-center py-2 column-row">
        <v-checkbox
          :model-value="state.visible.includes(col.key)"
          density="compact"
          hide-details
          class="mr-2"
          style="flex: 0 0 auto;"
          @update:model-value="toggleVisible(col.key, $event as boolean)"
        />
        <div class="flex-grow-1 text-body-2 text-truncate" :title="col.title">{{ col.title }}</div>
        <v-select
          v-if="state.visible.includes(col.key) && state.visible.length >= 2"
          :model-value="visiblePosition(col.key)"
          :items="orderOptions"
          density="compact"
          variant="outlined"
          hide-details
          label="№"
          style="max-width: 80px;"
          class="mr-2"
          @update:model-value="setPosition(col.key, $event as number)"
        />
        <v-text-field
          v-if="showWidth && state.visible.includes(col.key)"
          :model-value="state.widths[col.key] ?? col.width ?? 120"
          type="number"
          min="40"
          max="800"
          density="compact"
          variant="outlined"
          hide-details
          label="px"
          style="max-width: 80px;"
          @update:model-value="setWidth(col.key, Number($event))"
        />
      </div>
    </div>

    <div class="d-flex align-center pa-2" style="border-top: 1px solid rgba(0,0,0,0.08); position: absolute; bottom: 0; left: 0; right: 0; background: white;">
      <v-btn variant="text" color="error" size="small" @click="reset">Сбросить</v-btn>
      <v-spacer />
      <v-btn color="primary" variant="tonal" size="small" @click="dialog = false">Готово</v-btn>
    </div>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import type { ColumnDef, ColumnConfigState } from '@/composables/useColumnConfig'

const props = defineProps<{
  modelValue: boolean
  allColumns: MaybeRefOrGetter<ColumnDef[]>
  state: ColumnConfigState
  showWidth?: boolean  // отключаем для таблиц без resize
  groups?: { key: string; label: string }[]  // если есть табы
  toggleVisible: (key: string, show: boolean) => void
  setPosition: (key: string, pos: number) => void
  setWidth: (key: string, px: number) => void
  reset: () => void
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const dialog = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v),
})

const tab = ref(props.groups?.[0]?.key ?? '')
const hasGroups = computed(() => (props.groups?.length ?? 0) > 1)

const allColumnsList = computed(() => toValue(props.allColumns))

const displayedColumns = computed(() => {
  if (!hasGroups.value) return allColumnsList.value
  return allColumnsList.value.filter(c => (c.group ?? '') === tab.value)
})

function visiblePosition(key: string): number {
  const visibleOrdered = props.state.order.filter(k => props.state.visible.includes(k))
  return visibleOrdered.indexOf(key) + 1
}

const orderOptions = computed(() => {
  const count = props.state.visible.length
  return Array.from({ length: count }, (_, i) => i + 1)
})
</script>

<style scoped>
.column-row { border-bottom: 1px solid rgba(0, 0, 0, 0.06); }
.column-row:last-child { border-bottom: none; }
</style>
