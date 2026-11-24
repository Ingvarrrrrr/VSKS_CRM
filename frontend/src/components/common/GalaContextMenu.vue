<template>
  <div
    v-if="isMenuOpen"
    class="gala-context-menu-backdrop"
    @click="closeContextMenu"
    @contextmenu.prevent="closeContextMenu"
  >
    <div
      class="gala-context-menu elevation-6"
      :style="computedStyle"
      @click.stop
    >
      <!-- Header -->
      <div v-if="activeCellOptions?.fieldLabel" class="gala-context-menu-header">
        <span class="gala-context-menu-title">{{ activeCellOptions.fieldLabel }}</span>
        <span v-if="bulkCount > 1" class="gala-bulk-badge">
          Выделено: {{ bulkCount }}
        </span>
      </div>

      <!-- Color palette bar -->
      <gala-context-color-bar
        v-if="canMarkEntity"
        v-model:mode="colorBarMode"
        :allow-row-toggle="allowRowToggle"
        :current-color="currentMarkColor"
        @select-color="onSelectColor"
        @clear-color="onClearColor"
      />

      <div class="gala-context-menu-items">
        <!-- 💬 Комментарий к выделенному -->
        <button
          v-if="canMarkEntity"
          type="button"
          class="gala-context-menu-item"
          @click="onOpenComment"
        >
          <v-icon size="16" class="mr-2 text-warning">mdi-comment-outline</v-icon>
          <span>{{ hasActiveComment ? '💬 Открыть комментарий' : '💬 Комментарий к выделенному…' }}</span>
        </button>

        <!-- 🎨 Фильтр по этому цвету (если цвет есть) или Сброс фильтра по цвету -->
        <button
          v-if="canMarkEntity && (currentMarkColor || activeEntityTypeColorFilter)"
          type="button"
          class="gala-context-menu-item"
          @click="onToggleColorFilter"
        >
          <v-icon size="16" class="mr-2" :color="activeEntityTypeColorFilter ? 'primary' : undefined">
            {{ activeEntityTypeColorFilter ? 'mdi-filter-off' : 'mdi-filter' }}
          </v-icon>
          <span>
            {{ activeEntityTypeColorFilter ? 'Сбросить фильтр по цвету' : `Фильтр по цвету: ${currentColorLabel}` }}
          </span>
        </button>

        <div v-if="canMarkEntity" class="gala-context-menu-divider" />

        <!-- 🔍 Фильтровать по значению (если передано onFilterValue) -->
        <template v-if="hasFilterValue">
          <button
            type="button"
            class="gala-context-menu-item"
            @click="onApplyFilter('include')"
          >
            <v-icon size="16" class="mr-2 text-primary">mdi-filter-plus-outline</v-icon>
            <span class="text-truncate">Только «{{ filterValueLabel }}»</span>
          </button>
          <button
            type="button"
            class="gala-context-menu-item"
            @click="onApplyFilter('exclude')"
          >
            <v-icon size="16" class="mr-2 text-error">mdi-filter-minus-outline</v-icon>
            <span class="text-truncate">Исключить «{{ filterValueLabel }}»</span>
          </button>
          <div class="gala-context-menu-divider" />
        </template>

        <!-- ↗️ Открыть в новой вкладке -->
        <button
          v-if="activeCellOptions?.openUrl"
          type="button"
          class="gala-context-menu-item"
          @click="onOpenNewTab"
        >
          <v-icon size="16" class="mr-2">mdi-open-in-new</v-icon>
          <span>Открыть в новой вкладке</span>
        </button>

        <!-- 📋 Копировать значение -->
        <button
          type="button"
          class="gala-context-menu-item"
          @click="onCopyValue"
        >
          <v-icon size="16" class="mr-2">mdi-content-copy</v-icon>
          <span>Копировать значение</span>
        </button>

        <!-- 🔢 Копировать только число -->
        <button
          v-if="cleanNumber !== null"
          type="button"
          class="gala-context-menu-item"
          @click="onCopyCleanNumber"
        >
          <v-icon size="16" class="mr-2">mdi-numeric</v-icon>
          <span class="text-truncate">Копировать число ({{ cleanNumber }})</span>
        </button>

        <!-- 🔗 Скопировать ссылку на строку -->
        <button
          type="button"
          class="gala-context-menu-item"
          @click="onCopyRowLink"
        >
          <v-icon size="16" class="mr-2">mdi-link-variant</v-icon>
          <span>Скопировать ссылку на строку</span>
        </button>

        <!-- 🕘 История изменений -->
        <button
          type="button"
          class="gala-context-menu-item"
          @click="onOpenHistory"
        >
          <v-icon size="16" class="mr-2 text-primary">mdi-history</v-icon>
          <span>История изменений</span>
        </button>

        <!-- Дополнительные расширяемые пункты -->
        <template v-for="item in activeCellOptions?.extraItems" :key="item.key">
          <div v-if="item.dividerBefore" class="gala-context-menu-divider" />
          <button
            type="button"
            class="gala-context-menu-item"
            :class="{ 'gala-context-menu-item--danger': item.danger, 'gala-context-menu-item--disabled': item.disabled }"
            :disabled="item.disabled"
            @click="onExtraClick(item)"
          >
            <v-icon v-if="item.icon" size="16" class="mr-2" :color="item.danger ? 'error' : undefined">{{ item.icon }}</v-icon>
            <span>{{ item.label }}</span>
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import {
  useGalaContextMenu,
  extractNumericValue,
  type ContextMenuItem,
} from '@/composables/useGalaContextMenu'
import {
  useCellMarks,
  MARK_COLOR_PALETTE,
  type CellTarget,
  type MarkColor,
} from '@/composables/useCellMarks'
import { useToast } from '@/composables/useToast'
import GalaContextColorBar from './GalaContextColorBar.vue'

