<template>
  <v-dialog v-model="open" max-width="1120" scrollable :fullscreen="mobile">
    <v-card class="results-dialog-card">
      <!-- Шапка диалога -->
      <v-card-title class="d-flex align-center justify-space-between py-3 px-4 bg-deep-purple-lighten-5">
        <div class="d-flex align-center gap-2">
          <v-icon icon="mdi-gavel" color="deep-purple" size="24" />
          <span class="text-h6 font-weight-bold">Рассмотрение заявок и протокол закупки</span>
          <v-chip v-if="results.registration_number" size="small" color="deep-purple" variant="tonal" class="ml-2">
            № {{ results.registration_number }}
          </v-chip>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- Верхняя панель: синхронизация и импорт -->
        <v-card variant="outlined" class="pa-3 mb-4 bg-grey-lighten-5">
          <v-row dense align="center">
            <v-col cols="12" md="4">
              <v-text-field
                v-model="results.registration_number"
                label="Номер извещения на ЭТП"
                placeholder="Напр. B3004261856309 или 5503399"
                variant="outlined"
                density="compact"
                hide-details
                prepend-inner-icon="mdi-pound"
              />
            </v-col>
            <v-col cols="12" md="8" class="d-flex flex-wrap gap-2 justify-end">
              <v-btn
                color="deep-purple"
                variant="flat"
                size="small"
                prepend-icon="mdi-cloud-sync"
                :loading="syncing"
                @click="syncRoseltorg"
              >
                Получить заявки с Росэлторга
              </v-btn>
              <v-btn
                color="deep-purple"
                variant="tonal"
                size="small"
                prepend-icon="mdi-file-upload-outline"
                :loading="importing"
                title="Загрузить один или несколько файлов протокола, ZIP-архив или ТКП участников"
                @click="triggerFileImport"
              >
                Загрузить документы (.docx, .doc, .xlsx, .pdf, .zip)
              </v-btn>
              <input
                ref="fileInputRef"
                type="file"
                multiple
                accept=".docx,.doc,.xlsx,.pdf,.zip"
                style="display: none"
                @change="handleFileUpload"
              />
              <v-btn
                color="deep-purple"
                variant="outlined"
                size="small"
                prepend-icon="mdi-file-excel-outline"
                title="Скачать стандартизированную форму ТКП (Приложение № 2) в формате Excel"
                :href="`/api/publications/purchases/${props.purchaseId}/tkp-template.xlsx`"
                target="_blank"
              >
                Бланк ТКП (.xlsx)
              </v-btn>
              <v-btn
                color="deep-purple"
                variant="outlined"
                size="small"
                prepend-icon="mdi-file-pdf-box"
                title="Скачать интерактивную заполняемую форму ТКП (Приложение № 2) в формате PDF"
                :href="`/api/publications/purchases/${props.purchaseId}/tkp-template.pdf`"
                target="_blank"
              >
                Бланк ТКП (.pdf)
              </v-btn>
              <v-btn
                color="deep-purple"
                variant="outlined"
                size="small"
                prepend-icon="mdi-format-list-checks"
                :loading="initializingPositions"
                title="Подтянуть список товаров закупки во все заявки для попозиционного сравнения"
                @click="initPositions"
              >
                Позиции закупки
              </v-btn>
              <v-btn
                color="secondary"
                variant="outlined"
                size="small"
                prepend-icon="mdi-plus"
                @click="addManualApp"
              >
                + Заявка
              </v-btn>
            </v-col>
          </v-row>
          <div class="text-caption text-medium-emphasis mt-1 text-right">
            Поддерживаются протоколы (.docx/.doc/.xlsx/.pdf), ZIP-архивы и файлы заявок/ТКП участников с авто-распознаванием аналогов
          </div>
        </v-card>

        <!-- Сводная плашка показателей -->
        <div class="d-flex flex-wrap align-center gap-2 mb-4">
          <v-chip size="small" variant="tonal">
            Подано заявок: <strong>{{ results.applications?.length || 0 }}</strong>
          </v-chip>
          <v-chip size="small" color="success" variant="tonal">
            Допущено: <strong>{{ admittedCount }}</strong>
          </v-chip>
          <v-chip size="small" color="error" variant="tonal">
            Отклонено: <strong>{{ rejectedCount }}</strong>
          </v-chip>
          <v-chip size="small" :color="statusChipColor" variant="tonal">
            {{ statusChipLabel }}
          </v-chip>
          <v-chip v-if="winnerApp" size="small" color="amber-darken-3" variant="tonal" class="ml-auto">
            🏆 Победитель: <strong>{{ winnerApp.supplier_short_name || winnerApp.supplier_name }}</strong>
            ({{ formatMoney(winnerPrice) }} ₽)
          </v-chip>
        </div>

        <!-- Вкладки диалога -->
        <v-tabs v-model="tab" color="deep-purple" density="compact" class="mb-3">
          <v-tab value="apps">
            <v-icon icon="mdi-format-list-numbered" class="mr-1" />
            Заявки и рассмотрение ({{ results.applications?.length || 0 }})
          </v-tab>
          <v-tab value="commission">
            <v-icon icon="mdi-account-group" class="mr-1" />
            Комиссия и реквизиты протокола
          </v-tab>
        </v-tabs>

        <v-window v-model="tab">
          <!-- ВКЛАДКА 1: ЗАЯВКИ -->
          <v-window-item value="apps">
            <div v-if="!results.applications || !results.applications.length" class="text-center py-8 text-medium-emphasis">
              <v-icon icon="mdi-file-document-outline" size="48" class="mb-2 text-grey-lighten-1" />
              <div>Заявки ещё не загружены</div>
              <div class="text-caption mt-1">
                Нажмите «Получить заявки с Росэлторга», загрузите файл протокола или добавьте заявку вручную
              </div>
            </div>

            <div v-else class="d-flex flex-column gap-3">
              <v-card
                v-for="(app, aIdx) in results.applications"
                :key="aIdx"
                variant="outlined"
                :class="['pa-3', app.admitted ? 'border-success-light' : 'border-error-light']"
              >
                <!-- Верхняя строка карточки заявки -->
                <div class="d-flex align-center justify-space-between mb-2">
                  <div class="d-flex align-center gap-2">
                    <v-chip
                      v-if="app.admitted && app.place"
                      size="x-small"
                      :color="app.place === 1 ? 'amber-darken-3' : 'deep-purple'"
                      variant="flat"
                      class="font-weight-bold"
                    >
                      {{ app.place === 1 ? '1 место 🏆' : `${app.place} место` }}
                    </v-chip>
                    <v-chip v-else-if="!app.admitted" size="x-small" color="error" variant="tonal">
                      Отклонена
                    </v-chip>
                    <span class="font-weight-bold text-subtitle-2">
                      Заявка № {{ app.application_number || (aIdx + 1) }}
                    </span>
                    <span v-if="app.submitted_at" class="text-caption text-medium-emphasis">
                      ({{ app.submitted_at }})
                    </span>
                  </div>

                  <div class="d-flex align-center gap-1">
                    <v-btn
                      size="x-small"
                      variant="tonal"
                      color="deep-purple"
                      prepend-icon="mdi-table-arrow-up"
                      title="Загрузить ТКП / заявку конкретно этого участника"
                      @click="triggerAppDocUpload(aIdx)"
                    >
                      Прикрепить ТКП участника
                    </v-btn>
                    <v-btn
                      icon="mdi-delete-outline"
                      size="x-small"
                      variant="text"
                      color="error"
                      title="Удалить заявку"
                      @click="removeApp(aIdx)"
                    />
                  </div>
                </div>

                <!-- Данные участника и цена -->
                <v-row dense class="mb-2">
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="app.supplier_name"
                      label="Наименование участника"
                      variant="outlined"
                      density="compact"
                      hide-details
                      class="mb-2"
                    />
                    <v-row dense>
                      <v-col cols="6">
                        <v-text-field
                          v-model="app.inn"
                          label="ИНН"
                          variant="outlined"
                          density="compact"
                          hide-details
                        />
                      </v-col>
                      <v-col cols="6">
                        <v-text-field
                          v-model="app.kpp"
                          label="КПП"
                          variant="outlined"
                          density="compact"
                          hide-details
                        />
                      </v-col>
                    </v-row>
                  </v-col>

                  <v-col cols="12" md="6">
                    <v-row dense>
                      <v-col cols="7">
                        <v-text-field
                          v-model.number="app.price_with_vat"
                          label="Цена предложения, ₽"
                          type="number"
                          variant="outlined"
                          density="compact"
                          hide-details
                          @update:model-value="onPriceChange"
                        />
                      </v-col>
                      <v-col cols="5">
                        <v-select
                          v-model="app.vat_label"
                          :items="VAT_OPTIONS"
                          label="НДС"
                          variant="outlined"
                          density="compact"
                          hide-details
                        />
                      </v-col>
                    </v-row>

                    <!-- Переключатель допуска -->
                    <div class="mt-2">
                      <v-btn-toggle
                        v-model="app.admitted"
                        mandatory
                        density="compact"
                        rounded="lg"
                        class="w-100"
                        @update:model-value="onAdmittedChange(app)"
                      >
                        <v-btn :value="true" color="success" variant="tonal" class="flex-grow-1">
                          <v-icon icon="mdi-check" size="16" class="mr-1" />
                          Соответствует (Допущена)
                        </v-btn>
                        <v-btn :value="false" color="error" variant="tonal" class="flex-grow-1">
                          <v-icon icon="mdi-close" size="16" class="mr-1" />
                          Не соответствует (Отклонена)
                        </v-btn>
                      </v-btn-toggle>
                    </div>
                  </v-col>
                </v-row>

                <!-- Причина отклонения при admitted === false -->
                <div v-if="!app.admitted" class="mt-2 pa-2 rounded bg-red-lighten-5 border-error-subtle">
                  <div class="text-caption text-error font-weight-medium mb-1">
                    Быстрые шаблоны причин отклонения:
                  </div>
                  <div class="d-flex flex-wrap gap-1 mb-2">
                    <v-chip
                      v-for="(tpl, tIdx) in REJECTION_TEMPLATES"
                      :key="tIdx"
                      size="x-small"
                      color="error"
                      variant="outlined"
                      clickable
                      @click="app.rejection_reason = tpl; app.decision_text = `Не соответствует. ${tpl}`"
                    >
                      {{ tpl }}
                    </v-chip>
                  </div>
                  <v-text-field
                    v-model="app.rejection_reason"
                    label="Точная причина отклонения"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="Например: Заявка не подписана"
                    @update:model-value="app.decision_text = `Не соответствует. ${app.rejection_reason}`"
                  />
                </div>

                <!-- Позиции товаров и работа с аналогами -->
                <PurchaseApplicationPositionsPanel
                  :positions="app.positions || []"
                  :app-admitted="app.admitted"
                  :current-app-price="Number(app.price_with_vat || app.price_without_vat || 0)"
                  @update:positions="(pos) => app.positions = pos"
                  @update:compliance="(val) => onPanelCompliance(app, val)"
                  @apply-price="(p) => onApplyPositionsPrice(app, p)"
                />

                <!-- Прикреплённые документы заявки -->
                <div v-if="app.documents && app.documents.length" class="mt-2 d-flex flex-wrap align-center gap-1">
                  <span class="text-caption text-medium-emphasis">Документы:</span>
                  <v-chip
                    v-for="(doc, dIdx) in app.documents"
                    :key="dIdx"
                    size="x-small"
                    prepend-icon="mdi-paperclip"
                    color="deep-purple"
                    variant="outlined"
                    clickable
                    title="Открыть или скачать документ"
                    @click="openOrDownloadDoc(doc)"
                  >
                    {{ doc.name || doc.fileName || doc.title || `Файл ${dIdx + 1}` }}
                  </v-chip>
                </div>
              </v-card>
            </div>
          </v-window-item>

          <!-- ВКЛАДКА 2: КОМИССИЯ И РЕКВИЗИТЫ ПРОТОКОЛА -->
          <v-window-item value="commission">
            <PurchaseResultsCommissionTab
              :results="results"
              :purchase-id="purchaseId"
            />
          </v-window-item>
        </v-window>
      </v-card-text>

      <v-divider />

      <!-- Нижняя панель действий -->
      <v-card-actions class="px-4 py-3 bg-grey-lighten-5 d-flex flex-wrap align-center gap-2">
        <v-btn variant="text" @click="open = false">
          Закрыть
        </v-btn>
        <v-spacer />
        <v-checkbox
          v-if="winnerApp"
          v-model="applyAcceptedAlternatives"
          label="Перенести цены позиций и принятые аналоги"
          density="compact"
          hide-details
          color="deep-purple"
          class="mr-2"
        />
        <v-btn
          color="secondary"
          variant="outlined"
          prepend-icon="mdi-content-save"
          :loading="saving"
          @click="saveResults(false)"
        >
          Сохранить рассмотрение
        </v-btn>
        <v-btn
          color="deep-purple"
          variant="flat"
          prepend-icon="mdi-file-document-edit"
          :disabled="!winnerApp"
          :loading="applyingWinner"
          title="Вставить предложенные победителем товары, цены и НДС в спецификацию Договора"
          @click="applyWinner"
        >
          Вставить товары, цены и НДС победителя в договор
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-file-word"
          :loading="downloading"
          @click="downloadDocx"
        >
          Скачать Протокол ВСКС (.docx)
        </v-btn>

        <!-- Скрытый инпут для загрузки ТКП конкретного участника -->
        <input
          ref="appDocInputRef"
          type="file"
          accept=".docx,.doc,.xlsx,.pdf"
          style="display: none"
          @change="handleAppDocUpload"
        />
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { formatMoney } from '@/utils/formatMoney'
import PurchaseApplicationPositionsPanel from './PurchaseApplicationPositionsPanel.vue'
import PurchaseResultsCommissionTab from './PurchaseResultsCommissionTab.vue'

