<!-- WishDecisionSummary.vue — мобильный режим WishFormDialog.vue, согласующий
     (mobile && !isWishEditable && canAssigneeAct). Заменяет на телефоне строку
     «От кого/Кому/Создано/Статус» (v-card-subtitle) и оранжевую плашку
     «Вы согласующий…» — сводка для принятия решения без скролла по всей форме.
     Чисто презентационный компонент: все цифры и подписи приходят готовыми
     от родителя (Правило №6 — totalAmount/items те же, что в разделе «Позиции»
     формы, approvers/статусы те же, что в разделе «Согласующие»). -->
<template>
  <div class="wish-decision-summary">
    <div class="d-flex align-center flex-wrap mb-2" style="gap:8px">
      <v-chip size="small" variant="tonal" color="primary">{{ statusLabel[wish.status] || wish.status }}</v-chip>
      <v-chip size="small" variant="flat" color="orange" prepend-icon="mdi-clock-alert-outline">Ваша очередь</v-chip>
    </div>

    <div
      class="text-subtitle-1 font-weight-medium mb-1"
      :class="{ 'wish-decision-summary__subject--clamped': !subjectExpanded }"
    >{{ wish.title || 'Без названия' }}</div>
    <v-btn
      v-if="subjectOverflowCandidate"
      size="x-small"
      variant="text"
      color="primary"
      class="px-0 mb-2"
      @click="subjectExpanded = !subjectExpanded"
    >{{ subjectExpanded ? 'Свернуть' : 'Показать полностью' }}</v-btn>

    <div class="text-caption text-medium-emphasis mb-3">
      {{ shortName(wish.creator_name) || '—' }}{{ coAuthorsSuffix }} → {{ recipients || '—' }} · {{ formatDate(wish.created_at) }}
    </div>

    <v-card variant="outlined" class="pa-3 mb-3">
      <div class="text-h6 font-weight-bold">{{ formatMoney(totalAmount) }}</div>
      <div class="text-caption text-medium-emphasis mb-2">{{ items.length }} {{ pluralRu(items.length, 'позиция', 'позиции', 'позиций') }}</div>
      <v-row dense>
        <v-col v-if="subsidyName" cols="6">
          <div class="text-caption text-medium-emphasis">Субсидия</div>
          <div class="text-body-2">{{ subsidyName }}</div>
        </v-col>
        <v-col v-if="desiredDate" cols="6">
          <div class="text-caption text-medium-emphasis">Поставка к</div>
          <div class="text-body-2">{{ formatDate(desiredDate) }}</div>
        </v-col>
        <v-col v-if="contractFormLabel" cols="6">
          <div class="text-caption text-medium-emphasis">Форма договора</div>
          <div class="text-body-2">{{ contractFormLabel }}</div>
        </v-col>
        <v-col v-if="wish.priority" cols="6">
          <div class="text-caption text-medium-emphasis">Приоритет</div>
          <div class="text-body-2">{{ priorityLabel[wish.priority] || wish.priority }}</div>
        </v-col>
      </v-row>
    </v-card>

    <div class="text-subtitle-2 font-weight-medium mb-1">Позиции ({{ items.length }})</div>
    <div class="d-flex flex-column mb-3" style="gap:6px">
      <v-sheet v-for="(it, idx) in items" :key="idx" rounded="lg" border class="pa-2 d-flex align-center">
        <div class="flex-grow-1" style="min-width:0">
          <div class="text-body-2 text-truncate">{{ it.item_name || 'без названия' }}</div>
          <div class="text-caption text-medium-emphasis">
            {{ it.quantity }} {{ it.unit }} × {{ it.unit_price != null ? formatMoney(it.unit_price) : '—' }}
          </div>
          <div class="text-caption text-medium-emphasis">ФЭО: {{ feoCategoryNameById(it.feo_category_id) || '—' }}</div>
        </div>
        <div class="text-body-2 font-weight-medium ml-2 flex-shrink-0">{{ formatMoney(it.total_price || 0) }}</div>
      </v-sheet>
    </div>

    <div class="text-subtitle-2 font-weight-medium mb-1">
      Согласующие ({{ decidedCount }} из {{ approvers.length }})
    </div>
    <div class="d-flex flex-column mb-2" style="gap:6px">
      <div v-for="a in approvers" :key="a.id" class="d-flex align-center" style="gap:8px">
        <span class="text-body-2">{{ a.full_name || '—' }}</span>
        <v-chip v-if="a.user_id === currentUserId" size="x-small" variant="tonal" color="primary">Вы</v-chip>
        <v-spacer />
        <v-chip size="x-small" :color="approvalStatusColor[a.status]" variant="tonal">
          {{ approvalStatusLabel[a.status] || a.status }}
        </v-chip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { shortName, wishCoAuthors, wishRecipients, formatDate, statusLabel, priorityLabel } from '@/composables/wishes/useWishesContext'
import { formatMoney } from '@/utils/formatMoney'
import { pluralRu } from '@/composables/products/productsTypes'
import type { Wish, WishItem, WishApprover } from '@/composables/wishes/wishTypes'

const props = defineProps<{
  wish: Wish
  items: WishItem[]
  totalAmount: number
  subsidyName: string | null
  desiredDate: string | null
  contractFormLabel: string | null
  approvers: WishApprover[]
  currentUserId: number | null
  approvalStatusLabel: Record<string, string>
  approvalStatusColor: Record<string, string>
  feoCategoryNameById: (id?: number | null) => string
}>()

const subjectExpanded = ref(false)
// Грубая эвристика «нужна ли кнопка разворота» — порог на глаз, как и в
// остальных местах проекта, где длинный текст обрезают CSS line-clamp +
// кнопкой разворота (3 строки заголовка ~ 80+ символов на экране телефона).
const subjectOverflowCandidate = computed(() => (props.wish.title || '').length > 80)

const coAuthorsSuffix = computed(() => {
  const names = wishCoAuthors(props.wish)
  return names.length ? `, ${names.join(', ')}` : ''
})
const recipients = computed(() => wishRecipients(props.wish))

const decidedCount = computed(() => props.approvers.filter(a => a.status !== 'pending').length)
</script>

<style scoped>
.wish-decision-summary__subject--clamped {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