const {
  isMenuOpen,
  menuPosition,
  activeCellOptions,
  closeContextMenu,
  openCellHistory,
  copyCellValue,
  copyCleanNumber,
  copyRowLink,
} = useGalaContextMenu()

const {
  applyMarkBatch,
  clearMarksColor,
  openCommentAt,
  getMark,
  getExactMark,
  getRowMark,
  activeColorFilter,
  setColorFilter,
  selectedTargets,
  clearSelection,
} = useCellMarks()

const { addToast } = useToast()

const colorBarMode = ref<'cell' | 'row'>('cell')

const canMarkEntity = computed(() => {
  const opts = activeCellOptions.value
  return Boolean(opts?.entityType && opts.entityType !== 'table_row' && Number(opts.entityId) > 0) || Boolean(opts?.bulkTargets && opts.bulkTargets.length > 0)
})

const isSelectionActive = computed(() => {
  const opts = activeCellOptions.value
  if (!opts || selectedTargets.value.length === 0) return false
  const numId = Number(opts.entityId)
  const inSel = selectedTargets.value.some(
    t => t.entityType === opts.entityType && Number(t.entityId) === numId && (t.fieldName === '*' || t.fieldName === opts.fieldName)
  )
  const sameType = selectedTargets.value.length > 1 && selectedTargets.value.every(t => t.entityType === opts.entityType)
  return inSel || sameType
})

const bulkCount = computed(() => {
  if (activeCellOptions.value?.bulkTargets?.length) return activeCellOptions.value.bulkTargets.length
  if (isSelectionActive.value) return selectedTargets.value.length
  return 0
})
const allowRowToggle = computed(() => bulkCount.value === 0)

watch(
  () => isMenuOpen.value,
  isOpen => {
    if (isOpen) {
      colorBarMode.value = 'cell'
    }
  }
)

