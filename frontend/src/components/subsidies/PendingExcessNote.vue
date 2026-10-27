<!-- Шаг 6 (план humble-stirring-emerson.md, 23.10.2026), ПЕРЕРАБОТАНО
     27.10.2026 (задача владельца) — ссылка «выше ФЭО на N ₽» под карточкой
     «Запланировано» (SubsidyKpiCards.vue — ОДНА строка вставки там, сама
     логика/разметка здесь, в отдельном файле, Правило №5). С 27.10.2026
     карточка «Запланировано» показывает ПОЛНУЮ сумму плановых позиций
     СРАЗУ (включая эту часть) — ссылка больше не «прибавляется» к карточке,
     она ТОЛЬКО поясняет, что часть уже показанной суммы выше бюджета ФЭО
     статьи и ждёт решения согласующего (заявку/план это НЕ блокирует —
     решает согласующий). Слово «согласование» здесь не используется, пока
     по узлу нет реального запроса (PlanExcessApproval) — см. nodePending в
     usePendingExcessTotal.ts/строке списка ниже.

     N=0 — компонент ничего не рисует (v-if). Без права «Видеть ФОТ» — ФОТ-
     узлы просто отсутствуют в planTreeByCat (см. usePendingExcessTotal.ts),
     никакой второй проверки прав здесь не нужно. -->
<template>
  <div v-if="total > 0.005" class="kpi-sub-note kpi-pending-excess-note text-caption" @click.stop="dialogVisible = true"
    title="Из суммы «Запланировано» часть выше бюджета ФЭО статьи; заявку/план это не блокирует — решает согласующий">
    выше ФЭО на {{ formatCurrency(total) }}
  </div>

  <v-dialog v-model="dialogVisible" max-width="560">
    <v-card>
      <v-card-title class="text-subtitle-1">Выше ФЭО — превышение +{{ formatCurrency(total) }}</v-card-title>
      <v-card-text class="pending-excess-list">
        <div v-for="(row, i) in rows" :key="i" class="pending-excess-row"
          :class="{ 'pending-excess-row-clickable': row.purchaseId != null }"
          @click="openPurchase(row.purchaseId)"
        >
          <div class="pending-excess-row-main">
            <div class="pending-excess-cat text-caption text-medium-emphasis">{{ row.categoryName }}</div>
            <div class="pending-excess-item">
              <template v-if="row.purchaseNumber != null">закупка № {{ row.purchaseNumber }}</template>
              <template v-else-if="row.purchaseId != null">закупка #{{ row.purchaseId }}</template>
              <template v-else>без привязки к закупке</template>
              <template v-if="row.itemName"> «{{ row.itemName }}»</template>
              <template v-if="row.nodePending"> — отправлено на согласование</template>
            </div>
          </div>
          <div class="pending-excess-amount text-error">+{{ formatCurrency(row.amount) }}</div>
        </div>
        <div v-if="!rows.length" class="text-medium-emphasis text-caption">нет данных по позициям превышения</div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="dialogVisible = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePendingExcessTotal } from '@/composables/subsidies/usePendingExcessTotal'
import { formatCurrency } from '@/composables/subsidies/format'

const ctx = useSubsidyDetailCtx()
const { total, rows } = usePendingExcessTotal(ctx)

const dialogVisible = ref(false)

function openPurchase(purchaseId: number | null) {
  if (purchaseId == null) return
  dialogVisible.value = false
  ctx.router.push(`/orders/${purchaseId}`)
}
</script>

<style scoped>
.kpi-pending-excess-note {
  color: #B91C1C;
  cursor: pointer;
  text-decoration: underline dotted;
  margin-top: 2px;
}
.kpi-pending-excess-note:hover {
  opacity: 0.85;
}
.pending-excess-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pending-excess-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 8px;
  border-radius: 6px;
}
.pending-excess-row-clickable {
  cursor: pointer;
}
.pending-excess-row-clickable:hover {
  background: rgba(0, 0, 0, 0.05);
}
.pending-excess-row-main {
  min-width: 0;
}
.pending-excess-item {
  font-size: 13px;
}
.pending-excess-amount {
  flex: none;
  font-weight: 600;
  white-space: nowrap;
}
</style>
