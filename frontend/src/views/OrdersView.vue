<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Закупки</h1>
        <span class="text-body-2 text-medium-emphasis">{{ orders.length }} записей</span>
      </div>
      <div class="d-flex gap-2">
        <v-btn variant="outlined" size="small" prepend-icon="mdi-download" @click="downloadTemplate">Шаблон</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-import" color="blue" @click="importDialog.show = true">Импорт</v-btn>
        <v-btn variant="outlined" prepend-icon="mdi-file-export" color="success" @click="openExportDialog">Excel</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" to="/create-order">Добавить</v-btn>
      </div>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-select
            v-model="filterStatus"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:170px"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-btn
            size="small" variant="tonal" color="primary"
            prepend-icon="mdi-bookmark-plus-outline"
            @click="saveFilterPreset">
            Сохранить фильтр
          </v-btn>
        </div>
        <!-- Saved filter preset chips -->
        <div v-if="savedFilterPresets.length" class="d-flex align-center gap-2 flex-wrap mt-2">
          <span class="text-caption text-medium-emphasis">Пресеты:</span>
          <v-chip
            v-for="p in savedFilterPresets" :key="p.name"
            size="small" variant="tonal" color="primary"
            class="cursor-pointer"
            @click="applyFilterPreset(p)">
            {{ p.name }}
            <v-icon icon="mdi-close" size="12" class="ml-1" @click.stop="removeFilterPreset(p.name)" />
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- Status tab chips -->
    <v-chip-group v-model="filterStatus" class="mb-4">
      <v-chip value="" variant="outlined" filter>Все</v-chip>
      <v-chip
        v-for="s in statusItems"
        :key="s.value"
        :value="s.value"
        :color="s.color"
        filter
        variant="outlined"
      >
        {{ s.label }}
      </v-chip>
    </v-chip-group>

    <!-- FEO category filter badge -->
    <v-chip v-if="filterFeoCategoryId" color="teal" variant="tonal" closable class="mb-3" prepend-icon="mdi-filter"
      @click:close="filterFeoCategoryId = null; filterFeoCategoryName = ''">
      ФЭО: {{ filterFeoCategoryName }}
    </v-chip>

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
      @click:close="linkTaskId = null; $router.replace({ query: {} })">
      <div class="d-flex align-center ga-2">
        <v-icon>mdi-link-variant</v-icon>
        <span>Выберите закупку для привязки к задаче <b>#{{ linkTaskId }}</b></span>
        <v-btn size="small" variant="text" @click="linkTaskId = null; $router.replace({ query: {} })">Отмена</v-btn>
      </div>
    </v-alert>

    <!-- Table -->
    <v-card variant="outlined">
      <v-data-table
        ref="ordersTableRef"
        v-resizable-columns="'orders'"
        :headers="headers"
        :items="filteredOrders"
        :loading="loading"
        :search="search"
        density="compact"
        hover
        show-expand
        show-select
        v-model="selectedOrders"
        v-model:expanded="expanded"
        items-per-page="25"
        :items-per-page-options="[25, 50, 100]"
        return-object
        class="orders-clickable"
        @click:row="(_, { item }) => router.push(`/orders/${item.id}/edit`)"
      >
        <!-- Expand toggle column -->
        <template #item.data-table-expand="{ item, internalItem, isExpanded, toggleExpand }">
          <v-btn
            v-if="item.items && item.items.length > 0"
            :icon="isExpanded(internalItem) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
            variant="text"
            size="small"
            @click="toggleExpand(internalItem)"
          />
        </template>

        <!-- Предмет договора -->
        <template #item.subject="{ item }">
          <div>{{ item.subject || item.item_name || '—' }}</div>
          <div v-if="!item.contractor_name || !item.feo_category_id || !item.execution_term || !(item.planned_total_price)" class="d-flex flex-wrap ga-1 mt-1">
            <v-chip v-if="!item.contractor_name" size="x-small" color="error" variant="tonal" prepend-icon="mdi-domain-off">Контрагент</v-chip>
            <v-chip v-if="!item.feo_category_id" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-tag-off">ФЭО</v-chip>
            <v-chip v-if="!item.execution_term" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-calendar-alert">Срок</v-chip>
            <v-chip v-if="!item.planned_total_price" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-currency-rub">Сумма</v-chip>
          </div>
        </template>

        <!-- Display name (first item or legacy item_name) -->
        <template #item.display_name="{ item }">
          <span class="text-body-2">{{ itemDisplayName(item) }}</span>
        </template>

        <template #item.status="{ item }">
          <div class="d-flex align-center ga-1 flex-wrap">
            <v-chip :color="STATUS_COLOR[item.status] || 'grey'" size="small" variant="tonal">
              {{ statusLabelFor(item) }}
            </v-chip>
            <v-chip v-if="item.substatus" size="x-small" variant="outlined" color="teal">
              {{ SUBSTATUS_LABEL[item.substatus] || item.substatus }}
            </v-chip>
            <v-icon v-if="item.is_monthly_payment" size="x-small" color="blue" title="Ежемесячный платёж">mdi-calendar-sync</v-icon>
          </div>
        </template>

        <template #item.effective_price="{ item }">
          {{ formatMoney(effectivePrice(item)) }}
        </template>

        <template #item.contract_date="{ item }">
          {{ item.contract_date ? formatDate(item.contract_date) : '—' }}
        </template>

        <template #item.subsidy_name="{ item }">
          <span class="text-body-2 text-truncate" style="max-width:150px;display:inline-block">
            {{ item.subsidy_name || '—' }}
          </span>
        </template>

        <template #item.approval_status="{ item }">
          <v-chip v-if="item.approval_status" :color="APPROVAL_STATUS_COLOR[item.approval_status]" size="x-small" variant="tonal">
            {{ APPROVAL_STATUS_LABEL[item.approval_status] }}
          </v-chip>
          <span v-else class="text-caption text-medium-emphasis">—</span>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center gap-1" @click.stop>
            <v-btn
              v-if="!isAdmin && nextStatus(item.status)"
              size="x-small"
              :color="STATUS_COLOR[nextStatus(item.status)!]"
              variant="tonal"
              :loading="transitioning === item.id"
              @click.stop="doTransition(item)"
            >
              → {{ statusLabelFor(item, nextStatus(item.status)!) }}
            </v-btn>
            <v-menu v-if="isAdmin">
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" size="x-small" :color="STATUS_COLOR[item.status]" variant="tonal" :loading="transitioning === item.id" append-icon="mdi-chevron-down">
                  {{ statusLabelFor(item) }}
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item
                  v-for="s in statusItems" :key="s.value"
                  :title="s.label"
                  :active="item.status === s.value"
                  @click="doForceStatus(item, s.value)"
                />
              </v-list>
            </v-menu>
            <v-btn v-if="linkTaskId" size="x-small" variant="tonal" color="deep-purple"
              prepend-icon="mdi-link-variant" @click.stop="doLinkTask(item.id)">
              Привязать
            </v-btn>
            <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click.stop="confirmDeleteOne(item)" />
          </div>
        </template>

        <!-- Expanded row: items list -->
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-0 bg-grey-lighten-5">
              <div class="pa-3">
                <v-table density="compact" class="rounded border">
                  <thead>
                    <tr class="bg-grey-lighten-4">
                      <th>Наименование позиции</th>
                      <th>Тип</th>
                      <th class="text-right">Кол-во</th>
                      <th>Ед.</th>
                      <th class="text-right">Цена ед., ₽</th>
                      <th class="text-right">Сумма, ₽</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="itm in item.items" :key="itm.id">
                      <td>{{ itm.item_name }}</td>
                      <td>{{ itm.item_type || '—' }}</td>
                      <td class="text-right">{{ itm.quantity ?? '—' }}</td>
                      <td>{{ itm.unit || '—' }}</td>
                      <td class="text-right">{{ itm.unit_price ? Number(itm.unit_price).toLocaleString('ru-RU') : '—' }}</td>
                      <td class="text-right">{{ itm.total_price ? Number(itm.total_price).toLocaleString('ru-RU') : '—' }}</td>
                    </tr>
                    <tr v-if="!item.items?.length">
                      <td colspan="6" class="text-center text-medium-emphasis text-caption py-2">Нет позиций</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>
            </td>
          </tr>
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-clipboard-text-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Закупки не найдены</div>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Delete dialog -->
    <v-dialog v-model="deleteDialog.show" max-width="420">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon icon="mdi-alert-circle-outline" color="error" />
          Удалить закупки
        </v-card-title>
        <v-card-text class="px-6">
          <template v-if="deleteDialog.bulk">
            Удалить <strong>{{ selectedOrders.length }}</strong> выбранных закупок? Действие нельзя отменить.
          </template>
          <template v-else>
            Удалить закупку <strong>{{ deleteDialog.single?.subject || deleteDialog.single?.item_name || `#${deleteDialog.single?.id}` }}</strong>? Действие нельзя отменить.
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <!-- Guard dialog -->
    <v-dialog v-model="guardDialog.show" max-width="480">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Не заполнены обязательные поля</v-card-title>
        <v-card-text class="px-6">
          <p class="mb-3 text-body-2 text-medium-emphasis">
            Для перехода в статус «{{ guardDialog.targetStatus === 'contracted' && guardDialog.isFramework ? 'Заказ' : STATUS_LABEL[guardDialog.targetStatus] }}» заполните:
          </p>
          <v-list density="compact">
            <v-list-item
              v-for="f in guardDialog.missing"
              :key="f"
              prepend-icon="mdi-alert-circle-outline"
              :title="f"
            />
          </v-list>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="guardDialog.show = false">Закрыть</v-btn>
          <v-btn color="primary" :to="`/orders/${guardDialog.purchaseId}/edit`" @click="guardDialog.show = false">
            Открыть форму
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Import Dialog ── -->
    <v-dialog v-model="importDialog.show" max-width="580" persistent>
      <v-card>
        <v-card-title class="pa-5 pb-2 d-flex align-center">
          <v-icon icon="mdi-file-import" color="blue" class="mr-2" />
          Импорт закупок из Excel
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="resetImport" />
        </v-card-title>
        <v-card-text class="pa-5 pt-2">

          <!-- Step 1: Setup -->
          <template v-if="importDialog.step === 1">
            <!-- Format selection -->
            <v-radio-group v-model="importDialog.format" inline class="mb-3" hide-details density="compact">
              <template #label><span class="text-body-2 font-weight-medium mr-3">Формат файла:</span></template>
              <v-radio value="standard" label="Стандартный (17 колонок)" />
              <v-radio value="feo" label="ФЭО-формат (57 колонок)" />
            </v-radio-group>

            <!-- Standard: subsidy override -->
            <v-select
              v-if="importDialog.format === 'standard'"
              v-model="importDialog.subsidyId"
              :items="[{ id: null, name: '— Из файла (колонка «Субсидия»)' }, ...subsidies]"
              item-title="name" item-value="id"
              label="Субсидия (переопределить для всего файла)"
              variant="outlined" density="compact" class="mb-3"
            />

            <!-- FEO: info banner -->
            <v-alert
              v-else
              type="info" variant="tonal" density="compact" class="mb-3"
              prepend-icon="mdi-information-outline"
            >
              Субсидия определяется автоматически по категории ФЭО (колонка 5). Заголовки — в строке 6.
            </v-alert>

            <FileDropZone v-model="importDialog.file"
              accept=".xlsx,.xls"
              hint="Excel (.xlsx, .xls) — перетащите или нажмите"
              class="mb-2" />

            <div v-if="importDialog.format === 'standard'" class="mt-3 text-caption text-medium-emphasis">
              Допустимые заголовки колонок:
              <span class="fz-11">Наименование, Субсидия, Категория ФЭО, Контрагент, ИНН контрагента, НМЦД, Способ закупки, Реестровый №, № договора, Дата договора, Цена договора, Срок исполнения, ПП №, ПП дата, Оплачено, Статус, Год</span>
            </div>
          </template>

          <!-- Step 2: Result -->
          <template v-else-if="importDialog.step === 2">
            <div class="import-result-row">
              <div class="import-stat import-stat--ok">
                <div class="import-stat-val">{{ importDialog.result?.created ?? 0 }}</div>
                <div class="import-stat-lbl">Создано</div>
              </div>
              <div class="import-stat import-stat--skip">
                <div class="import-stat-val">{{ importDialog.result?.skipped ?? 0 }}</div>
                <div class="import-stat-lbl">Пропущено</div>
              </div>
              <div class="import-stat import-stat--err">
                <div class="import-stat-val">{{ importDialog.result?.errors?.length ?? 0 }}</div>
                <div class="import-stat-lbl">Ошибок</div>
              </div>
            </div>
            <div v-if="importDialog.result?.errors?.length" class="mt-4">
              <div class="text-caption font-weight-bold mb-2">Строки с ошибками:</div>
              <v-list density="compact" class="import-errors-list">
                <v-list-item
                  v-for="e in importDialog.result.errors" :key="e.row"
                  :subtitle="`Строка ${e.row}: ${e.message}`"
                  :title="e.name"
                  prepend-icon="mdi-alert-circle-outline"
                  color="error"
                />
              </v-list>
            </div>
          </template>

        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-btn variant="text" size="small" prepend-icon="mdi-download"
            @click="downloadTemplate">Скачать шаблон</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="resetImport">
            {{ importDialog.step === 2 ? 'Закрыть' : 'Отмена' }}
          </v-btn>
          <v-btn v-if="importDialog.step === 1" color="blue" variant="flat"
            :loading="importDialog.loading" :disabled="!importDialog.file"
            @click="doImport">
            Загрузить
          </v-btn>
          <v-btn v-else color="primary" variant="flat" @click="resetImport">Готово</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Save Filter Preset Dialog -->
    <v-dialog v-model="filterPresetDialog.show" max-width="380">
      <v-card>
        <v-card-title class="pa-4">Сохранить фильтр</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field
            v-model="filterPresetDialog.name"
            label="Название пресета"
            variant="outlined" density="compact" autofocus
            placeholder="Например: ФАДМ 2026 неоплачено"
            @keyup.enter="confirmSaveFilterPreset"
          />
          <div class="text-caption text-medium-emphasis mt-1">
            <span v-if="filterSubsidyId">Субсидия: {{ subsidies.find(s=>s.id===filterSubsidyId)?.name }}</span>
            <span v-if="filterStatus" class="ml-2">Статус: {{ STATUS_LABEL[filterStatus] }}</span>
            <span v-if="search" class="ml-2">Поиск: "{{ search }}"</span>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="filterPresetDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!filterPresetDialog.name.trim()" @click="confirmSaveFilterPreset">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Excel Export Dialog -->
    <v-dialog v-model="exportDialog.show" max-width="680" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-microsoft-excel" color="success" class="mr-2" />
          Экспорт в Excel
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="exportDialog.show = false" />
        </v-card-title>

        <v-card-text class="pa-0">
          <!-- Presets row -->
          <div class="d-flex align-center gap-2 px-4 py-2 bg-grey-lighten-5 border-b">
            <span class="text-caption text-medium-emphasis mr-1">Пресет:</span>
            <v-btn size="x-small" variant="tonal" @click="applyPreset('default')">Стандартный</v-btn>
            <v-btn size="x-small" variant="tonal" @click="applyPreset('all')">Полный</v-btn>
            <v-btn size="x-small" variant="tonal" color="blue" @click="applyPreset('saved')" :disabled="!hasSavedPreset">
              Мой ({{ savedPresetCount }})
            </v-btn>
            <v-spacer />
            <v-btn size="x-small" variant="outlined" prepend-icon="mdi-content-save" @click="savePreset">
              Сохранить
            </v-btn>
          </div>

          <!-- Columns by group -->
          <div v-if="exportDialog.loading" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <div v-else class="px-4 py-2">
            <div v-for="group in exportColumnGroups" :key="group.name" class="mb-3">
              <div class="d-flex align-center mb-1">
                <span class="text-caption font-weight-bold text-medium-emphasis text-uppercase">{{ group.name }}</span>
                <v-btn
                  size="x-small" variant="text" class="ml-1"
                  @click="toggleGroup(group.name, true)">все</v-btn>
                <v-btn
                  size="x-small" variant="text"
                  @click="toggleGroup(group.name, false)">ни одного</v-btn>
              </div>
              <div class="d-flex flex-wrap gap-1">
                <v-checkbox
                  v-for="col in group.cols" :key="col.key"
                  v-model="exportDialog.selected"
                  :value="col.key"
                  :label="col.label"
                  density="compact"
                  hide-details
                  class="export-col-check"
                />
              </div>
            </div>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 pt-2">
          <span class="text-caption text-medium-emphasis">Выбрано: {{ exportDialog.selected.length }}</span>
          <v-spacer />
          <v-btn variant="text" @click="exportDialog.show = false">Отмена</v-btn>
          <v-btn
            color="success" variant="flat"
            prepend-icon="mdi-download"
            :loading="exportDialog.exporting"
            :disabled="exportDialog.selected.length === 0"
            @click="doExport">
            Скачать Excel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { addResizeHandles, restoreTableWidths } from '@/composables/useTableResize'
