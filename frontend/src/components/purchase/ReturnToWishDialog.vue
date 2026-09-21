<template>
  <v-dialog v-model="show" max-width="560" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center ga-2 px-4 pt-4">
        <v-icon icon="mdi-undo-variant" color="error" />
        Вернуть закупку на доработку
      </v-card-title>
      <v-card-text class="px-4">
        <div v-if="loadingPreview" class="text-medium-emphasis py-2">Проверка…</div>
        <template v-else>
          <v-alert v-if="!preview?.allowed" type="error" variant="tonal" density="comfortable" class="mb-3">
            {{ preview?.reason || 'Возврат недоступен' }}
          </v-alert>
          <template v-else>
            <div class="text-body-2 mb-2">Что произойдёт:</div>
            <ul class="mb-3" style="padding-left: 20px">
              <li v-for="(c, i) in preview?.consequences || []" :key="i" class="text-body-2 mb-1">{{ c }}</li>
            </ul>
            <v-textarea
              v-model="comment"
              label="Причина возврата"
              placeholder="Опишите, что нужно исправить"
              rows="3"
              auto-grow
              variant="outlined"
              density="comfortable"
              :rules="[(v: string) => !!v?.trim() || 'Укажите причину']"
            />
          </template>
        </template>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-spacer />
        <v-btn
          v-if="preview?.allowed"
          color="error"
          variant="elevated"
          :loading="submitting"
          :disabled="!comment.trim()"
          @click="submit"
        >
          Вернуть на доработку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог возврата закупки в «Заявки» — третий вариант решения дублей ТЗ
// («Ошибка — вернуть на доработку», 21.09, corrections-21-09.md W3).
// GET preview / POST return-to-wish — backend/app/routers/purchase_return.py,
// текст последствий берётся ИСКЛЮЧИТЕЛЬНО из preview (Правило №6, один текст
// на предупреждение и на сам ответ мутации — не дублируем на фронте).
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'

interface ReturnPreview {
  allowed: boolean
  reason: string | null
  consequences: string[]
}

const props = defineProps<{
  modelValue: boolean
  purchaseId: number
  reasonHint?: string
  // Совпадает с composables/useToast.ts::ToastType — see TzRowsSection.vue,
  // передаётся насквозь от CreateOrderView.showSnack.
  showSnack?: (msg: string, color?: 'success' | 'error' | 'info' | 'warning') => void
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success', payload: { purchaseId: number; wishId: number }): void
}>()

const router = useRouter()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loadingPreview = ref(false)
const preview = ref<ReturnPreview | null>(null)
const comment = ref('')
const submitting = ref(false)
let commentTouched = false

async function loadPreview() {
  loadingPreview.value = true
  preview.value = null
  try {
    preview.value = await apiFetch<ReturnPreview>(`/purchases/${props.purchaseId}/return-to-wish/preview`)
  } catch (e: any) {
    preview.value = { allowed: false, reason: describeApiError(e, { fallback: 'Не удалось проверить возврат' }), consequences: [] }
  } finally {
    loadingPreview.value = false
  }
}

// commentTouched отличает правку пользователя от программной подстановки
// reasonHint — без suppressWatch второй watch(comment) сам же помечал бы
// только что подставленный текст как «тронутый пользователем».
let suppressTouch = false
function setComment(v: string) {
  suppressTouch = true
  comment.value = v
  suppressTouch = false
}

watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    commentTouched = false
    setComment(props.reasonHint || '')
    loadPreview()
  },
  { immediate: true },
)
watch(comment, () => { if (!suppressTouch) commentTouched = true })
watch(
  () => props.reasonHint,
  (hint) => { if (!commentTouched) setComment(hint || '') },
)

async function submit() {
  if (!comment.value.trim() || !preview.value?.allowed) return
  submitting.value = true
  try {
    // ApiFetchOptions['body'] типизирован как RequestInit['body'] (BodyInit) —
    // как и везде в проекте (см. useItemsCatalog.ts), объект под any перед передачей.
    const body: any = { comment: comment.value.trim() }
    const res = await apiFetch<{ ok: boolean; purchase_id: number; wish_id: number }>(
      `/purchases/${props.purchaseId}/return-to-wish`,
      { method: 'POST', body },
    )
    props.showSnack?.('Закупка возвращена на доработку — заявка отмечена «На доработке»')
    emit('success', { purchaseId: props.purchaseId, wishId: res.wish_id })
    show.value = false
    router.push(`/wishes?open=${res.wish_id}`)
  } catch (e: any) {
    props.showSnack?.(describeApiError(e, { fallback: 'Не удалось вернуть закупку на доработку' }), 'error')
  } finally {
    submitting.value = false
  }
}
</script>
