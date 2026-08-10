<template>
  <div class="contractors-page">

    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-account-group" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">Контрагенты</div>
          <div class="page-subtitle">Список поставщиков и исполнителей</div>
        </div>
      </div>
      <div class="page-header-right">
        <v-btn
          variant="tonal"
          color="secondary"
          prepend-icon="mdi-download"
          class="mr-2"
          @click="downloadTemplate"
        >
          Шаблон
        </v-btn>
        <v-btn
          variant="tonal"
          color="success"
          prepend-icon="mdi-file-import-outline"
          class="mr-2"
          @click="contractorImportDialog = true; contractorImportStep = 1"
        >
          Импорт из файла
        </v-btn>
        <v-btn v-if="isOwnerPlus" variant="tonal" color="blue" prepend-icon="mdi-database-refresh"
          class="mr-2" :loading="enrichAllLoading" @click="enrichAllFromFns">
          Обновить из ЕГРЮЛ
        </v-btn>
        <v-btn variant="outlined" color="warning" prepend-icon="mdi-content-duplicate"
               class="mr-2" @click="openDuplicatesDialog">
          Найти дубли по ИНН
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openAdd">
          Добавить контрагента
        </v-btn>
      </div>
    </div>

    <!-- ── Filters ── -->
    <div class="filters-bar mb-4">
      <v-text-field
        v-model="search"
        prepend-inner-icon="mdi-magnify"
        label="Поиск по названию или ИНН"
        variant="outlined"
        density="compact"
        hide-details
        style="max-width: 320px"
        clearable
        @input="onSearchInput"
        @click:clear="search = ''; onSearchInput()"
      />
      <v-autocomplete
        v-model="filterCategory"
        :items="allProductCategories"
        label="Категория товаров"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 260px"
      />
      <v-btn
        v-if="filterCategory || search"
        variant="text"
        size="small"
        color="grey"
        @click="clearFilters"
      >Сбросить</v-btn>
      <span class="search-count">{{ filtered.length }} из {{ contractorsTotal }}</span>
      <v-btn-toggle
        v-if="!mobile"
        v-model="viewMode"
        mandatory
        density="compact"
        variant="outlined"
        divided
        class="ml-1"
      >
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
    </div>

    <v-alert v-if="enrichAllResult" type="info" variant="tonal" density="compact" class="mb-4" closable @click:close="enrichAllResult = null">
      Обновлено: {{ enrichAllResult.updated }} из {{ enrichAllResult.total }}.
      Пропущено (уже заполнены): {{ enrichAllResult.skipped }}.
      <span v-if="enrichAllResult.errors.length"> Ошибок: {{ enrichAllResult.errors.length }}.</span>
    </v-alert>

    <!-- ── Bulk actions ── -->
    <div v-if="selectedIds.size > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedIds.size }}</span>
      <v-spacer />
      <v-btn color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDelete">
        Удалить выбранных
      </v-btn>
      <v-btn variant="text" size="small" @click="selectedIds = new Set()">Снять выделение</v-btn>
    </div>

    <!-- ── Loading ── -->
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <!-- ── Table ── -->
    <div v-if="effectiveView === 'table'" class="table-card">
      <v-table class="contractors-table">
        <thead>
          <tr>
            <th style="width:48px">
              <v-checkbox
                :model-value="filtered.length > 0 && selectedIds.size === filtered.length"
                :indeterminate="selectedIds.size > 0 && selectedIds.size < filtered.length"
                density="compact"
                hide-details
                @update:model-value="toggleAll"
              />
            </th>
            <th>Наименование</th>
            <th>ИНН</th>
            <th>КПП</th>
            <th>Адрес</th>
            <th>Телефон / Email</th>
            <th>Контактное лицо</th>
            <th style="min-width:160px">Категории товаров</th>
            <th class="text-right">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!loading && filtered.length === 0">
            <td colspan="9" class="text-center py-10 text-medium-emphasis">
              <v-icon icon="mdi-account-off-outline" size="40" color="grey-lighten-2" class="d-block mx-auto mb-2" />
              Контрагенты не найдены
            </td>
          </tr>
          <tr v-for="c in filtered" :key="c.id" class="contractor-row" :class="{ 'contractor-row--selected': selectedIds.has(c.id) }" style="cursor:pointer" @click="openEdit(c)">
            <td @click.stop>
              <v-checkbox
                :model-value="selectedIds.has(c.id)"
                density="compact"
                hide-details
                @update:model-value="toggleOne(c.id)"
              />
            </td>
            <td class="font-weight-medium">{{ c.name }}</td>
            <td class="text-mono">{{ c.inn || '—' }}</td>
            <td class="text-mono">{{ c.kpp || '—' }}</td>
            <td class="text-sm">{{ c.address || '—' }}</td>
            <td>
              <div class="text-sm">{{ formatPhoneRu(c.phone) || '—' }}</div>
              <div class="text-caption text-medium-emphasis">{{ c.email || '' }}</div>
            </td>
            <td class="text-sm">{{ c.contact_person || '—' }}</td>
            <td>
              <template v-if="c.product_categories.length > 0">
                <v-chip
                  v-if="c.product_categories.includes('Все')"
                  size="x-small"
                  color="blue"
                  variant="tonal"
                  class="mr-1 mb-1"
                >Все категории</v-chip>
                <template v-else>
                  <v-chip
                    v-for="cat in c.product_categories.slice(0, 2)"
                    :key="cat"
                    size="x-small"
                    color="teal"
                    variant="tonal"
                    class="mr-1 mb-1"
                  >{{ cat }}</v-chip>
                  <v-chip
                    v-if="c.product_categories.length > 2"
                    size="x-small"
                    color="grey"
                    variant="tonal"
                    class="cursor-pointer"
                    @click="openCategoriesDialog(c)"
                  >+{{ c.product_categories.length - 2 }}</v-chip>
                </template>
              </template>
              <span v-else class="text-medium-emphasis text-caption">—</span>
            </td>
            <td class="text-right" @click.stop>
              <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click.stop="confirmDelete(c)" />
            </td>
          </tr>
        </tbody>
      </v-table>
      <!-- Pagination -->
      <div v-if="totalPages > 1" class="d-flex justify-center align-center pa-3 gap-2">
        <v-btn icon="mdi-chevron-left" variant="text" size="small" :disabled="contractorsPage <= 1" @click="goPage(contractorsPage - 1)" />
        <span class="text-body-2">Стр. {{ contractorsPage }} из {{ totalPages }}</span>
        <v-btn icon="mdi-chevron-right" variant="text" size="small" :disabled="contractorsPage >= totalPages" @click="goPage(contractorsPage + 1)" />
      </div>
    </div>

    <!-- ── Cards view ── -->
    <div v-else>
      <v-row dense>
        <v-col v-for="c in pagedCards" :key="c.id" cols="12" sm="6" lg="4">
          <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="openEdit(c)">
            <v-card-item class="pb-1">
              <template #prepend>
                <v-checkbox-btn
                  :model-value="selectedIds.has(c.id)"
                  density="compact"
                  @click.stop
                  @update:model-value="toggleOne(c.id)"
                />
              </template>
              <v-card-title class="text-body-2 font-weight-bold" style="overflow-wrap:anywhere">
                {{ c.name }}
              </v-card-title>
            </v-card-item>
            <v-card-text class="py-1 flex-grow-1">
              <div class="d-flex gap-2 mb-2 flex-wrap">
                <span v-if="c.inn" class="text-caption text-medium-emphasis">ИНН: <span class="text-mono font-weight-medium text-body-2">{{ c.inn }}</span></span>
                <span v-if="c.kpp" class="text-caption text-medium-emphasis">КПП: <span class="text-mono font-weight-medium text-body-2">{{ c.kpp }}</span></span>
              </div>
              <div v-if="c.address" class="text-caption text-medium-emphasis mb-1">{{ c.address }}</div>
              <div v-if="c.contact_person" class="text-caption mb-1">{{ c.contact_person }}</div>
              <div v-if="c.phone || c.email" class="text-caption text-medium-emphasis">
                <span v-if="c.phone">{{ formatPhoneRu(c.phone) }}</span>
                <span v-if="c.phone && c.email"> · </span>
                <span v-if="c.email">{{ c.email }}</span>
              </div>
              <div v-if="c.product_categories.length > 0" class="d-flex flex-wrap gap-1 mt-2">
                <v-chip v-if="c.product_categories.includes('Все')" size="x-small" color="blue" variant="tonal">Все категории</v-chip>
                <template v-else>
                  <v-chip v-for="cat in c.product_categories.slice(0, 2)" :key="cat" size="x-small" color="teal" variant="tonal">{{ cat }}</v-chip>
                  <v-chip
                    v-if="c.product_categories.length > 2"
                    size="x-small" color="grey" variant="tonal"
                    class="cursor-pointer"
                    @click.stop="openCategoriesDialog(c)"
                  >+{{ c.product_categories.length - 2 }}</v-chip>
                </template>
              </div>
            </v-card-text>
            <v-divider />
            <v-card-actions class="py-1" @click.stop>
              <v-spacer />
              <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click.stop="confirmDelete(c)" />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!pagedCards.length" class="text-center py-10 text-medium-emphasis">
        <v-icon icon="mdi-account-off-outline" size="48" color="grey-lighten-1" class="d-block mx-auto mb-3" />
        Контрагенты не найдены
      </div>
      <v-pagination
        v-if="cardsTotalPages > 1"
        v-model="cardsPage"
        :length="cardsTotalPages"
        density="compact"
        total-visible="7"
        class="d-flex justify-center mt-4"
      />
    </div>

    <!-- ── Categories dialog ── -->
    <v-dialog v-model="categoriesDialog" max-width="480" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-tag-multiple-outline" color="teal" class="mr-2" />
          Категории товаров: {{ categoriesDialogContractor?.name }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="categoriesDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-chip
            v-for="cat in categoriesDialogContractor?.product_categories ?? []"
            :key="cat"
            color="teal"
            variant="tonal"
            class="mr-2 mb-2"
          >{{ cat }}</v-chip>
          <div v-if="!categoriesDialogContractor?.product_categories?.length" class="text-center text-medium-emphasis pa-4">
            Категории не указаны (нет закупок с товарами из каталога)
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- ── Add / Edit Dialog (reusable component) ── -->
    <ContractorEditDialog v-model="dialog" :contractor-id="editId" @saved="onContractorSaved" />


    <!-- ── Bulk delete confirm ── -->
    <v-dialog v-model="bulkDeleteDialog" max-width="440" persistent>
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить контрагентов?
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <p class="mb-3">
            Вы собираетесь удалить <strong>{{ selectedIds.size }}</strong> контрагентов.
            Это действие <strong>нельзя отменить</strong>.
          </p>
          <p v-if="selectedIds.size > 5" class="text-caption text-medium-emphasis mb-3">
            Для подтверждения введите количество удаляемых записей:
          </p>
          <v-text-field
            v-if="selectedIds.size > 5"
            v-model="bulkDeleteConfirmCount"
            :placeholder="`Введите ${selectedIds.size}`"
            variant="outlined"
            density="compact"
            hide-details
            autofocus
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="bulkDeleteDialog = false; bulkDeleteConfirmCount = ''">Отмена</v-btn>
          <v-btn
            color="error"
            :loading="saving"
            :disabled="selectedIds.size > 5 && bulkDeleteConfirmCount !== String(selectedIds.size)"
            @click="doBulkDelete"
          >Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Delete confirm ── -->
    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить контрагента?
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          Удалить <strong>{{ deleteTarget?.name }}</strong>? Действие нельзя отменить.
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="saving" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Contractor Import Dialog ── -->
    <v-dialog v-model="contractorImportDialog" max-width="1000" persistent scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <span>Импорт контрагентов — шаг {{ contractorImportStep }} из 2</span>
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="closeContractorImport" />
        </v-card-title>
        <v-divider />
        <v-card-text style="min-height:300px">

          <!-- Step 1 -->
          <template v-if="contractorImportStep === 1">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
              <div class="text-body-2">
                <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
                <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
                <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
              </div>
            </v-alert>
            <FileDropZone v-model="contractorImportFile"
              accept=".xlsx,.xls,.docx,.doc,.pdf"
              hint=".xlsx, .xls, .docx, .doc, .pdf — перетащите или нажмите"
              class="mb-4" />
            <v-alert v-if="contractorImportError" type="error" density="compact" class="mt-2">{{ contractorImportError }}</v-alert>
          </template>

          <!-- Step 2: mapping -->
          <template v-if="contractorImportStep === 2 && contractorImportPreview">
            <p class="text-caption text-medium-emphasis mb-2">
              Перетащите столбцы из файла в нужные поля. Всего строк: {{ contractorImportPreview.total_rows }}
            </p>
            <!-- TARGET ZONES (imap-grid) -->
            <div class="imap-grid mb-4">
              <div v-for="target in CONTRACTOR_TARGET_FIELDS" :key="target.value"
                class="imap-col"
                :class="{
                  'imap-col--over': contractorDragOverTarget === target.value,
                  'imap-col--filled': contractorIsTargetFilled(target.value),
                  'imap-col--required': target.required && !contractorIsTargetFilled(target.value),
                }"
                @dragover.prevent="contractorDragOverTarget = target.value"
                @dragleave="contractorDragOverTarget = null"
                @drop.prevent="contractorOnDropToTarget(target.value, $event)">
                <div class="imap-col-hdr">{{ target.title }}<span v-if="target.required" style="color:#e53935">*</span></div>
                <div class="imap-col-body">
                  <div v-if="contractorIsTargetFilled(target.value)"
                    class="imap-card" draggable="true"
                    @dragstart="contractorOnDragStart(contractorDragMapping[target.value] as number, $event)">
                    <div class="imap-card-row">
                      <span class="imap-card-name">{{ contractorGetLabel(contractorDragMapping[target.value] as number) }}</span>
                      <button class="imap-card-x" @click.stop="contractorUnmapTarget(target.value)">×</button>
                    </div>
                    <div class="imap-card-samples">{{ contractorGetSamples(contractorDragMapping[target.value] as number).join(', ') || '—' }}</div>
                  </div>
                  <div v-else class="imap-col-empty">—</div>
                </div>
              </div>
            </div>
            <!-- UNRESOLVED -->
            <div class="imap-unresolved"
              :class="{'imap-unresolved--over': contractorDragOverTarget === '_unresolved'}"
              @dragover.prevent="contractorDragOverTarget = '_unresolved'"
              @dragleave="contractorDragOverTarget = null"
              @drop.prevent="contractorOnDropToUnresolved($event)">
              <span class="imap-unresolved-label">Не определилось</span>
              <div class="d-flex gap-2 flex-wrap mt-1">
                <template v-for="(h, idx) in contractorImportPreview.headers" :key="idx">
                  <div v-if="!contractorIsMapped(idx) && !contractorIsIgnored(idx)"
                    class="imap-card imap-card--free" draggable="true"
                    @dragstart="contractorOnDragStart(idx, $event)">
                    <div class="imap-card-row">
                      <span class="imap-card-name">{{ h || `Столбец ${idx+1}` }}</span>
                      <button class="imap-card-x imap-card-x--grey" @click.stop="contractorIgnoreCol(idx)">×</button>
                    </div>
                    <div class="imap-card-samples">{{ contractorGetSamples(idx).join(', ') || '—' }}</div>
                  </div>
                </template>
              </div>
            </div>
            <v-alert v-if="!contractorIsTargetFilled('name')" type="warning" density="compact" class="mt-3">
              Укажите хотя бы столбец «Наименование»
            </v-alert>
          </template>

          <!-- Step 3: result -->
          <template v-if="contractorImportStep === 3 && contractorImportResult">
            <v-alert type="success" class="mb-3">
              Добавлено: <strong>{{ contractorImportResult.created }}</strong>
              <template v-if="contractorImportResult.updated">, дополнено: <strong>{{ contractorImportResult.updated }}</strong></template>
              <template v-if="contractorImportResult.skipped">, пропущено пустых: {{ contractorImportResult.skipped }}</template>
            </v-alert>
            <v-alert v-if="contractorImportResult.update_details?.length" type="info" variant="tonal" density="compact" class="mb-3">
              <div class="text-subtitle-2 mb-1">Дополненные контрагенты:</div>
              <div v-for="(d, i) in contractorImportResult.update_details.slice(0, 20)" :key="i" class="text-caption">{{ d }}</div>
              <div v-if="contractorImportResult.update_details.length > 20" class="text-caption text-medium-emphasis">...и ещё {{ contractorImportResult.update_details.length - 20 }}</div>
            </v-alert>
            <v-alert v-if="contractorImportResult.errors?.length" type="error" variant="tonal" density="compact" class="mb-3">
              <div class="text-subtitle-2 mb-1">Ошибки:</div>
              <div v-for="(e, i) in contractorImportResult.errors.slice(0, 10)" :key="i" class="text-caption">{{ e }}</div>
            </v-alert>
          </template>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="closeContractorImport">{{ contractorImportStep === 3 ? 'Закрыть' : 'Отмена' }}</v-btn>
          <v-btn v-if="contractorImportStep === 1" color="primary" :loading="contractorImportLoading"
            :disabled="!contractorImportFile" @click="doContractorImportPreview">
            Далее →
          </v-btn>
          <v-btn v-if="contractorImportStep === 2" color="success" :loading="contractorImportLoading"
            :disabled="!contractorIsTargetFilled('name')" @click="doContractorImportMapped">
            Импортировать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Duplicates by INN dialog ── -->
    <v-dialog v-model="showDuplicatesDialog" max-width="900" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="d-flex align-center pa-4 pb-2">
          <v-icon icon="mdi-content-duplicate" color="warning" class="mr-2" />
          Дубликаты контрагентов по ИНН
          <v-chip size="small" class="ml-2" v-if="duplicatesData">
            {{ duplicatesData.total_groups }} групп / {{ duplicatesData.total_extra }} лишних строк
          </v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showDuplicatesDialog = false" />
        </v-card-title>
        <v-card-text class="pa-4">
          <v-progress-circular v-if="duplicatesLoading" indeterminate color="warning" class="d-block mx-auto my-6" />
          <v-alert v-else-if="duplicatesError" type="error" variant="tonal" density="compact">
            {{ duplicatesError }}
          </v-alert>
          <v-alert v-else-if="duplicatesData && duplicatesData.groups.length === 0" type="success" variant="tonal" density="compact">
            Дубликатов по ИНН не найдено
          </v-alert>
          <div v-else-if="duplicatesData">
            <v-expansion-panels variant="accordion" multiple>
              <v-expansion-panel v-for="group in duplicatesData.groups" :key="group.inn">
                <v-expansion-panel-title>
                  <div class="d-flex align-center" style="width:100%">
                    <v-chip color="warning" size="small" class="mr-2">ИНН {{ group.inn }}</v-chip>
                    <span>{{ group.count }} записей</span>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Краткое</th>
                        <th>Полное</th>
                        <th>КПП</th>
                        <th>Адрес</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in group.contractors" :key="c.id">
                        <td>{{ c.id }}</td>
                        <td>{{ c.name }}</td>
                        <td class="text-caption">{{ c.full_name }}</td>
                        <td>{{ c.kpp }}</td>
                        <td class="text-caption">{{ c.address }}</td>
                        <td>
                          <v-btn size="x-small" variant="text" color="primary"
                                 prepend-icon="mdi-open-in-new"
                                 @click="openContractorCard(c.id)">
                            Открыть
                          </v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="showDuplicatesDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'
