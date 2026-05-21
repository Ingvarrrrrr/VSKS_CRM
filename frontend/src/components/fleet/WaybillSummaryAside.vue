<template>
  <div class="wb-aside">
    <!-- Sticky header -->
    <div class="wb-aside__header">Сводка</div>

    <!-- 2×3 metrics grid -->
    <div class="wb-aside__metrics">
      <div class="wb-aside__metric">
        <div class="wb-aside__metric-label">№ п/л</div>
        <div class="wb-aside__metric-val wb-aside__metric-val--mono">{{ waybill.number }}</div>
      </div>
      <div class="wb-aside__metric">
        <div class="wb-aside__metric-label">Дата</div>
        <div class="wb-aside__metric-val">{{ dateLabel }}</div>
      </div>
      <div class="wb-aside__metric" :class="inspectClass">
        <div class="wb-aside__metric-label">Тех./мед.</div>
        <div class="wb-aside__metric-val">{{ inspectLabel }}</div>
      </div>
      <div class="wb-aside__metric" :class="fillClass">
        <div class="wb-aside__metric-label">Заполнено</div>
        <div class="wb-aside__metric-val">{{ waybill.fill_percent ?? 0 }}%</div>
      </div>
      <div class="wb-aside__metric">
        <div class="wb-aside__metric-label">Пробег план</div>
        <div class="wb-aside__metric-val">{{ mileageLabel }}</div>
      </div>
      <div class="wb-aside__metric">
        <div class="wb-aside__metric-label">Время в пути</div>
        <div class="wb-aside__metric-val">{{ durationLabel }}</div>
      </div>
    </div>

    <!-- Timeline events -->
    <div class="wb-aside__section">
      <div class="wb-aside__section-title">История</div>
      <TimelineHistory :events="timelineEvents" />
    </div>

    <!-- Related documents -->
    <div class="wb-aside__section">
      <div class="wb-aside__section-title">Связанные документы</div>
      <div class="wb-aside__docs">
        <div
          v-for="doc in relatedDocs"
          :key="doc.title"
          class="wb-aside__doc"
        >
          <div class="wb-aside__doc-icon">
            <v-icon size="16">mdi-file-document-outline</v-icon>
          </div>
          <div class="wb-aside__doc-info">
            <div class="wb-aside__doc-name">{{ doc.title }}</div>
            <div v-if="doc.description" class="wb-aside__doc-desc">{{ doc.description }}</div>
          </div>
          <button type="button" class="wb-aside__doc-open" title="Открыть">↗</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TimelineHistory, { type TimelineEvent } from './TimelineHistory.vue'

export interface WaybillStatusHistoryItem {
  id: number | string
  status: string
  changed_at?: string
  changed_by?: string
  note?: string
}

export interface Waybill {
  id: number | string
  number: string
  date?: string
  valid_from?: string
  valid_to?: string
  fill_percent?: number
  planned_mileage_km?: number
  planned_duration_h?: number
  tech_inspect_ok?: boolean
  med_inspect_ok?: boolean
  status_history?: WaybillStatusHistoryItem[]
  related_docs?: Array<{ title: string; description?: string; url?: string }>
}

const props = defineProps<{
  waybill: Waybill
}>()

// Date label
const dateLabel = computed(() => {
  const d = props.waybill.date ?? props.waybill.valid_from
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })
  } catch { return d }
})

// Inspect status
const inspectLabel = computed(() => {
  const t = props.waybill.tech_inspect_ok ? 1 : 0
  const m = props.waybill.med_inspect_ok  ? 1 : 0
  return `${t + m}/2 ${t + m === 2 ? '✓' : ''}`
})

const inspectClass = computed(() =>
  props.waybill.tech_inspect_ok && props.waybill.med_inspect_ok
    ? 'wb-aside__metric--ok'
    : 'wb-aside__metric--warn'
)

// Fill percent
const fillClass = computed(() => {
  const p = props.waybill.fill_percent ?? 0
  return p >= 80 ? 'wb-aside__metric--ok' : p >= 40 ? 'wb-aside__metric--warn' : ''
})

