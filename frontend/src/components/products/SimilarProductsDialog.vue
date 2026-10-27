<template>
  <v-dialog v-model="show" max-width="1100" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>Похожие товары</span>
        <v-btn icon="mdi-close" variant="text" density="comfortable" @click="show = false" />
      </v-card-title>

      <v-card-text>
        <div class="d-flex gap-2 mb-4 flex-wrap align-center">
          <v-text-field
            v-model="query"
            label="Что ищем" placeholder="например, огнетуш, Makita"
            variant="outlined" density="compact" hide-details
            style="max-width: 320px"
            @keyup.enter="search"
          />
          <v-btn color="primary" :loading="loading" @click="search">Найти</v-btn>
        </div>

        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

        <div v-if="searched && !loading && !groups.length" class="text-body-2 text-medium-emphasis">
          Похожих карточек не найдено.
        </div>

        <div v-for="group in groups" :key="`${group.brand}__${group.base_model}__${group.match_key}`" class="sp-group mb-6">
          <div class="d-flex align-center gap-2 mb-2 flex-wrap">
            <span class="text-subtitle-1 font-weight-bold">{{ group.brand }} {{ group.model_display || group.base_model }}</span>
            <v-chip v-if="group.match_key === 'article'" color="success" size="small" variant="flat">
              Совпал артикул производителя
            </v-chip>
            <v-chip v-else color="warning" size="small" variant="flat">
              Проверьте — отличаются слова
            </v-chip>
          </div>

          <v-alert v-if="group.mergedReport" type="success" density="compact" variant="tonal" class="mb-2">
            {{ group.mergedReport }}
          </v-alert>

          <div class="sp-table-wrap mb-2">
            <v-table density="compact">
              <thead>
                <tr>
                  <th class="sp-nowrap-cell">Оставить эту</th>
                  <th>Объединить в неё</th>
                  <th>Название</th>
                  <th>Магазин</th>
                  <th class="sp-nowrap-cell">Цена</th>
                  <th>Ссылка</th>
                  <th class="sp-nowrap-cell">Цен в истории</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="card in group.cards" :key="card.id">
                  <td class="sp-nowrap-cell">
                    <v-radio-group
                      :model-value="group.winnerId" hide-details density="compact"
                      @update:model-value="(v: number) => setWinner(group, v)"
                    >
                      <v-radio :value="card.id" :label="`№${card.id}`" />
                    </v-radio-group>
                  </td>
                  <td>
                    <v-tooltip v-if="card.id !== group.winnerId && card.same_store_as_winner" text="Тот же магазин — это разные товары" location="top">
                      <template #activator="{ props: tipProps }">
                        <v-checkbox v-bind="tipProps" :model-value="false" disabled hide-details density="compact" />
                      </template>
                    </v-tooltip>
                    <v-checkbox
                      v-else-if="card.id !== group.winnerId"
                      :model-value="group.mergeIds.has(card.id)"
                      hide-details density="compact"
                      @update:model-value="() => toggleMerge(group, card.id)"
                    />
                  </td>
                  <td class="sp-name-cell">
                    <span v-for="(seg, i) in highlightDiffTokens(card.name, card.diff_tokens)" :key="i" :class="{ 'font-weight-bold text-primary': seg.bold }">{{ seg.text }}</span>
                  </td>
                  <td>{{ orgShortName(contractorName(card.contractor_id)) }}</td>
                  <td class="sp-nowrap-cell sp-price-cell">{{ card.price != null ? formatMoney(card.price) : '—' }}</td>
                  <td>
                    <a v-if="isUrl(card.source_ref)" :href="card.source_ref!" :title="card.source_ref!" target="_blank" rel="noopener noreferrer">{{ linkDomain(card.source_ref) }}</a>
                    <span v-else>—</span>
                  </td>
                  <td class="sp-nowrap-cell">{{ card.history_count }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>

          <v-btn
            color="primary" variant="tonal" size="small" prepend-icon="mdi-merge"
            :disabled="!group.winnerId || group.mergeIds.size === 0"
            :loading="group.merging"
            @click="requestMerge(group)"
          >
            Объединить выбранные ({{ group.mergeIds.size }})
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>

  <!-- Подтверждение слияния — внутри диалога, не window.confirm (память проекта). -->
  <v-dialog :model-value="!!confirmTarget" max-width="520" @update:model-value="(v: boolean) => { if (!v) cancelMergeConfirm() }">
    <v-card v-if="confirmTarget">
      <v-card-title>Объединить карточки?</v-card-title>
      <v-card-text>
        Карточки {{ confirmLoserLabels }} будут объединены в №{{ confirmTarget.winnerId }} «{{ confirmWinnerName }}».
        Цены всех магазинов, фото, описания, заявки и договоры перейдут в оставшуюся карточку. Отменить нельзя.
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="cancelMergeConfirm">Отмена</v-btn>
        <v-btn color="error" :loading="confirmTarget.merging" @click="confirmMerge">Объединить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// SimilarProductsDialog.vue — «Похожие товары» (владелец, 27.10.2026): ручная
// проверка и слияние карточек каталога, которые, вероятно, один и тот же
// товар у разных магазинов. Вся логика — в useSimilarProducts.ts (ПРАВИЛО
// №5), этот файл — только вёрстка.
import { computed } from 'vue'
import { useSimilarProducts, highlightDiffTokens } from '@/composables/products/useSimilarProducts'
import { isUrl, linkDomain } from '@/composables/products/productsTypes'
import { orgShortName } from '@/utils/orgShortName'
import { useToast, type ToastType } from '@/composables/useToast'

const props = defineProps<{
  reloadProducts: () => Promise<void>
}>()

const show = defineModel<boolean>({ default: false })

const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const {
  query, loading, searched, groups, confirmTarget,
  search, setWinner, toggleMerge, requestMerge, cancelMergeConfirm, confirmMerge,
  contractorName,
} = useSimilarProducts({ showSnack, reloadProducts: props.reloadProducts })

const confirmWinnerName = computed(() => {
  const g = confirmTarget.value
  if (!g) return ''
  return g.cards.find(c => c.id === g.winnerId)?.name || ''
})
const confirmLoserLabels = computed(() => {
  const g = confirmTarget.value
  if (!g) return ''
  return [...g.mergeIds].map(id => `№${id}`).join(', ')
})

function formatMoney(v: number): string {
  return Number(v).toLocaleString('ru-RU') + ' ₽'
}
</script>

<style scoped>
.sp-table-wrap {
  overflow-x: auto;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
}
.sp-table-wrap table {
  min-width: 720px;
}
.sp-name-cell {
  min-width: 220px;
  white-space: normal;
}
/* «№24»/«330 ₽» не должны разрываться на две строки в узкой колонке
   (владелец, 27.10.2026, приёмка п.2). */
.sp-nowrap-cell {
  white-space: nowrap;
}
.sp-price-cell {
  font-variant-numeric: tabular-nums;
}
</style>