const currentTargets = computed<CellTarget[]>(() => {
  const opts = activeCellOptions.value
  if (!opts) return []
  if (opts.bulkTargets && opts.bulkTargets.length > 0) {
    return [...opts.bulkTargets]
  }
  if (isSelectionActive.value) {
    return selectedTargets.value.map(t => ({
      entityType: t.entityType,
      entityId: Number(t.entityId),
      fieldName: colorBarMode.value === 'row' ? '*' : (t.fieldName || '*'),
      fieldLabel: t.fieldLabel,
      orgId: t.orgId ?? opts.orgId,
      subsidyId: t.subsidyId ?? opts.subsidyId,
    }))
  }

  const numId = typeof opts.entityId === 'number' ? opts.entityId : Number(opts.entityId)
  return [
    {
      entityType: opts.entityType,
      entityId: numId,
      fieldName: colorBarMode.value === 'row' ? '*' : opts.fieldName,
      fieldLabel: opts.fieldLabel,
      orgId: opts.orgId,
      subsidyId: opts.subsidyId,
    },
  ]
})

const currentMarkColor = computed<MarkColor | null>(() => {
  const opts = activeCellOptions.value
  if (!opts) return null
  const numId = typeof opts.entityId === 'number' ? opts.entityId : Number(opts.entityId)
  if (colorBarMode.value === 'row') {
    return getRowMark(opts.entityType, numId)?.color || null
  }
  return getMark(opts.entityType, numId, opts.fieldName)?.color || null
})

const currentColorLabel = computed(() => {
  const c = currentMarkColor.value
  if (!c) return ''
  return MARK_COLOR_PALETTE.find(p => p.key === c)?.label || c
})

const hasActiveComment = computed(() => {
  const opts = activeCellOptions.value
  if (!opts) return false
  const numId = typeof opts.entityId === 'number' ? opts.entityId : Number(opts.entityId)
  const exact = getExactMark(opts.entityType, numId, opts.fieldName)
  const row = getRowMark(opts.entityType, numId)
  return Boolean((exact && exact.comment) || (row && row.comment))
})

const activeEntityTypeColorFilter = computed(() => {
  const entityType = activeCellOptions.value?.entityType
  if (!entityType) return null
  return activeColorFilter.value[entityType] || null
})

const cleanNumber = computed<string | null>(() => {
  const opts = activeCellOptions.value
  if (!opts) return null
  if (opts.rawNumber !== undefined && opts.rawNumber !== null) {
    return String(opts.rawNumber)
  }
  return extractNumericValue(opts.cellValue)
})

const hasFilterValue = computed(() => {
  const opts = activeCellOptions.value
  return (
    typeof opts?.onFilterValue === 'function' &&
    opts.cellValue !== null &&
    opts.cellValue !== undefined &&
    opts.cellValue !== ''
  )
})

const filterValueLabel = computed(() => {
  const val = String(activeCellOptions.value?.cellValue ?? '')
  return val.length > 20 ? `${val.slice(0, 18)}…` : val
})

const MENU_WIDTH = 230
const ESTIMATED_HEIGHT = 280

const computedStyle = computed(() => {
  const x = menuPosition.value.x
  const y = menuPosition.value.y

  const maxX = typeof window !== 'undefined' ? window.innerWidth - MENU_WIDTH - 8 : 1000
  const maxY = typeof window !== 'undefined' ? window.innerHeight - ESTIMATED_HEIGHT - 8 : 800

  const safeX = Math.max(8, Math.min(x, maxX))
  const safeY = Math.max(8, Math.min(y, maxY))

  return {
    left: `${safeX}px`,
    top: `${safeY}px`,
  }
})

async function onSelectColor(color: MarkColor) {
  const targets = currentTargets.value
  if (targets.length === 0) return
  try {
    await applyMarkBatch({
      targets,
      color,
      subsidyId: activeCellOptions.value?.subsidyId,
      orgId: activeCellOptions.value?.orgId,
    })
    if (selectedTargets.value.length > 0) clearSelection()
  } catch (e: any) {
    console.error('Failed to set cell mark color', e)
    addToast('Не удалось применить цвет ячейки', 'error')
  } finally {
    closeContextMenu()
  }
}

