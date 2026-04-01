<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="text-h5 font-weight-bold">Реестр договоров</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ filtered.length }} из {{ contracts.length }} записей
        </span>
      </div>
      <div class="d-flex gap-2">
        <v-btn v-if="isAdmin" variant="outlined" prepend-icon="mdi-database-import" @click="migrateDialog = true">
          Мигрировать из закупок
        </v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-content-duplicate" color="warning" @click="checkDuplicates" :loading="dupLoading">
          Проверить дубли
        </v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-excel-outline" color="success" @click="exportDialog = true">
          Скачать реестр
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Добавить</v-btn>
      </div>
    </div>

    <!-- ── Filters ── -->
    <v-card class="mb-4" variant="outlined" rounded="lg">
      <v-card-text class="py-2 px-3">
        <div class="d-flex align-center gap-1 mb-2">
          <v-icon size="16" color="grey">mdi-filter</v-icon>
          <span class="text-caption font-weight-medium text-medium-emphasis">ФИЛЬТРЫ (мульти-выбор)</span>
          <v-spacer />
          <v-btn v-if="hasFilters" variant="text" size="x-small" color="error" prepend-icon="mdi-filter-remove" @click="clearFilters">
            Сбросить все
          </v-btn>
        </div>
        <div class="d-flex flex-wrap gap-2">

          <!-- Субсидия -->
          <v-autocomplete
            v-model="fSubsidy"
            :items="usedSubsidies"
            item-title="name" item-value="id"
            label="Субсидия" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:280px"
          />

          <!-- Тип документа -->
          <v-autocomplete
            v-model="fType"
            :items="usedContractTypes"
            item-title="label" item-value="value"
            label="Тип документа" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:300px"
          />

          <!-- Способ закупки -->
          <v-autocomplete
            v-model="fMethod"
            :items="usedPurchaseMethods"
            item-title="label" item-value="value"
            label="Способ закупки" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:180px; max-width:240px"
          />

          <!-- Контрагент -->
          <v-autocomplete
            v-model="fContractor"
            :items="usedContractors"
            item-title="name" item-value="id"
            label="Контрагент" multiple chips closable-chips
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:300px"
          />

          <!-- Поиск по товару -->
          <v-text-field
            v-model="fProduct"
            label="Поиск товара"
            prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:200px; max-width:280px"
            placeholder="Название товара..."
          />

          <!-- Дата от/до -->
          <v-text-field
            v-model="fDateFrom"
            label="Дата от" type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:145px; max-width:145px"
          />
          <v-text-field
            v-model="fDateTo"
            label="Дата до" type="date"
            variant="outlined" density="compact" hide-details clearable
            style="min-width:145px; max-width:145px"
          />

        </div>
      </v-card-text>
    </v-card>

    <!-- ── Table ── -->
    <v-data-table
      :headers="headers"
      :items="filtered"
      :loading="loading"
      density="compact"
      show-expand
      v-model:expanded="expanded"
      item-value="id"
      class="elevation-1"
      items-per-page="50"
      :items-per-page-options="[25,50,100,-1]"
      @click:row="(_e: any, { item }: any) => openEdit(item)"
      style="cursor: pointer"
    >
      <template #item.number="{ item }">
        <span class="font-weight-medium">{{ item.number }}</span>
      </template>
      <template #item.date="{ item }">
        {{ fmtDate(item.date) }}
      </template>
      <template #item.end_date="{ item }">
        <span :style="item.end_date && isExpired(item.end_date) ? 'color:#DC2626' : ''">
          {{ fmtDate(item.end_date) }}
        </span>
      </template>
      <template #item.contract_type="{ item }">
        <v-chip size="x-small" :color="contractTypeColor(item.contract_type)" variant="tonal">
          {{ contractTypeLabel(item.contract_type) }}
        </v-chip>
      </template>
      <template #item.purchase_method="{ item }">
        <span class="text-caption">{{ item.purchase_method ? purchaseMethodLabel(item.purchase_method) : '—' }}</span>
      </template>
      <template #item.contractor_name="{ item }">
        <div>{{ item.contractor_name || '—' }}</div>
        <div v-if="item.contractor_inn" class="text-caption text-medium-emphasis">ИНН {{ item.contractor_inn }}</div>
      </template>
      <template #item.max_amount="{ item }">
        {{ item.max_amount ? formatMoney(item.max_amount) : '—' }}
      </template>
      <template #item.total_ordered="{ item }">
        <span :style="item.max_amount && Number(item.total_ordered) > Number(item.max_amount) ? 'color:var(--color-loss);font-weight:700' : ''">
          {{ item.total_ordered ? formatMoney(item.total_ordered) : '—' }}
        </span>
      </template>
      <template #item.total_paid="{ item }">
        <span style="color:var(--color-profit)">{{ item.total_paid ? formatMoney(item.total_paid) : '—' }}</span>
      </template>
      <template #item.remaining="{ item }">
        <span :style="Number(item.remaining) < 0 ? 'color:var(--color-loss);font-weight:700' : 'color:var(--color-profit)'">
          {{ item.remaining != null ? formatMoney(item.remaining) : '—' }}
        </span>
      </template>
      <template #item.subsidy_name="{ item }">
        <div class="d-flex flex-wrap gap-1">
          <v-chip v-if="item.subsidy_name" size="x-small" color="primary" variant="tonal">{{ item.subsidy_name }}</v-chip>
          <v-chip v-for="es in (item.extra_subsidies || [])" :key="es.subsidy_id" size="x-small" color="secondary" variant="tonal">{{ es.subsidy_name }}</v-chip>
          <span v-if="!item.subsidy_name && !(item.extra_subsidies?.length)" class="text-medium-emphasis">—</span>
        </div>
      </template>
      <template #item.subject="{ item }">
        <span class="text-caption" :title="item.subject">{{ item.subject ? (item.subject.length > 60 ? item.subject.slice(0, 60) + '...' : item.subject) : '—' }}</span>
      </template>
      <template #item.item_type="{ item }">
        <v-chip v-if="item.item_type" size="x-small" :color="item.item_type === 'услуга' ? 'blue' : 'teal'" variant="tonal">
          {{ item.item_type === 'услуга' ? 'Услуги' : 'Товары' }}
        </v-chip>
        <span v-else class="text-medium-emphasis">—</span>
      </template>
      <template #item.index="{ index }">
        <span class="text-medium-emphasis">{{ index + 1 }}</span>
      </template>
      <!-- Expanded: закупки по договору -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0">
            <div class="pa-3 bg-grey-lighten-5">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-2">
                Закупки по документу {{ item.number }}
              </div>
              <div v-if="!purchasesByContract[item.id]" class="text-caption text-medium-emphasis">
                <v-btn size="x-small" variant="text" @click="loadPurchasesForContract(item.id)">Загрузить</v-btn>
              </div>
              <div v-else-if="!purchasesByContract[item.id].length" class="text-caption text-medium-emphasis">Нет закупок</div>
              <v-table v-else density="compact">
                <thead>
                  <tr>
                    <th>№ закупки</th>
                    <th>Наименование</th>
                    <th class="text-right">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="p in purchasesByContract[item.id]" :key="p.id">
                    <tr style="cursor:pointer" @click="router.push(`/orders/${p.id}/edit`)">
                      <td>
                        <v-btn v-if="p.items?.length" :icon="expandedPurchases[p.id] ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                          variant="text" size="x-small" @click.stop="expandedPurchases[p.id] = !expandedPurchases[p.id]" />
                        {{ p.purchase_number || p.id }}
                      </td>
                      <td class="text-caption">{{ p.subject || p.item_name || '—' }}</td>
                      <td class="text-right">{{ p.contract_price ? formatMoney(p.contract_price) : '—' }}</td>
                    </tr>
                    <tr v-if="expandedPurchases[p.id] && p.items?.length">
                      <td colspan="3" class="pa-0 pl-8">
                        <v-table density="compact" class="bg-grey-lighten-4">
                          <thead><tr><th>Наименование</th><th class="text-right">Кол-во</th><th class="text-right">Цена ед.</th><th class="text-right">Сумма</th></tr></thead>
                          <tbody>
                            <tr v-for="(pi, ii) in p.items" :key="ii"
                              :class="fProduct && pi.item_name?.toLowerCase().includes(fProduct.trim().toLowerCase()) ? 'bg-yellow-lighten-4' : ''">
                              <td class="text-caption">{{ pi.item_name }}</td>
                              <td class="text-right text-caption">{{ pi.quantity }}</td>
                              <td class="text-right text-caption">{{ pi.unit_price ? formatMoney(pi.unit_price) : '—' }}</td>
                              <td class="text-right text-caption">{{ pi.total_price ? formatMoney(pi.total_price) : '—' }}</td>
                            </tr>
                            <tr class="font-weight-bold">
                              <td colspan="3" class="text-right text-caption">Итого:</td>
                              <td class="text-right text-caption">{{ formatMoney(p.items.reduce((s, i) => s + (Number(i.total_price) || 0), 0)) }}</td>
                            </tr>
                          </tbody>
                        </v-table>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </v-table>
            </div>
          </td>
        </tr>
      </template>
    </v-data-table>

    <!-- Export Dialog -->
    <v-dialog v-model="exportDialog" max-width="480">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-file-excel-outline" color="success" class="mr-2" />Скачать реестр договоров
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <div class="text-body-2 mb-3">Выберите колонки для экспорта:</div>
          <v-checkbox v-for="col in exportColumns" :key="col.key"
            v-model="col.selected" :label="col.title" density="compact" hide-details />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn variant="text" size="small" @click="exportColumns.forEach(c => c.selected = true)">Выбрать все</v-btn>
          <v-btn variant="text" size="small" @click="exportColumns.forEach(c => c.selected = false)">Снять все</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="exportDialog = false">Отмена</v-btn>
          <v-btn color="success" variant="flat" prepend-icon="mdi-download" :loading="exportLoading" @click="doExport">Скачать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Duplicates Dialog -->
    <v-dialog v-model="dupDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-content-duplicate" color="warning" class="mr-2" />
          Найденные дубли ({{ duplicateGroups.length }} групп)
        </v-card-title>
        <v-card-text v-if="!duplicateGroups.length" class="text-center py-8 text-medium-emphasis">
          Дубликатов не найдено
        </v-card-text>
        <v-card-text v-else class="pa-4 pt-0">
          <div v-for="(group, gi) in duplicateGroups" :key="gi" class="mb-4 pa-3 rounded-lg" style="background:rgba(255,152,0,0.08);border-left:3px solid #ff9800">
            <div class="text-body-2 font-weight-bold mb-2">{{ group[0].number }} — {{ group[0].contractor_name || '?' }}</div>
            <v-table density="compact">
              <thead><tr><th>ID</th><th>Дата</th><th>Сумма</th><th>Закупок</th><th></th></tr></thead>
              <tbody>
                <tr v-for="c in group" :key="c.id">
                  <td>{{ c.id }}</td>
                  <td>{{ c.date || '—' }}</td>
                  <td>{{ c.max_amount ? Number(c.max_amount).toLocaleString('ru-RU') + ' ₽' : '—' }}</td>
                  <td>{{ c._purchaseCount ?? '?' }}</td>
                  <td>
                    <v-btn v-if="group.length > 1" size="x-small" variant="tonal" color="error"
                      @click="mergeContract(c.id, group.find(x => x.id !== c.id)!.id)">
                      Объединить в #{{ group.find(x => x.id !== c.id)?.id }}
                    </v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="dupDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Create/Edit Dialog -->
    <v-dialog v-model="dialog.show" max-width="680">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
          {{ dialog.id ? 'Редактировать документ' : 'Новый документ' }}
        </v-card-title>
        <v-card-text class="px-4 pb-2">
          <v-row dense>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.number" label="Номер *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.date" label="Дата" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.contract_type"
                :items="contractTypeItems" item-title="label" item-value="value"
                label="Тип документа *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="dialog.form.purchase_method"
                :items="purchaseMethodItems" item-title="label" item-value="value"
                label="Способ закупки" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="dialog.form.item_type"
                :items="[{ title: 'Товары', value: 'товар' }, { title: 'Услуги', value: 'услуга' }]"
                label="Товары / Услуги" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="4">
              <v-autocomplete v-model="dialog.form.contractor_id"
                :items="contractors" item-title="name" item-value="id"
                label="Контрагент" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.subsidy_id"
                :items="subsidies" item-title="name" item-value="id"
                label="Основная субсидия" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12">
              <v-autocomplete v-model="dialog.form.extra_subsidy_ids"
                :items="subsidies.filter(s => s.id !== dialog.form.subsidy_id)"
                item-title="name" item-value="id"
                label="Дополнительные субсидии" variant="outlined" density="compact"
                multiple chips closable-chips clearable
                hint="Договор может быть привязан к нескольким субсидиям одной организации"
                persistent-hint />
            </v-col>
            <v-col cols="12">
              <v-text-field v-model="dialog.form.subject" label="Предмет" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="dialog.form.max_amount" label="Предельная сумма, ₽" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model.number="dialog.form.planned_monthly" label="Плановый ежемесячный платёж, ₽" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.start_date" label="Дата начала" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field v-model="dialog.form.end_date" label="Дата окончания" type="date" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="dialog.form.status"
                :items="statusItems" item-title="label" item-value="value"
                label="Статус" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="dialog.form.notes" label="Примечания" variant="outlined" density="compact" rows="2" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-btn v-if="isAdmin && dialog.id" color="error" variant="text" prepend-icon="mdi-delete"
            @click="dialog.show = false; confirmDelete(contracts.find(c => c.id === dialog.id)!)">Удалить</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="tonal" :loading="dialog.saving" @click="saveContract">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog.show" max-width="400">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Удалить запись?</v-card-title>
        <v-card-text class="px-4">
          Удалить <strong>{{ deleteDialog.item?.number }}</strong>? Закупки сохранятся.
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Migrate dialog -->
    <v-dialog v-model="migrateDialog" max-width="480">
      <v-card>
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Мигрировать из закупок</v-card-title>
        <v-card-text class="px-4">
          <p class="text-body-2 mb-3">
            Создаст записи реестра из всех закупок с заполненным номером договора. Уже существующие номера пропускаются.
          </p>
          <v-alert v-if="migrateResult" :type="migrateResult.created > 0 ? 'success' : 'info'" variant="tonal" density="compact">
            Создано: <strong>{{ migrateResult.created }}</strong>,
            пропущено: <strong>{{ migrateResult.skipped }}</strong>
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-3">
          <v-spacer />
          <v-btn variant="text" @click="migrateDialog = false">Закрыть</v-btn>
          <v-btn v-if="!migrateResult" color="primary" variant="tonal" :loading="migrating" @click="doMigrate">
            Запустить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useAppSearch } from '@/composables/useAppSearch'

