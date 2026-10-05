<template>
  <v-card variant="outlined" class="h-100 d-flex flex-column wish-card" hover @click="$emit('open')">
    <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт на всю ширину карточки
         (.wish-stopped-banner — общий НЕ scoped класс, см. WishesView.vue::<style>). -->
    <div v-if="wish.stopped_at" class="wish-stopped-banner ma-2 mb-0">
      <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
      <span class="wish-stopped-banner__title">{{ wish.stopped_partial ? 'ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</span>
      <span class="wish-stopped-banner__meta">{{ stoppedByLine(wish) }}</span>
    </div>

    <v-card-text class="pb-1 pt-3 flex-grow-1">
      <!-- Владелец (мобильные карточки, 2026-10-05): «№N · дата создания» слева,
           «N позиций» справа — заменяет старую подпись registry_number на вкладках
           «На согласование мне»/«Заявки сотрудников»; на «Моих» оставлена старая
           подпись через showRegistryNumber, чтобы карточка выглядела ровно как раньше. -->
      <div v-if="showHeaderMeta" class="d-flex align-center justify-space-between mb-1" style="gap:8px">
        <span class="text-caption text-medium-emphasis">№{{ wish.id }} · {{ formatDate(wish.created_at) }}</span>
        <span v-if="wish.items_count" class="text-caption text-medium-emphasis">{{ wish.items_count }} {{ pluralRu(wish.items_count, 'позиция', 'позиции', 'позиций') }}</span>
      </div>

      <div
        class="font-weight-bold text-body-2 mb-2"
        :class="{ 'wish-card-title-clamp': titleClamp }"
        style="overflow-wrap:anywhere"
      >
        {{ wish.title || '—' }}
      </div>

      <div v-if="showStatusChip || showAwaitingChip || showRegistryNumber" class="d-flex flex-wrap align-center ga-1 mb-2">
        <v-chip
          v-if="showStatusChip"
          :color="statusColor[wish.status]"
          size="x-small"
          variant="tonal"
          :title="wish.status === 'rejected' ? rejectedByLine(wish) : undefined"
        >
          {{ statusLabel[wish.status] }}
        </v-chip>
        <!-- Владелец: «Ждёт вашего решения» — только когда заявка submitted И текущий
             пользователь входит в круг, кто может решить прямо из списка (см.
             canDecideFromList в useWishActions.ts, тот же предикат, что у кнопок
             «Одобрить»/«Отклонить» снизу). -->
        <v-chip v-if="showAwaitingChip && awaitingDecision" size="x-small" variant="tonal" :color="GALA_ORANGE">
          Ждёт вашего решения
        </v-chip>
        <span v-if="showRegistryNumber && wish.registry_number" class="text-caption text-medium-emphasis">{{ wish.registry_number }}</span>
      </div>

      <div v-if="wish.creator_name" class="text-caption text-medium-emphasis mb-1">
        От: <span class="font-weight-medium text-high-emphasis">{{ shortName(wish.creator_name) }}</span><span
          v-if="coAuthors.length">, {{ coAuthors.join(', ') }}</span>
      </div>
      <div v-if="showRecipients && recipients" class="text-caption text-medium-emphasis mb-1">
        Кому: <span class="font-weight-medium text-high-emphasis">{{ recipients }}</span>
      </div>
      <div v-if="showSubsidy && wish.subsidy_name" class="text-caption text-medium-emphasis mb-1">
        Субсидия: <span class="font-weight-medium text-high-emphasis">{{ wish.subsidy_name }}</span>
      </div>
      <div v-if="showExecutor && wish.executor_name" class="text-caption text-medium-emphasis mb-1">
        Исполнитель: <span class="font-weight-medium text-high-emphasis">{{ wish.executor_name }}</span>
      </div>
      <div v-if="showDeadline && wish.execution_deadline" class="text-caption text-medium-emphasis mb-1">
        Срок: <span class="font-weight-medium">{{ formatDate(wish.execution_deadline) }}</span>
      </div>

      <div v-if="total != null" class="mt-1" :class="sumLabel ? 'text-caption text-medium-emphasis' : ''">
        <span v-if="sumLabel">Сумма: </span><span
          class="font-weight-medium"
          :class="sumLabel ? '' : 'text-body-1'"
          style="font-variant-numeric: tabular-nums"
        >{{ formatPrice(total) }}</span>
      </div>
    </v-card-text>

    <v-divider />
    <v-card-actions class="py-1 flex-wrap" style="gap:4px" @click.stop>
      <slot name="actions" />
    </v-card-actions>
  </v-card>
</template>

<script setup lang="ts">
// WishCard.vue — единая карточка заявки для мобильного вида всех трёх вкладок
// «Заявки на закупку» (Мои / На согласование мне / Заявки сотрудников), ПРАВИЛО
// №5 (модульность) + ПРАВИЛО №6 (один источник истины — карточка не копируется
// в каждой вкладке). Сама карточка не решает, какие кнопки показывать снизу —
// это кладёт родитель через слот #actions (действия у каждой вкладки свои и
// уже реализованы в useWishActions.ts/WishFormDialog.vue, здесь НЕ дублируются).
// Через showHeaderMeta/showSubsidy/showRegistryNumber/titleClamp/sumLabel
// WishMyTab.vue воспроизводит СТАРЫЙ вид карточки «Мои заявки» (до разбиения —
// см. git-историю WishMyTab.vue), а WishIncomingTab.vue/WishAllTab.vue получают
// новый вид по макету владельца (2026-10-05): №/дата создания + позиции сверху,
// жирный заголовок с обрезкой в 2 строки, субсидия, крупная сумма.
import { computed } from 'vue'
import {
  useWishesContext, statusColor, statusLabel, GALA_ORANGE,
  shortName, wishCoAuthors, wishRecipients, wishItemsTotal, formatDate, formatPrice,
  stoppedByLine, rejectedByLine,
} from '@/composables/wishes/useWishesContext'
import { canDecideFromList } from '@/composables/wishes/useWishActions'
import { pluralRu } from '@/composables/products/productsTypes'
import type { Wish } from '@/composables/wishes/wishTypes'

const props = withDefaults(defineProps<{
  wish: Wish
  /** «№N · дата создания» слева / «N позиций» справа (новый макет, 2026-10-05). */
  showHeaderMeta?: boolean
  showStatusChip?: boolean
  /** Чип «Ждёт вашего решения» (только на submitted + canDecideFromList). */
  showAwaitingChip?: boolean
  /** Старая подпись registry_number рядом с чипом статуса (карточка «Мои заявки»). */
  showRegistryNumber?: boolean
  showRecipients?: boolean
  showSubsidy?: boolean
  showExecutor?: boolean
  showDeadline?: boolean
  /** Обрезка заголовка в 2 строки (новый макет). На «Моих» — false, как раньше. */
  titleClamp?: boolean
  /** true → «Сумма: 45 000 ₽» мелко (старый вид). false → крупная сумма без подписи. */
  sumLabel?: boolean
}>(), {
  showHeaderMeta: false,
  showStatusChip: true,
  showAwaitingChip: false,
  showRegistryNumber: false,
  showRecipients: true,
  showSubsidy: false,
  showExecutor: false,
  showDeadline: false,
  titleClamp: false,
  sumLabel: true,
})

defineEmits<{ (e: 'open'): void }>()

const ctx = useWishesContext()

const coAuthors = computed(() => wishCoAuthors(props.wish))
const recipients = computed(() => wishRecipients(props.wish))
const total = computed(() => wishItemsTotal(props.wish))
const awaitingDecision = computed(() => canDecideFromList(props.wish, ctx))
</script>

<style scoped>
.wish-card-title-clamp {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
</style>
