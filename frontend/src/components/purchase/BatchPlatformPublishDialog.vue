<template>
  <v-dialog v-model="show" max-width="880" scrollable>
    <v-card class="d-flex flex-column" style="max-height: 90vh">
      <v-card-title class="d-flex align-center pa-4 bg-surface-variant">
        <v-icon start color="teal">mdi-cloud-upload-outline</v-icon>
        <span class="text-h6 font-weight-bold">Массовая публикация на ЭТП</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="show = false" />
      </v-card-title>

      <v-card-text class="pa-4 flex-grow-1 overflow-y-auto">
        <v-row dense class="mb-3">
          <v-col cols="12" sm="6">
            <v-select
              v-model="platform"
              :items="PLATFORM_OPTIONS"
              item-title="title"
              item-value="value"
              label="Торговая площадка"
              variant="outlined"
              density="compact"
              hide-details
              @update:model-value="runCheck"
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-select
              v-model="procedureType"
              :items="currentProcedureTypes"
              item-title="title"
              item-value="value"
              label="Вид процедуры"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model="proposalStart"
              type="datetime-local"
              label="Начало приёма заявок"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model="proposalEnd"
              type="datetime-local"
              label="Окончание приёма (7 дн.)"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model="summingUpDate"
              type="datetime-local"
              label="Подведение итогов (+2 дн.)"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
        </v-row>

        <div class="d-flex flex-wrap align-center justify-space-between px-2 mb-3 bg-grey-lighten-4 rounded py-1">
          <v-switch
            v-model="asDraft"
            color="primary"
            density="compact"
            hide-details
            :label="asDraft ? 'Создать черновиком на ЭТП (по умолчанию)' : 'Сразу разместить процедуру на ЭТП'"
          />
          <v-checkbox
            v-model="attachDocs"
            color="primary"
            density="compact"
            hide-details
            label="Прикладывать файлы документов"
          />
        </div>

        <v-alert
          v-if="publishResults.length > 0"
          :type="hasPublishErrors ? 'warning' : 'success'"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          <div class="font-weight-bold mb-1">
            Отправлено: {{ successPublishCount }} из {{ publishResults.length }}
          </div>
          <div v-for="res in publishResults" :key="res.purchase_id" class="text-caption">
            <strong>{{ res.number || `#${res.purchase_id}` }}:</strong>
            <span v-if="res.status === 'publishing'" class="text-success font-weight-medium ml-1">
              Успешно отправлено на площадку (ID: {{ res.pub_id || '—' }})
            </span>
            <span v-else class="text-error font-weight-medium ml-1">
              Ошибка: {{ res.error || 'Сбой отправки' }}
            </span>
          </div>
        </v-alert>

        <div class="d-flex align-center justify-space-between mb-2">
          <div class="text-subtitle-2 font-weight-bold">
            Выбранные закупки ({{ selectedOrders.length }}):
            <span class="text-success ml-2">Готовы: {{ readyItems.length }}</span>
            <span v-if="notReadyItems.length" class="text-error ml-2">Замечания: {{ notReadyItems.length }}</span>
          </div>
          <v-btn
            size="small"
            variant="text"
            color="primary"
            prepend-icon="mdi-refresh"
            :loading="checking"
            @click="runCheck"
          >
            Перепроверить
          </v-btn>
        </div>

        <v-progress-linear v-if="checking" indeterminate color="teal" class="mb-2" />

        <v-table density="compact" class="border rounded">
          <thead>
            <tr>
              <th style="width: 25%">Закупка</th>
              <th style="width: 35%">Тема</th>
              <th style="width: 40%">Готовность к публикации</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in checkItems" :key="item.purchase_id">
              <td>
                <a
                  :href="`/orders/${item.purchase_id}`"
                  target="_blank"
                  class="text-decoration-none font-weight-medium text-primary"
                >
                  {{ item.number || `#${item.purchase_id}` }}
                  <v-icon size="x-small">mdi-open-in-new</v-icon>
                </a>
              </td>
              <td class="text-truncate" style="max-width: 250px" :title="item.subject">
                {{ item.subject || '—' }}
              </td>
              <td>
                <v-chip v-if="item.ready" color="success" size="small" variant="flat">
                  <v-icon start size="x-small">mdi-check-circle</v-icon>
                  Готова
                </v-chip>
                <div v-else class="d-flex flex-column gap-1">
                  <v-chip color="error" size="x-small" variant="tonal" class="align-self-start">
                    <v-icon start size="x-small">mdi-alert-circle</v-icon>Есть замечания
                  </v-chip>
                  <ul class="text-caption text-error pl-4 mb-0">
                    <li v-for="(iss, idx) in item.issues" :key="idx">{{ iss }}</li>
                  </ul>
                </div>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>

      <v-card-actions class="pa-4 bg-surface-variant">
        <v-spacer />
        <v-btn variant="text" :disabled="publishing" @click="show = false">Закрыть</v-btn>
        <v-btn
          color="teal"
          variant="flat"
          :loading="publishing"
          :disabled="checking || readyItems.length === 0"
          prepend-icon="mdi-cloud-upload"
          @click="doBatchPublish"
        >
          Отправить готовые ({{ readyItems.length }})
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import type { Purchase } from '@/composables/orders/ordersTypes'
import type { ToastType } from '@/composables/useToast'

