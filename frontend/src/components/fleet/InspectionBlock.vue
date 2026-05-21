<template>
  <div class="insp-block">
    <!-- Header -->
    <div class="insp-block__header">
      <GradientAvatar :full-name="inspectorName" size="sm" />
      <div class="insp-block__title-group">
        <div class="insp-block__title">{{ blockTitle }}</div>
        <div class="insp-block__phase">{{ phaseLabel }}</div>
      </div>
      <div class="insp-block__status">
        <v-chip
          v-if="isSigned"
          color="success"
          size="x-small"
          variant="tonal"
          prepend-icon="mdi-check"
        >Подписано {{ signedAt }}</v-chip>
        <v-chip v-else size="x-small" variant="tonal" color="default">Ожидается</v-chip>
      </div>
    </div>

    <!-- Fields -->
    <div class="insp-block__fields">
      <v-autocomplete
        :model-value="inspectorId"
        :items="users"
        :item-title="userLabel"
        item-value="id"
        :label="selectorLabel"
        :readonly="readonly"
        variant="outlined"
        density="compact"
        prepend-inner-icon="mdi-account"
        clearable
        @update:model-value="v => emit('update:inspectorId', v)"
      />

      <v-text-field
        :model-value="inspectedAt"
        label="Дата и время осмотра"
        type="datetime-local"
        :readonly="readonly"
        variant="outlined"
        density="compact"
        prepend-inner-icon="mdi-calendar-clock"
        @update:model-value="v => emit('update:inspectedAt', v)"
      />

      <v-textarea
        :model-value="result"
        :label="resultLabel"
        :placeholder="resultPlaceholder"
        :readonly="readonly"
        variant="outlined"
        density="compact"
        rows="2"
        auto-grow
        @update:model-value="v => emit('update:result', v)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GradientAvatar from './GradientAvatar.vue'

export interface User {
  id: number
  fullName: string
  role?: string
}

const props = withDefaults(defineProps<{
  kind: 'mechanic' | 'doctor'
  phase: 'pre' | 'post'
  inspectorId?: number
  inspectedAt?: string
  result?: string
  readonly?: boolean
  users: User[]
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'update:inspectorId', v: number | null): void
  (e: 'update:inspectedAt', v: string): void
  (e: 'update:result',      v: string): void
}>()

function userLabel(u: User): string {
  return u.fullName + (u.role ? ` (${u.role})` : '')
}

const blockTitle = computed(() =>
  props.kind === 'mechanic' ? 'Тех. осмотр' : 'Медосмотр'
)

const phaseLabel = computed(() => {
  const p = props.phase === 'pre' ? 'Предрейсовый' : 'Послерейсовый'
  const k = props.kind === 'mechanic' ? 'тех. осмотр' : 'медосмотр'
  return `${p} ${k}`
})

const selectorLabel = computed(() =>
  props.kind === 'mechanic' ? 'Механик' : 'Медицинский работник'
)

const resultLabel = computed(() => 'Результат осмотра')

const resultPlaceholder = computed(() =>
  props.kind === 'doctor'
    ? 'АД 120/80, пульс 72. К рейсу допущен.'
    : 'ТС исправно, тормоза проверены. К эксплуатации допущено.'
)

const inspectorName = computed<string>(() => {
  if (!props.inspectorId) return ''
  const u = props.users.find(u => u.id === props.inspectorId)
  return u?.fullName ?? ''
})

const isSigned = computed(() =>
  Boolean(props.inspectorId && props.inspectedAt)
)

const signedAt = computed(() => {
  if (!props.inspectedAt) return ''
  try {
    return new Date(props.inspectedAt).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return props.inspectedAt
  }
})
</script>

<style scoped>
.insp-block {
  display: grid;
  gap: 12px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line, #222838);
  border-radius: 12px;
}

.insp-block__header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  align-items: center;
}

.insp-block__title-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.insp-block__title {
  font-weight: 700;
  font-size: 13.5px;
  color: var(--text, #e9edf5);
}

.insp-block__phase {
  font-size: 10.5px;
  color: var(--muted, #8a93a8);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.4px;
}

.insp-block__status {
  flex-shrink: 0;
}

.insp-block__fields {
  display: grid;
  gap: 8px;
}
</style>