const props = defineProps<{
  purchaseId: number
}>()

const emit = defineEmits<{
  (e: 'winner-applied', payload: { contractor_id: number; contractor_name: string; contract_price: number | null }): void
}>()

const open = ref(false)
const tab = ref<'apps' | 'commission'>('apps')
const { mobile } = useDisplay()
const toast = useToast()

const syncing = ref(false)
const importing = ref(false)
const saving = ref(false)
const applyingWinner = ref(false)
const downloading = ref(false)

const pubId = ref<number | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const appDocInputRef = ref<HTMLInputElement | null>(null)
const targetAppIdx = ref<number | null>(null)
const initializingPositions = ref(false)
const applyAcceptedAlternatives = ref(true)

const results = ref<Record<string, any>>({
  registration_number: '',
  notice_date: '',
  protocol_number: '',
  protocol_date: new Date().toISOString().substring(0, 10),
  meeting_time: '16:30',
  meeting_address: '',
  commission_order_number: '',
  commission_order_date: '',
  commission_members: [] as Array<{ full_name: string; role: string }>,
  applications: [] as any[],
})

const VAT_OPTIONS = [
  'Без НДС',
  'в т.ч. НДС 20%',
  'в т.ч. НДС 22%',
  'в т.ч. НДС 10%',
  'в т.ч. НДС 5%',
  'в т.ч. НДС 7%',
  'с НДС',
]


