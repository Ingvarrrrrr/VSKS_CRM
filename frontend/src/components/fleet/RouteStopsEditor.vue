<template>
  <div class="route-stops">
    <div
      v-for="(stop, i) in modelValue"
      :key="stop.ord"
      class="stop"
      :class="`stop--${stop.kind}`"
    >
      <!-- Ord badge -->
      <div class="stop__ord">{{ ordLabel(stop, i) }}</div>

      <!-- Content -->
      <div class="stop__body">
        <template v-if="readonly">
          <div class="stop__name">{{ stop.name }}</div>
          <div v-if="stop.description" class="stop__desc">{{ stop.description }}</div>
        </template>
        <template v-else>
          <input
            class="stop__input stop__input--name"
            :value="stop.name"
            placeholder="Название точки"
            @input="updateStop(i, 'name', ($event.target as HTMLInputElement).value)"
          />
          <input
            class="stop__input stop__input--desc"
            :value="stop.description ?? ''"
            placeholder="Описание (необязательно)"
            @input="updateStop(i, 'description', ($event.target as HTMLInputElement).value)"
          />
        </template>
      </div>

      <!-- Planned time -->
      <div class="stop__right">
        <template v-if="readonly">
          <span class="stop__time">{{ formatTime(stop.planned_time) }}</span>
        </template>
        <template v-else>
          <input
            class="stop__input stop__input--time"
            type="datetime-local"
            :value="stop.planned_time ?? ''"
            @input="updateStop(i, 'planned_time', ($event.target as HTMLInputElement).value)"
          />
          <button
            v-if="stop.kind === 'regular'"
            type="button"
            class="stop__delete"
            title="Удалить точку"
            @click="removeStop(i)"
          >🗑</button>
        </template>
      </div>
    </div>

    <!-- Add stop button -->
    <button
      v-if="!readonly"
      type="button"
      class="stop-add"
      @click="addStop"
    >+ Добавить промежуточный стоп</button>
  </div>
</template>

<script setup lang="ts">
export interface RouteStop {
  ord: number
  kind: 'start' | 'regular' | 'end'
  name: string
  description?: string
  planned_time?: string
  actual_time?: string
  lat?: number
  lon?: number
}

const props = withDefaults(defineProps<{
  modelValue: RouteStop[]
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: RouteStop[]): void
}>()

const ORD_LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

function ordLabel(stop: RouteStop, i: number): string {
  if (stop.kind === 'start') return 'A'
  if (stop.kind === 'end') return ORD_LABELS[Math.min(i, ORD_LABELS.length - 1)] ?? 'Z'
  return String(i) // numeric for regular intermediate
}

function formatTime(iso?: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

function updateStop(index: number, field: keyof RouteStop, value: string) {
  const next = props.modelValue.map((s, i) =>
    i === index ? { ...s, [field]: value } : s
  )
  emit('update:modelValue', next)
}

function removeStop(index: number) {
  const next = props.modelValue
    .filter((_, i) => i !== index)
    .map((s, i) => ({ ...s, ord: i + 1 }))
  emit('update:modelValue', next)
}

function addStop() {
  const stops = [...props.modelValue]
  const endIdx = stops.findLastIndex(s => s.kind === 'end')
  const insertAt = endIdx >= 0 ? endIdx : stops.length

  const maxOrd = stops.reduce((m, s) => Math.max(m, s.ord), 0)
  const newStop: RouteStop = {
    ord: maxOrd + 1,
    kind: 'regular',
    name: '',
    description: '',
  }
  stops.splice(insertAt, 0, newStop)
  emit('update:modelValue', stops.map((s, i) => ({ ...s, ord: i + 1 })))
}
</script>

<style scoped>
.route-stops {
  display: grid;
  gap: 6px;
}

.stop {
  display: grid;
  grid-template-columns: 26px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  background: rgba(17, 21, 33, 0.8);
  border: 1px solid var(--line-2, #2b3245);
  border-radius: 10px;
  position: relative;
}

.stop__ord {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(106, 166, 255, 0.15);
  color: var(--accent, #6aa6ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
  flex-shrink: 0;
}

.stop--start .stop__ord {
  background: rgba(34, 201, 151, 0.15);
  color: var(--ok, #22c997);
}

.stop--end .stop__ord {
  background: rgba(255, 91, 106, 0.15);
  color: var(--alert, #ff5b6a);
}

.stop__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stop__name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text, #e9edf5);
}

.stop__desc {
  color: var(--muted, #8a93a8);
  font-size: 11.5px;
}

.stop__input {
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--line, #222838);
  color: var(--text, #e9edf5);
  font-size: 12.5px;
  font-weight: 600;
  font-family: inherit;
  padding: 2px 0;
  outline: none;
  width: 100%;
  transition: border-color 0.15s;
}

.stop__input:focus {
  border-bottom-color: var(--accent, #6aa6ff);
}

.stop__input::placeholder {
  color: var(--muted, #8a93a8);
  font-weight: 500;
}

.stop__input--desc {
  font-weight: 500;
  font-size: 11.5px;
  color: var(--muted, #8a93a8);
}

.stop__input--time {
  color-scheme: dark;
  font-size: 11.5px;
  width: 130px;
}

.stop__right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.stop__time {
  color: var(--muted, #8a93a8);
  font-size: 11.5px;
  font-weight: 600;
}

.stop__delete {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 14px;
  padding: 2px 4px;
  border-radius: 6px;
  opacity: 0.5;
  transition: opacity 0.15s;
}
.stop__delete:hover {
  opacity: 1;
}

.stop-add {
  padding: 10px 12px;
  background: transparent;
  border: 1px dashed var(--line-2, #2b3245);
  border-radius: 10px;
  color: var(--muted, #8a93a8);
  font-weight: 600;
  font-size: 12.5px;
  cursor: pointer;
  text-align: center;
  font-family: inherit;
  width: 100%;
  transition: border-color 0.15s, color 0.15s;
}
.stop-add:hover {
  border-color: var(--accent, #6aa6ff);
  color: var(--accent, #6aa6ff);
}
</style>
