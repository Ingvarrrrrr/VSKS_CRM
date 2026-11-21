<template>
  <v-dialog v-model="open" max-width="850" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-file-document-edit-outline" color="indigo" class="mr-2" />
        Формирование дополнительного соглашения (ДС)
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>
      <v-divider />
      <v-card-text style="max-height: 75vh" class="pt-3">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Дополнительное соглашение к Договору № <strong>{{ contract?.number || '—' }}</strong>.
          Преамбула автоматически склоняет должности и ФИО подписантов Заказчика и Подрядчика.
        </v-alert>

        <!-- Реквизиты ДС -->
        <v-row dense class="mb-2">
          <v-col cols="12" sm="6">
            <v-text-field
              v-model="amendmentNumber"
              label="Номер доп. соглашения (ДС №...)"
              placeholder="1"
              density="compact"
              variant="outlined"
              prepend-inner-icon="mdi-numeric"
              hide-details
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              v-model="amendmentDate"
              label="Дата доп. соглашения"
              type="date"
              density="compact"
              variant="outlined"
              prepend-inner-icon="mdi-calendar"
              hide-details
            />
          </v-col>
        </v-row>

        <!-- Раздел 1: Изменение цены -->
        <v-card variant="outlined" class="mb-3 pa-3">
          <div class="d-flex align-center mb-2">
            <v-checkbox
              v-model="enablePriceChange"
              label="1. Изменение цены договора"
              color="primary"
              density="compact"
              hide-details
              class="font-weight-medium"
            />
          </div>
          <v-expand-transition>
            <div v-if="enablePriceChange">
              <v-row dense class="pt-2">
                <v-col cols="12" sm="5">
                  <v-text-field
                    v-model.number="newPrice"
                    label="Новая цена договора (руб.)"
                    type="number"
                    step="0.01"
                    density="compact"
                    variant="outlined"
                    prepend-inner-icon="mdi-currency-rub"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" sm="4">
                  <v-select
                    v-model="vatMode"
                    :items="[
                      { title: 'В т.ч. НДС 20%', value: '20' },
                      { title: 'В т.ч. НДС 10%', value: '10' },
                      { title: 'НДС не облагается', value: 'none' }
                    ]"
                    label="НДС"
                    density="compact"
                    variant="outlined"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" sm="3">
                  <v-text-field
                    v-model="priceClauseRef"
                    label="Пункт договора"
                    placeholder="3.1"
                    density="compact"
                    variant="outlined"
                    hide-details
                  />
                </v-col>
              </v-row>
            </div>
          </v-expand-transition>
        </v-card>

        <!-- Раздел 2: Изменение срока -->
        <v-card variant="outlined" class="mb-3 pa-3">
          <div class="d-flex align-center mb-2">
            <v-checkbox
              v-model="enableTermChange"
              label="2. Изменение срока действия / поставки"
              color="primary"
              density="compact"
              hide-details
              class="font-weight-medium"
            />
          </div>
          <v-expand-transition>
            <div v-if="enableTermChange">
              <v-row dense class="pt-2">
                <v-col cols="12" sm="8">
                  <v-text-field
                    v-model="newTermDate"
                    label="Новый срок окончания / поставки"
                    type="date"
                    density="compact"
                    variant="outlined"
                    prepend-inner-icon="mdi-calendar-clock"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" sm="4">
                  <v-text-field
                    v-model="termClauseRef"
                    label="Пункт договора"
                    placeholder="4.1"
                    density="compact"
                    variant="outlined"
                    hide-details
                  />
                </v-col>
              </v-row>
            </div>
          </v-expand-transition>
        </v-card>

        <!-- Раздел 3: Спецификация позиций -->
        <v-card variant="outlined" class="mb-3 pa-3">
          <div class="d-flex align-center justify-space-between mb-2">
            <v-checkbox
              v-model="enableSpecChange"
              label="3. Новая редакция Спецификации (Приложение № 1)"
              color="primary"
              density="compact"
              hide-details
              class="font-weight-medium"
            />
            <v-btn
              v-if="enableSpecChange"
              size="small"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-plus"
              @click="addItem"
            >
              Добавить позицию
            </v-btn>
          </div>
          <v-expand-transition>
            <div v-if="enableSpecChange">
              <v-table density="compact" class="mb-2">
                <thead>
                  <tr>
                    <th>Наименование</th>
                    <th style="width: 100px">Ед. изм.</th>
                    <th style="width: 100px">Кол-во</th>
                    <th style="width: 130px">Цена, руб.</th>
                    <th style="width: 130px">Сумма, руб.</th>
                    <th style="width: 50px"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(it, idx) in items" :key="idx">
                    <td>
                      <v-text-field v-model="it.name" density="compact" variant="plain" hide-details />
                    </td>
                    <td>
                      <v-text-field v-model="it.unit" density="compact" variant="plain" hide-details />
                    </td>
                    <td>
                      <v-text-field v-model.number="it.quantity" type="number" density="compact" variant="plain" hide-details />
                    </td>
                    <td>
                      <v-text-field v-model.number="it.unit_price" type="number" step="0.01" density="compact" variant="plain" hide-details />
                    </td>
                    <td class="text-right font-weight-medium">
                      {{ formatMoney((it.quantity || 0) * (it.unit_price || 0)) }}
                    </td>
                    <td>
                      <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error" @click="removeItem(idx)" />
                    </td>
                  </tr>
                </tbody>
              </v-table>
              <div class="text-right text-subtitle-2 font-weight-bold">
                Итого по спецификации: {{ formatMoney(itemsTotal) }}
              </div>
            </div>
          </v-expand-transition>
        </v-card>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-download"
          :loading="downloading"
          @click="generateAndDownload"
        >
          Скачать .docx
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { useToast } from '@/composables/useToast'
import { formatMoney } from '@/utils/formatMoney'