import ContractorEditDialog from '@/components/ContractorEditDialog.vue'
import { formatPhoneRu } from '@/utils/phoneFormat'
import { useCardView } from '@/composables/useCardView'
import { useToast, type ToastType } from '@/composables/useToast'

interface ContractorWithStats {
  id: number
  name: string
  full_name?: string
  inn?: string
  kpp?: string
  address?: string
  contact_person?: string
  phone?: string
  org_phone?: string
  email?: string
  org_email?: string
  bank_details?: string
  signatory?: string
  signatory_basis?: string
  postal_address?: string
  ogrn?: string
  settlement_account?: string
  bank_name?: string
  bik?: string
  correspondent_account?: string
  product_categories: string[]
  manual_product_categories?: string[]
  org_type?: string
  passport_series?: string
  passport_number?: string
  passport_issuer?: string
  passport_issued_date?: string
  snils?: string
  registration_address?: string
  birth_date?: string
  website?: string
  registration_date?: string
  okpo?: string
  okved?: string
  treasury_account?: string
  single_treasury_account?: string
  signatory_position?: string
}

const CONTRACTOR_TARGET_FIELDS = [
  { value: 'name',                       title: 'Наименование',       required: true },
  { value: 'inn',                        title: 'ИНН',                required: false },
  { value: 'kpp',                        title: 'КПП',                required: false },
  { value: 'ogrn',                       title: 'ОГРН',               required: false },
  { value: 'org_type',                   title: 'Тип организации',    required: false },
  { value: 'address',                    title: 'Адрес',              required: false },
  { value: 'postal_address',             title: 'Почт. адрес',        required: false },
  { value: 'email',                      title: 'Email контакт. лица',    required: false },
  { value: 'phone',                      title: 'Телефон контакт. лица', required: false },
  { value: 'org_phone',                  title: 'Телефон организации',   required: false },
  { value: 'org_email',                  title: 'Email организации',     required: false },
  { value: 'contact_person',             title: 'Контактное лицо',       required: false },
  { value: 'signatory',                  title: 'Подписант',          required: false },
  { value: 'signatory_basis',            title: 'Основание',          required: false },
  { value: 'settlement_account',         title: 'Расч. счёт',         required: false },
  { value: 'bank_name',                  title: 'Банк',               required: false },
  { value: 'bik',                        title: 'БИК',                required: false },
  { value: 'correspondent_account',      title: 'Корр. счёт',         required: false },
  { value: 'manual_product_categories',  title: 'Категории товаров',  required: false },
  { value: 'website',                    title: 'Сайт организации',   required: false },
  { value: 'registration_date',          title: 'Дата регистрации',   required: false },
  { value: 'okpo',                       title: 'ОКПО',               required: false },
  { value: 'okved',                      title: 'ОКВЭД',              required: false },
  { value: 'treasury_account',           title: 'Казначейский счёт',  required: false },
  { value: 'single_treasury_account',    title: 'Единый казн. счёт',  required: false },
  { value: 'signatory_position',         title: 'Должность подписанта', required: false },
]

