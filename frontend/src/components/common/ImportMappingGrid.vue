<template>
  <div class="imap-grid">
    <div v-for="target in targetFields" :key="target.key"
      class="imap-col"
      :class="{
        'imap-col--over': dragOverTarget === target.key,
        'imap-col--filled': isTargetFilled(target.key),
        'imap-col--required': target.required && !isTargetFilled(target.key),
      }"
      @dragover.prevent="dragOverTarget = target.key"
      @dragleave="dragOverTarget = null"
      @drop.prevent="onDropToTarget(target.key, $event)">
      <div class="imap-col-hdr">
        {{ target.label }}<span v-if="target.required" class="imap-col-req">*</span>
        <div v-if="target.hint" class="imap-col-hint">{{ target.hint }}</div>
      </div>
      <div class="imap-col-body">
        <div v-if="isTargetFilled(target.key)"
          class="imap-card"
          draggable="true"
          @dragstart="onDragStart(modelValue[target.key] as number, $event)">
          <div class="imap-card-row">
            <span class="imap-card-name">{{ columnLabel(modelValue[target.key] as number) }}</span>
            <button type="button" class="imap-card-x" title="Убрать сопоставление" @click.stop="unmapTarget(target.key)">×</button>
          </div>
          <div v-if="approximateFields?.includes(target.key)" class="imap-card-approx" title="Подобрано по совпадению части заголовка — проверьте">предположительно</div>
          <div class="imap-card-samples">{{ samples(modelValue[target.key] as number).join(', ') || '—' }}</div>
        </div>
        <div v-else class="imap-col-empty">—</div>
      </div>
    </div>
  </div>

  <div class="imap-unresolved mt-3"
    :class="{ 'imap-unresolved--over': dragOverTarget === '_unresolved' }"
    @dragover.prevent="dragOverTarget = '_unresolved'"
    @dragleave="dragOverTarget = null"
    @drop.prevent="onDropToUnresolved($event)">
    <span class="imap-unresolved-label">Не определилось</span>
    <div class="d-flex gap-2 flex-wrap mt-1">
      <template v-for="(_, idx) in headers" :key="idx">
        <div v-if="!isMapped(idx) && !isIgnored(idx)"
          class="imap-card imap-card--free"
          draggable="true"
          @dragstart="onDragStart(idx, $event)">
          <div class="imap-card-row">
            <span class="imap-card-name">{{ columnLabel(idx) }}</span>
            <button type="button" class="imap-card-x imap-card-x--grey" title="Убрать" @click.stop="ignoreColumn(idx)">×</button>
          </div>
          <div class="imap-card-samples">{{ samples(idx).join(', ') || '—' }}</div>
        </div>
      </template>
      <span v-if="unmappedCount === 0" class="imap-unresolved-done">все распределены ✓</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// ImportMappingGrid.vue — общая drag&drop сетка сопоставления колонок Excel
// полям сущности. Вынесена из FeoImportMappingStep.vue (план
// dreamy-booping-piglet.md, задача B, п.5) — теперь используется и мастером
// ФЭО (FeoImportMappingStep.vue как тонкая обёртка), и мастером импорта
// товаров (ProductsImportDialog.vue). Поведение (drag/drop, подсветка
// обязательных незаполненных полей, «Не определилось») скопировано дословно,
// только имена полей обобщены (headers/sampleRows/targetFields/modelValue).
import { computed, ref } from 'vue'

export interface ImportMappingTargetField {
  key: string
  label: string
  required?: boolean
  hint?: string
}

const props = defineProps<{
  headers: string[]
  sampleRows: any[][]
  targetFields: ImportMappingTargetField[]
  modelValue: Record<string, number | null>
  ignoredColumns?: number[]
  // Ключи target-полей, подставленных «вторым проходом» подсказки маппинга
  // (например products_import_map.py::suggest_products_column_mapping_with_hints)
  // — заголовок не совпал буквально с эталоном, а подошёл по префиксу/слову.
  // Владелец, 2026-09-09: такие карточки нужно явно пометить — иначе
  // пользователь не глядя доверяет подсказке ровно там, где она рискованнее.
  approximateFields?: string[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, number | null>): void
  (e: 'update:ignoredColumns', value: number[]): void
}>()

