<template>
  <div
    v-if="effectiveVisible"
    class="gala-history-popover-backdrop"
    @click="closePopover"
    @contextmenu.prevent="closePopover"
  >
    <div class="gala-history-popover elevation-8" :style="computedStyle" @click.stop>
      <!-- Шапка карточки в стиле Google Sheets -->
      <div class="gala-history-header">
        <div class="gala-history-header-title-box">
          <div class="gala-history-header-title">История изменений</div>
          <div v-if="effectiveOptions?.fieldLabel" class="gala-history-header-subtitle">
            {{ effectiveOptions.fieldLabel }}
          </div>
        </div>

        <div class="d-flex align-center ga-1">
          <span v-if="events.length > 1" class="gala-history-counter">
            {{ currentIndex + 1 }} из {{ events.length }}
          </span>

          <!-- Кнопка «К более старой правке» (<) -->
          <button
            type="button"
            class="gala-nav-btn"
            :class="{ 'gala-nav-btn--active': canGoOlder }"
            :disabled="!canGoOlder"
            title="Более ранняя правка"
            @click="goOlder"
          >
            <v-icon size="16">mdi-chevron-left</v-icon>
          </button>

          <!-- Кнопка «К более свежей правке» (>) -->
          <button
            type="button"
            class="gala-nav-btn"
            :class="{ 'gala-nav-btn--active': canGoNewer }"
            :disabled="!canGoNewer"
            title="Более поздняя правка"
            @click="goNewer"
          >
            <v-icon size="16">mdi-chevron-right</v-icon>
          </button>

          <!-- Закрыть -->
          <button type="button" class="gala-close-btn ml-1" title="Закрыть" @click="closePopover">
            <v-icon size="16">mdi-close</v-icon>
          </button>
        </div>
      </div>

      <v-divider />

      <!-- Индикатор загрузки -->
      <div v-if="loading" class="gala-history-loading">
        <v-progress-circular indeterminate size="22" width="2" color="primary" />
        <span class="text-caption text-medium-emphasis ml-2">Загрузка истории…</span>
      </div>

      <!-- Ошибка загрузки -->
      <div v-else-if="error" class="pa-3 text-caption text-error">
        {{ error }}
      </div>

      <!-- Пустое состояние -->
      <div v-else-if="!currentEvent" class="gala-history-empty text-medium-emphasis text-body-2 pa-4 text-center">
        Изменений по этой ячейке пока не было
      </div>

      <!-- Содержимое текущей правки -->
      <div v-else class="gala-history-content">
        <!-- Блок автора -->
        <div class="gala-history-author-box">
          <div class="gala-history-avatar" :style="{ backgroundColor: avatarColor(authorName) }">
            {{ avatarLetter(authorName) }}
          </div>
          <div class="gala-history-author-meta">
            <div class="gala-history-author-name">
              {{ authorName }}
              <v-chip v-if="currentEvent.source && currentEvent.source !== 'manual'" size="x-small" variant="tonal" class="ml-1">
                {{ currentEvent.source }}
              </v-chip>
            </div>
            <div class="gala-history-author-date">
              {{ formatRussianDate(currentEvent.changedAt) }}
            </div>
          </div>
        </div>

        <!-- Тело изменения -->
        <div class="gala-history-body">
          <template v-if="currentEvent.isCreated">
            <span class="font-weight-medium">Создано: </span>
            <span v-if="hasValue(currentEvent.newValue)" class="gala-history-val">
              «{{ formatCellValue(currentEvent.newValue, effectiveOptions) }}»
            </span>
            <span v-else class="text-medium-emphasis">строка создана</span>
          </template>

          <template v-else-if="changeKind === 'added'">
            <span class="font-weight-medium">Добавлено: </span>
            <span class="gala-history-val">«{{ formatCellValue(currentEvent.newValue, effectiveOptions) }}»</span>
          </template>

          <template v-else-if="changeKind === 'deleted'">
            <span class="font-weight-medium">Удалено: </span>
            <span class="gala-history-val gala-history-val--deleted">«{{ formatCellValue(currentEvent.oldValue, effectiveOptions) }}»</span>
          </template>

          <template v-else>
            <span class="font-weight-medium">Заменено: </span>
            <span class="gala-history-val gala-history-val--deleted">«{{ formatCellValue(currentEvent.oldValue, effectiveOptions) }}»</span>
            <span class="mx-1 text-medium-emphasis">на</span>
            <span class="gala-history-val">«{{ formatCellValue(currentEvent.newValue, effectiveOptions) }}»</span>
          </template>

          <div v-if="currentEvent.comment" class="gala-history-comment mt-2">
            «{{ currentEvent.comment }}»
          </div>
        </div>

        <!-- Кнопка «⏪ Вернуть это значение» -->
        <div v-if="canRestore" class="gala-history-restore-box mt-3">
          <v-btn
            size="small"
            variant="tonal"
            color="primary"
            block
            prepend-icon="mdi-history"
            :loading="restoring"
            @click="onRestoreValue"
          >
            ⏪ Вернуть это значение
          </v-btn>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import {
  useGalaContextMenu,
  type GalaCellContextOptions,
  type CellHistoryEvent,
  type ContextMenuPosition,
} from '@/composables/useGalaContextMenu'
import {
  avatarColor,
  avatarLetter,
  formatRussianDate,
  formatCellValue,
  fetchCellHistory,
} from '@/composables/useCellHistory'
import { apiFetch } from '@/api'