const contractors = ref<ContractorWithStats[]>([])
const contractorsTotal = ref(0)
const contractorsPage = ref(1)
const contractorsPerPage = 50
const loading     = ref(false)
const saving      = ref(false)
const search      = ref('')
const filterCategory = ref<string | null>(null)
const userRole = localStorage.getItem('user_role') || ''
const isOwnerPlus = ['superadmin', 'account_owner'].includes(userRole)
const enrichAllLoading = ref(false)
const enrichAllResult = ref<{ total: number; updated: number; skipped: number; errors: any[] } | null>(null)
const dialog      = ref(false)
const deleteDialog     = ref(false)
const bulkDeleteDialog = ref(false)
const bulkDeleteConfirmCount = ref('')
const editId      = ref<number | null>(null)
const deleteTarget  = ref<ContractorWithStats | null>(null)
const selectedIds = ref(new Set<number>())

// Categories dialog
const categoriesDialog = ref(false)
const categoriesDialogContractor = ref<ContractorWithStats | null>(null)

const toast = useToast()

// ── Contractor import state ──
const contractorImportDialog  = ref(false)
const contractorImportStep    = ref(1)
const contractorImportFile    = ref<File | null>(null)
const contractorImportLoading = ref(false)
const contractorImportPreview = ref<{
  headers: string[]
  sample: string[][]
  total_rows: number
  header_row_offset: number
} | null>(null)
const contractorDragMapping   = ref<Record<string, number | null>>({})
const contractorIgnoredCols   = ref<number[]>([])
const contractorDragOverTarget = ref<string | null>(null)
const contractorImportResult  = ref<{ created: number; updated?: number; skipped: number; skipped_empty?: number; update_details?: string[]; errors?: string[] } | null>(null)
const contractorImportError   = ref('')

