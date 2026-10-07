<!-- Окно расшифровки клика по сумме строки дерева ФЭО («В закупках» /
     «законтрактовано» / «из них заказано» / «зарезервировано» / «не
     распределено») — по образцу ContractsDrillDialog.vue. Смонтирован ОДИН раз
     в FeoTreeTable.vue, состояние — singleton useFeoRowDrill.ts (открывает
     FeoTreeRow.vue). Бэк (GET /feo-categories/{id}/row-drill) уже считает по
     поддереву категории — здесь только показ готовых rows/total, свой расчёт
     не заводим (Правило №6). -->
<template>
  <v-dialog :model-value="drill.visible.value" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && drill.close()">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #1e3a5f, #312e81); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">
            {{ FEO_ROW_DRILL_LABELS[drill.kind.value] }} — {{ drill.categoryName.value }}
          </div>
        </div>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ drill.rows.value.length }} шт.</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="drill.close()" />
      </v-card-title>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="drill.loading.value" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка закупок…</div>
        </div>
        <v-alert v-else-if="drill.error.value" type="error" variant="tonal" density="compact" class="ma-3">{{ drill.error.value }}</v-alert>
        <div v-else style="overflow-x:auto">
          <v-table density="compact" style="min-width:960px">
            <thead>
              <tr>
                <th class="px-4">№ реестра</th>
                <th class="px-4">Контрагент</th>
                <th class="px-4">Тип договора</th>
                <th class="px-4">Статус</th>
                <th class="px-4">Статья ФЭО</th>
                <th class="text-right px-4">Сумма</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in drill.rows.value" :key="r.purchase_id" style="cursor:pointer"
                @click="router.push(`/orders/${r.purchase_id}/edit`); drill.close()"
              >
                <td class="px-4 py-2" style="max-width:260px">
                  <div style="font-size:13px">{{ r.registry_number || r.purchase_id }}</div>
                  <div v-if="r.subject" class="text-caption text-medium-emphasis" style="white-space:normal">{{ r.subject }}</div>
                </td>
                <td class="px-4 text-caption">
                  <div>{{ r.contractor || '—' }}</div>
                  <div v-if="r.reimbursement_user" class="text-caption text-medium-emphasis">кому возмещать: {{ r.reimbursement_user }}</div>
                </td>
                <td class="px-4 text-caption">{{ contractTypeLabel(r.contract_type) || '—' }}</td>
                <td class="px-4 text-caption">{{ purchaseStatusLabel(r.status) || '—' }}</td>
                <td class="px-4 text-caption">
                  {{ r.feo_category_id != null && r.feo_category_id !== drill.categoryId.value ? (r.feo_category_name || '—') : '' }}
                </td>
                <td class="text-right px-4 font-weight-medium text-primary">{{ formatCurrency(r.amount) }}</td>
              </tr>
              <tr v-if="drill.rows.value.length === 0">
                <td colspan="6" class="text-center py-6 text-medium-emphasis">Нет закупок</td>
              </tr>
            </tbody>
            <tfoot v-if="drill.rows.value.length">
              <tr>
                <td colspan="5" class="px-4 text-right font-weight-medium">Итого</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(drill.total.value) }}</td>
              </tr>
            </tfoot>
          </v-table>
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-btn v-if="drill.categoryId.value != null" color="primary" variant="tonal" prepend-icon="mdi-cart-outline"
          @click="router.push(`/orders?feo_category_id=${drill.categoryId.value}`); drill.close()"
        >Открыть закупки статьи</v-btn>
        <v-spacer />
        <v-btn @click="drill.close()">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { useRouter } from 'vue-router'
import { formatCurrency } from '@/composables/subsidies/format'
import { useFeoRowDrill, FEO_ROW_DRILL_LABELS } from '@/composables/subsidies/useFeoRowDrill'
import { contractTypeLabel, purchaseStatusLabel } from '@/constants/purchaseStatus'

const { mobile } = useDisplay()
const router = useRouter()
const drill = useFeoRowDrill()
</script>