const props = defineProps<{
  modelValue?: boolean
  options?: GalaCellContextOptions | null
  position?: ContextMenuPosition
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
}>()

const {
  isHistoryOpen,
  historyPosition,
  historyCellOptions,
  closeCellHistory,
} = useGalaContextMenu()

const effectiveVisible = computed(() => props.modelValue !== undefined ? props.modelValue : isHistoryOpen.value)
const effectiveOptions = computed<GalaCellContextOptions | null>(() => props.options !== undefined ? props.options : historyCellOptions.value)
const effectivePosition = computed<ContextMenuPosition>(() => props.position !== undefined ? props.position : historyPosition.value)

const events = ref<CellHistoryEvent[]>([])
const currentIndex = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const restoring = ref(false)

const ALLOWED_RESTORE_ENTITIES = ['feo_item', 'feo_category', 'purchase', 'wish', 'task']

const canRestore = computed(() => {
  const opts = effectiveOptions.value
  if (!opts) return false
  if (opts.canRestoreHistory === false) return false
  if (!ALLOWED_RESTORE_ENTITIES.includes(opts.entityType)) return false
  if (!currentEvent.value) return false
  return hasValue(currentEvent.value.newValue) || hasValue(currentEvent.value.oldValue)
})

const restoreTargetValue = computed(() => {
  if (!currentEvent.value) return null
  return hasValue(currentEvent.value.oldValue) ? currentEvent.value.oldValue : currentEvent.value.newValue
})

const POPOVER_WIDTH = 320
const ESTIMATED_HEIGHT = 220

const computedStyle = computed(() => {
  const x = effectivePosition.value.x
  const y = effectivePosition.value.y
  const maxX = typeof window !== 'undefined' ? window.innerWidth - POPOVER_WIDTH - 12 : 1000
  const maxY = typeof window !== 'undefined' ? window.innerHeight - ESTIMATED_HEIGHT - 12 : 800
  return {
    left: `${Math.max(12, Math.min(x, maxX))}px`,
    top: `${Math.max(12, Math.min(y, maxY))}px`,
  }
})

const currentEvent = computed<CellHistoryEvent | null>(() => events.value[currentIndex.value] || null)
const canGoOlder = computed(() => currentIndex.value < events.value.length - 1)
const canGoNewer = computed(() => currentIndex.value > 0)

function goOlder() { if (canGoOlder.value) currentIndex.value++ }
function goNewer() { if (canGoNewer.value) currentIndex.value-- }

function closePopover() {
  if (props.modelValue !== undefined) emit('update:modelValue', false)
  else closeCellHistory()
}

const authorName = computed(() => {
  if (!currentEvent.value) return 'Система'
  if (currentEvent.value.changedByName) return currentEvent.value.changedByName
  if (currentEvent.value.source === 'import') return 'Импорт Excel'
  return 'Система'
})

function hasValue(val: any): boolean {
  return val !== null && val !== undefined && val !== '' && val !== 'None'
}