import FileDropZone from '@/components/FileDropZone.vue'

const { globalSubsidyId } = useGlobalSubsidy()

const route = useRoute()
const router = useRouter()
const userRole = localStorage.getItem('user_role') || ''
const isAdmin = ['admin', 'superadmin', 'org_admin'].includes(userRole)

interface PurchaseItem { id: number; item_name: string; item_type?: string; quantity?: number; unit?: string; unit_price?: number; total_price?: number }
interface Subsidy { id: number; name: string; year: number }
interface Purchase {
  id: number
  purchase_number?: number
  item_name?: string
  contractor_name?: string
  feo_category_name?: string
  feo_category_id?: number
  subsidy_name?: string
  subsidy_id?: number
  subject?: string
  planned_total_price?: number
  total_nmck?: number
  purchase_method?: string
  contract_price?: number
  delivery_payment_amount?: number
  status: string
  substatus?: string
  is_monthly_payment?: boolean
  delivery_date?: string
  contract_number?: string
  contract_date?: string
  acceptance_doc_name?: string
  acceptance_doc_date?: string
  acceptance_doc_number?: string
  acceptance_doc_amount?: number
  payment_doc_number?: string
  payment_doc_date?: string
  payment_amount?: number
  items?: PurchaseItem[]
  approval_status?: string
  execution_term?: string
  purchase_contract_type?: string
  registry_number?: string
}

