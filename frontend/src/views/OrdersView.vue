<template>
  <v-container fluid class="pa-6">
    <OrdersToolbar
      :orders-count="orders.length"
      :can-add-wish="authStore.hasTab('wishes')"
      @download-template="importDialogRef?.downloadTemplate()"
      @open-import="importDialogRef?.open()"
      @open-scans="scansDialogRef?.open()"
      @open-payment-match="paymentMatchDialogRef?.open(filters.subsidyId)"
      @open-export="exportDialogRef?.open()"
    />

    <OrdersFilterBar
      :filters="filters"
      :subsidies="subsidies"
      :status-items="statusItems"
      :order-type-options="orderTypeOptions"
      :contractors-for-filter="contractorsForFilter"
      :mobile="mobile"
      v-model:view-mode="viewMode"
      :active-filter-count="activeFilterCount"
      :filtered-sum="filteredSum"
      :saved-filter-presets="savedFilterPresets"
      :orders-from-wish-count="filteredOrders.length"
      @save-preset="saveFilterPreset"
      @open-columns="showColumnPicker = true"
      @apply-preset="applyFilterPreset"
      @remove-preset="removeFilterPreset"
      @clear-filters="clearAllFilters(); filters.periodFrom = ''; filters.periodTo = ''"
    />

    <!-- Bulk actions bar -->
    <div v-if="selectedOrders.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedOrders.length }}</span>
      <v-menu>
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" size="small" variant="tonal" color="blue" prepend-icon="mdi-swap-horizontal">
            Сменить статус
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item
            v-for="s in statusItems" :key="s.value"
            :title="s.label"
            :prepend-icon="'mdi-circle-small'"
            @click="bulkChangeStatus(s.value)"
          />
        </v-list>
      </v-menu>
      <v-spacer />
      <v-btn v-if="isAdmin" color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDelete">
        Удалить выбранные
      </v-btn>
      <v-btn variant="text" size="small" @click="selectedOrders = []">Снять выделение</v-btn>
    </div>

    <!-- Link task banner -->
    <v-alert v-if="linkTaskId" type="info" variant="tonal" closable class="mb-3"
      @click:close="linkTaskId = null; router.replace({ query: {} })">
      <div class="d-flex align-center ga-2">
        <v-icon>mdi-link-variant</v-icon>
        <span>Выберите закупку для привязки к задаче <b>#{{ linkTaskId }}</b></span>
        <v-btn size="small" variant="text" @click="linkTaskId = null; router.replace({ query: {} })">Отмена</v-btn>
      </div>
    </v-alert>

    <!-- Владелец (2026-09-17): открыт фильтр статуса, который обычные фильтры
         реестра никогда не показывают (переход из диалога удаления субсидии,
         ?status=wishes/split) — плашка объясняет, почему эти строки обычно не
         видны, чтобы не выглядело так, будто реестр их "прячет" без причины. -->
    <v-alert v-if="hiddenStatusBanner" type="info" variant="tonal" class="mb-3">
      {{ hiddenStatusBanner }}
    </v-alert>

    <!-- Table / Cards toggle -->
    <OrdersTable
      v-if="effectiveView === 'table'"
      :headers="tableHeaders"
      :items="filteredOrdersWithRowNum"
      :filtered-orders="filteredOrders"
      :loading="loading"
      :search="filters.search"
      v-model:selected-orders="selectedOrders"
      v-model:expanded="expanded"
      :col-filters="colState.filters"
      :get-sort-by="getSortBy"
      :apply-sort="applySort"
      :set-filter="setFilter"
      :toggle-visible="toggleVisible"
      :dup-group-for="dupGroupFor"
      :is-admin="isAdmin"
      :transitioning="transitioning"
      :link-task-id="linkTaskId"
      :status-items="statusItems"
      @transition="doTransition"
      @force-status="doForceStatus"
      @link-task="doLinkTask"
      @delete-one="confirmDeleteOne"
      @open-files="item => filesViewerRef?.open(item)"
      @stop-purchase="stopAction.openStop"
      @resume-purchase="stopAction.openResume"
    />

    <!-- Cards view -->
    <OrdersCards
      v-else
      :paged-cards="pagedCards"
      v-model:cards-page="cardsPage"
      :cards-total-pages="cardsTotalPages"
      :is-order-selected="isOrderSelected"
      :toggle-order-selected="toggleOrderSelected"
      :is-admin="isAdmin"
      :transitioning="transitioning"
      @transition="doTransition"
      @delete-one="confirmDeleteOne"
      @open-files="item => filesViewerRef?.open(item)"
      @stop-purchase="stopAction.openStop"
      @resume-purchase="stopAction.openResume"
    />

    <PurchaseStopDialog
      v-model="stopAction.dialog.show"
      :mode="stopAction.dialog.mode"
      :purchase="stopAction.dialog.purchase"
      :reason="stopAction.dialog.reason"
      :loading="stopAction.loading.value"
      @update:reason="v => stopAction.dialog.reason = v"
      @confirm="onConfirmStopPurchase"
    />

    <OrdersDeleteDialog :dialog="deleteDialog" :selected-count="selectedOrders.length" :on-delete="doDelete" />
    <OrdersGuardDialog :dialog="guardDialog" />
    <OrdersFilesViewerDialog ref="filesViewerRef" :show-snack="showSnack" />
    <OrdersImportDialog ref="importDialogRef" :subsidies="subsidies" :show-snack="showSnack" :on-imported="loadOrders" />
    <OrdersScansDialog ref="scansDialogRef" :subsidies="subsidies" :show-snack="showSnack" />
    <OrdersPaymentMatchDialog ref="paymentMatchDialogRef" :subsidies="subsidies" :show-snack="showSnack" :on-applied="loadOrders" />
    <OrdersFilterPresetDialog :dialog="filterPresetDialog" :filters="filters" :subsidies="subsidies" :on-confirm="confirmSaveFilterPreset" />

    <!-- Column Config Dialog -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :groups="groups"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />

    <OrdersExportDialog ref="exportDialogRef" :filters="filters" :show-snack="showSnack" />
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '@/stores/auth'
import { ADMIN_ROLES } from '@/constants/roles'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { useToast, type ToastType } from '@/composables/useToast'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'

