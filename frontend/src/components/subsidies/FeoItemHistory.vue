<template>
  <div class="feo-item-history">
    <div v-if="loading" class="d-flex align-center py-3">
      <v-progress-circular indeterminate size="20" width="2" color="primary" class="mr-2" />
      <span class="text-caption text-medium-emphasis">Загрузка истории…</span>
    </div>

    <v-alert v-else-if="loadError" type="error" variant="tonal" density="compact" class="text-caption">
      {{ loadError }}
    </v-alert>

    <v-alert v-else-if="!events.length" type="info" variant="tonal" density="compact" class="text-caption">
      История изменений пуста
    </v-alert>

    <div v-else class="feo-history-list">
      <div v-for="(ev, idx) in events" :key="idx" class="feo-history-event">
        <!-- Создание — человеческая формулировка происхождения -->
        <template v-if="ev.isCreated">
          <div class="text-body-2">
            <v-icon icon="mdi-flag-outline" size="14" color="primary" class="mr-1" />
            <span v-if="ev.originLoading">Определяем происхождение…</span>
            <template v-else-if="ev.origin?.kind === 'wish'">
              Создана из заявки №{{ ev.origin.refId }}
              <template v-if="ev.origin.label"> «{{ ev.origin.label }}»</template>
              <a href="#" class="ml-1" @click.prevent="openWish(ev.origin!.refId!)">открыть</a>
            </template>
            <template v-else-if="ev.origin?.kind === 'purchase'">
              Создана из закупки №{{ ev.origin.refId }}
              <template v-if="ev.origin.label"> «{{ ev.origin.label }}»</template>
              <a href="#" class="ml-1" @click.prevent="openPurchase(ev.origin!.refId!)">открыть</a>
            </template>
            <template v-else-if="ev.origin?.kind === 'import'">
              Загружена импортом файла
              <template v-if="ev.origin.label"> «{{ ev.origin.label }}»</template>
              <template v-else> (файл не определён)</template>,
              {{ ev.origin.author || 'автор неизвестен' }}, {{ ev.origin.date || formatDate(ev.changedAt) }}
            </template>
            <template v-else-if="ev.source === 'manual' || (!ev.source && ev.changedByName)">
              Создана вручную{{ ev.changedByName ? `, ${ev.changedByName}` : '' }}
            </template>
            <template v-else-if="ev.source === 'autoassign'">
              Заведена автоматически (закупка/заявка сама стала планом)
            </template>
            <template v-else-if="ev.source === 'collapse'">
              Появилась при объединении дублирующих направлений ФЭО
            </template>
            <template v-else>
              Создана до появления журнала ({{ formatDate(ev.changedAt) }}), автор неизвестен
            </template>
          </div>
        </template>

        <!-- Удаление -->
        <template v-else-if="ev.isDeleted">
          <div class="text-body-2">
            <v-icon icon="mdi-trash-can-outline" size="14" color="error" class="mr-1" />
            Удалена{{ ev.changedByName ? `, ${ev.changedByName}` : '' }}
          </div>
        </template>

        <!-- Обычная правка — список изменённых полей -->
        <template v-else>
          <div class="text-body-2 mb-1">
            <v-icon icon="mdi-pencil-outline" size="14" color="grey" class="mr-1" />
            <span v-if="ev.changedByName">{{ ev.changedByName }}</span>
            <span v-else class="text-medium-emphasis">неизвестный автор</span>
            <v-chip v-if="ev.source && ev.source !== 'manual'" size="x-small" variant="tonal" class="ml-2">
              {{ sourceLabel(ev.source) }}
            </v-chip>
          </div>
          <div v-for="f in ev.fields" :key="f.field_name" class="feo-history-field text-caption mb-1">
            <span class="font-weight-medium">{{ fieldLabel(f.field_name) }}:</span>
            <span class="text-error text-decoration-line-through ml-1">{{ f.old_value ?? '—' }}</span>
            <v-icon icon="mdi-arrow-right" size="11" class="mx-1" />
            <span class="text-success">{{ f.new_value ?? '—' }}</span>
          </div>
        </template>

        <div class="text-caption text-medium-emphasis mt-1">{{ formatDate(ev.changedAt) }}</div>
        <v-divider v-if="idx < events.length - 1" class="my-2" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Лента истории ФЭО (позиция/категория) — волна 3, 26.09. Единственный
// компонент для feo_item И feo_category (тип различает только entityType).
// Данные — GET /api/entity-changes/{type}/{id} (app/routers/entity_changes.py,
// Правило №6: НЕ заводим второй источник истории). Происхождение записи
// «создание» дочитывается по source/source_ref: wish → /wishes/{id},
// purchase → /purchases/{id}, import → /feo-categories/import-runs/{id}
// (см. app/routers/feo_import_runs.py — путь именно такой, не /feo-import-runs,
// см. её докстринг про запрет трогать routes.py).
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { feoHistoryFieldLabel } from '@/constants/feoHistoryFieldLabels'

const props = defineProps<{
  entityType: 'feo_item' | 'feo_category'
  entityId: number | null | undefined
}>()

const router = useRouter()