const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])
function isItemFramework(item: Purchase) { return FRAMEWORK_TYPES.has(item.purchase_contract_type || '') }

const STATUS_ORDER = ['wishes', 'plan_schedule', 'confirmed', 'work_in_progress', 'contracted', 'delivered', 'paid']
const STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  confirmed: 'Подтверждено', work_in_progress: 'Ведётся работа',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено',
}
function statusLabelFor(item: Purchase, status?: string): string {
  const s = status || item.status
  if (s === 'contracted' && isItemFramework(item)) return 'Заказ'
  return STATUS_LABEL[s] || s
}
const STATUS_COLOR: Record<string, string> = {
  wishes: 'amber', plan_schedule: 'orange',
  confirmed: 'blue', work_in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const SUBSTATUS_LABEL: Record<string, string> = {
  tz_forming: 'Формируется ТЗ',
  kp_collecting: 'Сбор КП',
  on_platform: 'На площадке',
}
const APPROVAL_STATUS_COLOR: Record<string, string> = {
  in_progress: 'orange', approved: 'green', rejected: 'error',
}
const APPROVAL_STATUS_LABEL: Record<string, string> = {
  in_progress: 'На согласовании', approved: 'Согласовано', rejected: 'Отклонено',
}
const statusItems = STATUS_ORDER.map(v => ({ value: v, label: STATUS_LABEL[v], color: STATUS_COLOR[v] }))

function transitionRequired(item: Purchase): Record<string, { field: keyof Purchase; label: string }[]> {
  const fw = isItemFramework(item)
  return {
  contracted: [
    { field: 'contract_number', label: fw ? 'Номер заказа' : 'Номер договора' },
    { field: 'contract_date', label: fw ? 'Дата заказа' : 'Дата договора' },
  ],
  delivered: [
    { field: 'acceptance_doc_name', label: 'Наименование закрывающего документа' },
    { field: 'acceptance_doc_date', label: 'Дата закрывающего документа' },
    { field: 'acceptance_doc_number', label: 'Номер закрывающего документа' },
    { field: 'acceptance_doc_amount', label: 'Сумма закрывающего документа' },
  ],
  paid: [
    { field: 'payment_doc_number', label: 'Номер платёжного поручения' },
    { field: 'payment_doc_date', label: 'Дата платёжного поручения' },
    { field: 'payment_amount', label: 'Сумма платежа' },
  ],
}}

const headers = [
  { title: '', key: 'data-table-expand', width: 48, sortable: false },
  { title: '№', key: 'purchase_number', width: 60 },
  { title: 'Реестр. №', key: 'registry_number', width: 120 },
  { title: 'Предмет договора', key: 'subject', minWidth: 180 },
  { title: 'Контрагент', key: 'contractor_name', minWidth: 160 },
  { title: 'Субсидия', key: 'subsidy_name', minWidth: 150 },
  { title: 'Цена', key: 'effective_price', align: 'end' as const, minWidth: 120, sortable: false },
  { title: '№ договора', key: 'contract_number', minWidth: 120 },
  { title: 'Дата договора', key: 'contract_date', minWidth: 120 },
  { title: 'Статус', key: 'status', width: 130 },
  { title: 'Согласование', key: 'approval_status', width: 130, sortable: true },
  { title: 'Действия', key: 'actions', sortable: false, width: 200 },
]

// ── Link task mode (from ?link_task=ID) ──
const linkTaskId = ref<number | null>(null)

async function doLinkTask(purchaseId: number) {
  if (!linkTaskId.value) return
  try {
    await apiFetch(`/tasks/${linkTaskId.value}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId }),
    })
    const tid = linkTaskId.value
    linkTaskId.value = null
    router.replace({ path: '/my-tasks', query: { task: String(tid) } })
  } catch (e: any) {
    alert(e?.detail || 'Ошибка привязки')
  }
}

const orders = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const loading = ref(false)
const transitioning = ref<number | null>(null)
const filterStatus = ref<string>('')
const filterSubsidyId = ref<number | null>(null)
const filterFeoCategoryId = ref<number | null>(null)
const filterMethod   = ref<string>('')
const filterOverdue  = ref(false)
const filterDueSoon  = ref(false)
const filterFeoCategoryName = ref<string>('')
const search = ref('')
const expanded = ref<string[]>([])
const selectedOrders = ref<Purchase[]>([])

const snack = reactive({ show: false, text: '', color: 'success' })

// ---------------------------------------------------------------------------
// Saved filter presets
// ---------------------------------------------------------------------------
const FILTER_PRESETS_KEY = 'orders_filter_presets'
interface FilterPreset { name: string; subsidyId: number | null; status: string; search: string }

const savedFilterPresets = ref<FilterPreset[]>([])
const filterPresetDialog = reactive({ show: false, name: '' })

function loadFilterPresets() {
  try { savedFilterPresets.value = JSON.parse(localStorage.getItem(FILTER_PRESETS_KEY) || '[]') } catch {}
}
function saveFilterPreset() {
  filterPresetDialog.name = ''
  filterPresetDialog.show = true
}
function confirmSaveFilterPreset() {
  const name = filterPresetDialog.name.trim()
  if (!name) return
  const preset: FilterPreset = {
    name,
    subsidyId: filterSubsidyId.value,
    status: filterStatus.value,
    search: search.value,
  }
  const existing = savedFilterPresets.value.filter(p => p.name !== name)
  savedFilterPresets.value = [...existing, preset]
  localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(savedFilterPresets.value))
  filterPresetDialog.show = false
  showSnack('Пресет сохранён')
}
function applyFilterPreset(p: FilterPreset) {
  filterSubsidyId.value = p.subsidyId
  filterStatus.value = p.status
  search.value = p.search
}
function removeFilterPreset(name: string) {
  savedFilterPresets.value = savedFilterPresets.value.filter(p => p.name !== name)
  localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(savedFilterPresets.value))
}

const guardDialog = reactive({
  show: false, purchaseId: 0, targetStatus: '', missing: [] as string[], isFramework: false,
})
const deleteDialog = reactive({
  show: false, single: null as Purchase | null, bulk: false, deleting: false,
})

const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const formatMoney = (v?: number | null) =>
  v ? Number(v).toLocaleString('ru-RU') + ' ₽' : '—'

const effectivePrice = (item: Purchase): number | null => {
  switch (item.status) {
    case 'contracted':
      return item.contract_price ?? item.total_nmck ?? item.planned_total_price ?? null
    case 'delivered':
      return item.contract_price ?? item.total_nmck ?? item.planned_total_price ?? null
    case 'paid':
      return item.payment_amount ?? item.contract_price ?? null
    default:
      return item.total_nmck ?? item.planned_total_price ?? null
  }
}

const formatDate = (d: string) => {
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

const itemDisplayName = (p: Purchase) => {
  if (p.items && p.items.length > 0) {
    return p.items.length === 1
      ? p.items[0].item_name
      : `${p.items[0].item_name} (+${p.items.length - 1})`
  }
  return p.item_name || '—'
}

const nextStatus = (current: string): string | null => {
  const idx = STATUS_ORDER.indexOf(current)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? STATUS_ORDER[idx + 1] : null
}

const filteredOrders = computed(() => {
  let r = orders.value
  if (filterStatus.value) {
    const statuses = filterStatus.value.split(',').map(s => s.trim()).filter(Boolean)
    r = r.filter(o => statuses.includes(o.status))
  }
  if (filterSubsidyId.value) r = r.filter(o => o.subsidy_id === filterSubsidyId.value)
  if (filterFeoCategoryId.value) r = r.filter(o => o.feo_category_id === filterFeoCategoryId.value)
  if (filterMethod.value) r = r.filter(o => o.purchase_method === filterMethod.value)
  if (filterOverdue.value) {
    const today = new Date().toISOString().slice(0, 10)
    r = r.filter(o => o.execution_term && o.execution_term < today && !['paid', 'delivered'].includes(o.status))
  }
  if (filterDueSoon.value) {
    const today = new Date().toISOString().slice(0, 10)
    const in30  = new Date(Date.now() + 30 * 86400 * 1000).toISOString().slice(0, 10)
    r = r.filter(o => o.execution_term && o.execution_term >= today && o.execution_term <= in30 && !['paid', 'delivered'].includes(o.status))
  }
  return r
})

const loadOrders = async () => {
  loading.value = true
  try {
    orders.value = await apiFetch<Purchase[]>('/purchases/')
  } catch {
    showSnack('Ошибка загрузки закупок', 'error')
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => {
  try { subsidies.value = await apiFetch<Subsidy[]>('/subsidies/') } catch {}
}

const ordersTableRef = ref<any>(null)

onMounted(() => {
  loadOrders()
  loadSubsidies()
  loadFilterPresets()
  // Link task mode
  if (route.query.link_task) {
    linkTaskId.value = Number(route.query.link_task)
  }
  const qSub = route.query.subsidy_id
  if (qSub) {
    filterSubsidyId.value = Number(qSub)
    globalSubsidyId.value = Number(qSub)
  } else if (globalSubsidyId.value) {
    filterSubsidyId.value = globalSubsidyId.value
  }
  const qStatus = route.query.status
  if (qStatus && typeof qStatus === 'string') filterStatus.value = qStatus
  if (route.query.method)   filterMethod.value  = route.query.method as string
  if (route.query.overdue)  filterOverdue.value  = true
  if (route.query.due_soon) filterDueSoon.value  = true
  const qFeo = route.query.feo_category_id
  if (qFeo) {
    filterFeoCategoryId.value = Number(qFeo)
    // Find feo category name from loaded orders (or set generic label)
    filterFeoCategoryName.value = `ФЭО #${qFeo}`
    // Update name once orders load
    loadOrders().then(() => {
      const found = orders.value.find(o => o.feo_category_id === Number(qFeo))
      if (found?.feo_category_name) filterFeoCategoryName.value = found.feo_category_name
    })
  }

  // Enable column resize after table renders
  setTimeout(() => {
    const el = ordersTableRef.value?.$el?.querySelector('table') || document.querySelector('.v-data-table table')
    if (el) {
      el.setAttribute('data-resize-id', 'orders')
      addResizeHandles(el)
      restoreTableWidths(el)
    }
  }, 500)
})

// Bidirectional sync with global subsidy
watch(filterSubsidyId, (id: number | null) => { globalSubsidyId.value = id })
watch(globalSubsidyId, (id: number | null) => { filterSubsidyId.value = id })

const doTransition = async (item: Purchase) => {
  const target = nextStatus(item.status)
  if (!target) return
  const required = transitionRequired(item)[target]
  if (required) {
    const missing = required.filter(r => !item[r.field]).map(r => r.label)
    if (missing.length) {
      guardDialog.purchaseId = item.id
      guardDialog.targetStatus = target
      guardDialog.missing = missing
      guardDialog.isFramework = isItemFramework(item)
      guardDialog.show = true
      return
    }
  }
  transitioning.value = item.id
  try {
    await apiFetch(`/purchases/${item.id}/transition?status=${target}`, { method: 'POST' })
    showSnack(`Статус изменён → ${statusLabelFor(item, target)}`)
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка перехода', 'error')
  } finally {
    transitioning.value = null
  }
}

const doForceStatus = async (item: Purchase, status: string) => {
  if (item.status === status) return
  transitioning.value = item.id
  try {
    await apiFetch(`/purchases/${item.id}/transition?status=${status}`, { method: 'POST' })
    showSnack(`Статус изменён → ${statusLabelFor(item, status)}`)
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка изменения статуса', 'error')
  } finally {
    transitioning.value = null
  }
}

const confirmDeleteOne = (item: Purchase) => {
  deleteDialog.single = item
  deleteDialog.bulk = false
  deleteDialog.show = true
}

const confirmBulkDelete = () => {
  deleteDialog.single = null
  deleteDialog.bulk = true
  deleteDialog.show = true
}

const bulkChangeStatus = async (status: string) => {
  const ids = selectedOrders.value.map(o => o.id)
  let ok = 0, fail = 0
  for (const id of ids) {
    try {
      await apiFetch<any>(`/purchases/${id}/transition?status=${status}`, { method: 'POST' })
      const idx = orders.value.findIndex(o => o.id === id)
      if (idx >= 0) orders.value[idx].status = status
      ok++
    } catch { fail++ }
  }
  selectedOrders.value = []
  showSnack(`Обновлено: ${ok}${fail ? `, ошибок: ${fail}` : ''}`, fail ? 'warning' : 'success')
}

const doDelete = async () => {
  deleteDialog.deleting = true
  try {
    if (deleteDialog.bulk) {
      const ids = selectedOrders.value.map(o => o.id)
      const res = await apiFetch('/purchases/bulk', {
        method: 'DELETE',
        body: JSON.stringify(ids),
      })
      const deletedIds = new Set<number>(res.deleted)
      selectedOrders.value = selectedOrders.value.filter(o => !deletedIds.has(o.id))
      if (res.failed?.length) {
        showSnack(`Удалено: ${res.deleted.length}, не удалось: ${res.failed.length}`, 'warning')
      } else {
        showSnack(`Удалено ${res.deleted.length} закупок`, 'warning')
      }
    } else {
      await apiFetch(`/purchases/${deleteDialog.single!.id}`, { method: 'DELETE' })
      showSnack('Закупка удалена', 'warning')
    }
    deleteDialog.show = false
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

// ─── Import ───────────────────────────────────────────────────────────────────
const importDialog = reactive({
  show: false,
  step: 1,
  format: 'standard' as 'standard' | 'feo',
  subsidyId: null as number | null,
  file: null as File | null,
  loading: false,
  result: null as { created: number; skipped: number; errors: { row: number; name: string; message: string }[] } | null,
})

const resetImport = () => {
  importDialog.show = false
  importDialog.step = 1
  importDialog.format = 'standard'
  importDialog.file = null
  importDialog.subsidyId = null
  importDialog.result = null
}

const downloadTemplate = async () => {
  const token = localStorage.getItem('auth_token')
  const url = importDialog.format === 'feo'
    ? '/api/purchases/import/feo-format/template'
    : '/api/purchases/import/template'
  const filename = importDialog.format === 'feo' ? 'feo_import_template.xlsx' : 'import_template.xlsx'
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) return
  const blob = await response.blob()
  const blobUrl = window.URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = blobUrl; a.download = filename
  document.body.appendChild(a); a.click()
  window.URL.revokeObjectURL(blobUrl); document.body.removeChild(a)
}

const doImport = async () => {
  if (!importDialog.file) return
  importDialog.loading = true
  try {
    const formData = new FormData()
    formData.append('file', importDialog.file)
    const token = localStorage.getItem('auth_token')
    let endpoint: string
    if (importDialog.format === 'feo') {
      endpoint = '/api/purchases/import/feo-format'
    } else {
      const qs = importDialog.subsidyId ? `?subsidy_id=${importDialog.subsidyId}` : ''
      endpoint = `/api/purchases/import${qs}`
    }
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка импорта' }))
      showSnack(err.detail || 'Ошибка импорта', 'error')
      return
    }
    importDialog.result = await response.json()
    importDialog.step = 2
    if ((importDialog.result?.created ?? 0) > 0) await loadOrders()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    importDialog.loading = false
  }
}

// ---------------------------------------------------------------------------
// Excel export with configurable columns
// ---------------------------------------------------------------------------

interface ExportColumn { key: string; label: string; group: string }

const DEFAULT_EXPORT_KEYS = [
  'purchase_number', 'registry_number', 'item_name', 'item_type', 'unit', 'quantity',
  'nmck', 'contract_price', 'economy', 'purchase_method',
  'contract_number', 'contract_date', 'contractor',
  'execution_term', 'country_origin',
  'acceptance_doc_name', 'acceptance_doc_number', 'acceptance_doc_date', 'acceptance_doc_amount',
  'payment_doc_number', 'payment_doc_date', 'payment_amount', 'payment_federal',
  'status',
]
const SAVED_PRESET_KEY = 'export_columns_preset'

const exportDialog = reactive({
  show: false,
  loading: false,
  exporting: false,
  allColumns: [] as ExportColumn[],
  selected: [...DEFAULT_EXPORT_KEYS],
})

const exportColumnGroups = computed(() => {
  const map: Record<string, ExportColumn[]> = {}
  for (const col of exportDialog.allColumns) {
    if (!map[col.group]) map[col.group] = []
    map[col.group].push(col)
  }
  return Object.entries(map).map(([name, cols]) => ({ name, cols }))
})

const hasSavedPreset = computed(() => !!localStorage.getItem(SAVED_PRESET_KEY))
const savedPresetCount = computed(() => {
  try { return JSON.parse(localStorage.getItem(SAVED_PRESET_KEY) || '[]').length } catch { return 0 }
})

async function openExportDialog() {
  exportDialog.show = true
  if (exportDialog.allColumns.length === 0) {
    exportDialog.loading = true
    try {
      exportDialog.allColumns = await apiFetch<ExportColumn[]>('/purchases/export/columns')
    } finally {
      exportDialog.loading = false
    }
  }
}

function applyPreset(type: 'default' | 'all' | 'saved') {
  if (type === 'default') {
    exportDialog.selected = [...DEFAULT_EXPORT_KEYS]
  } else if (type === 'all') {
    exportDialog.selected = exportDialog.allColumns.map(c => c.key)
  } else {
    try {
      const saved = JSON.parse(localStorage.getItem(SAVED_PRESET_KEY) || '[]')
      if (saved.length) exportDialog.selected = saved
    } catch {}
  }
}

function savePreset() {
  localStorage.setItem(SAVED_PRESET_KEY, JSON.stringify(exportDialog.selected))
  showSnack('Пресет сохранён', 'success')
}

function toggleGroup(groupName: string, select: boolean) {
  const group = exportColumnGroups.value.find(g => g.name === groupName)
  if (!group) return
  const keys = group.cols.map(c => c.key)
  if (select) {
    exportDialog.selected = [...new Set([...exportDialog.selected, ...keys])]
  } else {
    exportDialog.selected = exportDialog.selected.filter(k => !keys.includes(k))
  }
}

async function doExport() {
  exportDialog.exporting = true
  try {
    const token = localStorage.getItem('auth_token')
    const params = new URLSearchParams()
    if (filterSubsidyId.value) params.set('subsidy_id', String(filterSubsidyId.value))
    if (filterStatus.value) params.set('status', filterStatus.value)
    params.set('columns', exportDialog.selected.join(','))
    const response = await fetch(`/api/purchases/export/excel?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error('Ошибка экспорта')
    const missing = response.headers.get('X-Missing-Columns')
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `zakupki_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    exportDialog.show = false
    if (missing) {
      showSnack(`Предупреждение: мало данных в колонках: ${missing}`, 'warning')
    }
  } catch {
    showSnack('Ошибка экспорта', 'error')
  } finally {
    exportDialog.exporting = false
  }
}
</script>

<style scoped>
.orders-clickable :deep(tbody tr) { cursor: pointer; }
.import-result-row {
  display: flex; gap: 16px; justify-content: center; margin: 16px 0;
}
.import-stat {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px 24px; border-radius: 10px; min-width: 100px;
}
.import-stat--ok   { background: rgba(34,197,94,0.1); }
.import-stat--skip { background: rgba(245,158,11,0.1); }
.import-stat--err  { background: rgba(239,68,68,0.1); }
.import-stat-val { font-size: 32px; font-weight: 700; color: var(--crm-text); }
.import-stat-lbl { font-size: 12px; color: var(--crm-text-muted); margin-top: 4px; }
.import-errors-list { max-height: 200px; overflow-y: auto; border: 1px solid var(--crm-border); border-radius: 8px; }
.fz-11 { font-size: 11px; }
.export-col-check { min-width: 180px; max-width: 220px; }
.border-b { border-bottom: 1px solid var(--crm-border-strong); }
</style>
