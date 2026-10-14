<!-- ProposeToCatalogDialog.vue — единое окно «предложить правку описания
     каталога» (Этап В, план item-tz-description.md, владелец 14.10.2026,
     п.4). Переиспользуется из ДВУХ мест (ПРАВИЛО №6, один механизм отправки
     предложения, не второй):
       1) ProductFormDialog.vue, кнопка «Предложить правку описания» — поле
          выбирается (description / description_44fz), текст предложения
          редактируется прямо здесь (editableOwn=true).
       2) WishTzSection.vue / ItemsTableStages.vue, кнопка «Предложить в
          каталог» — своё ТЗ позиции (tz_description) уже написано, текст
          только показывается (editableOwn=false), поле всегда 'description'
          (эффективное ТЗ сравнивается только с ним, см. utils/itemTz.ts).

     Шлёт ОДИН эндпоинт — POST /api/products/{id}/description-proposals
     (backend/app/routers/product_description.py). Если у автора есть право
     products.edit_catalog — применяется сразу (бэкенд возвращает
     status='accepted'), иначе остаётся pending — текст тоста различается
     этим статусом из ответа, а не повторной проверкой права на фронте. -->
<template>
  <v-dialog v-model="show" max-width="640" :fullscreen="mobile" scrollable>
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        Предложить правку каталога
        <div v-if="productName" class="text-caption text-medium-emphasis mt-1">{{ productName }}</div>
      </v-card-title>
      <v-card-text class="px-6">
        <v-select
          v-if="fieldOptions && fieldOptions.length > 1"
          v-model="fieldModel"
          :items="fieldOptions"
          item-title="label" item-value="value"
          label="Какое поле предлагаете изменить"
          variant="outlined" density="compact" class="mb-3"
        />
        <v-row dense>
          <v-col cols="12" sm="6">
            <div class="text-caption text-medium-emphasis mb-1">Сейчас в каталоге</div>
            <v-textarea
              :model-value="catalogValue || '—'"
              readonly variant="outlined" density="compact"
              rows="6" auto-grow hide-details
            />
          </v-col>
          <v-col cols="12" sm="6">
            <div class="text-caption text-medium-emphasis mb-1">
              {{ editableOwn ? 'Ваше предложение' : 'Ваше ТЗ' }}
            </div>
            <v-textarea
              v-if="editableOwn"
              v-model="ownText"
              variant="outlined" density="compact"
              rows="6" auto-grow hide-details
              placeholder="Опишите, что должно быть в каталоге"
            />
            <v-textarea
              v-else
              :model-value="ownText || '—'"
              readonly variant="outlined" density="compact"
              rows="6" auto-grow hide-details
            />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" :loading="sending" @click="send">Отправить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

export interface ProductDescriptionProposalResult {
  id: number
  status: string
  [key: string]: any
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  productId: number
  productName?: string | null
  /** Поле описания, которое предлагается изменить. По умолчанию 'description' —
   * то самое, с которым сравнивается своё ТЗ позиции (utils/itemTz.ts). */
  field?: 'description' | 'description_44fz'
  /** Если задано (>1 элемента) — показывается выбор поля (используется из
   * карточки товара); из ряда ТЗ позиции не передаётся — поле фиксировано. */
  fieldOptions?: { value: 'description' | 'description_44fz'; label: string }[]
  /** Текущее каталожное значение выбранного поля — показывается слева. */
  catalogValue?: string | null
  /** Исходный текст предложения — если editableOwn, предзаполняет
   * редактируемое поле; иначе показывается как есть (своё ТЗ позиции). */
  ownValue?: string | null
  /** true — текст справа редактируется в этом диалоге (карточка товара);
   * false — только показывается, это уже готовое своё ТЗ позиции. */
  editableOwn?: boolean
  wishItemId?: number | null
  purchaseItemId?: number | null
}>(), {
  field: 'description',
  editableOwn: false,
  catalogValue: null,
  ownValue: null,
  productName: null,
  wishItemId: null,
  purchaseItemId: null,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'applied', proposal: ProductDescriptionProposalResult): void
}>()

const { mobile } = useDisplay()
const toast = useToast()

const show = ref(props.modelValue)
watch(() => props.modelValue, (v) => { show.value = v })
watch(show, (v) => emit('update:modelValue', v))

const fieldModel = ref<'description' | 'description_44fz'>(props.field)
const ownText = ref(props.ownValue || '')
watch(() => props.modelValue, (v) => {
  if (v) {
    fieldModel.value = props.field
    ownText.value = props.ownValue || ''
  }
})

const sending = ref(false)
async function send() {
  sending.value = true
  try {
    const proposal = await apiFetch<ProductDescriptionProposalResult>(
      `/products/${props.productId}/description-proposals`,
      {
        method: 'POST',
        body: {
          field: fieldModel.value,
          proposed_value: ownText.value,
          wish_item_id: props.wishItemId ?? undefined,
          purchase_item_id: props.purchaseItemId ?? undefined,
        },
      },
    )
    toast.success(
      proposal.status === 'accepted'
        ? 'Описание в каталоге обновлено'
        : 'Предложение отправлено, его рассмотрит сотрудник с правом на каталог',
    )
    show.value = false
    emit('applied', proposal)
  } catch (e: any) {
    toast.error(describeApiError(e, { fallback: 'Не удалось отправить предложение' }))
  } finally {
    sending.value = false
  }
}
</script>