const REJECTION_TEMPLATES = [
  'Заявка не подписана',
  'Нет ценового предложения / формы заявки',
  'Срок действия заявки не соответствует документации',
  'Предложены аналоги, не соответствующие ТЗ',
  'Отсутствуют обязательные документы',
]

const admittedCount = computed(() => {
  return (results.value.applications || []).filter((a: any) => a.admitted).length
})

const rejectedCount = computed(() => {
  return (results.value.applications || []).filter((a: any) => !a.admitted).length
})

const winnerApp = computed(() => {
  const apps = results.value.applications || []
  return apps.find((a: any) => a.admitted && a.place === 1) || apps.find((a: any) => a.admitted)
})

const winnerPrice = computed(() => {
  if (!winnerApp.value) return 0
  return winnerApp.value.price_with_vat || winnerApp.value.price_without_vat || 0
})

const statusChipColor = computed(() => {
  const adm = admittedCount.value
  if (adm >= 2) return 'success'
  if (adm === 1) return 'warning'
  return 'error'
})

const statusChipLabel = computed(() => {
  const adm = admittedCount.value
  if (adm >= 2) return 'Статус: Закупка состоялась'
  if (adm === 1) return 'Статус: Несостоявшаяся (1 допущенная заявка)'
  return 'Статус: Несостоявшаяся (0 допущенных заявок)'
})

