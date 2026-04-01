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
    </div>

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
    <div class="table-card">
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
              <div class="text-sm">{{ c.phone || '—' }}</div>
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

    <!-- ── Categories dialog ── -->
    <v-dialog v-model="categoriesDialog" max-width="480" scrollable>
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

    <!-- ── Add / Edit Dialog ── -->
    <v-dialog v-model="dialog" max-width="780" persistent scrollable>
      <v-card class="dialog-card">
        <v-card-title class="dialog-title">
          <v-icon :icon="editId ? 'mdi-pencil-outline' : 'mdi-plus-circle-outline'" color="primary" class="mr-2" />
          {{ editId ? 'Редактировать контрагента' : 'Добавить контрагента' }}
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="dialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4" style="max-height:75vh">
          <v-form ref="formRef">
            <div class="section-label">Основные данные</div>
            <v-select
              v-model="form.org_type"
              :items="['Юр.лицо', 'ИП', 'Самозанятый', 'Физ.лицо']"
              label="Форма организации"
              variant="outlined"
              density="compact"
              clearable
              hide-details
              class="mb-3"
            />
            <v-text-field
              v-model="form.name"
              label="Наименование организации *"
              variant="outlined"
              density="compact"
              :rules="[v => !!v || 'Обязательное поле']"
              class="mb-3"
              hide-details="auto"
            />
            <v-row dense>
              <v-col cols="4">
                <v-text-field v-model="form.inn" label="ИНН" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="4">
                <v-text-field v-model="form.kpp" label="КПП" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="3">
                <v-text-field v-model="form.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="1" class="d-flex align-center">
                <v-btn icon="mdi-database-search" variant="tonal" size="small" color="blue"
                  :loading="fnsLoading" :disabled="!form.inn || form.inn.length < 10"
                  title="Заполнить по ИНН из ЕГРЮЛ (nalog.ru)" @click="lookupFns" />
              </v-col>
            </v-row>
            <v-alert v-if="fnsMessage" :type="fnsMessageType" variant="tonal" density="compact" class="mt-2 mb-0 text-caption" closable @click:close="fnsMessage = ''">
              {{ fnsMessage }}
            </v-alert>
            <v-textarea v-model="form.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
            <v-textarea v-model="form.postal_address" label="Почтовый адрес" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

            <div class="section-label mt-4">Подписант</div>
            <v-text-field v-model="form.signatory" label="Подписант (ФИО, должность)" variant="outlined" density="compact" class="mb-3" hide-details />
            <v-text-field v-model="form.signatory_basis" label="На основании чего действует" variant="outlined" density="compact" hide-details
              placeholder="Устава, доверенности №..." />

            <div class="section-label mt-4">Контакты</div>
            <v-row dense class="mb-3">
              <v-col cols="6">
                <v-text-field v-model="form.org_phone" label="Телефон организации" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="form.org_email" label="Email организации" variant="outlined" density="compact" hide-details />
              </v-col>
            </v-row>
            <v-text-field v-model="form.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mb-3" hide-details />
            <v-row dense>
              <v-col cols="6">
                <v-text-field v-model="form.phone" label="Телефон контактного лица" variant="outlined" density="compact" hide-details />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="form.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
              </v-col>
            </v-row>

            <div class="section-label mt-4">Банковские реквизиты</div>
            <v-text-field v-model="form.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details maxlength="20" />
            <v-text-field v-model="form.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details
              placeholder="в ПАО «Сбербанк»..." />
            <v-row dense>
              <v-col cols="6">
                <v-text-field v-model="form.bik" label="БИК" variant="outlined" density="compact" hide-details maxlength="9" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="form.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details maxlength="20" />
              </v-col>
            </v-row>
            <v-textarea v-model="form.bank_details" label="Банковские реквизиты (свободное поле)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

            <div class="section-label mt-4">Категории товаров</div>
            <v-combobox
              v-model="form.manual_product_categories"
              :items="categoryOptions"
              label="Категории товаров / услуг"
              variant="outlined"
              density="compact"
              multiple
              chips
              closable-chips
              clearable
              hide-details
              hint="Введите категорию и нажмите Enter. Выберите «Все» для всех категорий."
              persistent-hint
              :disabled="form.manual_product_categories?.includes('Все')"
            />
            <v-checkbox
              v-model="allCategoriesToggle"
              label="Все категории"
              density="compact"
              hide-details
              color="teal"
              class="mt-1"
            />
          </v-form>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
    <v-dialog v-model="contractorImportDialog" max-width="1000" persistent scrollable>
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <span>Импорт контрагентов — шаг {{ contractorImportStep }} из 2</span>
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="closeContractorImport" />
        </v-card-title>
        <v-divider />
        <v-card-text style="min-height:300px">

          <!-- Step 1 -->
          <template v-if="contractorImportStep === 1">
            <p class="mb-3">Поддерживаемые форматы: <strong>.xlsx, .xls, .docx, .doc, .pdf</strong></p>
            <v-file-input
              v-model="contractorImportFile"
              label="Выберите файл"
              accept=".xlsx,.xls,.docx,.doc,.pdf"
              variant="outlined" density="compact" prepend-icon=""
              prepend-inner-icon="mdi-file-import-outline"
              hide-details class="mb-4" />
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

    <!-- ── Snackbar ── -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="4000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiFetch } from '@/api'