// Mileage
const mileageLabel = computed(() => {
  const m = props.waybill.planned_mileage_km
  return m !== undefined ? `${m.toLocaleString('ru-RU')} км` : '—'
})

// Duration
const durationLabel = computed(() => {
  const h = props.waybill.planned_duration_h
  return h !== undefined ? `${h} ч.` : '—'
})

// Build timeline events from status_history
const STATUS_LABELS: Record<string, string> = {
  created:      'Создан',
  tech_inspect: 'Тех. осмотр пройден',
  med_inspect:  'Медосмотр пройден',
  in_progress:  'В пути',
  closing:      'Закрытие',
  on_review:    'На проверке',
  closed:       'Закрыт',
  overdue:      'Просрочен',
}

const timelineEvents = computed<TimelineEvent[]>(() => {
  const history = props.waybill.status_history ?? []
  if (!history.length) return []

  const lastIdx = history.length - 1
  return history.map((h, i): TimelineEvent => ({
    id: h.id,
    status: i < lastIdx ? 'done' : 'active',
    title: STATUS_LABELS[h.status] ?? h.status,
    description: h.note,
    timestamp: h.changed_at,
    user: h.changed_by,
  }))
})

// Related docs: use provided or fallback placeholders
const relatedDocs = computed(() => {
  if (props.waybill.related_docs?.length) return props.waybill.related_docs
  return [
    { title: 'Заявка на ТС', description: 'Placeholder — данные появятся после привязки' },
    { title: 'Накладная',    description: 'Placeholder — данные появятся после привязки' },
    { title: 'ОСАГО',        description: 'Placeholder — данные появятся после привязки' },
  ]
})
</script>

<style scoped>
.wb-aside {
  display: grid;
  gap: 14px;
}

.wb-aside__header {
  font-size: 14px;
  font-weight: 700;
  color: var(--text, #e9edf5);
  position: sticky;
  top: 0;
  background: var(--panel, #141823);
  padding: 4px 0;
  z-index: 1;
}

/* Metrics 2×3 grid */
.wb-aside__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.wb-aside__metric {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line, #222838);
  border-radius: 10px;
  padding: 10px 12px;
}

.wb-aside__metric--ok   { border-color: rgba(34,  201, 151, 0.3); }
.wb-aside__metric--warn { border-color: rgba(246, 179, 74,  0.3); }

.wb-aside__metric-label {
  color: var(--muted, #8a93a8);
  font-size: 10.5px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.wb-aside__metric-val {
  font-weight: 800;
  font-size: 15px;
  margin-top: 3px;
  letter-spacing: -0.3px;
  color: var(--text, #e9edf5);
}

.wb-aside__metric-val--mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  letter-spacing: 0.2px;
}

.wb-aside__metric--ok   .wb-aside__metric-val { color: var(--ok,   #22c997); }
.wb-aside__metric--warn .wb-aside__metric-val { color: var(--warn, #f6b34a); }

/* Section */
.wb-aside__section {
  display: grid;
  gap: 8px;
}

.wb-aside__section-title {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--muted, #8a93a8);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

/* Docs */
.wb-aside__docs {
  display: grid;
  gap: 6px;
}

.wb-aside__doc {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line, #222838);
  border-radius: 10px;
}

.wb-aside__doc-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: rgba(106, 166, 255, 0.1);
  color: var(--accent, #6aa6ff);
  display: flex;
  align-items: center;
  justify-content: center;
}

.wb-aside__doc-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text, #e9edf5);
}

.wb-aside__doc-desc {
  font-size: 11px;
  color: var(--muted, #8a93a8);
  margin-top: 1px;
}

.wb-aside__doc-open {
  background: transparent;
  border: none;
  color: var(--muted, #8a93a8);
  cursor: pointer;
  font-size: 14px;
  padding: 2px 4px;
  border-radius: 6px;
  transition: color 0.15s;
}
.wb-aside__doc-open:hover {
  color: var(--accent, #6aa6ff);
}
</style>