function recalculatePlaces() {
  const apps = results.value.applications || []
  const admitted = apps.filter((a: any) => a.admitted)
  const rejected = apps.filter((a: any) => !a.admitted)

  admitted.sort((a: any, b: any) => {
    const pA = Number(a.price_with_vat || a.price_without_vat || 0)
    const pB = Number(b.price_with_vat || b.price_without_vat || 0)
    if (pA !== pB) return pA - pB
    return String(a.submitted_at || '').localeCompare(String(b.submitted_at || ''))
  })

  admitted.forEach((a: any, idx: number) => {
    a.place = idx + 1
  })
  rejected.forEach((a: any) => {
    a.place = null
  })
}

function onPriceChange() {
  recalculatePlaces()
}

function onAdmittedChange(app: any) {
  if (app.admitted) {
    app.rejection_reason = ''
    app.decision_text = 'Признать соответствующей требованиям закупочной документации.'
  } else {
    if (!app.rejection_reason) {
      app.rejection_reason = REJECTION_TEMPLATES[0]
    }
    app.decision_text = `Не соответствует. ${app.rejection_reason}`
  }
  recalculatePlaces()
}

function addManualApp() {
  const nextNum = String((results.value.applications?.length || 0) + 1)
  results.value.applications.push({
    app_id: nextNum,
    application_number: nextNum,
    supplier_name: '',
    supplier_short_name: '',
    inn: '',
    kpp: '',
    submitted_at: '',
    price_with_vat: 0,
    price_without_vat: 0,
    vat_label: 'Без НДС',
    admitted: true,
    rejection_reason: '',
    decision_text: 'Признать соответствующей требованиям закупочной документации.',
    place: null,
  })
  recalculatePlaces()
}

