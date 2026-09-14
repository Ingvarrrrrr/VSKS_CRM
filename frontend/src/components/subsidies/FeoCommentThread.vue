<template>
  <div class="feo-comment-thread">
    <div v-if="loading" class="d-flex align-center" style="gap:8px;padding:6px 0">
      <v-progress-circular indeterminate size="14" color="teal" />
      <span class="text-caption text-medium-emphasis">Загрузка комментариев...</span>
    </div>
    <template v-else>
      <div v-if="!comments.length" class="text-caption text-medium-emphasis feo-comment-empty">
        Комментариев пока нет — будьте первым
      </div>
      <div v-for="c in comments" :key="c.id" class="feo-comment-card">
        <div class="feo-comment-avatar" :style="{ background: stringToColor(c.author_name || '?') }">
          {{ initialOf(c.author_name) }}
        </div>
        <div class="feo-comment-body">
          <div class="feo-comment-head">
            <span class="feo-comment-author">{{ c.author_name || 'Пользователь' }}</span>
            <span class="feo-comment-time">{{ formatCommentTime(c.created_at) }}</span>
          </div>
          <div v-if="c.parent_id != null" class="feo-comment-reply-quote">
            <v-icon icon="mdi-reply" size="11" class="mr-1" />{{ replyQuoteText(c.parent_id) }}
          </div>
          <div class="feo-comment-text">{{ c.text }}</div>
          <button type="button" class="feo-comment-reply-btn" @click="startReply(c)">Ответить</button>
          <div v-if="replyTargetId === c.id" class="feo-comment-reply-box">
            <v-textarea
              v-model="replyText" rows="2" auto-grow density="compact" hide-details
              placeholder="Ваш ответ..." variant="outlined"
            />
            <div class="d-flex mt-1" style="gap:6px">
              <v-btn size="x-small" color="teal" variant="tonal" :loading="submitting"
                :disabled="!replyText.trim()" @click="submitReply(c.id)"
              >Отправить</v-btn>
              <v-btn size="x-small" variant="text" @click="cancelReply">Отмена</v-btn>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div class="feo-comment-new">
      <v-textarea
        v-model="newText" rows="2" auto-grow density="compact" hide-details
        placeholder="Написать комментарий..." variant="outlined"
      />
      <v-btn class="mt-1" size="x-small" color="teal" variant="tonal" :loading="submitting"
        :disabled="!newText.trim()" @click="submitNew"
      >Отправить</v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
// Ветка комментариев (мини-чат) — ОДИН переиспользуемый компонент и для
// плановой позиции ФЭО (FeoLevel5Panel.vue), и для категории/направления
// дерева ФЭО (FeoTreeRow.vue), см. Правило №6 задачи («двух копий быть не
// должно»). Кто вызывает — определяется тем, какой из двух props передан;
// ровно один обязателен (сущность одна и та же, что и в модели FeoComment).
//
// Рендер плоским списком по created_at (а не деревом с отступами) — ответ
// показывается как «→ Автор: цитата» прямо над своим текстом (как reply-превью
// в мессенджерах), а не вложенной иерархией: макет владельца — это плоские
// карточки «кто и когда», вложенность глубже одного уровня цитаты не нужна и
// не помещается в узкий раскрывающийся блок под строкой таблицы (см. докстринг
// задачи про плотную таблицу плановых позиций).
import { ref, onMounted } from 'vue'
import { useFeoComments, formatCommentTime, type FeoComment } from '@/composables/subsidies/useFeoComments'
import { stringToColor } from '@/composables/chat/chatFormat'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  feoPlannedItemId?: number | null
  feoCategoryId?: number | null
  // Нужен ТОЛЬКО для инвалидации кэша счётчиков (useFeoComments.loadCounts)
  // после успешного добавления комментария/ответа — сама ветка её не
  // запрашивает и не показывает.
  subsidyId?: number | null
}>()

const feoComments = useFeoComments()
const toast = useToast()