interface ContractorWithStats {
  id: number
  name: string
  inn?: string
  kpp?: string
  address?: string
  contact_person?: string
  phone?: string
  email?: string
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
]

const contractors = ref<ContractorWithStats[]>([])
const contractorsTotal = ref(0)
const contractorsPage = ref(1)
const contractorsPerPage = 50
const loading     = ref(false)
const saving      = ref(false)
const fnsLoading  = ref(false)
const fnsMessage  = ref('')
const fnsMessageType = ref<'success' | 'info' | 'error'>('info')
const search      = ref('')
const filterCategory = ref<string | null>(null)
const dialog      = ref(false)
const deleteDialog     = ref(false)
const bulkDeleteDialog = ref(false)
const bulkDeleteConfirmCount = ref('')
const editId      = ref<number | null>(null)
const deleteTarget  = ref<ContractorWithStats | null>(null)
const formRef     = ref()
const selectedIds = ref(new Set<number>())

// Categories dialog
const categoriesDialog = ref(false)
const categoriesDialogContractor = ref<ContractorWithStats | null>(null)

const snack = ref({ show: false, text: '', color: 'success' })

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

const emptyForm = () => ({
  name: '', inn: '', kpp: '', address: '',
  contact_person: '', phone: '', email: '', org_phone: '', org_email: '', bank_details: '',
  signatory: '', signatory_basis: '', postal_address: '',
  ogrn: '', settlement_account: '', bank_name: '', bik: '', correspondent_account: '',
  org_type: '' as string | null,
  manual_product_categories: [] as string[],
})
const form = ref(emptyForm())

const allProductCategories = computed(() => {
  const cats = new Set<string>()
  contractors.value.forEach(c => c.product_categories.forEach(p => { if (p !== 'Все') cats.add(p) }))
  return [...cats].sort()
})

// All known categories (from products + manual) — loaded from backend
const allKnownCategories = ref<string[]>([])

async function loadCategories() {
  try {
    allKnownCategories.value = await apiFetch<string[]>('/contractors/product-categories')
  } catch { /* ignore */ }
}

// Options for category combobox: backend list + any currently in form (user-typed new ones)
const categoryOptions = computed(() => {
  const set = new Set(allKnownCategories.value)
  // Add categories from loaded contractors too
  contractors.value.forEach(c => c.product_categories.forEach(p => { if (p !== 'Все') set.add(p) }))
  return [...set].sort()
})

// "All categories" toggle
const allCategoriesToggle = computed({
  get: () => form.value.manual_product_categories?.includes('Все') ?? false,
  set: (val: boolean) => {
    if (val) {
      form.value.manual_product_categories = ['Все']
    } else {
      form.value.manual_product_categories = []
    }
  },
})