function removeApp(idx: number) {
  results.value.applications.splice(idx, 1)
  recalculatePlaces()
}


async function openDialog(targetPub?: any) {
  open.value = true
  tab.value = 'apps'
  if (targetPub && targetPub.id) {
    pubId.value = targetPub.id
  }
  await loadResults()
}

async function loadResults() {
  try {
    // Гарантируем публикацию
    const ensureRes = await apiFetch<any>(`/publications/purchases/${props.purchaseId}/ensure-for-results`, {
      method: 'POST',
      body: JSON.stringify({
        platform: 'roseltorg_rb',
        platform_number: results.value.registration_number || null,
      }),
    })
    pubId.value = ensureRes.pub_id
    if (ensureRes.results) {
      results.value = ensureRes.results
      recalculatePlaces()
    }
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка загрузки результатов закупки', 'error')
  }
}

async function syncRoseltorg() {
  if (!pubId.value) {
    await loadResults()
  }
  syncing.value = true
  try {
    const res = await apiFetch<any>(`/publications/${pubId.value}/results/sync`, {
      method: 'POST',
      body: JSON.stringify({
        registration_number: results.value.registration_number || null,
      }),
    })
    if (res.results) {
      results.value = res.results
      recalculatePlaces()
      toast.addToast(`Заявки получены с Росэлторга: ${results.value.applications?.length || 0}`, 'success')
    }
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка получения заявок с Росэлторга', 'error')
  } finally {
    syncing.value = false
  }
}

function triggerFileImport() {
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

async function handleFileUpload(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files || !files.length) return
  if (!pubId.value) await loadResults()

  importing.value = true
  try {
    const formData = new FormData()
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i])
    }
    // Для совместимости добавляем первый файл
    formData.append('file', files[0])

    const res = await apiFetch<any>(`/publications/${pubId.value}/results/import-file`, {
      method: 'POST',
      body: formData,
    })
    if (res.results) {
      results.value = res.results
      recalculatePlaces()
      toast.addToast(`Документы успешно обработаны! Заявок: ${results.value.applications?.length || 0}`, 'success')
    }
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка импорта файлов протокола/заявок', 'error')
  } finally {
    importing.value = false
  }
}

function triggerAppDocUpload(aIdx: number) {
  targetAppIdx.value = aIdx
  if (appDocInputRef.value) {
    appDocInputRef.value.value = ''
    appDocInputRef.value.click()
  }
}