const comments = ref<FeoComment[]>([])
const loading = ref(true)
const newText = ref('')
const replyText = ref('')
const replyTargetId = ref<number | null>(null)
const submitting = ref(false)

function errText(e: any, fallback: string): string {
  return e?.payload?.message || e?.detail || e?.message || fallback
}

async function load() {
  loading.value = true
  try {
    comments.value = await feoComments.fetchThread({
      feoPlannedItemId: props.feoPlannedItemId,
      feoCategoryId: props.feoCategoryId,
    })
  } catch (e: any) {
    toast.addToast(errText(e, 'Не удалось загрузить комментарии'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function initialOf(name: string | null): string {
  const n = (name || '').trim()
  return n ? n.charAt(0).toUpperCase() : '?'
}

function replyQuoteText(parentId: number): string {
  const p = comments.value.find(c => c.id === parentId)
  if (!p) return 'ответ на удалённый комментарий'
  const snippet = p.text.length > 60 ? p.text.slice(0, 60) + '…' : p.text
  return `${p.author_name || 'Пользователь'}: ${snippet}`
}

function startReply(c: FeoComment) {
  replyTargetId.value = c.id
  replyText.value = ''
}
function cancelReply() {
  replyTargetId.value = null
  replyText.value = ''
}

async function submitNew() {
  const text = newText.value.trim()
  if (!text) return
  submitting.value = true
  try {
    await feoComments.addComment({
      feoPlannedItemId: props.feoPlannedItemId,
      feoCategoryId: props.feoCategoryId,
      text,
      subsidyId: props.subsidyId,
    })
    newText.value = ''
    await load()
  } catch (e: any) {
    toast.addToast(errText(e, 'Не удалось добавить комментарий'), 'error')
  } finally {
    submitting.value = false
  }
}

async function submitReply(parentId: number) {
  const text = replyText.value.trim()
  if (!text) return
  submitting.value = true
  try {
    await feoComments.replyToComment(parentId, text, props.subsidyId)
    cancelReply()
    await load()
  } catch (e: any) {
    toast.addToast(errText(e, 'Не удалось отправить ответ'), 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
/* Стили — ТОЛЬКО на разметку этого же компонента (все .feo-comment-* элементы
   ниже — прямые дети шаблона FeoCommentThread.vue, не дочерних SFC), поэтому
   scoped здесь безопасен и не натыкается на инцидент проекта «scoped CSS
   родителя не достаёт до дочерних компонентов» — здесь нет чужих компонентов
   внутри, которым стиль нужно было бы пробросить снаружи. */
.feo-comment-thread {
  padding: 6px 4px;
}
.feo-comment-empty {
  padding: 4px 0 8px;
}
.feo-comment-card {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #EEF2F7;
}
.feo-comment-card:last-of-type {
  border-bottom: none;
}
.feo-comment-avatar {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.feo-comment-body {
  flex: 1 1 auto;
  min-width: 0;
}
.feo-comment-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.feo-comment-author {
  font-weight: 600;
  font-size: 12px;
  color: #0f172a;
}
.feo-comment-time {
  font-size: 11px;
  color: #94a3b8;
}
.feo-comment-reply-quote {
  margin-top: 2px;
  padding: 3px 6px;
  background: #F1F5F9;
  border-left: 2px solid #94A3B8;
  font-size: 11px;
  color: #64748b;
  border-radius: 3px;
  display: flex;
  align-items: center;
  white-space: normal;
  word-break: break-word;
}
.feo-comment-text {
  margin-top: 3px;
  font-size: 12px;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}
.feo-comment-reply-btn {
  margin-top: 3px;
  border: none;
  background: none;
  padding: 0;
  font-size: 11px;
  color: #0d9488;
  cursor: pointer;
}
.feo-comment-reply-btn:hover {
  text-decoration: underline;
}
.feo-comment-reply-box {
  margin-top: 6px;
  max-width: 420px;
}
.feo-comment-new {
  margin-top: 8px;
  max-width: 480px;
}
</style>
