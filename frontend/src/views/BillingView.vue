<template>
  <v-container fluid class="pa-4">
    <div class="d-flex align-center mb-4">
      <v-icon icon="mdi-currency-rub" class="mr-2" color="primary" />
      <h2 class="text-h5 font-weight-bold">Биллинг</h2>
    </div>

    <!-- ── Superadmin: таблица всех контуров ── -->
    <template v-if="isSuperadmin">
      <v-card variant="outlined" rounded="lg">
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <span class="text-subtitle-1 font-weight-bold">Контуры — текущий месяц</span>
          <v-spacer />
          <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" class="mr-2" @click="showColumnPicker = true">Колонки</v-btn>
          <v-btn size="small" variant="outlined" :color="showHistory ? 'primary' : undefined"
            prepend-icon="mdi-history" @click="showHistory = !showHistory">
            {{ showHistory ? 'Скрыть историю' : 'История' }}
          </v-btn>
        </v-card-title>

        <v-data-table
          v-if="!showHistory"
          :headers="visibleHeaders"
          :items="orgs"
          :loading="loading"
          item-value="org_id"
          density="comfortable"
          show-expand
          :items-per-page="-1"
          hide-default-footer
        >
          <!-- Expand: разбивка по org -->
          <template #expanded-row="{ columns, item }">
            <tr>
              <td :colspan="columns.length" class="pa-0">
                <div class="pa-3 bg-grey-lighten-5">
                  <div class="text-caption font-weight-medium text-medium-emphasis mb-2">
                    Сотрудники по организациям контура
                  </div>
                  <v-table density="compact" class="rounded">
                    <thead>
                      <tr>
                        <th>Организация</th>
                        <th class="text-right">Сотрудников</th>
                        <th class="text-right">Примечание</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="row in item.org_breakdown" :key="row.org_id">
                        <td>{{ row.org_name }}</td>
                        <td class="text-right font-weight-medium">{{ row.user_count }}</td>
                        <td class="text-right text-caption text-medium-emphasis">
                          {{ row.org_id === item.org_id ? 'головная' : 'дочерняя' }}
                        </td>
                      </tr>
                    </tbody>
                    <tfoot>
                      <tr class="bg-blue-lighten-5">
                        <td class="font-weight-bold text-primary">Уникальных итого</td>
                        <td class="text-right font-weight-bold text-primary">{{ item.unique_user_count }}</td>
                        <td class="text-right text-caption text-medium-emphasis">основа для расчёта</td>
                      </tr>
                    </tfoot>
                  </v-table>
                </div>
              </td>
            </tr>
          </template>

          <template #item.created_at="{ item }">
            {{ fmtDate(item.created_at) }}
          </template>
          <template #item.current.month_num="{ item }">
            <span class="font-weight-medium">{{ item.current.month_num }}</span>
          </template>
          <template #item.current.tier="{ item }">
            <v-chip :color="tierColor(item.current.tier)" size="small" label variant="flat">
              {{ item.current.tier_label }}
            </v-chip>
          </template>
          <template #item.current.user_count="{ item }">
            <div>
              <span class="font-weight-bold">{{ item.unique_user_count }}</span>
              <span v-if="item.org_breakdown.length > 1" class="text-caption text-medium-emphasis ml-1">
                (ун.)
              </span>
            </div>
          </template>
          <template #item.current.amount_due="{ item }">
            <span class="font-weight-bold">
              {{ item.current.amount_due === 0 ? '0 ₽' : fmtMoney(item.current.amount_due) }}
            </span>
          </template>
          <template #item.current.is_paid="{ item }">
            <v-chip
              :color="item.current.is_paid ? 'success' : (item.current.amount_due > 0 ? 'error' : 'grey')"
              size="small" label variant="flat"
            >
              <v-icon :icon="item.current.is_paid ? 'mdi-check-circle' : 'mdi-close-circle'" size="16" class="mr-1" />
              {{ item.current.is_paid ? 'Оплачено' : (item.current.amount_due > 0 ? 'Не оплачено' : '—') }}
            </v-chip>
          </template>
          <template #item.actions="{ item }">
            <v-btn v-if="item.current.amount_due > 0 && !item.current.is_paid"
              size="small" variant="tonal" color="success" prepend-icon="mdi-check"
              :loading="payingId === item.org_id" @click="markPaid(item)">
              Оплачено
            </v-btn>
            <v-btn v-else-if="item.current.is_paid"
              size="small" variant="text" color="error" prepend-icon="mdi-undo"
              :loading="payingId === item.org_id" @click="markUnpaid(item)">
              Отменить
            </v-btn>
          </template>
        </v-data-table>

        <!-- История по выбранной организации -->
        <template v-if="showHistory">
          <v-card-text class="pt-0">
            <v-autocomplete
              v-model="historyOrgId" :items="orgs" item-title="org_name" item-value="org_id"
              label="Выберите организацию" prepend-inner-icon="mdi-domain"
              density="compact" class="mb-3" style="max-width: 400px;"
              @update:model-value="loadHistory"
            />
          </v-card-text>
          <v-data-table v-if="historyItems.length"
            :headers="historyHeaders" :items="historyItems" :loading="historyLoading"
            density="comfortable" :items-per-page="12" class="billing-table">
            <template #item.month="{ item }">{{ monthName(item.month) }} {{ item.year }}</template>
            <template #item.tier="{ item }">
              <v-chip :color="tierColor(item.tier)" size="small" label variant="flat">{{ item.tier_label }}</v-chip>
            </template>
            <template #item.amount_due="{ item }">
              <span class="font-weight-bold">{{ item.amount_due === 0 ? '0 ₽' : fmtMoney(item.amount_due) }}</span>
            </template>
            <template #item.is_paid="{ item }">
              <v-chip :color="item.is_paid ? 'success' : (item.amount_due > 0 ? 'error' : 'grey')" size="small" label variant="flat">
                <v-icon :icon="item.is_paid ? 'mdi-check-circle' : 'mdi-close-circle'" size="16" class="mr-1" />
                {{ item.is_paid ? 'Оплачено' : (item.amount_due > 0 ? 'Не оплачено' : '—') }}
              </v-chip>
            </template>
            <template #item.actions="{ item }">
              <v-btn v-if="item.amount_due > 0 && !item.is_paid" size="x-small" variant="tonal" color="success" icon="mdi-check"
                :loading="payingKey === `${item.year}-${item.month}`" @click="markPaidHistory(item)" />
              <v-btn v-else-if="item.is_paid" size="x-small" variant="text" color="error" icon="mdi-undo"
                :loading="payingKey === `${item.year}-${item.month}`" @click="markUnpaidHistory(item)" />
            </template>
          </v-data-table>
        </template>
      </v-card>
    </template>

    <!-- ── account_owner: карточка своего контура ── -->
    <template v-else-if="isAccountOwner">
      <v-row v-if="myBilling">
        <!-- KPI сверху -->
        <v-col cols="12" sm="4">
          <v-card variant="tonal" color="primary" rounded="lg" class="pa-4">
            <div class="text-caption text-medium-emphasis mb-1">Уникальных сотрудников</div>
            <div class="text-h4 font-weight-bold">{{ myBilling.user_count }}</div>
            <div class="text-caption text-medium-emphasis mt-1">основа для расчёта стоимости</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="4">
          <v-card variant="tonal" :color="tierColor(myBilling.tier)" rounded="lg" class="pa-4">
            <div class="text-caption text-medium-emphasis mb-1">Тариф</div>
            <div class="text-h6 font-weight-bold">{{ myBilling.tier_label }}</div>
            <div class="text-caption text-medium-emphasis mt-1">Месяц подключения: {{ myBilling.month_num }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="4">
          <v-card variant="tonal" :color="myBilling.is_paid ? 'success' : (myBilling.amount_due > 0 ? 'error' : 'grey')" rounded="lg" class="pa-4">
            <div class="text-caption text-medium-emphasis mb-1">К оплате (текущий месяц)</div>
            <div class="text-h4 font-weight-bold">{{ myBilling.amount_due === 0 ? '0 ₽' : fmtMoney(myBilling.amount_due) }}</div>
            <v-chip size="small" :color="myBilling.is_paid ? 'success' : (myBilling.amount_due > 0 ? 'error' : 'grey')" variant="flat" class="mt-2">
              <v-icon :icon="myBilling.is_paid ? 'mdi-check-circle' : 'mdi-close-circle'" size="14" class="mr-1" />
              {{ myBilling.is_paid ? 'Оплачено' : (myBilling.amount_due > 0 ? 'Не оплачено' : 'Бесплатный период') }}
            </v-chip>
          </v-card>
        </v-col>

        <!-- Разбивка по организациям -->
        <v-col cols="12">
          <v-card variant="outlined" rounded="lg">
            <v-card-title class="text-subtitle-2 pa-4 pb-2">Сотрудники по организациям</v-card-title>
            <v-table density="comfortable">
              <thead>
                <tr>
                  <th>Организация</th>
                  <th class="text-right">Сотрудников</th>
                  <th class="text-right">Тип</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in myContourBreakdown" :key="row.org_id">
                  <td>
                    <v-icon size="14" class="mr-1" :color="row.is_root ? 'primary' : 'grey'">
                      {{ row.is_root ? 'mdi-domain' : 'mdi-office-building-outline' }}
                    </v-icon>
                    {{ row.org_name }}
                  </td>
                  <td class="text-right font-weight-medium">{{ row.user_count }}</td>
                  <td class="text-right">
                    <v-chip size="x-small" :color="row.is_root ? 'primary' : 'grey'" variant="tonal">
                      {{ row.is_root ? 'головная' : 'дочерняя' }}
                    </v-chip>
                  </td>
                </tr>
              </tbody>
              <tfoot>
                <tr style="background: rgb(var(--v-theme-primary), 0.05)">
                  <td class="font-weight-bold text-primary">Уникальных итого</td>
                  <td class="text-right font-weight-bold text-primary text-h6">{{ myBilling.user_count }}</td>
                  <td class="text-right text-caption text-medium-emphasis">основа для расчёта</td>
                </tr>
              </tfoot>
            </v-table>
            <v-card-text class="text-caption text-medium-emphasis pt-0">
              * Уникальные — сотрудники без двойного счёта. Если человек в нескольких организациях — считается один раз.
            </v-card-text>
          </v-card>
        </v-col>

        <!-- История -->
        <v-col cols="12">
          <v-card variant="outlined" rounded="lg">
            <v-card-title class="text-subtitle-2 pa-4 pb-2">История платежей</v-card-title>
            <v-data-table
              :headers="orgAdminHistoryHeaders" :items="myHistory"
              :loading="historyLoading" density="compact" :items-per-page="6">
              <template #item.month="{ item }">{{ monthName(item.month) }} {{ item.year }}</template>
              <template #item.tier="{ item }">
                <v-chip :color="tierColor(item.tier)" size="x-small" label variant="flat">{{ item.tier_label }}</v-chip>
              </template>
              <template #item.user_count="{ item }">{{ item.user_count }}</template>
              <template #item.amount_due="{ item }">{{ item.amount_due === 0 ? '0 ₽' : fmtMoney(item.amount_due) }}</template>
              <template #item.is_paid="{ item }">
                <v-icon
                  :icon="item.is_paid ? 'mdi-check-circle' : (item.amount_due > 0 ? 'mdi-close-circle' : 'mdi-minus-circle')"
                  :color="item.is_paid ? 'success' : (item.amount_due > 0 ? 'error' : 'grey')"
                  size="20"
                />
              </template>
            </v-data-table>
          </v-card>
        </v-col>
      </v-row>
      <v-progress-circular v-else-if="loading" indeterminate class="mt-8 d-block mx-auto" />
    </template>

    <!-- Нет доступа -->
    <v-alert v-else type="info" variant="tonal" class="mt-4">
      Раздел доступен администраторам организаций.
    </v-alert>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'

const role = localStorage.getItem('user_role') || ''
const isSuperadmin = role === 'superadmin'
const isAccountOwner = role === 'account_owner'

const loading = ref(false)
const snack = ref({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.value = { show: true, text, color } }

// ── Superadmin state ──
const orgs = ref<any[]>([])
const showHistory = ref(false)
const historyOrgId = ref<number | null>(null)
const historyItems = ref<any[]>([])
const historyLoading = ref(false)
const payingId = ref<number | null>(null)
const payingKey = ref<string | null>(null)

const allColumns: ColumnDef[] = [
  { title: '', key: 'data-table-expand', width: 40, sortable: false },
  { title: 'Контур / Организация', key: 'org_name', sortable: true },
  { title: 'Подключена', key: 'created_at', sortable: true, width: 120 },
  { title: 'Мес.', key: 'current.month_num', sortable: true, width: 70 },
  { title: 'Тариф', key: 'current.tier', width: 160 },
  { title: 'Уник. сотр.', key: 'current.user_count', sortable: true, width: 110 },
  { title: 'К оплате', key: 'current.amount_due', sortable: true, width: 120 },
  { title: 'Статус', key: 'current.is_paid', width: 150 },
  { title: '', key: 'actions', sortable: false, width: 130 },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('billing', allColumns)
const showColumnPicker = ref(false)

const historyHeaders = [
  { title: 'Период', key: 'month', width: 140 },
  { title: 'Мес. №', key: 'month_num', width: 70 },
  { title: 'Тариф', key: 'tier', width: 140 },
  { title: 'Сотр.', key: 'user_count', width: 80 },
  { title: 'Сумма', key: 'amount_due', width: 120 },
  { title: 'Статус', key: 'is_paid', width: 140 },
  { title: '', key: 'actions', width: 60, sortable: false },
]

// ── account_owner state ──
const myOrgId = ref<number | null>(null)
const myBilling = ref<any>(null)
const myHistory = ref<any[]>([])
const myContourOrgs = ref<any[]>([])

const myContourBreakdown = computed(() => {
  if (!myOrgId.value || !myContourOrgs.value.length) return []
  return myContourOrgs.value.map(o => ({ ...o, is_root: o.org_id === myOrgId.value }))
})

const orgAdminHistoryHeaders = [
  { title: 'Период', key: 'month', width: 120 },
  { title: 'Тариф', key: 'tier', width: 120 },
  { title: 'Уник. сотр.', key: 'user_count', width: 100 },
  { title: 'Сумма', key: 'amount_due', width: 100 },
  { title: 'Статус', key: 'is_paid', width: 60 },
]

// ── Helpers ──
const MONTHS = ['','Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']
function monthName(m: number) { return MONTHS[m] || m }
function fmtDate(d: string) { return d ? new Date(d).toLocaleDateString('ru-RU') : '—' }
function fmtMoney(n: number) { return n.toLocaleString('ru-RU') + ' ₽' }
function tierColor(tier: string) {
  if (tier === 'free') return 'success'
  if (tier === 'flat') return 'info'
  if (tier === 'per_user') return 'warning'
  return 'grey'
}

// ── Load ──
async function loadOrgs() {
  loading.value = true
  try {
    orgs.value = await apiFetch('/billing/')
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки биллинга', 'error')
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  if (!historyOrgId.value) { historyItems.value = []; return }
  historyLoading.value = true
  try {
    historyItems.value = await apiFetch(`/billing/${historyOrgId.value}`)
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки истории', 'error')
  } finally {
    historyLoading.value = false
  }
}

async function loadMyBilling() {
  loading.value = true
  try {
    const orgInfo = await apiFetch('/organizations/me')
    myOrgId.value = orgInfo.id
    if (orgInfo.id) {
      const months = await apiFetch(`/billing/${orgInfo.id}`)
      if (months.length) myBilling.value = months[0]
      myHistory.value = months

      // Load contour orgs for breakdown
      try {
        const contourData: any[] = await apiFetch('/billing/')
        const myContour = contourData.find((o: any) => o.org_id === orgInfo.id)
        if (myContour?.org_breakdown) {
          myContourOrgs.value = myContour.org_breakdown
        }
      } catch {}
    }
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

// ── Pay / unpay ──
async function markPaid(item: any) {
  payingId.value = item.org_id
  try {
    await apiFetch(`/billing/${item.org_id}/pay`, { method: 'POST', body: { year: item.current.year, month: item.current.month } })
    item.current.is_paid = true
    showSnack('Отмечено как оплаченное')
  } catch (e: any) { showSnack(e?.message || 'Ошибка', 'error') }
  finally { payingId.value = null }
}

async function markUnpaid(item: any) {
  payingId.value = item.org_id
  try {
    await apiFetch(`/billing/${item.org_id}/unpay`, { method: 'POST', body: { year: item.current.year, month: item.current.month } })
    item.current.is_paid = false
    showSnack('Оплата отменена')
  } catch (e: any) { showSnack(e?.message || 'Ошибка', 'error') }
  finally { payingId.value = null }
}

async function markPaidHistory(item: any) {
  payingKey.value = `${item.year}-${item.month}`
  try {
    await apiFetch(`/billing/${historyOrgId.value}/pay`, { method: 'POST', body: { year: item.year, month: item.month } })
    item.is_paid = true
    showSnack('Отмечено как оплаченное')
  } catch (e: any) { showSnack(e?.message || 'Ошибка', 'error') }
  finally { payingKey.value = null }
}

async function markUnpaidHistory(item: any) {
  payingKey.value = `${item.year}-${item.month}`
  try {
    await apiFetch(`/billing/${historyOrgId.value}/unpay`, { method: 'POST', body: { year: item.year, month: item.month } })
    item.is_paid = false
    showSnack('Оплата отменена')
  } catch (e: any) { showSnack(e?.message || 'Ошибка', 'error') }
  finally { payingKey.value = null }
}

onMounted(() => {
  if (isSuperadmin) loadOrgs()
  else if (isAccountOwner) loadMyBilling()
})
</script>

<style scoped>
.billing-table :deep(th) { white-space: nowrap; }
</style>