async function handleAppDocUpload(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files || !files.length || targetAppIdx.value === null) return
  const file = files[0]
  if (!pubId.value) await loadResults()

  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await apiFetch<any>(`/publications/${pubId.value}/results/applications/${targetAppIdx.value}/upload-doc`, {
      method: 'POST',
      body: formData,
    })
    if (res.results) {
      results.value = res.results
      recalculatePlaces()
      toast.addToast(`ТКП участника распознано и прикреплено! Позиций: ${results.value.applications?.[targetAppIdx.value]?.positions?.length || 0}`, 'success')
    }
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка загрузки ТКП участника', 'error')
  } finally {
    importing.value = false
    targetAppIdx.value = null
  }
}

async function initPositions() {
  if (!pubId.value) await loadResults()
  initializingPositions.value = true
  try {
    const res = await apiFetch<any>(`/publications/${pubId.value}/results/init-positions`, {
      method: 'POST',
    })
    if (res.results) {
      results.value = res.results
      recalculatePlaces()
      toast.addToast('Позиции товаров закупки добавлены во все заявки', 'success')
    }
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка инициализации позиций', 'error')
  } finally {
    initializingPositions.value = false
  }
}

function onPanelCompliance(app: any, payload: { admitted: boolean; rejection_reason: string; decision_text: string }) {
  app.admitted = payload.admitted
  app.rejection_reason = payload.rejection_reason
  app.decision_text = payload.decision_text
  recalculatePlaces()
}

function onApplyPositionsPrice(app: any, price: number) {
  app.price_with_vat = price
  app.price_without_vat = price
  recalculatePlaces()
  toast.addToast(`Цена заявки обновлена по сумме позиций: ${formatMoney(price)} ₽`, 'info')
}

function openOrDownloadDoc(doc: any) {
  if (doc.url) {
    window.open(doc.url, '_blank')
  } else if (pubId.value && doc.name) {
    window.open(`/api/publications/${pubId.value}/results/files/${encodeURIComponent(doc.name)}`, '_blank')
  }
}

async function saveResults(silent = false) {
  if (!pubId.value) await loadResults()
  saving.value = true
  try {
    recalculatePlaces()
    const res = await apiFetch<any>(`/publications/${pubId.value}/results`, {
      method: 'PUT',
      body: JSON.stringify(results.value),
    })
    if (res.results) {
      results.value = res.results
    }
    if (!silent) {
      toast.addToast('Рассмотрение заявок сохранено', 'success')
    }
    return true
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка сохранения результатов', 'error')
    return false
  } finally {
    saving.value = false
  }
}

async function applyWinner() {
  if (!pubId.value) return
  applyingWinner.value = true
  try {
    await saveResults(true)
    const res = await apiFetch<any>(`/publications/${pubId.value}/results/apply-winner`, {
      method: 'POST',
      body: JSON.stringify({
        apply_positions_prices: true,
        apply_accepted_alternatives: applyAcceptedAlternatives.value,
      }),
    })
    const vatModeLabel = res.vat_mode === 'per_item' ? 'попозиционный' : 'единый'
    const ciCount = res.created_contract_items_count || res.updated_positions_count || 0
    toast.addToast(
      `В договор вставлены товары победителя ${res.contractor_name}! Позиций договора: ${ciCount}, режим НДС: ${vatModeLabel}`,
      'success'
    )
    emit('winner-applied', {
      contractor_id: res.contractor_id,
      contractor_name: res.contractor_name,
      contract_price: res.contract_price,
    })
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка переноса победителя в закупку', 'error')
  } finally {
    applyingWinner.value = false
  }
}

async function downloadDocx() {
  if (!pubId.value) return
  downloading.value = true
  try {
    await saveResults(true)
    const blob = await apiFetch<Blob>(`/publications/${pubId.value}/results/protocol.docx`, {
      responseType: 'blob',
    })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Протокол_${results.value.registration_number || props.purchaseId}.docx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
    toast.addToast('Протокол успешно сформирован и скачан', 'success')
  } catch (e: any) {
    toast.addToast(e?.detail || 'Ошибка формирования протокола', 'error')
  } finally {
    downloading.value = false
  }
}

defineExpose({
  openDialog,
})
</script>

<style scoped>
.results-dialog-card {
  display: flex;
  flex-direction: column;
}
.border-success-light {
  border-color: #4caf50 !important;
  border-width: 1.5px !important;
}
.border-error-light {
  border-color: #ef5350 !important;
  border-width: 1.5px !important;
}
.border-error-subtle {
  border: 1px dashed #ef9a9a;
}
</style>