import OrdersToolbar from '@/components/orders/OrdersToolbar.vue'
import OrdersFilterBar from '@/components/orders/OrdersFilterBar.vue'
import OrdersTable from '@/components/orders/OrdersTable.vue'
import OrdersCards from '@/components/orders/OrdersCards.vue'
import OrdersDeleteDialog from '@/components/orders/OrdersDeleteDialog.vue'
import OrdersGuardDialog from '@/components/orders/OrdersGuardDialog.vue'
import OrdersFilesViewerDialog from '@/components/orders/OrdersFilesViewerDialog.vue'
import OrdersImportDialog from '@/components/orders/OrdersImportDialog.vue'
import OrdersScansDialog from '@/components/orders/OrdersScansDialog.vue'
import OrdersPaymentMatchDialog from '@/components/orders/OrdersPaymentMatchDialog.vue'
import OrdersFilterPresetDialog from '@/components/orders/OrdersFilterPresetDialog.vue'
import OrdersExportDialog from '@/components/orders/OrdersExportDialog.vue'
import PurchaseStopDialog from '@/components/orders/PurchaseStopDialog.vue'

import { allColumns, getRowField, groups, useOrdersColumns } from '@/composables/orders/useOrdersColumns'
import { useOrdersFilters } from '@/composables/orders/useOrdersFilters'
import { useOrdersData } from '@/composables/orders/useOrdersData'
import { usePurchaseStop } from '@/composables/orders/usePurchaseStop'
import { orderTypeOptions, statusItems } from '@/composables/orders/ordersLabels'
import type { Purchase } from '@/composables/orders/ordersTypes'

const { globalSubsidyId } = useGlobalSubsidy()
const authStore = useAuthStore()

const route = useRoute()
const router = useRouter()

// View mode toggle (table ↔ cards)
const { mobile } = useDisplay()
const viewMode = ref<'table' | 'cards'>((localStorage.getItem('orders_view_mode') as 'table' | 'cards') || 'table')
watch(viewMode, v => localStorage.setItem('orders_view_mode', v))
const effectiveView = computed(() => (mobile.value ? 'cards' : viewMode.value))
const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ADMIN_ROLES.includes(userRole as typeof ADMIN_ROLES[number])

// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// duration=0 по умолчанию: результат действия (смена статуса, удаление и т.п.)
// не должен исчезать сам, пока пользователь не прочитал и не закрыл.
const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const {
  colState, toggleVisible, setPosition, setWidth, resetColumns, setFilter, clearAllFilters, activeFilterCount,
  tableHeaders, showColumnPicker, localSort, getSortBy, applySort, matchesColumnFilters,
} = useOrdersColumns()

const {
  filters, linkTaskId, doLinkTask,
  savedFilterPresets, filterPresetDialog, loadFilterPresets, saveFilterPreset,
  confirmSaveFilterPreset, applyFilterPreset, removeFilterPreset, applyFiltersFromQuery,
} = useOrdersFilters({ route, router, globalSubsidyId, showSnack })

const {
  orders, dupGroupFor, subsidies, loading, transitioning,
  contractorsForFilter, expanded, selectedOrders, guardDialog, deleteDialog,
  filteredOrders, filteredOrdersWithRowNum,
  cardsPage, cardsTotalPages, pagedCards,
  isOrderSelected, toggleOrderSelected, filteredSum,
  loadOrders, loadDuplicateGroups, loadSubsidies, suppressNextStatusReload,
  doTransition, doForceStatus, confirmDeleteOne, confirmBulkDelete, bulkChangeStatus, doDelete,
} = useOrdersData({
  filters, matchesColumnFilters, localSort, getRowField,
  showSnack,
})

// Владелец, 2026-09-15: остановка/возобновление закупки — общий composable
// (usePurchaseStop.ts), тот же используется в CreateOrderView.vue (карточка).
const stopAction = usePurchaseStop({ showSnack })
function onConfirmStopPurchase() {
  stopAction.confirm((updated: Purchase) => {
    const idx = orders.value.findIndex(o => o.id === updated.id)
    if (idx >= 0) orders.value[idx] = { ...orders.value[idx], ...updated }
  })
}

// Component refs (dialogs, opened imperatively — см. defineExpose в компонентах)
const filesViewerRef = ref<InstanceType<typeof OrdersFilesViewerDialog> | null>(null)
const importDialogRef = ref<InstanceType<typeof OrdersImportDialog> | null>(null)
const scansDialogRef = ref<InstanceType<typeof OrdersScansDialog> | null>(null)
const paymentMatchDialogRef = ref<InstanceType<typeof OrdersPaymentMatchDialog> | null>(null)
const exportDialogRef = ref<InstanceType<typeof OrdersExportDialog> | null>(null)

// Владелец (2026-09-17): "заявки не в работе"/"разделённые закупки" скрыты в
// реестре обычными фильтрами — эта плашка появляется, только когда открыт
// именно такой служебный фильтр (например, по ссылке из диалога удаления
// субсидии), и объясняет причину прямым текстом без жаргона статусов.
const hiddenStatusBanner = computed(() => {
  if (filters.status === 'wishes') return 'Показаны заявки, не переданные в работу — обычно они не отображаются в реестре закупок, пока не будут переданы в план.'
  if (filters.status === 'split') return 'Показаны разделённые закупки (родительские записи) — после разделения их части учитываются отдельно, сама родительская запись обычно скрыта в реестре.'
  return null
})

// Phase 26-ZZ: bulk-load контрагентов убран. Фильтр контрагентов
// dedupe-by-name из orders, не требует справочника.
onMounted(async () => {
  // Владелец (2026-09-17): статус/субсидию/т.п. из query-строки нужно применить
  // ДО первого loadOrders() — иначе первый запрос уходит без ?status= (реестр
  // не знает про wishes/split из ссылки), см. useOrdersData.ts::loadOrders.
  // suppressNextStatusReload() ДО applyFiltersFromQuery — иначе синхронная
  // установка filters.status из ?status= в ссылке триггерит watch внутри
  // useOrdersData и уходит ВТОРОЙ (дублирующий) запрос вдобавок к явному
  // loadOrders() ниже (QA-баг 2026-09-17, см. комментарий у watch в
  // useOrdersData.ts).
  suppressNextStatusReload()
  applyFiltersFromQuery(() => {
    const found = orders.value.find(o => o.feo_category_id === filters.feoCategoryId)
    if (found?.feo_category_name) filters.feoCategoryName = found.feo_category_name
  })
  loadOrders()
  loadDuplicateGroups()
  loadSubsidies(() => { globalSubsidyId.value = null })
  loadFilterPresets()
})
</script>

<style scoped>
</style>
