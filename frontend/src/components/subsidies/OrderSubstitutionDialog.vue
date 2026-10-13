<!-- Задача владельца (13.10.2026) — окно «Перерасход/экономия по заказам»:
     клик по подписи «в т.ч. перерасход по заказам +X · экономия −Y» на
     карточке «Запланировано» (SubsidyKpiCards.vue, без categoryId — вся
     субсидия) ИЛИ по подписи у категории дерева (FeoCategoryEconomyNote.vue,
     с categoryId — она + поддерево) — ОДНО окно для обоих входов. Данные —
     GET /api/feo-categories/order-substitution-rows (app.services.feo_order_diff,
     ПРАВИЛО №6 — та же точка, что считает order_overspend/order_economy
     дерева, см. её докстринг) — фронт ничего не считает, только показывает
     готовые строки/итоги. -->
<template>
  <v-dialog :model-value="visible" max-width="1000" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #7c2d12, #166534); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">Перерасход / экономия по заказам</div>
          <div v-if="categoryId" class="text-caption" style="opacity:0.85">только категория и её подкатегории</div>
        </div>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-card-text class="pa-0" style="max-height:70vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка позиций…</div>
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact" class="ma-3">{{ error }}</v-alert>
        <template v-else>
          <!-- Блок 1 — Перерасход -->
          <div class="pa-3">
            <div class="text-subtitle-2 font-weight-bold mb-1" style="color:#b91c1c">
              Перерасход по заказам — {{ overspendRows.length }} поз., +{{ formatCurrency(overspendTotal) }}
            </div>
            <div v-if="!overspendRows.length" class="text-caption text-medium-emphasis mb-2">нет позиций с перерасходом</div>
            <div v-else style="overflow-x:auto">
              <v-table density="compact" style="min-width:760px">
                <thead>
                  <tr>
                    <th class="px-3">Категория</th>
                    <th class="px-3">Позиция</th>
                    <th class="text-right px-3">План из файла</th>
                    <th class="text-right px-3">Сумма по договору</th>
                    <th class="text-right px-3">Разница</th>
                    <th class="px-3">Закупка(и)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in overspendRows" :key="'o-' + r.feo_item_id">
                    <td class="px-3 text-caption">{{ r.category_path }}</td>
                    <td class="px-3">{{ r.name }}</td>
                    <td class="text-right px-3">{{ formatCurrency(r.plan_from_file) }}</td>
                    <td class="text-right px-3">{{ formatCurrency(r.contract_amount) }}</td>
                    <td class="text-right px-3 font-weight-medium" style="color:#b91c1c">+{{ formatCurrency(r.diff) }}</td>
                    <td class="px-3">
                      <a v-for="p in r.purchases" :key="p.id" href="#" class="d-block text-caption"
                        @click.prevent="emit('open-purchase', p.id)">
                        {{ p.registry_number || p.purchase_number || ('№' + p.id) }}
                      </a>
                    </td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr>
                    <td colspan="4" class="px-3 text-right font-weight-medium">Итого перерасход</td>
                    <td class="text-right px-3 font-weight-bold" style="color:#b91c1c">+{{ formatCurrency(overspendTotal) }}</td>
                    <td class="px-3" />
                  </tr>
                </tfoot>
              </v-table>
            </div>
          </div>

          <v-divider />

          <!-- Блок 2 — Экономия -->
          <div class="pa-3">
            <div class="text-subtitle-2 font-weight-bold mb-1" style="color:#15803d">
              Экономия по заказам — {{ economyRows.length }} поз., −{{ formatCurrency(economyTotal) }}
            </div>
            <div v-if="!economyRows.length" class="text-caption text-medium-emphasis mb-2">нет позиций с экономией</div>
            <div v-else style="overflow-x:auto">
              <v-table density="compact" style="min-width:760px">
                <thead>
                  <tr>
                    <th class="px-3">Категория</th>
                    <th class="px-3">Позиция</th>
                    <th class="text-right px-3">План из файла</th>
                    <th class="text-right px-3">Сумма по договору</th>
                    <th class="text-right px-3">Разница</th>
                    <th class="px-3">Закупка(и)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in economyRows" :key="'e-' + r.feo_item_id">
                    <td class="px-3 text-caption">{{ r.category_path }}</td>
                    <td class="px-3">{{ r.name }}</td>
                    <td class="text-right px-3">{{ formatCurrency(r.plan_from_file) }}</td>
                    <td class="text-right px-3">{{ formatCurrency(r.contract_amount) }}</td>
                    <td class="text-right px-3 font-weight-medium" style="color:#15803d">{{ formatCurrency(r.diff) }}</td>
                    <td class="px-3">
                      <a v-for="p in r.purchases" :key="p.id" href="#" class="d-block text-caption"
                        @click.prevent="emit('open-purchase', p.id)">
                        {{ p.registry_number || p.purchase_number || ('№' + p.id) }}
                      </a>
                    </td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr>
                    <td colspan="4" class="px-3 text-right font-weight-medium">Итого экономия</td>
                    <td class="text-right px-3 font-weight-bold" style="color:#15803d">−{{ formatCurrency(economyTotal) }}</td>
                    <td class="px-3" />
                  </tr>
                </tfoot>
              </v-table>
            </div>
          </div>

          <v-divider />
          <div class="pa-3 text-right font-weight-bold">
            Итого: {{ netSign }}{{ formatCurrency(Math.abs(netTotal)) }} = Запланировано − план из файла
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { formatCurrency } from '@/composables/subsidies/format'

const { mobile } = useDisplay()

interface OrderSubstitutionRow {
  feo_item_id: number
  category_id: number
  category_path: string
  name: string
  plan_from_file: number
  contract_amount: number
  diff: number
  purchases: { id: number; registry_number: string | null; purchase_number: string | null }[]
}

const props = defineProps<{
  visible: boolean
  subsidyId: number | null
  categoryId?: number | null
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'open-purchase', purchaseId: number): void }>()

const loading = ref(false)
const error = ref<string | null>(null)
const overspendRows = ref<OrderSubstitutionRow[]>([])
const economyRows = ref<OrderSubstitutionRow[]>([])
const overspendTotal = ref(0)
const economyTotal = ref(0)

// Задача владельца — «Итого: +259 876,27 = Запланировано − план из файла»:
// netTotal = overspend − economy (та же разница, что и order_overspend −
// order_economy узла/дерева, ПРАВИЛО №6, не вторая формула).
const netTotal = computed(() => overspendTotal.value - economyTotal.value)
const netSign = computed(() => (netTotal.value >= 0 ? '+' : '−'))

async function load() {
  if (!props.subsidyId) {
    overspendRows.value = []
    economyRows.value = []
    overspendTotal.value = 0
    economyTotal.value = 0
    return
  }
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ subsidy_id: String(props.subsidyId) })
    if (props.categoryId != null) params.set('category_id', String(props.categoryId))
    const res = await apiFetch<{
      overspend: OrderSubstitutionRow[]; economy: OrderSubstitutionRow[]
      overspend_total: number; economy_total: number
    }>(`/feo-categories/order-substitution-rows?${params.toString()}`)
    overspendRows.value = res.overspend || []
    economyRows.value = res.economy || []
    overspendTotal.value = res.overspend_total || 0
    economyTotal.value = res.economy_total || 0
  } catch (e: any) {
    error.value = describeApiError(e, { fallback: 'Не удалось загрузить перерасход/экономию по заказам' })
    overspendRows.value = []
    economyRows.value = []
    overspendTotal.value = 0
    economyTotal.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId, props.categoryId], () => { if (props.visible) load() }, { immediate: true })
</script>