const showDuplicatesDialog = ref(false)
const duplicatesLoading = ref(false)
const duplicatesError = ref('')
const duplicatesData = ref<{groups: any[], total_groups: number, total_extra: number} | null>(null)

async function openDuplicatesDialog() {
  showDuplicatesDialog.value = true
  duplicatesData.value = null
  duplicatesError.value = ''
  duplicatesLoading.value = true
  try {
    duplicatesData.value = await apiFetch('/contractors/duplicates-by-inn')
  } catch (e: any) {
    duplicatesError.value = e?.payload?.message || e?.message || 'Ошибка загрузки дублей'
  } finally {
    duplicatesLoading.value = false
  }
}

function openContractorCard(cid: number) {
  // Карточка грузится компонентом по id — работает и для контрагентов не из текущей страницы
  editId.value = cid
  dialog.value = true
}

const allProductCategories = computed(() => {
  const cats = new Set<string>()
  contractors.value.forEach(c => c.product_categories.forEach(p => { if (p !== 'Все') cats.add(p) }))
  return [...cats].sort()
})

// Server-side filtering — all filtering done on server
const filtered = computed(() => contractors.value)

const totalPages = computed(() => Math.ceil(contractorsTotal.value / contractorsPerPage))

// ── Card view (table ↔ cards toggle) ─────────────────
// IMPORTANT: called AFTER `filtered` to avoid Temporal Dead Zone
const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedCards,
} = useCardView({
  storageKey: 'contractors_view_mode',
  source: () => filtered.value,
  search: () => search.value,
  searchFields: (c: any) => [c.name, c.inn, c.kpp, c.full_name],
  pageSize: 24,
})