// Server-side filtering — all filtering done on server
const filtered = computed(() => contractors.value)

const totalPages = computed(() => Math.ceil(contractorsTotal.value / contractorsPerPage))

function clearFilters() {
  search.value = ''
  filterCategory.value = null
  contractorsPage.value = 1
  loadContractors()
}

async function lookupFns() {
  const inn = form.value.inn?.trim()
  if (!inn || inn.length < 10) return
  fnsLoading.value = true
  fnsMessage.value = ''
  try {
    const data = await apiFetch<Record<string, string | null>>(`/contractors/lookup-inn/${inn}`)
    const filled: string[] = []
    if (data.name && !form.value.name) { form.value.name = data.name; filled.push('Наименование') }
    if (data.kpp && !form.value.kpp) { form.value.kpp = data.kpp; filled.push('КПП') }
    if (data.ogrn && !form.value.ogrn) { form.value.ogrn = data.ogrn; filled.push('ОГРН') }
    if (data.address && !form.value.address) { form.value.address = data.address; filled.push('Адрес') }
    if (data.signatory && !form.value.signatory) { form.value.signatory = data.signatory; filled.push('Подписант') }
    if (data.org_type && !form.value.org_type) { form.value.org_type = data.org_type; filled.push('Тип') }
    if (filled.length) {
      fnsMessage.value = `Заполнено из ЕГРЮЛ: ${filled.join(', ')}`
      fnsMessageType.value = 'success'
    } else {
      fnsMessage.value = `Найден: ${data.name || inn}. Все поля уже заполнены.`
      fnsMessageType.value = 'info'
    }
  } catch (e: any) {
    fnsMessage.value = e.message || 'Ошибка запроса к ФНС'
    fnsMessageType.value = 'error'
  } finally {
    fnsLoading.value = false
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
function openAdd() {
  editId.value = null
  form.value = emptyForm()
  dialog.value = true
}

function openEdit(c: ContractorWithStats) {
  editId.value = c.id
  form.value = {
    name:                 c.name,
    inn:                  c.inn                  || '',
    kpp:                  c.kpp                  || '',
    address:              c.address              || '',
    contact_person:       c.contact_person       || '',
    phone:                c.phone                || '',
    email:                c.email                || '',
    bank_details:         c.bank_details         || '',
    signatory:            c.signatory            || '',
    signatory_basis:      c.signatory_basis      || '',
    postal_address:       c.postal_address       || '',
    ogrn:                 c.ogrn                 || '',
    settlement_account:   c.settlement_account   || '',
    bank_name:            c.bank_name            || '',
    bik:                  c.bik                  || '',
    correspondent_account: c.correspondent_account || '',
    manual_product_categories: mergeCategories(c.manual_product_categories || [], c.product_categories || []),
  }
  dialog.value = true
}

/** Merge manual + auto categories, deduplicate */
function mergeCategories(manual: string[], auto: string[]): string[] {
  if (manual.includes('Все')) return ['Все']
  return [...new Set([...manual, ...auto])]
}

async function save() {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  saving.value = true
  try {
    if (editId.value) {
      await apiFetch<ContractorWithStats>(`/contractors/${editId.value}`, {
        method: 'PUT',
        body: form.value as any,
      })
      showSnack('Контрагент обновлён')
    } else {
      await apiFetch<ContractorWithStats>('/contractors/', {
        method: 'POST',
        body: form.value as any,
      })
      showSnack('Контрагент добавлен')
    }
    dialog.value = false
    await loadContractors()
    loadCategories()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
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
  a.href = url; a.download = 'contractors_template.xlsx'; a.click()
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
function showSnack(text: string, color = 'success') {
  snack.value = { show: true, text, color }
}

watch(filterCategory, () => { contractorsPage.value = 1; loadContractors() })
onMounted(() => { loadContractors(); loadCategories() })
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
