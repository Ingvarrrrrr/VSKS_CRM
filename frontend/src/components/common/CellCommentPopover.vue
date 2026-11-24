<template>
  <div
    v-if="isCommentOpen"
    class="gala-comment-popover-backdrop"
    @click="onClose"
    @contextmenu.prevent="onClose"
  >
    <div
      class="gala-comment-popover elevation-8"
      :style="computedStyle"
      @click.stop
    >
      <!-- Header -->
      <div class="gala-comment-header">
        <div class="gala-comment-title-box">
          <div class="gala-comment-title">
            {{ isEditing ? (existingMark ? 'Редактировать комментарий' : 'Новый комментарий') : 'Комментарий' }}
          </div>
          <div class="gala-comment-subtitle">
            {{ targetSubtitle }}
          </div>
        </div>
        <button type="button" class="gala-close-btn" title="Закрыть" @click="onClose">
          <v-icon size="16">mdi-close</v-icon>
        </button>
      </div>

      <v-divider />

      <!-- View mode (when mark has existing comment and not editing) -->
      <div v-if="existingMark?.comment && !isEditing" class="gala-comment-body">
        <!-- Author metadata -->
        <div class="gala-comment-author-box">
          <div class="gala-comment-avatar" :style="{ backgroundColor: avatarColor(authorName) }">
            {{ avatarLetter(authorName) }}
          </div>
          <div class="gala-comment-author-meta">
            <div class="gala-comment-author-name">
              {{ authorName }}
              <v-chip size="x-small" :color="existingMark.visibility === 'private' ? 'warning' : 'primary'" variant="tonal" class="ml-1">
                {{ existingMark.visibility === 'private' ? '🔒 Только мне' : '👥 Всем' }}
              </v-chip>
            </div>
            <div class="gala-comment-date">
              {{ formatRussianDate(existingMark.created_at) }}
            </div>
          </div>

          <!-- Edit button -->
          <button type="button" class="gala-action-icon-btn" title="Редактировать" @click="startEdit">
            <v-icon size="15">mdi-pencil</v-icon>
          </button>
        </div>

        <!-- Comment text -->
        <div class="gala-comment-text">
          {{ existingMark.comment }}
        </div>

        <!-- Color mark badge if any -->
        <div v-if="existingMark.color" class="gala-comment-color-info mt-2">
          <span class="gala-color-dot" :style="{ backgroundColor: currentColorSwatch }" />
          <span class="text-caption text-medium-emphasis">Метка: {{ currentColorLabel }}</span>
        </div>

        <!-- Resolve button: ✓ Вопрос решён -->
        <div class="mt-3">
          <v-btn
            size="small"
            color="success"
            variant="tonal"
            block
            prepend-icon="mdi-check-circle-outline"
            :loading="resolving"
            @click="onResolve"
          >
            ✓ Вопрос решён
          </v-btn>
        </div>
      </div>

      <!-- Create / Edit mode -->
      <div v-else class="gala-comment-form">
        <v-textarea
          v-model="commentText"
          rows="3"
          variant="outlined"
          density="compact"
          placeholder="Напишите комментарий к ячейке или строке…"
          hide-details
          autofocus
          class="mb-3"
        />

        <!-- Color selection row -->
        <div class="mb-3">
          <div class="text-caption text-medium-emphasis mb-1">Цвет метки:</div>
          <div class="d-flex align-center ga-1">
            <button
              v-for="item in MARK_COLOR_PALETTE"
              :key="item.key"
              type="button"
              class="gala-color-circle"
              :class="{ 'gala-color-circle--selected': selectedColor === item.key }"
              :style="{ backgroundColor: item.swatch }"
              :title="item.label"
              @click="selectedColor = (selectedColor === item.key ? null : item.key)"
            />
            <button
              type="button"
              class="gala-color-circle gala-color-circle--clear"
              title="Без цвета"
              @click="selectedColor = null"
            >
              <v-icon size="13">mdi-close</v-icon>
            </button>
          </div>
        </div>

        <!-- Visibility toggle -->
        <div class="mb-3">
          <v-btn-toggle
            v-model="visibility"
            mandatory
            density="compact"
            color="primary"
            class="w-100 gala-vis-toggle"
          >
            <v-btn value="shared" size="small" class="flex-1">
              <v-icon size="14" class="mr-1">mdi-account-group</v-icon>
              Видно всем
            </v-btn>
            <v-btn value="private" size="small" class="flex-1">
              <v-icon size="14" class="mr-1">mdi-lock-outline</v-icon>
              Только для меня
            </v-btn>
          </v-btn-toggle>
        </div>

        <!-- Actions -->
        <div class="d-flex justify-end ga-2">
          <v-btn size="small" variant="text" @click="cancelEdit">
            Отмена
          </v-btn>
          <v-btn
            size="small"
            color="primary"
            variant="flat"
            :loading="saving"
            @click="onSave"
          >
            Сохранить
          </v-btn>
        </div>
      </div>

      <!-- Spoiler: Resolved comments -->
      <div v-if="resolvedList.length > 0 || loadingResolved" class="gala-resolved-spoiler mt-2">
        <button type="button" class="gala-spoiler-toggle" @click="showResolved = !showResolved">
          <v-icon size="14" class="mr-1">
            {{ showResolved ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
          </v-icon>
          <span>Решённые комментарии ({{ resolvedList.length }})</span>
        </button>

        <div v-if="showResolved" class="gala-resolved-list">
          <div v-for="res in resolvedList" :key="res.id" class="gala-resolved-item">
            <div class="d-flex align-center justify-space-between">
              <span class="text-caption font-weight-medium">{{ res.created_by_name || 'Сотрудник' }}</span>
              <span class="text-caption text-medium-emphasis">{{ formatRussianDate(res.resolved_at || res.created_at) }}</span>
            </div>
            <div class="text-caption mt-1">{{ res.comment }}</div>
            <div class="text-caption text-success mt-1">✓ Решено: {{ res.resolved_by_name || 'Пользователь' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  useCellMarks,
  MARK_COLOR_PALETTE,
  type MarkColor,
  type CellMarkRecord,
} from '@/composables/useCellMarks'
import { avatarColor, avatarLetter, formatRussianDate } from '@/composables/useCellHistory'
import { useToast } from '@/composables/useToast'
import { apiFetch } from '@/api'

const {
  isCommentOpen,
  commentPosition,
  activeCommentTargets,
  closeComment,
  applyMarkBatch,
  resolveMarkGroup,
  getExactMark,
  getRowMark,
} = useCellMarks()

const { addToast } = useToast()

const commentText = ref('')
const selectedColor = ref<MarkColor | null>(null)
const visibility = ref<'shared' | 'private'>('shared')
const isEditing = ref(false)
const saving = ref(false)
const resolving = ref(false)

const showResolved = ref(false)
const resolvedList = ref<CellMarkRecord[]>([])
const loadingResolved = ref(false)

const primaryTarget = computed(() => activeCommentTargets.value[0] || null)

const existingMark = computed<CellMarkRecord | null>(() => {
  const target = primaryTarget.value
  if (!target) return null
  if (target.fieldName === '*') {
    return getRowMark(target.entityType, target.entityId)
  }
  return getExactMark(target.entityType, target.entityId, target.fieldName)
})

const authorName = computed(() => existingMark.value?.created_by_name || 'Сотрудник')
const currentColorSwatch = computed(() => {
  const c = existingMark.value?.color
  return MARK_COLOR_PALETTE.find(p => p.key === c)?.swatch || '#fbbf24'
})
const currentColorLabel = computed(() => {
  const c = existingMark.value?.color
  return MARK_COLOR_PALETTE.find(p => p.key === c)?.label || ''
})

const targetSubtitle = computed(() => {
  const count = activeCommentTargets.value.length
  if (count > 1) return `Выделено ячеек/строк: ${count}`
  const target = primaryTarget.value
  if (!target) return ''
  if (target.fieldName === '*') return 'Вся строка'
  return target.fieldLabel || target.fieldName
})

watch(
  () => isCommentOpen.value,
  isOpen => {
    if (isOpen) {
      initForm()
      loadResolvedComments()
    } else {
      isEditing.value = false
      showResolved.value = false
    }
  }
)

function initForm() {
  const mark = existingMark.value
  if (mark && mark.comment) {
    commentText.value = mark.comment
    selectedColor.value = mark.color
    visibility.value = mark.visibility || 'shared'
    isEditing.value = false
  } else {
    commentText.value = ''
    selectedColor.value = mark?.color || null
    visibility.value = 'shared'
    isEditing.value = true
  }
}

async function loadResolvedComments() {
  const target = primaryTarget.value
  if (!target) {
    resolvedList.value = []
    return
  }

  loadingResolved.value = true
  try {
    const query = new URLSearchParams({
      entity_type: target.entityType,
      entity_ids: String(target.entityId),
      include_resolved: 'true',
    })
    const data = await apiFetch<CellMarkRecord[]>(`/cell-marks?${query.toString()}`)
    const list = Array.isArray(data) ? data : []
    resolvedList.value = list.filter(m => m.is_resolved)
  } catch (e) {
    console.warn('Failed to load resolved cell comments', e)
    resolvedList.value = []
  } finally {
    loadingResolved.value = false
  }
}

function startEdit() {
  isEditing.value = true
}

function cancelEdit() {
  if (existingMark.value?.comment) {
    initForm()
    isEditing.value = false
  } else {
    onClose()
  }
}

async function onSave() {
  const targets = activeCommentTargets.value
  if (targets.length === 0) return

  saving.value = true
  try {
    await applyMarkBatch({
      targets,
      comment: commentText.value.trim() || null,
      color: selectedColor.value,
      visibility: visibility.value,
      subsidyId: targets[0]?.subsidyId,
      orgId: targets[0]?.orgId,
    })
    addToast('Комментарий сохранён', 'success', { duration: 1500 })
    onClose()
  } catch (e: any) {
    console.error('Failed to save comment', e)
    addToast(e?.message || 'Не удалось сохранить комментарий', 'error', { duration: 2500 })
  } finally {
    saving.value = false
  }
}

async function onResolve() {
  const mark = existingMark.value
  if (!mark?.group_id) return

  resolving.value = true
  try {
    await resolveMarkGroup(mark.group_id)
    addToast('Вопрос решён, метка снята', 'success', { duration: 2000 })
    onClose()
  } catch (e: any) {
    console.error('Failed to resolve comment', e)
    addToast(e?.message || 'Не удалось закрыть комментарий', 'error', { duration: 2500 })
  } finally {
    resolving.value = false
  }
}

function onClose() {
  closeComment()
}

const POPOVER_WIDTH = 310
const ESTIMATED_HEIGHT = 280

const computedStyle = computed(() => {
  const x = commentPosition.value.x
  const y = commentPosition.value.y

  const maxX = typeof window !== 'undefined' ? window.innerWidth - POPOVER_WIDTH - 12 : 1000
  const maxY = typeof window !== 'undefined' ? window.innerHeight - ESTIMATED_HEIGHT - 12 : 800

  const safeX = Math.max(12, Math.min(x, maxX))
  const safeY = Math.max(12, Math.min(y, maxY))

  return {
    left: `${safeX}px`,
    top: `${safeY}px`,
  }
})

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isCommentOpen.value) {
    onClose()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<style scoped>
.gala-comment-popover-backdrop {
  position: fixed; inset: 0; z-index: 99999; background: transparent;
}
.gala-comment-popover {
  position: fixed; width: 310px; background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface)); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px; overflow: hidden; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); user-select: text;
}
.gala-comment-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; }
.gala-comment-title-box { min-width: 0; flex: 1; }
.gala-comment-title { font-size: 13px; font-weight: 600; line-height: 1.2; }
.gala-comment-subtitle {
  font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.6);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;
}
.gala-close-btn {
  display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px;
  border-radius: 4px; border: none; background: transparent; color: rgba(var(--v-theme-on-surface), 0.6);
  cursor: pointer; transition: background-color 0.15s;
}
.gala-close-btn:hover { background: rgba(var(--v-theme-on-surface), 0.08); }
.gala-comment-body, .gala-comment-form { padding: 10px 12px; }
.gala-comment-author-box { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gala-comment-avatar {
  width: 28px; height: 28px; border-radius: 50%; color: #ffffff;
  display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.gala-comment-author-meta { min-width: 0; flex: 1; }
.gala-comment-author-name { font-size: 12px; font-weight: 600; line-height: 1.2; }
.gala-comment-date { font-size: 10px; color: rgba(var(--v-theme-on-surface), 0.55); margin-top: 1px; }
.gala-action-icon-btn {
  border: none; background: transparent; color: rgba(var(--v-theme-on-surface), 0.6);
  cursor: pointer; padding: 4px; border-radius: 4px;
}
.gala-action-icon-btn:hover { background: rgba(var(--v-theme-on-surface), 0.08); }
.gala-comment-text {
  font-size: 13px; line-height: 1.4; white-space: pre-wrap; word-break: break-word;
  background: rgba(var(--v-theme-on-surface), 0.03); padding: 8px; border-radius: 6px;
  border: 1px solid rgba(var(--v-border-color), 0.08);
}
.gala-comment-color-info { display: flex; align-items: center; gap: 6px; }
.gala-color-dot { width: 10px; height: 10px; border-radius: 50%; }
.gala-color-circle {
  width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent;
  cursor: pointer; transition: transform 0.12s ease; padding: 0;
}
.gala-color-circle:hover { transform: scale(1.15); }
.gala-color-circle--selected { border-color: rgb(var(--v-theme-on-surface)); transform: scale(1.12); }
.gala-color-circle--clear {
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.35); background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.6); display: flex; align-items: center; justify-content: center;
}
.gala-vis-toggle :deep(.v-btn) { text-transform: none; font-size: 11px; }
.gala-resolved-spoiler { border-top: 1px solid rgba(var(--v-border-color), 0.08); padding: 6px 12px; }
.gala-spoiler-toggle {
  display: flex; align-items: center; border: none; background: transparent;
  font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.65); cursor: pointer; padding: 2px 0;
}
.gala-resolved-list {
  max-height: 120px; overflow-y: auto; margin-top: 4px; display: flex; flex-direction: column; gap: 6px;
}
.gala-resolved-item { padding: 6px; background: rgba(var(--v-theme-on-surface), 0.02); border-radius: 4px; }
</style>