const router = useRouter()

const { appSearch, appSearchScope } = useAppSearch()

const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ['admin', 'superadmin', 'org_admin'].includes(userRole)

interface ContractSubsidyItem { id: number; subsidy_id: number; subsidy_name?: string }
interface Contract {
  id: number
  number: string
  date?: string
  contract_type: string
  purchase_method?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  subsidy_id?: number
  subsidy_name?: string
  extra_subsidies?: ContractSubsidyItem[]
  subject?: string
  max_amount?: number
  total_ordered?: number
  total_paid?: number
  remaining?: number
  start_date?: string
  end_date?: string
  status?: string
  notes?: string
  planned_monthly?: number
}
interface Subsidy { id: number; name: string; year: number }
interface Contractor { id: number; name: string; inn?: string }
interface PurchaseItem { item_name: string; quantity?: number; unit_price?: number; total_price?: number }
interface Purchase { id: number; purchase_number?: number; subject?: string; item_name?: string; contract_price?: number; status: string; items?: PurchaseItem[] }

const contracts = ref<Contract[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const expanded = ref<number[]>([])

// Export
const exportDialog = ref(false)
const exportColumns = reactive([
  { key: 'number', title: '№ договора', selected: true },
  { key: 'date', title: 'Дата договора', selected: true },
  { key: 'contract_type', title: 'Тип договора', selected: true },
  { key: 'purchase_method', title: 'Способ закупки', selected: true },
  { key: 'contractor_name', title: 'Контрагент', selected: true },
  { key: 'contractor_inn', title: 'ИНН контрагента', selected: true },
  { key: 'subject', title: 'Предмет договора', selected: true },
  { key: 'subsidy_name', title: 'Субсидия', selected: true },
  { key: 'max_amount', title: 'Макс. сумма', selected: true },
  { key: 'total_ordered', title: 'Заказано', selected: true },
  { key: 'total_paid', title: 'Оплачено', selected: true },
  { key: 'remaining', title: 'Остаток', selected: true },
  { key: 'start_date', title: 'Дата начала', selected: true },
  { key: 'end_date', title: 'Дата окончания', selected: true },
  { key: 'notes', title: 'Примечания', selected: false },
  { key: 'documents', title: 'Документы (ссылки)', selected: true },
])

const exportLoading = ref(false)

async function doExport() {
  exportLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const JSZip = (await import('jszip')).default
    const zip = new JSZip()
    const docsFolder = zip.folder('Документы')!
    const selected = exportColumns.filter(c => c.selected)
    const hasDocCol = selected.some(c => c.key === 'documents')

    // Build header row
    const header = selected.map(c => c.title)
    const rows: any[][] = [header]

    // Track files per contract for ZIP + links
    const contractFiles: Map<number, { name: string; path: string }[]> = new Map()

    const token = localStorage.getItem('token')
    const baseUrl = window.location.origin

    // Collect and download all files
    if (hasDocCol) {
      for (const contract of filtered.value) {
        const files: { name: string; path: string }[] = []
        const safeNum = (contract.number || contract.id).toString().replace(/[\\/:*?"<>|]/g, '_')
        const folderName = `${safeNum}_${contract.contractor_name || 'без_контрагента'}`.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
        const contractFolder = docsFolder.folder(folderName)!

        // Files from purchases
        const purchasesForContract = purchasesByContract.value[contract.id] || []
        for (const p of purchasesForContract) {
          try {
            const filesResp = await apiFetch(`/purchases/${p.id}/files`)
            if (Array.isArray(filesResp)) {
              for (const f of filesResp) {
                try {
                  const resp = await fetch(`${baseUrl}/api/purchases/${p.id}/files/${f.id}/download`, {
                    headers: { Authorization: `Bearer ${token}` }
                  })
                  if (resp.ok) {
                    const blob = await resp.blob()
                    const fileName = f.filename || `file_${f.id}`
                    contractFolder.file(fileName, blob)
                    files.push({ name: fileName, path: `Документы/${folderName}/${fileName}` })
                  }
                } catch { /* skip download error */ }
              }
            }
          } catch { /* skip */ }
        }
        contractFiles.set(contract.id, files)
      }
    }

    // Build data rows
    for (const contract of filtered.value) {
      const row: any[] = []
      for (const col of selected) {
        if (col.key === 'documents') {
          const files = contractFiles.get(contract.id) || []
          row.push(files.map(f => f.path).join('\n') || '')
        } else if (col.key === 'contract_type') {
          row.push(contractTypeLabel(contract.contract_type))
        } else if (col.key === 'purchase_method') {
          row.push(purchaseMethodLabel(contract.purchase_method))
        } else if (['max_amount', 'total_ordered', 'total_paid', 'remaining'].includes(col.key)) {
          const v = (contract as any)[col.key]
          row.push(v != null ? Number(v) : '')
        } else if (col.key === 'date' || col.key === 'start_date' || col.key === 'end_date') {
          row.push(fmtDate((contract as any)[col.key]))
        } else {
          row.push((contract as any)[col.key] ?? '')
        }
      }
      rows.push(row)
    }

    const ws = XLSX.utils.aoa_to_sheet(rows)

    // Make document file names clickable (relative links inside ZIP)
    const docColIdx = selected.findIndex(c => c.key === 'documents')
    if (docColIdx >= 0) {
      for (let r = 1; r < rows.length; r++) {
        const cellRef = XLSX.utils.encode_cell({ r, c: docColIdx })
        const cell = ws[cellRef]
        if (cell && cell.v) {
          const paths = String(cell.v).split('\n').filter(Boolean)
          if (paths.length === 1) {
            cell.l = { Target: paths[0], Tooltip: 'Открыть документ' }
          } else if (paths.length > 1) {
            // Show count, first link
            cell.l = { Target: paths[0], Tooltip: `${paths.length} документов` }
          }
          // Show file names instead of paths
          cell.v = paths.map(p => p.split('/').pop()).join(', ')
        }
      }
    }

    // Auto-width columns
    const colWidths = header.map((h: string, i: number) => {
      let max = h.length
      for (let r = 1; r < rows.length; r++) {
        const val = String(rows[r][i] ?? '')
        max = Math.max(max, val.length)
      }
      return { wch: Math.min(max + 2, 50) }
    })
    ws['!cols'] = colWidths

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Реестр договоров')

    // Write Excel into ZIP
    const xlsxData = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
    const dateSuffix = new Date().toISOString().slice(0, 10)
    zip.file(`Реестр_договоров_${dateSuffix}.xlsx`, xlsxData)

    // Generate ZIP and download
    const zipBlob = await zip.generateAsync({ type: 'blob' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(zipBlob)
    a.download = `Реестр_договоров_${dateSuffix}.zip`
    a.click()
    URL.revokeObjectURL(a.href)

    exportDialog.value = false
    showSnack('Реестр скачан')
  } catch (e: any) {
    showSnack(`Ошибка экспорта: ${e.message || e}`, 'error')
  } finally {
    exportLoading.value = false
  }
}

// Duplicates
const dupDialog = ref(false)
const dupLoading = ref(false)
const duplicateGroups = ref<any[][]>([])

async function checkDuplicates() {
  dupLoading.value = true
  try {
    // Group contracts by number+contractor_id+subsidy_id
    const groups = new Map<string, any[]>()
    for (const c of contracts.value) {
      const key = `${c.number}|${c.contractor_id || ''}|${c.subsidy_id || ''}`
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(c)
    }
    // Filter groups with >1 contract
    const dups: any[][] = []
    for (const group of groups.values()) {
      if (group.length > 1) {
        // Count purchases per contract
        for (const c of group) {
          try {
            const p = await apiFetch<any[]>(`/purchases/by-contract/${c.id}`)
            c._purchaseCount = p.length
          } catch { c._purchaseCount = 0 }
        }
        dups.push(group)
      }
    }
    duplicateGroups.value = dups
    dupDialog.value = true
  } finally {
    dupLoading.value = false
  }
}

async function mergeContract(sourceId: number, targetId: number) {
  if (!confirm(`Объединить договор #${sourceId} в #${targetId}? Закупки будут перепривязаны, #${sourceId} удалён.`)) return
  try {
    await apiFetch(`/contracts/${sourceId}/merge/${targetId}`, { method: 'POST' })
    showSnack('Договоры объединены')
    dupDialog.value = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка объединения', 'error')
  }
}
const purchasesByContract = ref<Record<number, Purchase[]>>({})
const expandedPurchases = ref<Record<number, boolean>>({})

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

// ── Filters (all multi-select, client-side) ────────────────────────────────
const fSubsidy    = ref<number[]>([])
const fType       = ref<string[]>([])
const fMethod     = ref<string[]>([])
const fStatus     = ref<string[]>([])
const fContractor = ref<number[]>([])
const fProduct    = ref('')
const fDateFrom   = ref('')
const fDateTo     = ref('')

const hasFilters = computed(() =>
  fSubsidy.value.length > 0 || fType.value.length > 0 || fMethod.value.length > 0 ||
  fStatus.value.length > 0 || fContractor.value.length > 0 || !!fProduct.value || !!fDateFrom.value || !!fDateTo.value
)

const clearFilters = () => {
  fSubsidy.value = []; fType.value = []; fMethod.value = []
  fStatus.value = []; fContractor.value = []; fProduct.value = ''; fDateFrom.value = ''; fDateTo.value = ''
}

// ── Dropdown items: only values present in contracts ──────────────────────
const usedSubsidies = computed(() => {
  const ids = new Set(contracts.value.map(c => c.subsidy_id).filter(Boolean))
  return subsidies.value.filter(s => ids.has(s.id))
})
const usedContractors = computed(() => {
  const ids = new Set(contracts.value.map(c => c.contractor_id).filter(Boolean))
  return contractors.value.filter(c => ids.has(c.id))
})
const usedContractTypes = computed(() => {
  const types = new Set(contracts.value.map(c => c.contract_type))
  return contractTypeItems.filter(i => types.has(i.value))
})
const usedPurchaseMethods = computed(() => {
  const methods = new Set(contracts.value.map(c => c.purchase_method).filter(Boolean))
  return purchaseMethodItems.filter(i => methods.has(i.value))
})

function matchesSearch(c: Contract, q: string): boolean {
  const lq = q.toLowerCase()
  return [c.number, c.contractor_name, c.contractor_inn, c.subsidy_name, c.subject, c.notes]
    .some(v => v?.toLowerCase().includes(lq))
}

// Product search: contracts whose purchases contain matching items
const productMatchContractIds = computed(() => {
  const q = fProduct.value.trim().toLowerCase()
  if (!q) return null
  const ids = new Set<number>()
  for (const [cid, purchases] of Object.entries(purchasesByContract.value)) {
    for (const p of purchases) {
      if (p.items?.some(i => i.item_name?.toLowerCase().includes(q)) ||
          p.subject?.toLowerCase().includes(q) ||
          p.item_name?.toLowerCase().includes(q)) {
        ids.add(Number(cid))
      }
    }
  }
  return ids
})

// Auto-expand contracts and purchases when product search is active
watch(productMatchContractIds, (ids) => {
  if (!ids || ids.size === 0) return
  // Expand matching contracts
  const toExpand = [...ids].filter(id => !expanded.value.includes(id))
  if (toExpand.length) expanded.value = [...expanded.value, ...toExpand]
  // Expand matching purchases to show items
  const q = fProduct.value.trim().toLowerCase()
  if (!q) return
  for (const [cid, purchases] of Object.entries(purchasesByContract.value)) {
    if (!ids.has(Number(cid))) continue
    for (const p of purchases) {
      if (p.items?.some(i => i.item_name?.toLowerCase().includes(q))) {
        expandedPurchases[p.id] = true
      }
    }
  }
})

const filtered = computed(() => {
  const q = appSearch.value.trim()

  // "По всей БД" — global search handled by GlobalSearch dialog, page shows all
  if (q && appSearchScope.value === 'global') return contracts.value

  let list = contracts.value
  if (fSubsidy.value.length)    list = list.filter(c => c.subsidy_id != null && fSubsidy.value.includes(c.subsidy_id))
  if (fType.value.length)       list = list.filter(c => fType.value.includes(c.contract_type))
  if (fMethod.value.length)     list = list.filter(c => c.purchase_method != null && fMethod.value.includes(c.purchase_method))
  if (fStatus.value.length)     list = list.filter(c => c.status != null && fStatus.value.includes(c.status))
  if (fContractor.value.length) list = list.filter(c => c.contractor_id != null && fContractor.value.includes(c.contractor_id))
  if (fDateFrom.value)          list = list.filter(c => !c.date || c.date >= fDateFrom.value)
  if (fDateTo.value)            list = list.filter(c => !c.date || c.date <= fDateTo.value)
  // Product filter
  if (productMatchContractIds.value) list = list.filter(c => productMatchContractIds.value!.has(c.id))
  // "По странице" — filter current list by search query
  if (q && appSearchScope.value === 'page') list = list.filter(c => matchesSearch(c, q))
  return list
})

// ── Type / method / status lookup tables ──────────────────────────────────
const contractTypeItems = [
  { value: 'single',                label: 'Разовая поставка' },
  { value: 'framework_cumulative',  label: 'Рамочный (нарастающий итог)' },
  { value: 'framework_with_amount', label: 'Рамочный (с суммой)' },
  { value: 'invoice',               label: 'Счёт' },
  { value: 'invoice_contract',      label: 'Счёт-договор' },
  { value: 'advance_report',        label: 'Авансовый отчёт' },
]
const purchaseMethodItems = [
  { value: 'single',      label: 'Единственный поставщик' },
  { value: 'competitive', label: 'Конкурсная процедура' },
]
const statusItems = [
  { value: 'active', label: 'Активен' },
  { value: 'closed', label: 'Закрыт' },
]

const contractTypeLabel = (t?: string) => contractTypeItems.find(i => i.value === t)?.label || t || '—'
const purchaseMethodLabel = (m?: string) => purchaseMethodItems.find(i => i.value === m)?.label || m || '—'
const statusLabel = (s?: string) => statusItems.find(i => i.value === s)?.label || s || '—'

const PURCHASE_STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график', confirmed: 'Подтверждено',
  work_in_progress: 'Ведётся работа', contracted: 'Договор',
  delivered: 'Поставлено', paid: 'Оплачено',
}
const PURCHASE_STATUS_COLOR: Record<string, string> = {
  wishes: 'grey', plan_schedule: 'orange', confirmed: 'blue',
  work_in_progress: 'teal', contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const contractTypeColor = (t?: string) => {
  if (t === 'single') return 'blue'
  if (t?.startsWith('framework')) return 'orange'
  if (t === 'invoice' || t === 'invoice_contract') return 'teal'
  if (t === 'advance_report') return 'purple'
  return 'grey'
}

const isExpired = (d: string) => new Date(d) < new Date()
const fmtDate = (d?: string) => d ? new Date(d).toLocaleDateString('ru-RU') : '—'
const formatMoney = (v: number | string) =>
  Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' ₽'

// ── Table headers ──────────────────────────────────────────────────────────
const headers = [
  { title: '', key: 'data-table-expand', width: 40, sortable: false },
  { title: '№', key: 'index', width: 50, sortable: false },
  { title: '№ документа', key: 'number', minWidth: 120 },
  { title: 'Дата', key: 'date', width: 110 },
  { title: 'Тип', key: 'contract_type', width: 170 },
  { title: 'Способ', key: 'purchase_method', width: 130 },
  { title: 'Контрагент', key: 'contractor_name', minWidth: 160 },
  { title: 'Субсидия', key: 'subsidy_name', minWidth: 120 },
  { title: 'Предельная сумма', key: 'max_amount', align: 'end' as const, width: 140 },
  { title: 'Заказано', key: 'total_ordered', align: 'end' as const, width: 120 },
  { title: 'Оплачено', key: 'total_paid', align: 'end' as const, width: 120 },
  { title: 'Остаток', key: 'remaining', align: 'end' as const, width: 120 },
  { title: 'Предмет договора', key: 'subject', minWidth: 160 },
  { title: 'Тип', key: 'item_type', width: 90 },
  { title: 'Срок', key: 'end_date', width: 110 },
]

// ── Load data (all contracts, no server-side filter) ──────────────────────
const loadContracts = async () => {
  loading.value = true
  try {
    contracts.value = await apiFetch<Contract[]>('/contracts/')
  } catch {
    showSnack('Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => { subsidies.value = await apiFetch<Subsidy[]>('/subsidies/') }
const loadContractors = async () => { contractors.value = await apiFetch<Contractor[]>('/contractors/') }

const loadPurchasesForContract = async (contractId: number) => {
  const items = await apiFetch<Purchase[]>(`/purchases/by-contract/${contractId}`)
  purchasesByContract.value = { ...purchasesByContract.value, [contractId]: items }
}

const loadAllPurchases = async () => {
  // Load purchases for all contracts (needed for product search)
  const ids = contracts.value.map(c => c.id)
  const batchSize = 10
  for (let i = 0; i < ids.length; i += batchSize) {
    const batch = ids.slice(i, i + batchSize)
    await Promise.all(batch.filter(id => !purchasesByContract.value[id]).map(id => loadPurchasesForContract(id)))
  }
}

watch(expanded, (newVal) => {
  for (const id of newVal) {
    if (!purchasesByContract.value[id]) loadPurchasesForContract(id)
  }
})

// When product filter starts being typed, load all purchases if not yet loaded
watch(fProduct, (val) => {
  if (val && val.trim().length >= 2) {
    const missingIds = contracts.value.filter(c => !purchasesByContract.value[c.id]).map(c => c.id)
    if (missingIds.length) loadAllPurchases()
  }
})

// ── Dialog ─────────────────────────────────────────────────────────────────
const emptyForm = () => ({
  number: '', date: '', contract_type: 'single', purchase_method: null as string | null, item_type: null as string | null,
  contractor_id: null as number | null, subsidy_id: null as number | null,
  extra_subsidy_ids: [] as number[],
  subject: '', max_amount: null as number | null, planned_monthly: null as number | null,
  start_date: '', end_date: '', status: 'active', notes: '',
})
const dialog = reactive({ show: false, saving: false, id: 0, form: emptyForm() })

const openCreate = () => { dialog.id = 0; Object.assign(dialog.form, emptyForm()); dialog.show = true }

const openEdit = async (c: Contract) => {
  dialog.id = c.id
  // Ensure contractor is loaded before showing
  if (c.contractor_id && !contractors.value.find(x => x.id === c.contractor_id)) {
    try {
      const fetched = await apiFetch<Contractor>(`/contractors/${c.contractor_id}`)
      contractors.value.push(fetched)
    } catch {}
  }
  Object.assign(dialog.form, {
    number: c.number || '', date: c.date || '', contract_type: c.contract_type || 'single',
    purchase_method: c.purchase_method || null, item_type: (c as any).item_type || null, contractor_id: c.contractor_id || null,
    subsidy_id: c.subsidy_id || null,
    extra_subsidy_ids: (c.extra_subsidies || []).map(es => es.subsidy_id),
    subject: c.subject || '',
    max_amount: c.max_amount || null, planned_monthly: c.planned_monthly || null,
    start_date: c.start_date || '', end_date: c.end_date || '',
    status: c.status || 'active', notes: c.notes || '',
  })
  dialog.show = true
}

const saveContract = async () => {
  dialog.saving = true
  try {
    const body = { ...dialog.form, date: dialog.form.date || null, start_date: dialog.form.start_date || null, end_date: dialog.form.end_date || null }
    if (dialog.id) {
      await apiFetch(`/contracts/${dialog.id}`, { method: 'PUT', body: JSON.stringify(body) })
      showSnack('Сохранено')
    } else {
      await apiFetch('/contracts/', { method: 'POST', body: JSON.stringify(body) })
      showSnack('Создано')
    }
    dialog.show = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка сохранения', 'error')
  } finally {
    dialog.saving = false
  }
}

const deleteDialog = reactive({ show: false, deleting: false, item: null as Contract | null })
const confirmDelete = (c: Contract) => { deleteDialog.item = c; deleteDialog.show = true }
const doDelete = async () => {
  if (!deleteDialog.item) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/contracts/${deleteDialog.item.id}`, { method: 'DELETE' })
    showSnack('Удалено', 'warning')
    deleteDialog.show = false
    await loadContracts()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

// ── Migration ──────────────────────────────────────────────────────────────
const migrateDialog = ref(false)
const migrating = ref(false)
const migrateResult = ref<{ created: number; skipped: number } | null>(null)

watch(migrateDialog, (v) => { if (!v) migrateResult.value = null })

const doMigrate = async () => {
  migrating.value = true
  try {
    const res = await apiFetch<{ created: number; skipped: number }>('/contracts/migrate-from-purchases', { method: 'POST' })
    migrateResult.value = res
    if (res.created > 0) await loadContracts()
    showSnack(`Создано: ${res.created}`)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка миграции', 'error')
  } finally {
    migrating.value = false
  }
}

onMounted(() => { loadContracts(); loadSubsidies(); loadContractors() })
</script>