const changeKind = computed<'added' | 'deleted' | 'replaced'>(() => {
  const ev = currentEvent.value
  if (!ev) return 'added'
  if (!hasValue(ev.oldValue) && hasValue(ev.newValue)) return 'added'
  if (hasValue(ev.oldValue) && !hasValue(ev.newValue)) return 'deleted'
  return 'replaced'
})

async function loadHistory() {
  const opts = effectiveOptions.value
  if (!opts) { events.value = []; return }
  loading.value = true
  error.value = null
  currentIndex.value = 0
  try {
    events.value = await fetchCellHistory(opts)
  } catch (e: any) {
    console.error('Failed to load cell history', e)
    error.value = 'Не удалось загрузить историю изменений'
    events.value = []
  } finally {
    loading.value = false
  }
}

async function onRestoreValue() {
  const opts = effectiveOptions.value
  if (!opts || !canRestore.value) return

  const valToRestore = restoreTargetValue.value
  restoring.value = true
  try {
    await apiFetch(`/entity-changes/${opts.entityType}/${opts.entityId}/restore`, {
      method: 'POST',
      body: {
        field_name: opts.fieldName,
        value: valToRestore,
      },
    })

    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('gala:entity-restored', {
          detail: {
            entityType: opts.entityType,
            entityId: opts.entityId,
            fieldName: opts.fieldName,
            value: valToRestore,
          },
        })
      )
    }
    closePopover()
  } catch (e: any) {
    console.error('Failed to restore entity value', e)
    error.value = e?.message || 'Не удалось вернуть значение'
  } finally {
    restoring.value = false
  }
}

watch(
  () => [effectiveVisible.value, effectiveOptions.value?.entityId, effectiveOptions.value?.fieldName],
  ([visible]) => { if (visible) loadHistory() },
  { immediate: true }
)

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && effectiveVisible.value) closePopover()
  else if (e.key === 'ArrowLeft' && effectiveVisible.value) goOlder()
  else if (e.key === 'ArrowRight' && effectiveVisible.value) goNewer()
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<style scoped>
.gala-history-popover-backdrop {
  position: fixed; inset: 0; z-index: 99999; background: transparent;
}
.gala-history-popover {
  position: fixed; width: 320px; max-width: calc(100vw - 24px);
  background: rgb(var(--v-theme-surface)); color: rgb(var(--v-theme-on-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px; overflow: hidden; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); user-select: text;
}
.gala-history-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; }
.gala-history-header-title-box { min-width: 0; flex: 1; }
.gala-history-header-title { font-size: 13px; font-weight: 600; line-height: 1.2; }
.gala-history-header-subtitle { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
.gala-history-counter { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); margin-right: 4px; }
.gala-nav-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
  border-radius: 4px; border: none; background: transparent; color: rgba(var(--v-theme-on-surface), 0.35);
  cursor: not-allowed; transition: all 0.15s ease;
}
.gala-nav-btn--active { color: #0f9d58; cursor: pointer; }
.gala-nav-btn--active:hover { background: rgba(15, 157, 88, 0.12); }
.gala-close-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
  border-radius: 4px; border: none; background: transparent; color: rgba(var(--v-theme-on-surface), 0.6);
  cursor: pointer; transition: background-color 0.15s;
}
.gala-close-btn:hover { background: rgba(var(--v-theme-on-surface), 0.08); }
.gala-history-loading { display: flex; align-items: center; justify-content: center; padding: 24px; }
.gala-history-content { padding: 12px; }
.gala-history-author-box { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.gala-history-avatar {
  width: 32px; height: 32px; border-radius: 50%; color: #ffffff;
  display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.gala-history-author-meta { min-width: 0; flex: 1; }
.gala-history-author-name { font-size: 13px; font-weight: 600; line-height: 1.2; }
.gala-history-author-date { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6); margin-top: 2px; }
.gala-history-body {
  max-height: 210px; overflow-y: auto; font-size: 13px; line-height: 1.4; padding: 8px 10px;
  background: rgba(var(--v-theme-on-surface), 0.03); border-radius: 6px; border: 1px solid rgba(var(--v-border-color), 0.08);
}
.gala-history-val { font-style: italic; font-weight: 500; }
.gala-history-val--deleted { text-decoration: line-through; opacity: 0.65; }
.gala-history-comment { font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.7); font-style: italic; }
.gala-history-restore-box {
  display: flex;
}
</style>