function clearFilters() {
  search.value = ''
  filterCategory.value = null
  contractorsPage.value = 1
  loadContractors()
}

async function enrichAllFromFns() {
  enrichAllLoading.value = true
  enrichAllResult.value = null
  try {
    const data = await apiFetch<{ total: number; updated: number; skipped: number; errors: any[] }>('/contractors/enrich-all-fns', { method: 'POST' })
    enrichAllResult.value = data
    if (data.updated > 0) loadContractors()
  } catch (e: any) {
    enrichAllResult.value = { total: 0, updated: 0, skipped: 0, errors: [{ error: e.message }] }
  } finally {
    enrichAllLoading.value = false
  }
}

let _searchTimeout: any = null
function onSearchInput() {
  clearTimeout(_searchTimeout)
  _searchTimeout = setTimeout(() => {
    contractorsPage.value = 1
    loadContractors()
  }, 400)
}

function goPage(page: number) {
  contractorsPage.value = page
  loadContractors()
}

// ── Load ──────────────────────────────────────────
async function loadContractors() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('offset', String((contractorsPage.value - 1) * contractorsPerPage))
    params.set('limit', String(contractorsPerPage))
    if (search.value) params.set('search', search.value)
    if (filterCategory.value) params.set('category', filterCategory.value)
    const data = await apiFetch<{ items: ContractorWithStats[]; total: number }>(`/contractors/with-stats?${params}`)
    contractors.value = data.items
    contractorsTotal.value = data.total
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