interface EntityChangeRow {
  id: number
  entity_type: string
  entity_id: number
  field_name: string
  old_value: string | null
  new_value: string | null
  changed_by_id: number | null
  changed_by_name: string | null
  changed_at: string | null
  source: string | null
  source_ref: number | null
}

interface OriginInfo {
  kind: 'wish' | 'purchase' | 'import'
  refId: number
  label?: string | null
  author?: string | null
  date?: string | null
}

interface HistoryEvent {
  isCreated: boolean
  isDeleted: boolean
  changedAt: string | null
  changedByName: string | null
  source: string | null
  sourceRef: number | null
  fields: EntityChangeRow[]
  origin?: OriginInfo | null
  originLoading?: boolean
}

const loading = ref(false)
const loadError = ref<string | null>(null)
const events = ref<HistoryEvent[]>([])

const SOURCE_LABELS: Record<string, string> = {
  import: 'импорт',
  wish: 'заявка',
  purchase: 'закупка',
  autoassign: 'автозаведение',
  collapse: 'объединение направлений',
}
function sourceLabel(s: string): string {
  return SOURCE_LABELS[s] ?? s
}

function fieldLabel(f: string): string {
  return feoHistoryFieldLabel(f)
}

function formatDate(s: string | null): string {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return s
  }
}

function openWish(id: number) {
  router.push({ path: '/wishes', query: { open: String(id) } })
}
function openPurchase(id: number) {
  router.push(`/orders/${id}`)
}

async function resolveOrigin(ev: HistoryEvent) {
  if (!ev.source || !ev.sourceRef) return
  ev.originLoading = true
  try {
    if (ev.source === 'wish') {
      const wish = await apiFetch<{ id: number; title?: string | null }>(`/wishes/${ev.sourceRef}`)
      ev.origin = { kind: 'wish', refId: ev.sourceRef, label: wish?.title ?? null }
    } else if (ev.source === 'purchase') {
      const purchase = await apiFetch<{ id: number; subject?: string | null }>(`/purchases/${ev.sourceRef}`)
      ev.origin = { kind: 'purchase', refId: ev.sourceRef, label: purchase?.subject ?? null }
    } else if (ev.source === 'import') {
      const run = await apiFetch<{ id: number; filename?: string | null; user_name?: string | null; started_at?: string | null }>(
        `/feo-categories/import-runs/${ev.sourceRef}`,
      )
      ev.origin = {
        kind: 'import', refId: ev.sourceRef,
        label: run?.filename ?? null, author: run?.user_name ?? null,
        date: run?.started_at ? formatDate(run.started_at) : null,
      }
    }
  } catch {
    // Не удалось дотянуть происхождение (например, заявка/закупка с тех пор
    // удалена) — молча падаем на общую фразу source-без-деталей ниже
    // (шаблон уже покрывает эту ветку через v-else-if по ev.source).
  } finally {
    ev.originLoading = false
  }
}

async function load() {
  if (!props.entityId) { events.value = []; return }
  loading.value = true
  loadError.value = null
  try {
    const rows = await apiFetch<EntityChangeRow[]>(`/entity-changes/${props.entityType}/${props.entityId}`)
    // rows приходят новые-сверху (см. entity_changes.py ORDER BY changed_at DESC) —
    // группируем построчные правки одного «сохранения» (тот же changed_at+автор)
    // в одно событие ленты; создание/удаление — маркерные поля, всегда своим событием.
    const grouped: HistoryEvent[] = []
    let i = 0
    const n = rows.length
    while (i < n) {
      const r = rows[i]!
      if (r.field_name === '__created__' || r.field_name === '__deleted__') {
        grouped.push({
          isCreated: r.field_name === '__created__',
          isDeleted: r.field_name === '__deleted__',
          changedAt: r.changed_at, changedByName: r.changed_by_name,
          source: r.source, sourceRef: r.source_ref, fields: [],
        })
        i += 1
        continue
      }
      const key = `${r.changed_at}__${r.changed_by_id}`
      const fields: EntityChangeRow[] = [r]
      let j = i + 1
      while (j < n) {
        const next = rows[j]!
        if (`${next.changed_at}__${next.changed_by_id}` !== key
          || next.field_name === '__created__' || next.field_name === '__deleted__') break
        fields.push(next)
        j += 1
      }
      grouped.push({
        isCreated: false, isDeleted: false,
        changedAt: r.changed_at, changedByName: r.changed_by_name,
        source: r.source, sourceRef: r.source_ref, fields,
      })
      i = j
    }
    events.value = grouped
    // Происхождение создания дотягиваем асинхронно, не блокируя показ ленты.
    for (const ev of grouped) {
      if (ev.isCreated && ev.source && ev.sourceRef) resolveOrigin(ev)
    }
  } catch (e: any) {
    loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить историю'
    events.value = []
  } finally {
    loading.value = false
  }
}

watch(() => [props.entityType, props.entityId], load)
onMounted(load)
</script>

<style scoped>
.feo-history-list {
  max-height: 360px;
  overflow-y: auto;
}
.feo-history-event {
  padding: 2px 0;
}
.feo-history-field {
  padding-left: 18px;
}
</style>