interface CheckItem {
  purchase_id: number; number?: string; subject?: string; ready: boolean; issues: string[]
}
interface PublishItemResult {
  purchase_id: number; number?: string; pub_id?: number; status: string; error?: string
}

const props = defineProps<{
  showSnack: (text: string, color?: ToastType) => void
  onPublished?: () => void
}>()

const show = ref(false)
const checking = ref(false)
const publishing = ref(false)
const selectedOrders = ref<Purchase[]>([])
const checkItems = ref<CheckItem[]>([])
const publishResults = ref<PublishItemResult[]>([])

const PLATFORM_OPTIONS = [
  { value: 'roseltorg_rb', title: 'Росэлторг.Бизнес' },
  { value: 'fabrikant', title: 'Фабрикант' },
]
const ROSELTORG_PROCEDURES = [
  { value: 'request_quotations', title: 'Закупка с выбором победителя' },
  { value: 'request_proposals', title: 'Закупка без выбора победителя (анализ рынка)' },
]
const FABRIKANT_PROCEDURES = [
  { value: 'zp', title: 'Запрос предложений' },
  { value: 'reduction', title: 'Редукцион' },
  { value: 'price_monitoring', title: 'Мониторинг цен' },
]

const platform = ref('roseltorg_rb')
const procedureType = ref('request_quotations')
const asDraft = ref(true)
const attachDocs = ref(true)
const proposalStart = ref('')
const proposalEnd = ref('')
const summingUpDate = ref('')

const currentProcedureTypes = computed(() =>
  platform.value === 'fabrikant' ? FABRIKANT_PROCEDURES : ROSELTORG_PROCEDURES,
)
const readyItems = computed(() => checkItems.value.filter(i => i.ready))
const notReadyItems = computed(() => checkItems.value.filter(i => !i.ready))
const successPublishCount = computed(() => publishResults.value.filter(r => r.status === 'publishing').length)
const hasPublishErrors = computed(() => publishResults.value.some(r => r.status === 'failed'))

function initDates() {
  const pad = (n: number) => String(n).padStart(2, '0')
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  const now = new Date()
  const end = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000)
  const sum = new Date(end.getTime() + 2 * 24 * 60 * 60 * 1000)
  proposalStart.value = fmt(new Date(now.getTime() + 60 * 60 * 1000))
  proposalEnd.value = fmt(end)
  summingUpDate.value = fmt(sum)
}

async function runCheck() {
  if (!selectedOrders.value.length) return
  if (platform.value === 'fabrikant' && procedureType.value.startsWith('request_')) {
    procedureType.value = 'zp'
  } else if (platform.value === 'roseltorg_rb' && !procedureType.value.startsWith('request_')) {
    procedureType.value = 'request_quotations'
  }
  checking.value = true
  try {
    const ids = selectedOrders.value.map(o => o.id)
    const res = await apiFetch<CheckItem[]>('/publications/batch-check', {
      method: 'POST',
      body: JSON.stringify({ purchase_ids: ids, platform: platform.value }),
      suppressErrorDialog: true,
    })
    checkItems.value = res || []
  } catch (e: any) {
    props.showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка предпроверки', 'error')
  } finally {
    checking.value = false
  }
}

async function doBatchPublish() {
  const readyIds = readyItems.value.map(i => i.purchase_id)
  if (!readyIds.length) return
  publishing.value = true
  publishResults.value = []
  try {
    const res = await apiFetch<PublishItemResult[]>('/publications/batch-publish', {
      method: 'POST',
      body: JSON.stringify({
        purchase_ids: readyIds,
        platform: platform.value,
        as_draft: asDraft.value,
        procedure_type: procedureType.value,
        proposal_start: proposalStart.value || null,
        proposal_end: proposalEnd.value || null,
        summing_up_date: summingUpDate.value || null,
        attach_documents: attachDocs.value,
      }),
      suppressErrorDialog: true,
    })
    publishResults.value = res || []
    const successCount = res.filter(r => r.status === 'publishing').length
    if (successCount > 0) {
      props.showSnack(`Отправлено на площадку: ${successCount} из ${readyIds.length}`, 'success')
      props.onPublished?.()
    } else {
      props.showSnack('Не удалось отправить закупки на площадку', 'error')
    }
    await runCheck()
  } catch (e: any) {
    props.showSnack(e?.payload?.message || e?.detail || e?.message || 'Сбой пакетной публикации', 'error')
  } finally {
    publishing.value = false
  }
}

function open(orders: Purchase[]) {
  selectedOrders.value = [...orders]
  publishResults.value = []
  initDates()
  show.value = true
  runCheck()
}

defineExpose({ open })
</script>