const dragOverTarget = ref<string | null>(null)

const ignored = computed(() => props.ignoredColumns || [])

const unmappedCount = computed(() =>
  props.headers.filter((_, i) => !isMapped(i) && !isIgnored(i)).length
)

function isMapped(idx: number): boolean {
  return Object.values(props.modelValue).includes(idx)
}
function isIgnored(idx: number): boolean {
  return ignored.value.includes(idx)
}
function isTargetFilled(key: string): boolean {
  return props.modelValue[key] != null
}
function columnLabel(idx: number): string {
  return props.headers[idx] || `Столбец ${idx + 1}`
}
function samples(idx: number): string[] {
  return (props.sampleRows || []).slice(0, 3)
    .map((row) => String(row?.[idx] ?? '').trim())
    .filter(Boolean)
}
function clearFromMapping(idx: number): Record<string, number | null> {
  const next = { ...props.modelValue }
  for (const f of Object.keys(next)) {
    if (next[f] === idx) next[f] = null
  }
  return next
}
function onDragStart(idx: number, e: DragEvent) {
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(idx))
}
function onDropToTarget(key: string, e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'), 10)
  if (Number.isNaN(idx)) return
  const next = clearFromMapping(idx)
  next[key] = idx
  emit('update:modelValue', next)
  if (ignored.value.includes(idx)) emit('update:ignoredColumns', ignored.value.filter(i => i !== idx))
  dragOverTarget.value = null
}
function onDropToUnresolved(e: DragEvent) {
  const idx = parseInt(e.dataTransfer!.getData('text/plain'), 10)
  if (!Number.isNaN(idx)) emit('update:modelValue', clearFromMapping(idx))
  dragOverTarget.value = null
}
function unmapTarget(key: string) {
  emit('update:modelValue', { ...props.modelValue, [key]: null })
}
function ignoreColumn(idx: number) {
  emit('update:modelValue', clearFromMapping(idx))
  if (!ignored.value.includes(idx)) emit('update:ignoredColumns', [...ignored.value, idx])
}
</script>

<style scoped>
.imap-grid {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.imap-col {
  flex: 1;
  min-width: 130px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  background: #fafafa;
  transition: border-color 0.15s, background 0.15s;
}
.imap-col--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.imap-col--filled {
  border-style: solid;
  border-color: #43A047;
  background: #f6fff6;
}
.imap-col--required {
  border-color: #ef9a9a;
  background: #fff8f8;
}
.imap-col-hdr {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #555;
  padding: 5px 7px 3px;
  border-bottom: 1px solid #e8e8e8;
  white-space: normal;
  word-break: break-word;
}
.imap-col-req { color: #e53935; }
.imap-col-hint {
  font-size: 10px;
  font-weight: 400;
  text-transform: none;
  color: #999;
  margin-top: 2px;
}
.imap-col-body {
  padding: 5px;
  min-height: 58px;
}
.imap-col-empty {
  font-size: 10px;
  color: #ccc;
  text-align: center;
  margin-top: 10px;
  font-style: italic;
}
.imap-card {
  border-radius: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.imap-card:hover {
  border-color: #1976D2;
  box-shadow: 0 1px 5px rgba(25, 118, 210, 0.15);
}
.imap-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
}
.imap-card-name {
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.imap-card-x {
  font-size: 14px;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #aaa;
  padding: 0 2px;
  flex-shrink: 0;
}
.imap-card-x:hover { color: #e53935; }
.imap-card-x--grey { color: #bbb; }
.imap-card-samples {
  font-size: 10px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.3;
}
.imap-card-approx {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.2px;
  color: #b45309;
  background: #fef3c7;
  border-radius: 3px;
  padding: 1px 4px;
  display: inline-block;
  margin-top: 3px;
}
.imap-card--free {
  background: #fafafa;
}
.imap-unresolved {
  border: 1px dashed #ccc;
  border-radius: 6px;
  padding: 6px 10px;
  min-height: 44px;
  transition: border-color 0.15s, background 0.15s;
}
.imap-unresolved--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.imap-unresolved-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #aaa;
  letter-spacing: 0.3px;
}
.imap-unresolved-done {
  font-size: 11px;
  color: #888;
  align-self: center;
}
</style>