interface SpecItem {
  name: string
  unit: string
  quantity: number
  unit_price: number
}

const props = defineProps<{
  contract: any
}>()

const open = defineModel<boolean>({ default: false })
const { mobile } = useDisplay()
const toast = useToast()

const downloading = ref(false)
const amendmentNumber = ref('1')
const amendmentDate = ref(new Date().toISOString().slice(0, 10))

const enablePriceChange = ref(false)
const newPrice = ref<number>(0)
const vatMode = ref('20')
const priceClauseRef = ref('3.1')

const enableTermChange = ref(false)
const newTermDate = ref('')
const termClauseRef = ref('4.1')

const enableSpecChange = ref(false)
const items = ref<SpecItem[]>([])

const itemsTotal = computed(() => {
  return items.value.reduce((acc, it) => acc + (it.quantity || 0) * (it.unit_price || 0), 0)
})

watch(() => props.contract, (c) => {
  if (c) {
    if (c.max_amount) newPrice.value = Number(c.max_amount)
    if (c.end_date) newTermDate.value = String(c.end_date)
  }
}, { immediate: true })

function addItem() {
  items.value.push({
    name: '',
    unit: 'шт.',
    quantity: 1,
    unit_price: 0,
  })
}

function removeItem(idx: number) {
  items.value.splice(idx, 1)
}

async function generateAndDownload() {
  if (!props.contract?.id) {
    toast.addToast('Договор не выбран', 'error')
    return
  }

  downloading.value = true
  try {
    const payload: Record<string, any> = {
      amendment_number: amendmentNumber.value || '1',
      amendment_date: amendmentDate.value,
    }

    if (enablePriceChange.value) {
      payload.price_change = {
        new_price: Number(newPrice.value) || 0,
        clause_ref: priceClauseRef.value || '3.1',
        vat_applicable: vatMode.value !== 'none',
        vat_rate: vatMode.value === 'none' ? 0 : Number(vatMode.value),
      }
    }

    if (enableTermChange.value && newTermDate.value) {
      payload.term_change = {
        new_date: newTermDate.value,
        clause_ref: termClauseRef.value || '4.1',
      }
    }

    if (enableSpecChange.value && items.value.length > 0) {
      payload.specification_items = items.value.map(it => ({
        name: it.name || 'Товар',
        unit: it.unit || 'шт.',
        quantity: Number(it.quantity) || 1,
        unit_price: Number(it.unit_price) || 0,
        total: (Number(it.quantity) || 1) * (Number(it.unit_price) || 0),
      }))
    }

    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/contracts/${props.contract.id}/amendments/generate-docx`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Ошибка сервера: ${res.status}`)
    }

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Доп_соглашение_${amendmentNumber.value}_к_договору_${props.contract.number || props.contract.id}.docx`
    a.click()
    URL.revokeObjectURL(url)

    toast.addToast(`Доп. соглашение №${amendmentNumber.value} успешно сформировано и скачано`, 'success')
    open.value = false
  } catch (e: any) {
    console.error('generateAndDownload failed:', e)
    toast.addToast(e.message || 'Ошибка генерации документа', 'error')
  } finally {
    downloading.value = false
  }
}
</script>
