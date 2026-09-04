<template>
  <div class="feocat-page">

    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-folder-tree" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">Категории ФЭО</div>
          <div class="page-subtitle">Направления расходов по субсидиям</div>
        </div>
      </div>
      <div class="page-header-right">
        <v-chip-group v-if="availableYears.length" v-model="selectedYear" mandatory class="year-chips mr-3">
          <v-chip
            v-for="year in availableYears" :key="year" :value="year"
            filter variant="elevated" color="primary" size="small"
          >{{ year }}</v-chip>
        </v-chip-group>
      </div>
    </div>

    <!-- ── Loading subsidies ── -->
    <div v-if="loadingSubs" class="d-flex justify-center py-16">
      <v-progress-circular indeterminate color="primary" size="52" />
    </div>

    <template v-else>
      <!-- ── Subsidy cards grid ── -->
      <div v-if="filteredSubsidies.length === 0" class="empty-state">
        <v-icon icon="mdi-cash-off" size="64" color="grey-lighten-2" />
        <div class="text-h6 text-medium-emphasis mt-3">Нет субсидий за {{ selectedYear }} год</div>
      </div>

      <div v-else class="subsidies-grid">
        <div
          v-for="s in filteredSubsidies" :key="s.id"
          class="subsidy-card"
          :class="{ 'subsidy-card--active': selectedId === s.id }"
          @click="selectSubsidy(s.id)"
        >
          <div class="sc-header">
            <div class="sc-name">{{ s.name }}</div>
          </div>
          <div class="sc-budget">{{ formatCurrencyShort(s.budget) }}</div>
          <div class="sc-budget-label">Бюджет</div>
          <div class="sc-mini-row">
            <div class="sc-mini">
              <div class="sc-mini-label">Запланировано</div>
              <div class="sc-mini-val" style="color:var(--color-planned)">{{ formatCurrencyShort(s.planned) }}</div>
            </div>
            <div class="sc-mini">
              <div class="sc-mini-label">Оплачено</div>
              <div class="sc-mini-val" style="color:var(--color-paid)">{{ formatCurrencyShort(s.paid) }}</div>
            </div>
          </div>
          <v-progress-linear
            :model-value="pct(s.planned, s.budget)"
            :color="progressColor(pct(s.planned, s.budget))"
            height="6" rounded class="mt-3"
          />
          <div class="sc-pct">{{ pct(s.planned, s.budget) }}% запланировано</div>
        </div>
      </div>

      <!-- ── FEO panel ── -->
      <div v-if="selectedSubsidy" class="detail-panel">
        <div class="detail-header">
          <v-icon icon="mdi-folder-open-outline" size="20" color="#3B82F6" class="mr-2" />
          <span class="detail-title">{{ selectedSubsidy.name }} — категории ФЭО</span>
          <div class="d-flex align-center ml-auto gap-2">
            <v-text-field
              v-model="search"
              prepend-inner-icon="mdi-magnify"
              placeholder="Поиск..."
              variant="outlined"
              density="compact"
              hide-details
              clearable
              style="max-width:220px"
            />
            <v-btn size="small" variant="outlined" color="success" prepend-icon="mdi-file-excel-outline" @click="exportToExcel">Выгрузить</v-btn>
            <template v-if="canEditFeo">
              <v-btn size="small" variant="outlined" prepend-icon="mdi-download-outline" @click="downloadFeoTemplate">Шаблон</v-btn>
              <v-btn size="small" variant="outlined" color="secondary" prepend-icon="mdi-upload-outline" @click="feoImport.show = true">Импорт</v-btn>
              <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openAddDialog(null)">
                Добавить
              </v-btn>
            </template>
            <v-btn icon="mdi-close" size="x-small" variant="text" @click="selectedId = null" />
          </div>
        </div>

        <v-progress-linear v-if="loadingFeo" indeterminate color="primary" />

        <div v-else>
          <div v-if="flatTree.length === 0" class="feo-empty">
            <v-icon icon="mdi-folder-off" size="40" color="grey-lighten-2" />
            <div class="text-caption text-medium-emphasis mt-2">Нет категорий ФЭО</div>
          </div>

          <div v-else class="feo-table-wrap">
            <table class="feo-table">
              <thead>
                <tr>
                  <th class="feo-th feo-th-name">Наименование</th>
                  <th class="feo-th feo-th-num">Финансирование по ФЭО</th>
                  <th class="feo-th feo-th-num">Фактически запланировано</th>
                  <th class="feo-th feo-th-actions"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="node in flatTree" :key="node.id">
                  <tr
                    v-if="isVisible(node)"
                    class="feo-tr"
                    :class="[
                      `feo-tr--l${node.level}`,
                      feoDisplayedFor(node) !== null && feoPurchasedFor(node) > feoDisplayedFor(node)! ? 'feo-tr--over' : '',
                      dragOverId === node.id ? 'feo-drop-target' : '',
                      dragNodeId === node.id ? 'feo-dragging' : '',
                    ]"
                    :draggable="canEditFeo"
                    @dragstart="canEditFeo && onDragStart($event, node)"
                    @dragover.prevent="canEditFeo && onDragOver($event, node)"
                    @dragleave="onDragLeave"
                    @drop="canEditFeo && onDrop($event, node)"
                    @dragend="onDragEnd"
                  >
                    <!-- Наименование -->
                    <td class="feo-td feo-td-name" :style="{ paddingLeft: `${node.depth * 20 + 8}px` }">
                      <span class="feo-tree-chevron" @click="node.hasChildren ? toggleExpand(node.id) : undefined">
                        <v-icon
                          v-if="node.hasChildren"
                          size="15"
                          :icon="expanded.has(node.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                          color="grey"
                          class="mr-1 cursor-pointer"
                        />
                        <span v-else style="width:16px;display:inline-block" />
                      </span>
                      <v-icon
                        size="16"
                        class="mr-1 flex-shrink-0"
                        :icon="node.hasChildren ? (expanded.has(node.id) ? 'mdi-folder-open' : 'mdi-folder') : 'mdi-file-document-outline'"
                        :color="node.level === 1 ? '#3B82F6' : node.level === 2 ? '#F59E0B' : '#22C55E'"
                      />
                      <span class="feo-name" :class="`feo-name--l${node.level}`">{{ node.name }}</span>
                      <span v-if="node.code" class="feo-code ml-2">{{ node.code }}</span>
                      <span v-if="node.appendix" class="feo-appendix ml-1">{{ node.appendix }}</span>
                    </td>

                    <!-- Финансирование по ФЭО (inline edit) -->
                    <td class="feo-td feo-td-num">
                      <!-- Поле ввода -->
                      <div v-if="inlineBudgetId === node.id" class="d-flex align-center justify-end">
                        <input
                          ref="inlineInputEl"
                          v-model="inlineBudgetVal"
                          type="number"
                          class="inline-input"
                          @blur="saveInlineBudget(node)"
                          @keydown.enter="saveInlineBudget(node)"
                          @keydown.esc="inlineBudgetId = null"
                        />
                      </div>
                      <!-- Группа без ручной суммы: расчёт серым + чип, клик = задать вручную -->
                      <div v-else-if="isAutoNode(node)" class="feo-amount-cell d-flex align-center justify-end"
                        :class="{ 'feo-amount-cell--readonly': !canEditFeo }"
                        :title="canEditFeo ? 'Расчёт: ручное ФЭО дочерних, без него — факт закупок. Кликните, чтобы задать вручную' : 'Расчёт: ручное ФЭО дочерних, без него — факт закупок'"
                        @click="canEditFeo && startInlineBudget(node)"
                      >
                        <template v-if="feoEffectiveFor(node) > 0">
                          <span class="feo-amount text-medium-emphasis">{{ formatCurrency(feoEffectiveFor(node)) }}</span>
                          <v-chip size="x-small" color="blue-grey" variant="tonal" class="ml-2">расчёт</v-chip>
                        </template>
                        <span v-else-if="canEditFeo" class="feo-empty-hint">Задать</span>
                        <span v-else class="feo-empty-hint">—</span>
                      </div>
                      <!-- Ручной режим: значение или "Задать" -->
                      <div v-else class="feo-amount-cell" :class="{ 'feo-amount-cell--readonly': !canEditFeo }" @click="canEditFeo && startInlineBudget(node)">
                        <span v-if="feoBudgetFor(node) !== null" class="feo-amount">
                          {{ formatCurrency(feoBudgetFor(node)!) }}
                        </span>
                        <span v-else-if="canEditFeo" class="feo-empty-hint">Задать</span>
                        <span v-else class="feo-empty-hint">—</span>
                      </div>
                    </td>

                    <!-- Фактически запланировано -->
                    <td class="feo-td feo-td-num">
                      <span v-if="feoPurchasedFor(node) > 0" class="feo-amount"
                        :class="feoDisplayedFor(node) !== null && feoPurchasedFor(node) > feoDisplayedFor(node)! ? 'text-error' : ''"
                      >
                        {{ formatCurrency(feoPurchasedFor(node)) }}
                      </span>
                      <span v-else class="feo-empty-hint">—</span>
                    </td>

                    <!-- Действия -->
                    <td class="feo-td feo-th-actions">
                      <template v-if="canEditFeo">
                        <v-btn icon="mdi-arrow-up" variant="text" size="small" color="grey-darken-1"
                          title="Переместить вверх" @click="reorderNode(node, 'up')" />
                        <v-btn icon="mdi-arrow-down" variant="text" size="small" color="grey-darken-1"
                          title="Переместить вниз" @click="reorderNode(node, 'down')" />
                        <v-btn icon="mdi-plus-circle-outline" variant="text" size="small" color="primary"
                          title="Добавить дочернюю" @click="openAddDialog(node)" />
                        <v-btn icon="mdi-pencil-outline" variant="text" size="small" color="secondary"
                          title="Редактировать" @click="openEditDialog(node)" />
                        <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                          title="Удалить" @click="openDeleteDialog(node)" />
                      </template>
                    </td>
                  </tr>
                </template>

                <!-- Drop zone: переместить на верхний уровень -->
                <tr v-if="dragNodeId"
                  class="feo-tr feo-drop-root"
                  :class="{ 'feo-drop-target': dragOverId === -1 }"
                  @dragover.prevent="dragOverId = -1"
                  @dragleave="dragOverId = null"
                  @drop.prevent="onDropToRoot"
                >
                  <td colspan="4" class="feo-td text-center text-caption text-medium-emphasis" style="padding:12px">
                    <v-icon icon="mdi-arrow-up-bold" size="16" class="mr-1" />
                    Переместить на верхний уровень (корень)
                  </td>
                </tr>
                <!-- Итого -->
                <tr class="feo-tr feo-tr--total">
                  <td class="feo-td feo-td-name pl-4 font-weight-bold" style="padding-left:8px">ИТОГО</td>
                  <td class="feo-td feo-td-num font-weight-bold">
                    {{ totalBudget !== null ? formatCurrency(totalBudget) : '—' }}
                  </td>
                  <td class="feo-td feo-td-num font-weight-bold">{{ formatCurrency(totalPurchased) }}</td>
                  <td class="feo-td" />
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <!-- ── Диалог добавления ── -->
    <v-dialog v-model="addDialog" max-width="560" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-5 pb-2">Добавить категорию</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-form ref="addFormRef">
            <v-row dense>
              <v-col cols="12">
                <v-text-field v-model="addForm.name" label="Наименование *" variant="outlined" density="compact"
                  :rules="[r => !!r || 'Обязательное поле']" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="addForm.code" label="Код" variant="outlined" density="compact" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="addForm.appendix" label="Приложение" variant="outlined" density="compact" />
              </v-col>
              <v-col cols="12">
                <v-text-field v-model.number="addForm.budget" label="Финансирование по ФЭО (₽)"
                  variant="outlined" density="compact" type="number"
                  hint="Оставьте пустым для авто-суммы из дочерних" persistent-hint />
              </v-col>
              <v-col cols="12">
                <v-checkbox v-model="addForm.is_active" label="Активна" density="compact" hide-details />
              </v-col>
            </v-row>
          </v-form>
          <v-alert v-if="dialogError" type="error" class="mt-3" density="compact">{{ dialogError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="addDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="dialogLoading" @click="submitAdd">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог редактирования ── -->
    <v-dialog v-model="editDialog" max-width="560" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-5 pb-2">Редактировать категорию</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-form ref="editFormRef">
            <v-row dense>
              <v-col cols="12">
                <v-text-field v-model="editForm.name" label="Наименование *" variant="outlined" density="compact"
                  :rules="[r => !!r || 'Обязательное поле']" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="editForm.code" label="Код" variant="outlined" density="compact" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="editForm.appendix" label="Приложение" variant="outlined" density="compact" />
              </v-col>
              <v-col cols="12">
                <v-text-field v-model.number="editForm.budget" label="Финансирование по ФЭО (₽)"
                  variant="outlined" density="compact" type="number"
                  hint="Оставьте пустым для авто-суммы из дочерних" persistent-hint />
              </v-col>
              <v-col cols="12">
                <v-autocomplete
                  v-model="editForm.parent_id"
                  :items="parentOptions"
                  item-title="name"
                  item-value="id"
                  label="Родительская категория"
                  variant="outlined"
                  density="compact"
                  clearable
                  hint="Очистите для корневого уровня. Или перетащите в таблице."
                  persistent-hint
                />
              </v-col>
              <v-col cols="12">
                <v-checkbox v-model="editForm.is_active" label="Активна" density="compact" hide-details />
              </v-col>
            </v-row>
          </v-form>
          <v-alert v-if="dialogError" type="error" class="mt-3" density="compact">{{ dialogError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="dialogLoading" @click="submitEdit">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог удаления ── -->
    <v-dialog v-model="deleteDialog" max-width="440">
      <v-card>
        <v-card-title class="pa-5 pb-2 text-error">Удалить категорию?</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <div class="mb-2">«{{ deleteTarget?.name }}»</div>
          <v-alert v-if="deleteChildrenCount > 0" type="warning" density="compact" variant="tonal" class="mb-3">
            Будет удалено вместе с {{ deleteChildrenCount }}
            {{ deleteChildrenCount === 1 ? 'дочерней категорией' : 'дочерними категориями' }}
          </v-alert>
          <v-alert v-if="dialogError" type="error" density="compact">{{ dialogError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="dialogLoading" @click="submitDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Import FEO dialog -->
    <v-dialog v-model="feoImport.show" max-width="540" persistent :fullscreen="mobile">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Импорт категорий ФЭО из Excel</v-card-title>
        <v-card-text class="px-6">
          <template v-if="feoImport.step === 1">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls)<br>
                <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
                <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
              </div>
            </v-alert>
            <p class="text-body-2 text-medium-emphasis mb-4">
              Загрузите файл .xlsx с колонками:<br>
              <strong>Наименование</strong> (обяз.), <strong>Субсидия</strong> (обяз.),
              Родительская категория, Код, Приложение, Финансирование, Активна (да/нет).<br><br>
              Иерархия строится автоматически: укажите имя родительской категории в колонке
              «Родительская категория». Строки без родителя → уровень 1.
            </p>
            <v-file-input
              v-model="feoImport.fileList"
              label="Файл Excel (.xlsx)"
              accept=".xlsx,.xls"
              variant="outlined" density="compact"
              prepend-icon="mdi-file-excel"
              show-size
              @update:model-value="feoImport.file = $event?.[0] ?? null"
            />
          </template>
          <template v-else>
            <template v-if="feoImport.result">
              <div class="d-flex flex-wrap mb-3" style="gap:8px;">
                <v-chip size="small" color="success" variant="flat">Создано: {{ feoImport.result.created }}</v-chip>
                <v-chip size="small" color="info" variant="flat"
                  :class="{ 'cursor-pointer': feoImport.result.updated_details?.length }"
                  :disabled="!feoImport.result.updated_details?.length"
                  @click="feoImport.showUpdated = !feoImport.showUpdated">
                  Обновлено: {{ feoImport.result.updated }}
                  <v-icon v-if="feoImport.result.updated_details?.length" end size="small">{{ feoImport.showUpdated ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
                </v-chip>
                <v-chip size="small" color="warning" variant="flat"
                  :class="{ 'cursor-pointer': feoImport.result.skipped_details?.length }"
                  :disabled="!feoImport.result.skipped_details?.length"
                  @click="feoImport.showSkipped = !feoImport.showSkipped">
                  Пропущено: {{ feoImport.result.skipped }}
                  <v-icon v-if="feoImport.result.skipped_details?.length" end size="small">{{ feoImport.showSkipped ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
                </v-chip>
              </div>
              <v-expand-transition>
                <div v-if="feoImport.showUpdated && feoImport.result.updated_details?.length" class="mb-2">
                  <div class="text-subtitle-2 mb-1 text-info">Обновлено ({{ feoImport.result.updated_details.length }}):</div>
                  <v-list density="compact" class="rounded border" style="max-height:220px;overflow-y:auto;">
                    <v-list-item v-for="(u, i) in feoImport.result.updated_details" :key="'u'+i"
                      :subtitle="`Стр. ${u.row}: ${u.name} — ${u.reason}`" />
                  </v-list>
                </div>
              </v-expand-transition>
              <v-expand-transition>
                <div v-if="feoImport.showSkipped && feoImport.result.skipped_details?.length" class="mb-2">
                  <div class="text-subtitle-2 mb-1 text-warning">Пропущено ({{ feoImport.result.skipped_details.length }}):</div>
                  <v-list density="compact" class="rounded border" style="max-height:220px;overflow-y:auto;">
                    <v-list-item v-for="(s, i) in feoImport.result.skipped_details" :key="'s'+i"
                      :subtitle="`Стр. ${s.row}: ${s.name} — ${s.reason}`" />
                  </v-list>
                </div>
              </v-expand-transition>
              <div v-if="feoImport.result.errors?.length" class="mt-2">
                <div class="text-subtitle-2 mb-1 text-error">Ошибки ({{ feoImport.result.errors.length }}):</div>
                <v-list density="compact" class="bg-error-lighten-5 rounded">
                  <v-list-item v-for="e in feoImport.result.errors" :key="e.row"
                    :subtitle="`Стр. ${e.row}: ${e.name} — ${e.message}`" />
                </v-list>
              </div>
            </template>
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="closeFeoImport">{{ feoImport.step === 2 ? 'Закрыть' : 'Отмена' }}</v-btn>
          <v-btn v-if="feoImport.step === 1" color="primary" :loading="feoImport.loading"
            :disabled="!feoImport.file" @click="doFeoImport">Загрузить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive, nextTick } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { numOrNull } from '@/utils/numberFormat'

const { mobile } = useDisplay()
const authStore = useAuthStore()
// B5: право на запись в дерево ФЭО (backend-гейт — feo_category.edit, см.
// backend/app/routers/feo_categories.py). Экспорт/просмотр остаются доступны
// без этого права — прячем только create/edit/delete/import/reorder/drag,
// а не саму вкладку (require_tab('feo_categories') отдельный, читающий).
const canEditFeo = computed(() => authStore.hasAction('feo_category.edit'))

interface SubsidyRow {
  id: number; name: string; year: number
  budget: number; planned: number; paid: number; contracted: number
}

interface FeoCategory {
  id: number; name: string; level: number
  code?: string | null; appendix?: string | null
  subsidy_id: number; parent_id?: number | null
  is_active: boolean; budget?: number | null
}

interface FeoNode extends FeoCategory {
  depth: number; hasChildren: boolean; children: FeoNode[]
}

// ─── State ───────────────────────────────────────────────────────────────────
const allSubsidies = ref<SubsidyRow[]>([])
const loadingSubs  = ref(false)
const selectedId   = ref<number | null>(null)
const selectedYear = ref<number | null>(null)

const categories     = ref<FeoCategory[]>([])
const purchaseTotals = ref<Record<number, number>>({})
const loadingFeo     = ref(false)
const search         = ref('')
const expanded       = ref<Set<number>>(new Set())

const inlineBudgetId  = ref<number | null>(null)
const inlineBudgetVal = ref('')
const inlineInputEl   = ref<HTMLInputElement | null>(null)

const toast       = useToast()
const dialogError = ref('')
const dialogLoading = ref(false)

const addDialog  = ref(false)
const addFormRef = ref()
const addForm    = reactive({ name: '', code: '', appendix: '', budget: null as number | null, is_active: true, parent_id: null as number | null })

const editDialog  = ref(false)
const editFormRef = ref()
const editTarget  = ref<FeoNode | null>(null)
const editForm    = reactive({ name: '', code: '', appendix: '', budget: null as number | null, is_active: true, parent_id: null as number | null })

const deleteDialog = ref(false)
const deleteTarget = ref<FeoNode | null>(null)

// Drag & Drop state
const dragNodeId = ref<number | null>(null)
const dragOverId = ref<number | null>(null)

// ─── Subsidies ───────────────────────────────────────────────────────────────
const availableYears = computed(() => [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a))

const filteredSubsidies = computed(() =>
  selectedYear.value ? allSubsidies.value.filter(s => s.year === selectedYear.value) : allSubsidies.value
)

const selectedSubsidy = computed(() =>
  allSubsidies.value.find(s => s.id === selectedId.value) ?? null
)

const loadSubsidies = async () => {
  loadingSubs.value = true
  try {
    // Используем dashboard/charts как SubsidiesView — там есть planned/paid/contracted
    const charts = await apiFetch<any>('/dashboard/charts')
    allSubsidies.value = charts.subsidy_stats.map((s: any) => ({
      id: s.id, name: s.name, year: s.year, budget: s.budget,
      planned: s.total_planned ?? 0, paid: s.total_paid ?? 0, contracted: s.total_confirmed ?? 0,
    }))
    if (availableYears.value.length) selectedYear.value = availableYears.value[0]
  } finally {
    loadingSubs.value = false
  }
}

const selectSubsidy = (id: number) => {
  selectedId.value = selectedId.value === id ? null : id
}

watch(selectedId, id => {
  categories.value = []
  purchaseTotals.value = {}
  search.value = ''
  if (id) loadFeo(id)
})

// ─── FEO load ─────────────────────────────────────────────────────────────────
const loadFeo = async (subsidyId: number) => {
  loadingFeo.value = true
  try {
    const [cats, totals] = await Promise.all([
      apiFetch<FeoCategory[]>(`/feo-categories/?subsidy_id=${subsidyId}`),
      apiFetch<Record<number, number>>(`/feo-categories/purchase-totals?subsidy_id=${subsidyId}`),
    ])
    categories.value = cats
    purchaseTotals.value = totals
    // Авто-раскрыть уровень 1
    expanded.value = new Set(cats.filter(c => c.level === 1).map(c => c.id))
  } finally {
    loadingFeo.value = false
  }
}

// ─── Tree ────────────────────────────────────────────────────────────────────
const rootNodes = computed((): FeoNode[] => {
  const byId = new Map<number, FeoNode>()
  for (const c of categories.value)
    byId.set(c.id, { ...c, depth: 0, hasChildren: false, children: [] })
  const roots: FeoNode[] = []
  for (const c of categories.value) {
    const node = byId.get(c.id)!
    if (c.parent_id && byId.has(c.parent_id)) {
      const p = byId.get(c.parent_id)!
      p.children.push(node); p.hasChildren = true
    } else roots.push(node)
  }
  const setDepth = (nodes: FeoNode[], d: number) => nodes.forEach(n => { n.depth = d; setDepth(n.children, d + 1) })
  setDepth(roots, 0)
  return roots
})

const flatTree = computed((): FeoNode[] => {
  const q = search.value.toLowerCase()
  const flatten = (nodes: FeoNode[]): FeoNode[] => nodes.flatMap(n => [n, ...flatten(n.children)])
  if (!q) return flatten(rootNodes.value)
  return flatten(rootNodes.value).filter(n =>
    n.name.toLowerCase().includes(q) || (n.code ?? '').toLowerCase().includes(q)
  )
})

const isVisible = (node: FeoNode): boolean => {
  if (search.value) return true
  if (!node.parent_id) return true
  const checkParent = (pid: number): boolean => {
    if (!expanded.value.has(pid)) return false
    const p = categories.value.find(c => c.id === pid)
    return !p?.parent_id || checkParent(p.parent_id)
  }
  return checkParent(node.parent_id)
}

const toggleExpand = (id: number) => {
  const s = new Set(expanded.value)
  s.has(id) ? s.delete(id) : s.add(id)
  expanded.value = s
}

// ─── Budget calc ──────────────────────────────────────────────────────────────
// Решение 14.07: финансирование по ФЭО — ТОЛЬКО ручное значение узла (без авто-суммы)
const feoBudgetFor = (node: FeoNode): number | null => node.budget ?? null

// Расчётная справка: ручное ФЭО, если задано; иначе факт закупок; группа — Σ по детям
const feoEffectiveFor = (node: FeoNode): number => {
  if (node.budget != null) return Number(node.budget)
  if (!node.hasChildren) return purchaseTotals.value[node.id] ?? 0
  return node.children.reduce((acc, c) => acc + feoEffectiveFor(c), 0)
}

// Группа без ручной суммы — показываем расчёт серым (редактирование доступно)
const isAutoNode = (node: FeoNode): boolean => node.hasChildren && node.budget == null

// Отображаемое ФЭО: ручное, для групп без ручного — расчёт (для сравнений с фактом)
const feoDisplayedFor = (node: FeoNode): number | null => {
  if (node.budget != null) return Number(node.budget)
  return node.hasChildren ? feoEffectiveFor(node) : null
}

const feoPurchasedFor = (node: FeoNode): number => {
  if (!node.hasChildren) return purchaseTotals.value[node.id] ?? 0
  return node.children.reduce((acc, c) => acc + feoPurchasedFor(c), 0)
}

const totalBudget = computed(() => {
  const sum = rootNodes.value.reduce((a, r) => a + feoEffectiveFor(r), 0)
  return sum > 0 ? sum : null
})
const totalPurchased = computed(() => rootNodes.value.reduce((a, r) => a + feoPurchasedFor(r), 0))

// ─── Inline budget edit ───────────────────────────────────────────────────────
const startInlineBudget = async (node: FeoNode) => {
  inlineBudgetId.value = node.id
  inlineBudgetVal.value = node.budget != null ? String(node.budget) : ''
  await nextTick(); inlineInputEl.value?.focus()
}

const saveInlineBudget = async (node: FeoNode) => {
  if (inlineBudgetId.value !== node.id) return
  inlineBudgetId.value = null
  const val = inlineBudgetVal.value.trim() === '' ? null : parseFloat(inlineBudgetVal.value)
  try {
    await apiFetch(`/feo-categories/${node.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: node.name, code: node.code ?? null, appendix: node.appendix ?? null,
        is_active: node.is_active, budget: val, subsidy_id: node.subsidy_id }),
    })
    const cat = categories.value.find(c => c.id === node.id)
    if (cat) cat.budget = val
    categories.value = [...categories.value]
  } catch (e: any) { showSnack(e.detail || 'Ошибка сохранения', 'error') }
}

// ─── Dialogs ──────────────────────────────────────────────────────────────────
const openAddDialog = (parent: FeoNode | null) => {
  addForm.name = ''; addForm.code = ''; addForm.appendix = ''
  addForm.budget = null; addForm.is_active = true; addForm.parent_id = parent?.id ?? null
  dialogError.value = ''; addDialog.value = true
}

const submitAdd = async () => {
  const { valid } = await addFormRef.value.validate()
  if (!valid) return
  dialogLoading.value = true; dialogError.value = ''
  try {
    await apiFetch('/feo-categories/', {
      method: 'POST',
      body: JSON.stringify({ name: addForm.name, code: addForm.code || null,
        // budget — v-model.number: `?? null` не ловит '' после очистки поля (backend
        // страхует пустую строку в FeoCategoryCreate, но фронт должен слать null сам —
        // см. комментарий там же). numOrNull: '' → null, 0 сохраняется как число.
        appendix: addForm.appendix || null, budget: numOrNull(addForm.budget),
        is_active: addForm.is_active, subsidy_id: selectedId.value, parent_id: addForm.parent_id }),
    })
    addDialog.value = false; showSnack('Категория добавлена')
    await loadFeo(selectedId.value!)
  } catch (e: any) { dialogError.value = e.detail || 'Ошибка' }
  finally { dialogLoading.value = false }
}

const openEditDialog = (node: FeoNode) => {
  editTarget.value = node
  editForm.name = node.name; editForm.code = node.code ?? ''
  editForm.appendix = node.appendix ?? ''; editForm.budget = node.budget ?? null
  editForm.is_active = node.is_active; editForm.parent_id = node.parent_id ?? null
  dialogError.value = ''; editDialog.value = true
}

const submitEdit = async () => {
  const { valid } = await editFormRef.value.validate()
  if (!valid || !editTarget.value) return
  dialogLoading.value = true; dialogError.value = ''
  try {
    // Если parent_id изменился — вызываем move endpoint
    const oldParentId = editTarget.value.parent_id ?? null
    const newParentId = editForm.parent_id ?? null
    if (oldParentId !== newParentId) {
      const res = await apiFetch<any>(`/feo-categories/${editTarget.value.id}/move`, {
        method: 'PATCH',
        body: JSON.stringify({ parent_id: newParentId }),
      })
      if (res?.warning) showSnack(res.warning, 'warning')
    }
    // Обновляем остальные поля
    await apiFetch(`/feo-categories/${editTarget.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: editForm.name, code: editForm.code || null,
        appendix: editForm.appendix || null, budget: numOrNull(editForm.budget),
        is_active: editForm.is_active, subsidy_id: selectedId.value }),
    })
    editDialog.value = false; showSnack('Сохранено')
    await loadFeo(selectedId.value!)
  } catch (e: any) { dialogError.value = e.detail || 'Ошибка' }
  finally { dialogLoading.value = false }
}

const openDeleteDialog = (node: FeoNode) => {
  deleteTarget.value = node; dialogError.value = ''; deleteDialog.value = true
}

const submitDelete = async () => {
  if (!deleteTarget.value) return
  dialogLoading.value = true; dialogError.value = ''
  try {
    await apiFetch(`/feo-categories/${deleteTarget.value.id}`, { method: 'DELETE' })
    deleteDialog.value = false; showSnack('Удалено')
    await loadFeo(selectedId.value!)
  } catch (e: any) { dialogError.value = e.detail || 'Ошибка удаления' }
  finally { dialogLoading.value = false }
}

const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

// ─── Drag & Drop ──────────────────────────────────────────────────────────────
function collectSubtreeIds(nodeId: number): number[] {
  const ids = [nodeId]
  const find = (pid: number) => {
    for (const c of categories.value) {
      if (c.parent_id === pid) { ids.push(c.id); find(c.id) }
    }
  }
  find(nodeId)
  return ids
}

function onDragStart(e: DragEvent, node: FeoNode) {
  dragNodeId.value = node.id
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', String(node.id))
}

function onDragOver(e: DragEvent, node: FeoNode) {
  if (!dragNodeId.value || dragNodeId.value === node.id) return
  // Нельзя перетащить в собственное поддерево
  const subtree = collectSubtreeIds(dragNodeId.value)
  if (subtree.includes(node.id)) return
  dragOverId.value = node.id
}

function onDragLeave() {
  dragOverId.value = null
}

async function onDrop(e: DragEvent, targetNode: FeoNode) {
  e.preventDefault()
  if (!dragNodeId.value || dragNodeId.value === targetNode.id) return
  const srcId = dragNodeId.value
  const srcNode = flatTree.value.find(n => n.id === srcId)
  dragOverId.value = null; dragNodeId.value = null
  if (!srcNode) return

  // Нельзя в собственное поддерево
  const subtree = collectSubtreeIds(srcId)
  if (subtree.includes(targetNode.id)) {
    showSnack('Нельзя переместить в собственное поддерево', 'error')
    return
  }

  // Если уже является дочерней этого узла — пропускаем
  if (srcNode.parent_id === targetNode.id) return

  try {
    const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ parent_id: targetNode.id }),
    })
    showSnack('Категория перемещена')
    if (res?.warning) showSnack(res.warning, 'warning')
    await loadFeo(selectedId.value!)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка перемещения', 'error')
  }
}

async function onDropToRoot(e: DragEvent) {
  e.preventDefault()
  if (!dragNodeId.value) return
  const srcId = dragNodeId.value
  const srcNode = flatTree.value.find(n => n.id === srcId)
  dragOverId.value = null; dragNodeId.value = null
  if (!srcNode || !srcNode.parent_id) return  // уже корневая

  try {
    const res = await apiFetch<any>(`/feo-categories/${srcId}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ parent_id: null }),
    })
    showSnack('Категория перемещена на верхний уровень')
    if (res?.warning) showSnack(res.warning, 'warning')
    await loadFeo(selectedId.value!)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка перемещения', 'error')
  }
}

function onDragEnd() {
  dragNodeId.value = null; dragOverId.value = null
}

async function reorderNode(node: FeoNode, direction: 'up' | 'down') {
  try {
    const res = await apiFetch<any>(`/feo-categories/${node.id}/reorder`, {
      method: 'PATCH',
      body: JSON.stringify({ direction }),
    })
    if (res?.moved === false) return
    await loadFeo(selectedId.value!)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка перемещения', 'error')
  }
}

// ─── Parent options for edit dialog ───────────────────────────────────────────
const parentOptions = computed(() => {
  if (!editTarget.value) return []
  const excludeIds = new Set(collectSubtreeIds(editTarget.value.id))
  return categories.value
    .filter(c => !excludeIds.has(c.id))
    .map(c => ({ id: c.id, name: '  '.repeat(c.level - 1) + c.name }))
})

// ─── Delete children count ───────────────────────────────────────────────────
const deleteChildrenCount = computed(() => {
  if (!deleteTarget.value) return 0
  return collectSubtreeIds(deleteTarget.value.id).length - 1
})

// ─── FEO Import ───────────────────────────────────────────────────────────────
const feoImport = reactive({
  show: false, step: 1, file: null as File | null, fileList: [] as File[],
  loading: false, showUpdated: false, showSkipped: false,
  result: null as {
    created: number; updated: number; skipped: number;
    errors: { row: number; name: string; message: string }[];
    updated_details?: { row: number; name: string; reason: string }[];
    skipped_details?: { row: number; name: string; reason: string }[];
  } | null,
})

function closeFeoImport() {
  const wasCreated = (feoImport.result?.created ?? 0) > 0
  feoImport.show = false; feoImport.step = 1
  feoImport.file = null; feoImport.fileList = []; feoImport.result = null
  feoImport.showUpdated = false; feoImport.showSkipped = false
  if (wasCreated && selectedId.value) loadFeo(selectedId.value)
}

async function exportToExcel() {
  if (!selectedId.value) return
  const token = localStorage.getItem('auth_token')
  const res = await fetch(`/api/feo-categories/export?subsidy_id=${selectedId.value}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка экспорта', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const cd = res.headers.get('Content-Disposition') || ''
  const star = cd.match(/filename\*\s*=\s*UTF-8''([^;\n]+)/i)
  const plain = cd.match(/filename\s*=\s*(?:"([^"]+)"|([^;\n]+))/i)
  let name = 'ФЭО_выгрузка.xlsx'
  if (star) name = decodeURIComponent(star[1].trim())
  else if (plain) name = (plain[1] ?? plain[2] ?? name).trim()
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

async function downloadFeoTemplate() {
  const token = localStorage.getItem('auth_token')
  const res = await fetch('/api/feo-categories/import/template', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'Шаблон_импорта_направлений_ФЭО.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function doFeoImport() {
  if (!feoImport.file) return
  feoImport.loading = true
  try {
    const fd = new FormData()
    fd.append('file', feoImport.file)
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/feo-categories/import', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      showSnack(err.detail || 'Ошибка импорта', 'error'); return
    }
    feoImport.result = await res.json()
    feoImport.step = 2
    showSnack(`Импорт завершён: создано ${feoImport.result!.created}`)
  } catch {
    showSnack('Ошибка импорта', 'error')
  } finally {
    feoImport.loading = false
  }
}

// ─── Formatting ───────────────────────────────────────────────────────────────
const formatCurrency = (v: number) => v.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + ' ₽'
const formatCurrencyShort = (v: number) => {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1).replace('.', ',') + ' млн ₽'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}
const pct = (a: number, b: number) => b > 0 ? Math.round((a / b) * 100) : 0
const progressColor = (p: number) => p >= 100 ? '#EF4444' : p >= 80 ? '#F59E0B' : '#22C55E'

loadSubsidies()
</script>

<style scoped>
.feocat-page {
  padding: 20px 24px;
  max-width: 1600px;
}

/* ── Header ── */
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 24px; flex-wrap: wrap; gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Empty state ── */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 64px 0; color: var(--crm-text-faint);
}

/* ── Subsidy cards ── */
.subsidies-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.subsidy-card {
  background: var(--crm-surface); border-radius: 12px; border: 2px solid transparent;
  box-shadow: 0 1px 4px var(--crm-shadow); padding: 18px 20px;
  cursor: pointer; transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
}
.subsidy-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px var(--crm-shadow-hover); }
.subsidy-card--active {
  border-color: #3B82F6;
  box-shadow: 0 0 0 4px rgba(59,130,246,0.12), 0 4px 16px var(--crm-shadow-hover);
}
.sc-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 8px; }
.sc-name { font-size: 14px; font-weight: 700; color: var(--crm-text); line-height: 1.3; word-break: break-word; }
.sc-budget       { font-size: 22px; font-weight: 700; color: var(--crm-text); }
.sc-budget-label { font-size: 11px; color: var(--crm-text-faint); margin-bottom: 12px; }
.sc-mini-row  { display: flex; gap: 20px; }
.sc-mini-label{ font-size: 11px; color: var(--crm-text-faint); margin-bottom: 2px; }
.sc-mini-val  { font-size: 13px; font-weight: 600; }
.sc-pct { font-size: 11px; color: var(--crm-text-faint); margin-top: 4px; }

/* ── Detail panel ── */
.detail-panel {
  background: var(--crm-surface); border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  overflow: hidden; margin-bottom: 20px;
}
.detail-header {
  display: flex; align-items: center; padding: 14px 16px;
  border-bottom: 1px solid var(--crm-border);
  background: var(--crm-surface-alt); flex-wrap: wrap; gap: 8px;
}
.detail-title { font-size: 14px; font-weight: 600; color: var(--crm-text-secondary); }

/* ── FEO table ── */
.feo-table-wrap { overflow-x: hidden; }
.feo-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; table-layout: fixed; }
.feo-th {
  padding: 10px 12px; text-align: left; font-weight: 600;
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--crm-text-muted); border-bottom: 2px solid var(--crm-border);
  background: var(--crm-table-header);
}
.feo-th-name    { width: auto; }
.feo-th-num     { width: 160px; text-align: right; }
.feo-th-actions { width: 100px; white-space: nowrap; }
.feo-td { padding: 7px 12px; border-bottom: 1px solid var(--crm-border); vertical-align: top; }
.feo-td-name { display: flex; align-items: flex-start; min-width: 0; }
.feo-name { white-space: normal; word-break: break-word; line-height: 1.4; min-width: 0; flex: 1; }
.feo-td-num  { text-align: right; }
.feo-tr:hover { background: var(--crm-surface-alt); }
.feo-tr--over { background: rgba(244,67,54,0.08) !important; }
.feo-tr--over:hover { background: rgba(244,67,54,0.13) !important; }
.feo-tr--total { background: var(--crm-surface-alt); border-top: 2px solid var(--crm-border-strong); }
.feo-tr--l1 .feo-name { font-weight: 700; font-size: 0.9rem; }
.feo-tr--l2 .feo-name { font-weight: 600; }
.feo-name  { color: var(--crm-text); }
.feo-code  { font-size: 11px; color: var(--crm-text-muted); background: var(--crm-input-bg); padding: 1px 5px; border-radius: 4px; }
.feo-appendix { font-size: 11px; color: var(--crm-text-faint); }
.feo-amount { color: var(--crm-text); font-weight: 500; }
.feo-empty-hint { font-size: 12px; color: var(--crm-text-faint); cursor: pointer; }
.feo-empty-hint:hover { color: #3B82F6; }
.feo-amount-cell { cursor: pointer; padding: 2px 4px; border-radius: 4px; display: inline-flex; align-items: center; }
.feo-amount-cell:hover { background: rgba(59,130,246,0.07); }
.feo-amount-cell--readonly { cursor: default; }
.feo-amount-cell--readonly:hover { background: none; }
.feo-tree-chevron { display: inline-flex; align-items: center; flex-shrink: 0; }
.feo-empty { display: flex; flex-direction: column; align-items: center; padding: 40px 0; }

.inline-input {
  border: 1px solid rgba(59,130,246,0.7); border-radius: 4px;
  padding: 2px 6px; width: 120px; text-align: right;
  font-size: 0.875rem; outline: none; background: var(--crm-surface);
}
.gap-2 { gap: 8px; }

/* ── Drag & Drop ── */
.feo-tr[draggable="true"] { cursor: grab; }
.feo-tr[draggable="true"]:active { cursor: grabbing; }
.feo-dragging { opacity: 0.45; background: var(--crm-surface-alt) !important; }
.feo-drop-target {
  background: rgba(59, 130, 246, 0.12) !important;
  outline: 2px dashed rgba(59, 130, 246, 0.6);
  outline-offset: -2px;
}
.feo-drop-root {
  border-top: 2px dashed var(--crm-border);
  transition: background 0.15s;
}
.feo-drop-root.feo-drop-target {
  background: rgba(59, 130, 246, 0.08) !important;
}
</style>