// ── Categories dialog ──────────────────────────────
function openCategoriesDialog(c: ContractorWithStats) {
  categoriesDialogContractor.value = c
  categoriesDialog.value = true
}


// ── Add / Edit ────────────────────────────────────
// Форма редактирования/создания вынесена в компонент ContractorEditDialog.
// Здесь только управление открытием диалога (editId + dialog) и перезагрузка списка.
function openAdd() {
  editId.value = null
  dialog.value = true
}

function openEdit(c: ContractorWithStats) {
  editId.value = c.id
  dialog.value = true
}

// Вызывается после успешного сохранения внутри ContractorEditDialog
async function onContractorSaved() {
  dialog.value = false
  await loadContractors()
}

// ── Selection ─────────────────────────────────────
function toggleOne(id: number) {
  const s = new Set(selectedIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedIds.value = s
}

function toggleAll(val: boolean) {
  selectedIds.value = val ? new Set(filtered.value.map(c => c.id)) : new Set()
}

function confirmBulkDelete() {
  bulkDeleteDialog.value = true
}

async function doBulkDelete() {
  saving.value = true
  const ids = [...selectedIds.value]
  try {
    const res = await apiFetch<{ deleted: number; skipped_linked: number; skipped_not_found: number }>('/contractors/bulk', {
      method: 'DELETE',
      body: { ids } as any,
    })
    selectedIds.value = new Set()
    bulkDeleteDialog.value = false
    bulkDeleteConfirmCount.value = ''
    let msg = `Удалено: ${res.deleted}`
    if (res.skipped_linked) msg += `, пропущено (есть закупки): ${res.skipped_linked}`
    if (res.skipped_not_found) msg += `, не найдено: ${res.skipped_not_found}`
    showSnack(msg, res.skipped_linked ? 'warning' : 'success')
    await loadContractors()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка удаления', 'error')
  } finally {
    saving.value = false
  }
}

// ── Delete ────────────────────────────────────────
function confirmDelete(c: ContractorWithStats) {
  deleteTarget.value = c
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    await apiFetch(`/contractors/${deleteTarget.value.id}`, { method: 'DELETE' })
    deleteDialog.value = false
    showSnack('Контрагент удалён', 'warning')
    await loadContractors()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка удаления', 'error')
  } finally {
    saving.value = false
  }
}