async function onClearColor() {
  const targets = currentTargets.value
  if (targets.length === 0) return
  try {
    await clearMarksColor(targets)
    if (selectedTargets.value.length > 0) clearSelection()
  } catch (e: any) {
    console.error('Failed to clear cell mark color', e)
    addToast('Не удалось сбросить цвет ячейки', 'error')
  } finally {
    closeContextMenu()
  }
}

function onOpenComment() {
  const targets = currentTargets.value
  if (targets.length === 0) return
  openCommentAt(menuPosition.value, targets)
  if (selectedTargets.value.length > 0) clearSelection()
  closeContextMenu()
}

function onToggleColorFilter() {
  const opts = activeCellOptions.value
  if (!opts) return
  const entityType = opts.entityType
  if (activeEntityTypeColorFilter.value) {
    setColorFilter(entityType, null)
  } else if (currentMarkColor.value) {
    setColorFilter(entityType, currentMarkColor.value)
  }
  closeContextMenu()
}

function onApplyFilter(mode: 'include' | 'exclude') {
  const opts = activeCellOptions.value
  if (opts?.onFilterValue) {
    opts.onFilterValue(opts.cellValue, mode)
  }
  closeContextMenu()
}

function onOpenNewTab() {
  const url = activeCellOptions.value?.openUrl
  if (url && typeof window !== 'undefined') {
    window.open(url, '_blank')
  }
  closeContextMenu()
}

function onOpenHistory() {
  openCellHistory()
}

function onCopyValue() {
  copyCellValue()
}

function onCopyCleanNumber() {
  copyCleanNumber(cleanNumber.value)
}

function onCopyRowLink() {
  copyRowLink()
}

async function onExtraClick(item: ContextMenuItem) {
  if (item.disabled) return
  if (item.onClick) await item.onClick()
  closeContextMenu()
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isMenuOpen.value) closeContextMenu()
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<style scoped>
.gala-context-menu-backdrop {
  position: fixed; inset: 0; z-index: 200000; background: transparent;
}
.gala-context-menu {
  position: fixed; width: 230px; background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface)); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px; padding: 4px; box-shadow: 0 4px 18px rgba(0, 0, 0, 0.18); user-select: none;
}
.gala-context-menu-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 8px 6px 8px; border-bottom: 1px solid rgba(var(--v-border-color), 0.08); margin-bottom: 4px;
}
.gala-context-menu-title {
  font-size: 11px; font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.6);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1;
}
.gala-bulk-badge {
  font-size: 10px; background: rgba(var(--v-theme-primary), 0.12); color: rgb(var(--v-theme-primary));
  padding: 1px 5px; border-radius: 10px; font-weight: 600; margin-left: 4px; white-space: nowrap;
}
.gala-context-menu-items { display: flex; flex-direction: column; gap: 1px; }
.gala-context-menu-item {
  display: flex; align-items: center; width: 100%; padding: 5px 8px; font-size: 12.5px;
  border: none; background: transparent; color: inherit; border-radius: 5px; cursor: pointer; text-align: left;
  transition: background-color 0.12s ease;
}
.gala-context-menu-item:hover:not(:disabled) { background: rgba(var(--v-theme-primary), 0.08); }
.gala-context-menu-item--danger { color: rgb(var(--v-theme-error)); }
.gala-context-menu-item--danger:hover:not(:disabled) { background: rgba(var(--v-theme-error), 0.1); }
.gala-context-menu-item--disabled { opacity: 0.45; cursor: not-allowed; }
.gala-context-menu-divider { height: 1px; background: rgba(var(--v-border-color), 0.12); margin: 3px 0; }
</style>
