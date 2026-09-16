<!--
  Блок «Чеки» — состояние и вся логика (QR/JSON-импорт, удаление, пересчёт)
  вынесены в composables/purchase/usePurchaseReceipts.ts, ручной ввод — в уже
  существующий composables/purchase/useManualReceipt.ts (не дублируется).

  Раньше этот блок был вставлен ТРЕМЯ копиями прямо в CreateOrderView.vue:
  «Чеки вверху» (только avdance_report, variant="top"), «1.7. Чеки»
  (variant="block") и внутри вкладки «Чек» секции «Договор/Счёт» (variant="tab",
  только .json-загрузка, без QR/пересчёта — своя, более узкая кнопочная панель).
  Один компонент, три варианта разметки через проп variant — без изменения
  поведения каждого места использования (ПРАВИЛО №6: один источник состояния).
-->
<template>
  <!-- ── variant="top": авансовый отчёт, крупный блок вверху формы ── -->
  <v-card
    v-if="variant === 'top'"
    variant="outlined"
    class="mb-4"
    style="border: 2px solid var(--gala-accent, #fb923c); background: rgba(251,146,60,0.04);"
  >
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex flex-wrap align-center ga-2">
      <v-icon color="#fb923c" size="24" class="mr-2">mdi-receipt-text</v-icon>
      <span class="d-flex align-center" style="color: #fb923c;">
        <span>Загрузите чеки&nbsp;</span>
        <v-chip size="x-small" color="#fb923c" variant="tonal" class="ml-1">{{ receipts.length }}</v-chip>
      </span>
      <v-spacer />
      <v-btn size="small" variant="flat" color="#fb923c" @click="onScanQrClick?.()">
        <v-icon start>mdi-qrcode-scan</v-icon>Сканировать QR
      </v-btn>
      <v-btn size="small" variant="tonal" color="#fb923c" @click="onJsonBtnClick?.()">
        <v-icon start>mdi-file-upload</v-icon>Загрузить чек
      </v-btn>
      <v-btn size="small" variant="tonal" @click="onManualClick">
        <v-icon start>mdi-plus</v-icon>Вручную
      </v-btn>
      <v-btn
        v-if="isEdit && purchaseId"
        size="small"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-refresh"
        :loading="recomputeLoading"
        @click="onRecompute?.()"
      >
        Пересчитать из чеков
      </v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert type="warning" variant="tonal" density="compact" class="mb-3 text-caption" color="#fb923c">
        Сначала загрузите все чеки — сканируйте QR или перетащите фото/PDF/HTML/JSON. После загрузки позиции и суммы подтянутся автоматически.
      </v-alert>

      <FileDropZone
        :accept="RECEIPT_FILE_ACCEPT"
        multiple
        :hint="RECEIPT_FILE_HINT"
        class="mb-3"
        @files="onJsonReceiptUpload"
      />

      <!-- Empty-state: нет чеков — крупный призыв -->
      <div v-if="receipts.length === 0" class="text-center py-6">
        <v-icon size="48" style="color: #ccc; margin-bottom: 8px;" class="d-block mx-auto">mdi-receipt-text-plus</v-icon>
        <div class="text-subtitle-2 text-medium-emphasis mb-1">Пока нет чеков</div>
        <div class="text-caption text-medium-emphasis mb-4">Перетащите файл выше или нажмите «Сканировать QR» / «Загрузить чек»</div>
        <div class="d-flex justify-center ga-2 flex-wrap">
          <v-btn variant="flat" color="#fb923c" @click="onScanQrClick?.()">
            <v-icon start>mdi-qrcode-scan</v-icon>Сканировать QR
          </v-btn>
          <v-btn variant="tonal" color="#fb923c" @click="onJsonBtnClick?.()">
            <v-icon start>mdi-file-upload</v-icon>Загрузить чек
          </v-btn>
        </div>
      </div>

      <!-- Список загруженных чеков -->
      <v-table v-else density="compact">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Продавец</th>
            <th>ИНН</th>
            <th class="text-right">Сумма ₽</th>
            <th>Источник</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in receipts" :key="r.id">
            <td>{{ r.receipt_datetime ? new Date(r.receipt_datetime).toLocaleString('ru-RU') : '—' }}</td>
            <td>{{ r.seller_name || '—' }}</td>
            <td>{{ r.seller_inn || '—' }}</td>
            <td class="text-right">{{ r.total_sum != null ? Number(r.total_sum).toLocaleString('ru-RU') : '—' }}</td>
            <td><v-chip size="x-small">{{ sourceLabel(r.source) }}</v-chip></td>
            <td>
              <v-btn size="x-small" variant="text" color="primary"
                icon="mdi-file-pdf-box"
                :href="`/api/purchases/${purchaseId}/receipts/${r.id}/pdf`"
                target="_blank" rel="noopener" />
              <v-btn size="x-small" variant="text" color="primary"
                icon="mdi-file-image"
                :href="`/api/purchases/${purchaseId}/receipts/${r.id}/png`"
                target="_blank" rel="noopener" />
              <v-btn size="x-small" variant="text" color="error"
                icon="mdi-delete" @click="onDeleteReceipt(r.id)" />
            </td>
          </tr>
        </tbody>
      </v-table>

      <!-- Файлы чеков без автораспознавания (PDF/TIF/HEIC/нераспознанный HTML) —
           чтобы владелец видел, что файл не пропал (жалоба 2026-09-15). -->
      <template v-if="receiptFiles && receiptFiles.length">
        <div class="text-caption text-medium-emphasis mt-4 mb-1">
          Прикреплённые файлы чеков (без автораспознавания):
        </div>
        <v-list density="compact" class="pa-0" style="background: transparent;">
          <v-list-item
            v-for="rf in receiptFiles" :key="rf.id"
            :href="`/api/purchases/${purchaseId}/files/${rf.id}/download`"
            target="_blank" rel="noopener"
            prepend-icon="mdi-paperclip"
            density="compact"
          >
            <v-list-item-title class="text-body-2">{{ rf.original_name || rf.filename }}</v-list-item-title>
            <template #append>
              <v-btn size="x-small" variant="text" color="error" icon="mdi-delete"
                @click.prevent.stop="onDeleteReceiptFile?.(rf.id)" />
            </template>
          </v-list-item>
        </v-list>
      </template>
    </v-card-text>
  </v-card>

  <!-- ── variant="block": «1.7. Чеки» — для авансовых и обычных закупок ── -->
  <v-card v-else-if="variant === 'block'" variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex flex-wrap align-center ga-2">
      <span class="d-flex align-center">
        <v-icon start>mdi-receipt-text-outline</v-icon>
        <span>Чеки ({{ receipts.length }})</span>
      </span>
      <v-spacer />
      <v-btn size="small" variant="tonal" color="primary" @click="onScanQrClick?.()">
        <v-icon start>mdi-qrcode-scan</v-icon>Сканировать QR
      </v-btn>
      <v-btn size="small" variant="tonal" @click="onJsonBtnClick?.()">
        <v-icon start>mdi-file-upload</v-icon>Загрузить чек
      </v-btn>
      <v-btn size="small" variant="tonal" @click="onManualClick">
        <v-icon start>mdi-plus</v-icon>Вручную
      </v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert v-if="!isEdit || !purchaseId" type="info" variant="tonal" density="compact" class="mb-0 text-caption">
        При сканировании QR или загрузке фото/PDF/HTML/JSON чека запись сохранится автоматически, позиции из чеков подтянутся в «Позиции закупки».
      </v-alert>
      <template v-else>
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Сканируйте QR с чека или перетащите его фото / PDF / HTML (proverkacheka) / JSON — данные подтянутся из ФНС, позиции попадут в «Позиции закупки» ниже. Для каждой позиции укажите товар из каталога (или создайте новый).
        </v-alert>
        <FileDropZone
          :accept="RECEIPT_FILE_ACCEPT"
          multiple
          :hint="RECEIPT_FILE_HINT"
          class="mb-3"
          @files="onJsonReceiptUpload"
        />
        <div v-if="receipts.length === 0" class="text-center text-medium-emphasis py-4 text-caption">
          Чеков нет — перетащите файл выше, отсканируйте QR или загрузите его вручную
        </div>
        <v-table v-else density="compact">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Продавец</th>
              <th>ИНН</th>
              <th class="text-right">Сумма ₽</th>
              <th>Источник</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in receipts" :key="r.id">
              <td>{{ r.receipt_datetime ? new Date(r.receipt_datetime).toLocaleString('ru-RU') : '—' }}</td>
              <td>{{ r.seller_name || '—' }}</td>
              <td>{{ r.seller_inn || '—' }}</td>
              <td class="text-right">{{ r.total_sum != null ? Number(r.total_sum).toLocaleString('ru-RU') : '—' }}</td>
              <td><v-chip size="x-small">{{ sourceLabel(r.source) }}</v-chip></td>
              <td>
                <v-btn size="x-small" variant="text" color="primary"
                  icon="mdi-file-pdf-box"
                  :href="`/api/purchases/${purchaseId}/receipts/${r.id}/pdf`"
                  target="_blank" rel="noopener" />
                <v-btn size="x-small" variant="text" color="primary"
                  icon="mdi-file-image"
                  :href="`/api/purchases/${purchaseId}/receipts/${r.id}/png`"
                  target="_blank" rel="noopener" />
                <v-btn size="x-small" variant="text" color="error"
                  icon="mdi-delete" @click="onDeleteReceipt(r.id)" />
              </td>
            </tr>
          </tbody>
        </v-table>

        <!-- Файлы чеков без автораспознавания — см. комментарий в variant="top". -->
        <template v-if="receiptFiles && receiptFiles.length">
          <div class="text-caption text-medium-emphasis mt-4 mb-1">
            Прикреплённые файлы чеков (без автораспознавания):
          </div>
          <v-list density="compact" class="pa-0" style="background: transparent;">
            <v-list-item
              v-for="rf in receiptFiles" :key="rf.id"
              :href="`/api/purchases/${purchaseId}/files/${rf.id}/download`"
              target="_blank" rel="noopener"
              prepend-icon="mdi-paperclip"
              density="compact"
            >
              <v-list-item-title class="text-body-2">{{ rf.original_name || rf.filename }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </template>
      </template>
    </v-card-text>
  </v-card>

  <!-- ── variant="tab": вкладка «Чек» секции «Договор/Счёт» — только когда закупка уже сохранена ── -->
  <v-card v-else variant="outlined" class="mb-3">
    <v-card-title class="d-flex align-center pa-3 text-subtitle-2">
      <v-icon start>mdi-receipt-text-outline</v-icon>
      <span>Чеки ({{ receipts.length }})</span>
      <v-spacer />
      <v-btn size="small" variant="tonal" @click="tabDropZone?.openPicker()">
        <v-icon start>mdi-file-upload</v-icon>Загрузить чек
      </v-btn>
      <v-btn size="small" variant="tonal" class="ml-2" @click="onManualClick">
        <v-icon start>mdi-plus</v-icon>Вручную
      </v-btn>
    </v-card-title>
    <v-card-text class="pb-0">
      <FileDropZone
        ref="tabDropZone"
        :accept="RECEIPT_FILE_ACCEPT"
        multiple
        :hint="RECEIPT_FILE_HINT"
        class="mb-3"
        @files="onJsonReceiptUpload"
      />
    </v-card-text>
    <v-card-text v-if="receipts.length === 0" class="text-center text-medium-emphasis py-4">
      Чеков нет — перетащите файл выше (PDF/HTML/фото/JSON) или введите данные вручную
    </v-card-text>
    <v-table v-else density="compact">
      <thead>
        <tr>
          <th>Дата</th>
          <th>Продавец</th>
          <th>ИНН</th>
          <th class="text-right">Сумма ₽</th>
          <th>Источник</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in receipts" :key="r.id">
          <td>{{ r.receipt_datetime ? new Date(r.receipt_datetime).toLocaleString('ru-RU') : '—' }}</td>
          <td>{{ r.seller_name || '—' }}</td>
          <td>{{ r.seller_inn || '—' }}</td>
          <td class="text-right">{{ r.total_sum != null ? Number(r.total_sum).toLocaleString('ru-RU') : '—' }}</td>
          <td><v-chip size="x-small">{{ sourceLabel(r.source) }}</v-chip></td>
          <td>
            <v-btn size="x-small" variant="text" color="primary"
              icon="mdi-file-pdf-box"
              :href="`/api/purchases/${purchaseId}/receipts/${r.id}/pdf`"
              target="_blank" rel="noopener" />
            <v-btn size="x-small" variant="text" color="primary"
              icon="mdi-file-image"
              :href="`/api/purchases/${purchaseId}/receipts/${r.id}/png`"
              target="_blank" rel="noopener" />
            <v-btn size="x-small" variant="text" color="error"
              icon="mdi-delete" @click="onDeleteReceipt(r.id)" />
          </td>
        </tr>
      </tbody>
    </v-table>

    <!-- Файлы чеков без автораспознавания — см. комментарий в variant="top". -->
    <v-card-text v-if="receiptFiles && receiptFiles.length" class="pt-0">
      <div class="text-caption text-medium-emphasis mb-1">
        Прикреплённые файлы чеков (без автораспознавания):
      </div>
      <v-list density="compact" class="pa-0" style="background: transparent;">
        <v-list-item
          v-for="rf in receiptFiles" :key="rf.id"
          :href="`/api/purchases/${purchaseId}/files/${rf.id}/download`"
          target="_blank" rel="noopener"
          prepend-icon="mdi-paperclip"
          density="compact"
        >
          <v-list-item-title class="text-body-2">{{ rf.original_name || rf.filename }}</v-list-item-title>
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Receipt, ReceiptFile } from '@/composables/purchase/usePurchaseReceipts'
import { RECEIPT_FILE_ACCEPT, RECEIPT_FILE_HINT } from '@/composables/purchase/usePurchaseReceipts'
import FileDropZone from '@/components/FileDropZone.vue'

defineProps<{
  variant: 'top' | 'block' | 'tab'
  receipts: Receipt[]
  receiptFiles?: ReceiptFile[]
  purchaseId: number | null
  isEdit: boolean
  sourceLabel: (s?: string | null) => string
  recomputeLoading?: boolean
  onScanQrClick?: () => void
  onJsonBtnClick?: () => void
  onManualClick: () => void
  onRecompute?: () => void
  onJsonReceiptUpload: (files: File[]) => void
  onDeleteReceipt: (id: number) => void
  onDeleteReceiptFile?: (id: number) => void
}>()

// variant="tab" открывает свою drop-zone напрямую (было $refs.jsonReceiptInput.click()
// в CreateOrderView.vue) — тот же эффект, локальный ref вместо родительского $refs.
const tabDropZone = ref<InstanceType<typeof FileDropZone> | null>(null)
</script>