// ── Template download ──────────────────────────────
async function downloadTemplate() {
  const token = localStorage.getItem('auth_token') || ''
  const res = await fetch('/api/contractors/import/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { showSnack('Ошибка скачивания шаблона', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'Шаблон_импорта_контрагентов.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

// ── Contractor import helpers ──────────────────────
const _FIELD_KEYWORDS: Record<string, string[]> = {
  name:                       ['назван', 'наимен', 'name', 'органи'],
  inn:                        ['инн', 'inn', 'идентиф'],
  kpp:                        ['кпп', 'kpp'],
  ogrn:                       ['огрн', 'ogrn'],
  org_type:                   ['тип орг', 'org_type', 'юр.лицо', 'форма'],
  address:                    ['адрес', 'address'],
  postal_address:             ['почтов', 'postal'],
  email:                      ['email', 'e-mail', 'mail'],
  phone:                      ['телефон', 'phone', 'тел'],
  org_phone:                  ['тел. орг', 'org_phone'],
  org_email:                  ['email орг', 'org_email'],
  contact_person:             ['контакт', 'contact', 'лицо'],
  signatory:                  ['подписант', 'signatory', 'директор', 'руководит'],
  signatory_basis:            ['основан', 'basis', 'устав', 'действует'],
  settlement_account:         ['расч', 'р/с', 'settlement'],
  bank_name:                  ['банк', 'bank'],
  bik:                        ['бик', 'bik'],
  correspondent_account:      ['корр', 'к/с', 'correspondent'],
  manual_product_categories:  ['категор', 'товар', 'product', 'categ'],
  website:                    ['сайт', 'website'],
  registration_date:          ['дата регистрац', 'зарегистр'],
  okpo:                       ['окпо'],
  okved:                      ['оквэд', 'оквед'],
  treasury_account:           ['казначейск'],
  single_treasury_account:    ['единый казн'],
  signatory_position:         ['должност'],
}

function contractorAutoDetect(headers: string[]): Record<string, number | null> {
  const mapping: Record<string, number | null> = {}
  const used = new Set<number>()
  for (const field of CONTRACTOR_TARGET_FIELDS) {
    const kws = _FIELD_KEYWORDS[field.value] || []
    for (let i = 0; i < headers.length; i++) {
      if (used.has(i)) continue
      const h = (headers[i] || '').toLowerCase()
      if (kws.some(k => h.includes(k))) {
        mapping[field.value] = i
        used.add(i)
        break
      }
    }
  }
  return mapping
}

function contractorIsMapped(idx: number): boolean {
  return Object.values(contractorDragMapping.value).includes(idx)
}

function contractorIsIgnored(idx: number): boolean {
  return contractorIgnoredCols.value.includes(idx)
}

function contractorIsTargetFilled(field: string): boolean {
  return contractorDragMapping.value[field] != null
}

function contractorGetLabel(idx: number): string {
  return contractorImportPreview.value?.headers[idx] || `Столбец ${idx + 1}`
}

function contractorGetSamples(idx: number): string[] {
  if (!contractorImportPreview.value) return []
  return contractorImportPreview.value.sample
    .slice(0, 1)
    .map(row => (row[idx] != null ? String(row[idx]).trim() : ''))
    .filter(Boolean)
}

let _dragIdx: number | null = null

function contractorOnDragStart(idx: number, e: DragEvent) {
  _dragIdx = idx
  e.dataTransfer?.setData('text/plain', String(idx))
}

function contractorOnDropToTarget(field: string, e: DragEvent) {
  contractorDragOverTarget.value = null
  const raw = e.dataTransfer?.getData('text/plain')
  const idx = raw != null ? parseInt(raw) : _dragIdx
  if (idx == null || isNaN(idx as number)) return
  // Unmap if this idx was in another target
  for (const [f, v] of Object.entries(contractorDragMapping.value)) {
    if (v === idx) contractorDragMapping.value[f] = null
  }
  contractorDragMapping.value[field] = idx as number
  // Remove from ignored
  contractorIgnoredCols.value = contractorIgnoredCols.value.filter(i => i !== idx)
}

function contractorOnDropToUnresolved(e: DragEvent) {
  contractorDragOverTarget.value = null
  const raw = e.dataTransfer?.getData('text/plain')
  const idx = raw != null ? parseInt(raw) : _dragIdx
  if (idx == null || isNaN(idx as number)) return
  for (const [f, v] of Object.entries(contractorDragMapping.value)) {
    if (v === idx) contractorDragMapping.value[f] = null
  }
}

function contractorUnmapTarget(field: string) {
  contractorDragMapping.value[field] = null
}

function contractorIgnoreCol(idx: number) {
  if (!contractorIgnoredCols.value.includes(idx)) {
    contractorIgnoredCols.value.push(idx)
  }
}

async function doContractorImportPreview() {
  if (!contractorImportFile.value) return
  contractorImportLoading.value = true
  contractorImportError.value = ''
  try {
    const token = localStorage.getItem('auth_token') || ''
    const fd = new FormData()
    // contractorImportFile from v-file-input may be a File[] or File
    const fileObj = Array.isArray(contractorImportFile.value)
      ? contractorImportFile.value[0]
      : contractorImportFile.value
    fd.append('file', fileObj)
    const res = await fetch('/api/contractors/import/preview', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      let detail = await res.text()
      try { detail = JSON.parse(detail).detail } catch {}
      throw new Error(detail)
    }
    const data = await res.json()
    contractorImportPreview.value = data
    contractorDragMapping.value = contractorAutoDetect(data.headers)
    contractorIgnoredCols.value = []
    contractorImportStep.value = 2
  } catch (e: any) {
    contractorImportError.value = e.message || 'Ошибка чтения файла'
  } finally {
    contractorImportLoading.value = false
  }
}

async function doContractorImportMapped() {
  if (!contractorImportFile.value || !contractorImportPreview.value) return
  contractorImportLoading.value = true
  contractorImportError.value = ''
  try {
    const token = localStorage.getItem('auth_token') || ''
    const fd = new FormData()
    const fileObj = Array.isArray(contractorImportFile.value)
      ? contractorImportFile.value[0]
      : contractorImportFile.value
    fd.append('file', fileObj)

    const params = new URLSearchParams()
    params.set('header_row_offset', String(contractorImportPreview.value.header_row_offset))
    const m = contractorDragMapping.value
    const colFields = [
      'name', 'inn', 'kpp', 'ogrn', 'org_type', 'address', 'postal_address',
      'signatory', 'signatory_basis', 'contact_person', 'phone', 'email',
      'org_phone', 'org_email',
      'settlement_account', 'bank_name', 'bik', 'correspondent_account', 'bank_details',
      'manual_product_categories',
      'website', 'registration_date', 'okpo', 'okved',
      'treasury_account', 'single_treasury_account', 'signatory_position',
    ]
    for (const f of colFields) {
      if (m[f] != null) params.set(`col_${f}`, String(m[f]))
    }

    const res = await fetch(`/api/contractors/import/mapped?${params.toString()}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      let detail = await res.text()
      try { detail = JSON.parse(detail).detail } catch {}
      throw new Error(detail)
    }
    const data = await res.json()
    contractorImportResult.value = data
    contractorImportStep.value = 3
    showSnack(`Добавлено: ${data.created}, дополнено: ${data.updated || 0}, пропущено: ${data.skipped}`, 'success')
    await loadContractors()
  } catch (e: any) {
    contractorImportError.value = e.message || 'Ошибка импорта'
  } finally {
    contractorImportLoading.value = false
  }
}

function closeContractorImport() {
  contractorImportDialog.value = false
  contractorImportStep.value = 1
  contractorImportFile.value = null
  contractorImportPreview.value = null
  contractorDragMapping.value = {}
  contractorIgnoredCols.value = []
  contractorImportResult.value = null
  contractorImportError.value = ''
}

// ── Helpers ───────────────────────────────────────
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

watch(filterCategory, () => { contractorsPage.value = 1; loadContractors() })
onMounted(() => { loadContractors() })
</script>

<style scoped>
.contractors-page {
  padding: 20px 24px;
  max-width: 1600px;
}

/* ── Header ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

/* ── Filters ── */
.filters-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.search-count {
  font-size: 13px;
  color: var(--crm-text-muted);
  white-space: nowrap;
  margin-left: auto;
}

/* ── Table ── */
.table-card {
  background: var(--crm-surface);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  overflow: hidden;
}
.contractors-table thead th {
  font-size: 11px !important;
  font-weight: 600 !important;
  color: var(--crm-text-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--crm-table-header);
  padding: 10px 14px !important;
  white-space: nowrap;
}
.contractors-table tbody td {
  padding: 10px 14px !important;
  vertical-align: top;
}
.contractor-row:hover td { background: var(--crm-surface-alt); }
.contractor-row--selected td { background: var(--crm-surface-hover); }
.text-mono { font-family: monospace; font-size: 13px; }
.text-sm   { font-size: 13px; }
.cursor-pointer { cursor: pointer; }

/* ── Dialogs ── */
.dialog-title {
  display: flex;
  align-items: center;
  font-size: 16px !important;
  font-weight: 600 !important;
  padding: 16px 20px !important;
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--crm-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--crm-border);
}

/* ── imap drag-and-drop (contractor import) ── */
.imap-grid { display:flex; gap:4px; overflow-x:auto; padding-bottom:4px; flex-wrap:wrap; }
.imap-col { flex:1; min-width:100px; border:1px dashed #ccc; border-radius:6px; background:#fafafa; transition:border-color .15s,background .15s; }
.imap-col--over { border-color:#1976D2; background:rgba(25,118,210,.04); }
.imap-col--filled { border-style:solid; border-color:#43A047; background:#f6fff6; }
.imap-col--required { border-color:#ef9a9a; background:#fff8f8; }
.imap-col-hdr { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.3px; color:#555; padding:5px 7px 3px; border-bottom:1px solid #e8e8e8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.imap-col-body { padding:5px; min-height:58px; }
.imap-col-empty { font-size:10px; color:#ccc; text-align:center; margin-top:10px; font-style:italic; }
.imap-card { border-radius:4px; background:#fff; border:1px solid #e0e0e0; padding:4px 6px; cursor:grab; user-select:none; transition:border-color .15s,box-shadow .15s; }
.imap-card:hover { border-color:#1976D2; box-shadow:0 1px 5px rgba(25,118,210,.15); }
.imap-card-row { display:flex; align-items:center; justify-content:space-between; gap:2px; }
.imap-card-name { font-size:11px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.imap-card-x { font-size:14px; line-height:1; background:none; border:none; cursor:pointer; color:#aaa; padding:0 2px; flex-shrink:0; }
.imap-card-x:hover { color:#e53935; }
.imap-card-x--grey { color:#bbb; }
.imap-card-samples { font-size:10px; color:#999; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; line-height:1.3; }
.imap-card--free { background:#fafafa; }
.imap-unresolved { border:1px dashed #ccc; border-radius:6px; padding:6px 10px; min-height:44px; transition:border-color .15s,background .15s; }
.imap-unresolved--over { border-color:#1976D2; background:rgba(25,118,210,.04); }
.imap-unresolved-label { font-size:10px; font-weight:700; text-transform:uppercase; color:#aaa; letter-spacing:.3px; }
</style>
