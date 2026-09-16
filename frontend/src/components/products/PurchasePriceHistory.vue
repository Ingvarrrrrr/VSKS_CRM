<template>
  <div>
    <div class="text-subtitle-2 mb-2">Цены</div>

    <div v-if="!productId" class="text-caption text-medium-emphasis">
      Сохраните товар, чтобы вести историю цен.
    </div>

    <template v-else>
      <!-- Средняя цена (решение владельца 2026-09-16, п.3) -->
      <div class="pph-avg-block mb-3">
        <template v-if="stats && stats.avg_price != null">
          <div class="pph-avg-value">{{ formatMoney(stats.avg_price) }}</div>
          <div v-if="!stats.stale" class="text-caption text-medium-emphasis">
            на основании {{ avgPriceBasisText(stats.basis_count) }} за {{ stats.window_days }} дней
          </div>
          <v-alert v-else type="warning" density="compact" variant="tonal" class="mt-1">
            на основании {{ avgPriceBasisText(stats.basis_count) }}, все старше {{ stats.window_days }} дней
          </v-alert>
        </template>
        <div v-else class="text-body-2 text-medium-emphasis">Цен нет</div>
      </div>

      <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />

      <div v-if="rows.length" class="pph-table-wrap mb-3">
        <v-table density="compact">
          <thead>
            <tr>
              <th>Дата</th><th>Цена</th><th>Источник</th><th>Контрагент</th><th>Ссылка / №</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.key">
              <td>{{ r.collected_at || '—' }}</td>
              <td class="font-weight-medium">{{ r.price != null ? formatMoney(r.price) : '—' }}</td>
              <td>{{ r.sourceLabel }}</td>
              <td>{{ r.contractor_name || '—' }}</td>
              <td>
                <a v-if="r.linkUrl" :href="r.linkUrl" target="_blank" rel="noopener noreferrer">ссылка</a>
                <span v-else-if="r.source_ref">{{ r.source_ref }}</span>
                <span v-else>—</span>
              </td>
              <td>
                <v-btn
                  v-if="r.canDelete"
                  icon="mdi-delete-outline" variant="text" size="x-small" color="error"
                  :loading="deletingId === r.id"
                  @click="removeEntry(r.id as number)"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
      <div v-else-if="!loading" class="text-caption text-medium-emphasis mb-3">Записей нет.</div>

      <!-- Добавить цену -->
      <div class="pph-add-form">
        <div class="text-caption font-weight-medium mb-2">Добавить цену</div>
        <v-row dense>
          <v-col cols="6" md="3">
            <v-text-field v-model.number="form.price" label="Цена, ₽" type="number" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6" md="3">
            <v-text-field v-model="form.collected_at" label="Дата" type="date" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-select
              v-model="form.source"
              :items="SOURCE_OPTIONS"
              label="Источник" variant="outlined" density="compact" hide-details
            />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="form.source_ref" label="Ссылка / №" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <ContractorPicker v-model="form.contractor_id" label="Контрагент" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="form.note" label="Заметка" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-btn class="mt-3" color="primary" variant="tonal" prepend-icon="mdi-plus" :loading="saving" @click="addEntry">
          Добавить цену
        </v-btn>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// PurchasePriceHistory.vue — блок «Цены» в карточке товара (решение владельца
// 2026-09-16, п.2/п.3): вместо редактируемых price_links — таблица истории +
// форма добавления + средняя цена. Старые price_links (если у товара есть)
// показываются в этой же таблице read-only строками «мониторинг (старая
// ссылка)» — новых через них не создаём (см. legacyPriceLinks ниже).
import { computed, watch } from 'vue'
import ContractorPicker from '@/components/ContractorPicker.vue'
import { useProductPriceHistory } from '@/composables/products/useProductPriceHistory'
import { avgPriceBasisText, priceSourceLabel } from '@/composables/products/productsTypes'
import type { PriceLink } from '@/composables/products/productsTypes'
import { useToast, type ToastType } from '@/composables/useToast'

const props = defineProps<{
  productId: number | null
  legacyPriceLinks: PriceLink[]
}>()

const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const { entries, stats, loading, saving, deletingId, form, load, addEntry, removeEntry } =
  useProductPriceHistory({ showSnack })

watch(() => props.productId, (id) => { load(id) }, { immediate: true })

const SOURCE_OPTIONS = [
  { title: 'Вручную', value: 'manual' },
  { title: 'КП', value: 'kp' },
  { title: 'Ссылка-мониторинг', value: 'monitoring' },
]

function formatMoney(v: number): string {
  return Number(v).toLocaleString('ru-RU') + ' ₽'
}

// «Кнопка удалить у своих» (решение владельца, п.2) — сравнение с текущим
// пользователем по имени, тот же ключ localStorage, что App.vue/AppBar.vue
// используют для отображения имени в шапке (Правило №6 — не заводим второй
// способ узнать «это я»).
const currentUserName = localStorage.getItem('user_name') || ''

interface DisplayRow {
  id: number | string
  key: string
  collected_at: string | null
  price: number | null
  sourceLabel: string
  contractor_name: string | null
  source_ref: string | null
  linkUrl: string | null
  canDelete: boolean
}

function isUrl(v: string | null | undefined): boolean {
  return !!v && /^https?:\/\//i.test(v.trim())
}

const rows = computed<DisplayRow[]>(() => {
  const real: DisplayRow[] = entries.value.map(e => ({
    id: e.id,
    key: `h-${e.id}`,
    collected_at: e.collected_at || null,
    price: e.price,
    sourceLabel: priceSourceLabel(e.source, e.source_ref),
    contractor_name: e.contractor_name || null,
    source_ref: isUrl(e.source_ref) ? null : (e.source_ref || null),
    linkUrl: isUrl(e.source_ref) ? e.source_ref! : null,
    canDelete: !!e.created_by && e.created_by === currentUserName,
  }))
  const legacy: DisplayRow[] = (props.legacyPriceLinks || [])
    .filter(l => l.url?.trim())
    .map((l, i) => ({
      id: `legacy-${i}`,
      key: `legacy-${i}`,
      collected_at: null,
      price: l.price ?? null,
      sourceLabel: 'Мониторинг (старая ссылка)',
      contractor_name: null,
      source_ref: null,
      linkUrl: l.url,
      canDelete: false,
    }))
  // Свежие сверху — legacy без даты в конце.
  return [
    ...real.slice().sort((a, b) => (b.collected_at || '').localeCompare(a.collected_at || '')),
    ...legacy,
  ]
})
</script>

<style scoped>
.pph-avg-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}
.pph-table-wrap {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
}
.pph-add-form {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 12px;
}
</style>
