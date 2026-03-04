<template>
  <v-container fluid class="pa-6" style="max-width:1200px">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">
          {{ isEdit ? `Закупка #${form.purchase_number || route.params.id}` : 'Новая закупка' }}
        </h1>
        <div class="d-flex align-center gap-2 mt-1">
          <v-chip v-if="isEdit && form.status" :color="STATUS_COLOR[form.status]" size="small" variant="tonal">
            {{ STATUS_LABEL[form.status] }}
          </v-chip>
          <span v-if="isEdit && form.registry_number" class="text-caption text-medium-emphasis">
            Реестр: {{ form.registry_number }}
          </span>
        </div>
      </div>
      <v-btn variant="outlined" prepend-icon="mdi-arrow-left" to="/orders">К списку</v-btn>
    </div>

    <v-alert v-if="budgetInfo" :type="budgetInfo.exceeded ? 'error' : 'info'" variant="tonal" class="mb-4" density="compact">
      <template v-if="budgetInfo.exceeded">
        Превышение бюджета субсидии на <strong>{{ formatMoney(budgetInfo.over) }}</strong>
      </template>
      <template v-else>
        Остаток бюджета субсидии: <strong>{{ formatMoney(budgetInfo.remaining) }}</strong>
      </template>
    </v-alert>

    <v-form ref="formRef" @submit.prevent="save">

      <!-- 1. Основная информация -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Основная информация</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <v-select v-model="form.purchase_method"
                :items="[{value:'single',title:'Единственный исполнитель'},{value:'competitive',title:'Конкурсная процедура'}]"
                item-title="title" item-value="value" label="Способ закупки" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="form.subsidy_id" :items="subsidies" item-title="name" item-value="id"
                label="Субсидия *" variant="outlined" density="compact"
                :rules="[r => !!r || 'Выберите субсидию']" @update:model-value="onSubsidyChange" />
            </v-col>
            <v-col cols="12" md="3">
              <v-autocomplete
                v-model="form.contractor_id"
                :items="contractors"
                item-title="name"
                item-value="id"
                label="Контрагент"
                variant="outlined"
                density="compact"
                clearable
                auto-select-first
                :custom-filter="contractorFilter"
                @update:model-value="onContractorSelect"
              >
                <template #item="{ item, props }">
                  <v-list-item v-bind="props">
                    <template #subtitle>
                      <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
                    </template>
                  </v-list-item>
                </template>
              </v-autocomplete>
            </v-col>
            <v-col cols="12" md="2">
              <v-text-field
                v-model="contractorInn"
                label="ИНН"
                variant="outlined"
                density="compact"
                maxlength="12"
                @update:model-value="onInnInput"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-combobox
                v-model="form.country_origin"
                :items="COUNTRIES"
                label="Страна происхождения"
                variant="outlined"
                density="compact"
              />
            </v-col>
            <v-col cols="12" md="4">
              <v-select v-model="form.feo_category_id" :items="flatFeoForSubsidy" item-title="name" item-value="id"
                label="Категория ФЭО" variant="outlined" density="compact" clearable />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.registry_number" label="Реестровый номер"
                variant="outlined" density="compact" :readonly="!isEdit"
                :bg-color="!isEdit ? 'grey-lighten-4' : undefined"
                hint="Генерируется автоматически" persistent-hint />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 2. Позиции закупки -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center justify-space-between">
          <span>Позиции закупки</span>
          <v-chip color="primary" variant="tonal" size="small">
            НМЦК: {{ formatMoney(totalNmck) }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <div class="overflow-x-auto">
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="min-width:280px">Наименование</th>
                  <th style="min-width:130px">Тип</th>
                  <th style="min-width:80px">Кол-во</th>
                  <th style="min-width:70px">Ед.</th>
                  <th style="min-width:110px">Цена ед., ₽</th>
                  <th style="min-width:110px">Сумма, ₽</th>
                  <th style="width:48px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in items" :key="idx">
                  <td>
                    <v-combobox
                      v-model="item.item_name"
                      :items="products"
                      item-title="name"
                      item-value="name"
                      density="compact"
                      variant="outlined"
                      hide-details
                      clearable
                      class="my-1"
                      @update:model-value="(v) => onItemProductSelect(idx, v)"
                    >
                      <template #item="{ item: drop, props }">
                        <v-list-item v-bind="props" :title="drop.raw?.name || drop.title">
                          <template #prepend>
                            <v-avatar v-if="drop.raw?.photo_url" size="36" rounded="sm" class="mr-2">
                              <v-img :src="drop.raw.photo_url" cover />
                            </v-avatar>
                            <v-icon v-else size="28" class="mr-2">mdi-package-variant</v-icon>
                          </template>
                          <template #subtitle>
                            <div v-if="drop.raw?.description" class="text-caption" style="max-width:340px;white-space:normal">
                              {{ drop.raw.description.slice(0, 100) }}
                            </div>
                            <div v-if="drop.raw?.price" class="text-caption text-primary">
                              {{ Number(drop.raw.price).toLocaleString('ru-RU') }} ₽
                            </div>
                          </template>
                        </v-list-item>
                      </template>
                    </v-combobox>
                  </td>
                  <td>
                    <v-select v-model="item.item_type"
                      :items="[{value:'товар',title:'Товар'},{value:'услуга',title:'Услуга'},{value:'работа',title:'Работа'}]"
                      item-title="title" item-value="value" density="compact" variant="outlined"
                      hide-details class="my-1" />
                  </td>
                  <td>
                    <v-text-field v-model.number="item.quantity" type="number" density="compact"
                      variant="outlined" hide-details class="my-1"
                      @update:model-value="calcItemTotal(idx)" />
                  </td>
                  <td>
                    <v-text-field v-model="item.unit" density="compact" variant="outlined"
                      hide-details class="my-1" />
                  </td>
                  <td>
                    <v-text-field v-model.number="item.unit_price" type="number" density="compact"
                      variant="outlined" hide-details class="my-1"
                      @update:model-value="calcItemTotal(idx)" />
                  </td>
                  <td>
                    <v-text-field :model-value="item.total_price ?? ''" readonly density="compact"
                      variant="outlined" hide-details bg-color="grey-lighten-4" class="my-1" />
                  </td>
                  <td>
                    <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                      @click="removeItem(idx)" />
                  </td>
                </tr>
                <tr v-if="!items.length">
                  <td colspan="7" class="text-center text-medium-emphasis py-4">
                    Нет позиций. Нажмите «Добавить позицию».
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
          <v-btn variant="tonal" prepend-icon="mdi-plus" size="small" class="mt-3"
            @click="addItem">
            Добавить позицию
          </v-btn>
        </v-card-text>
      </v-card>

      <!-- 3. Финансы -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Финансовые показатели</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <v-text-field :model-value="formatMoney(totalNmck)" label="НМЦК (итого)" variant="outlined"
                density="compact" readonly bg-color="grey-lighten-4" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="form.contract_price" label="Цена договора" variant="outlined"
                density="compact" type="number" suffix="₽" @update:model-value="calcEconomy" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field :model-value="form.economy ?? ''" label="Экономия (авто)" variant="outlined"
                density="compact" suffix="₽" readonly bg-color="grey-lighten-4" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="form.price_increase" label="Увеличение цены (доп. соглашения)"
                variant="outlined" density="compact" type="number" suffix="₽" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 4. Договор -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Договор</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.contract_number" label="Номер договора" variant="outlined" density="compact"
                :hint="needsContract ? 'Обязательно для перехода в статус Договор' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.contract_date" label="Дата договора" variant="outlined"
                density="compact" type="date"
                :rules="contractDateRules" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.execution_term" label="Срок исполнения" variant="outlined"
                density="compact" type="date"
                :rules="executionTermRules" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.execution_term_changed" label="Срок (с учётом изменений)"
                variant="outlined" density="compact" type="date" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 5. Акт приёмки -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Акт приёмки</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="form.acceptance_doc_name" label="Наименование документа" variant="outlined" density="compact"
                :hint="needsAcceptance ? 'Обязательно для перехода в статус Поставлено' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.acceptance_doc_number" label="Номер акта" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model="form.acceptance_doc_date" label="Дата акта" variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.acceptance_doc_amount" label="Сумма акта" variant="outlined"
                density="compact" type="number" suffix="₽" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 6. Платёж -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Платёж</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.payment_doc_number" label="Номер платёжного поручения" variant="outlined" density="compact"
                :hint="needsPayment ? 'Обязательно для перехода в статус Оплачено' : ''" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="form.payment_doc_date" label="Дата ПП" variant="outlined" density="compact" type="date" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.payment_amount" label="Сумма платежа" variant="outlined"
                density="compact" type="number" suffix="₽" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="form.payment_federal" label="в т.ч. федеральный бюджет" variant="outlined"
                density="compact" type="number" suffix="₽" />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 7. Файлы (только в режиме редактирования) -->
      <v-card v-if="isEdit" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы к закупке</v-card-title>
        <v-card-text>
          <div class="d-flex align-center gap-3 mb-3">
            <v-btn prepend-icon="mdi-upload" variant="tonal" size="small"
              :loading="uploading" @click="fileInputEl?.click()">
              Загрузить файл
            </v-btn>
            <span class="text-caption text-medium-emphasis">PDF, Word, JPEG, PNG</span>
          </div>
          <input ref="fileInputEl" type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
            style="display:none" @change="uploadFile" />

          <v-list v-if="uploadedFiles.length" density="compact" lines="one">
            <v-list-item v-for="f in uploadedFiles" :key="f.id"
              :prepend-icon="fileIcon(f.mime_type)"
              :title="f.filename"
              :subtitle="formatSize(f.size)"
            >
              <template #append>
                <v-btn icon="mdi-download" variant="text" size="small" @click="downloadFile(f.id, f.filename)" />
                <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
                  @click="deleteFile(f.id)" />
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="text-caption text-medium-emphasis">Нет загруженных файлов</div>
        </v-card-text>
      </v-card>

      <!-- 8. Формирование документов (только в режиме редактирования) -->
      <v-card v-if="isEdit" variant="outlined" class="mb-4">
        <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы</v-card-title>
        <v-card-text>
          <div class="d-flex gap-3 flex-wrap">
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'service_note'"
              @click="downloadDoc('service_note')"
            >
              Служебная записка
            </v-btn>
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'contract_tz'"
              @click="downloadDoc('contract_tz')"
            >
              Договор + ТЗ
            </v-btn>
            <v-btn
              prepend-icon="mdi-file-word-outline"
              variant="tonal"
              color="blue-darken-2"
              size="small"
              :loading="docLoading === 'approval_sheet'"
              @click="downloadDoc('approval_sheet')"
            >
              Лист согласования
            </v-btn>
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            Документы формируются по шаблонам из backend/templates/
          </div>
        </v-card-text>
      </v-card>

      <!-- Кнопки -->
      <div class="d-flex gap-3 mt-4 flex-wrap">
        <v-btn type="submit" color="primary" size="large" :loading="saving" prepend-icon="mdi-content-save">
          {{ isEdit ? 'Сохранить' : 'Создать закупку' }}
        </v-btn>
        <v-btn v-if="isEdit && nextStatusTarget" :color="STATUS_COLOR[nextStatusTarget]" size="large"
          variant="tonal" :loading="transitioning" prepend-icon="mdi-arrow-right-circle" @click="doTransition">
          → {{ STATUS_LABEL[nextStatusTarget] }}
        </v-btn>
        <v-btn variant="outlined" to="/orders" size="large">Отмена</v-btn>
      </div>
    </v-form>

    <!-- Диалог подтверждения превышения бюджета -->
    <v-dialog v-model="budgetOverrideDialog" max-width="480">
      <v-card>
        <v-card-title class="text-h6 d-flex align-center ga-2">
          <v-icon color="warning">mdi-alert</v-icon>
          Превышение бюджета субсидии
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" class="mb-3">
            Сумма закупки превышает остаток бюджета субсидии на
            <strong>{{ budgetInfo ? formatMoney(budgetInfo.over) : '' }}</strong>.
          </v-alert>
          Как администратор вы можете сохранить закупку с превышением бюджета.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="outlined" @click="budgetOverrideDialog = false">Отмена</v-btn>
          <v-btn color="warning" variant="flat" :loading="saving" @click="doSave(true)">
            Сохранить с превышением
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3500" location="bottom right">
      {{ snack.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => !!route.params.id)
const purchaseId = computed(() => Number(route.params.id) || null)

const STATUS_ORDER = ['planned', 'confirmed', 'contracted', 'delivered', 'paid']
const STATUS_LABEL: Record<string, string> = {
  planned: 'Планируется', confirmed: 'Подтверждено',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_COLOR: Record<string, string> = {
  planned: 'orange', confirmed: 'blue',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const COUNTRIES = ['Российская Федерация', 'Беларусь', 'Казахстан', 'Китай', 'Германия', 'США', 'Япония', 'Турция', 'Индия']

interface FeoCategory { id: number; name: string; parent_id: number | null; level: number; subsidy_id: number }
interface Contractor { id: number; name: string; inn?: string }
interface Subsidy { id: number; name: string; year: number; budget: number }
interface Product { id: number; name: string; price?: number; product_type?: string; description?: string; photo_url?: string }
interface OrderItem {
  product_id: number | null
  item_name: string
  item_type: string
  quantity: number | null
  unit: string
  unit_price: number | null
  total_price: number | null
  final_unit_price: number | null
  final_total: number | null
}
interface UploadedFile { id: number; purchase_id: number; filename: string; mime_type?: string; size?: number }

const form = reactive({
  purchase_method: '',
  subsidy_id: null as number | null,
  contractor_id: null as number | null,
  registry_number: '',
  feo_category_id: null as number | null,
  country_origin: 'Российская Федерация',
  contract_price: null as number | null,
  economy: null as number | null,
  price_increase: null as number | null,
  contract_number: '',
  contract_date: '',
  execution_term: '',
  execution_term_changed: '',
  acceptance_doc_name: '',
  acceptance_doc_number: '',
  acceptance_doc_date: '',
  acceptance_doc_amount: null as number | null,
  payment_doc_number: '',
  payment_doc_date: '',
  payment_amount: null as number | null,
  payment_federal: null as number | null,
  status: 'planned',
  purchase_number: null as number | null,
})

const items = ref<OrderItem[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const products = ref<Product[]>([])
const allFeoCategories = ref<FeoCategory[]>([])
const formRef = ref()
const saving = ref(false)
const transitioning = ref(false)
const uploading = ref(false)
const docLoading = ref<string | null>(null)
const snack = reactive({ show: false, text: '', color: 'success' })
const budgetInfo = ref<{ remaining: number; exceeded: boolean; over: number } | null>(null)
const budgetOverrideDialog = ref(false)
const isAdmin = computed(() => localStorage.getItem('user_role') === 'admin')
const contractorInn = ref('')
const fileInputEl = ref<HTMLInputElement | null>(null)
const uploadedFiles = ref<UploadedFile[]>([])

const totalNmck = computed(() =>
  items.value.reduce((s, i) => s + (i.total_price || 0), 0)
)

const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }
const formatMoney = (v: number) => v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
const formatSize = (bytes?: number) => !bytes ? '' : bytes > 1048576 ? (bytes / 1048576).toFixed(1) + ' МБ' : (bytes / 1024).toFixed(0) + ' КБ'

const fileIcon = (mime?: string) => {
  if (!mime) return 'mdi-file'
  if (mime === 'application/pdf') return 'mdi-file-pdf-box'
  if (mime.startsWith('image/')) return 'mdi-file-image'
  if (mime.includes('word')) return 'mdi-file-word'
  return 'mdi-file'
}

// FEO - flat list filtered by subsidy
const flatFeoForSubsidy = computed(() =>
  form.subsidy_id
    ? allFeoCategories.value.filter(c => c.subsidy_id === form.subsidy_id)
    : allFeoCategories.value
)

const onSubsidyChange = () => { form.feo_category_id = null; calcBudget() }

const calcEconomy = () => {
  form.economy = (totalNmck.value > 0 && form.contract_price != null)
    ? Math.round((totalNmck.value - form.contract_price) * 100) / 100
    : null
}

const calcBudget = async () => {
  if (!form.subsidy_id) { budgetInfo.value = null; return }
  try {
    const all = await apiFetch<any[]>(`/purchases/?subsidy_id=${form.subsidy_id}`)
    const subsidy = subsidies.value.find(s => s.id === form.subsidy_id)
    if (!subsidy) return
    const total = all
      .filter(p => !purchaseId.value || p.id !== purchaseId.value)
      .reduce((s, p) => s + (Number(p.planned_total_price) || 0), 0)
    const mine = totalNmck.value
    const remaining = subsidy.budget - total - mine
    budgetInfo.value = { remaining, exceeded: remaining < 0, over: remaining < 0 ? -remaining : 0 }
  } catch {}
}

watch(totalNmck, () => { calcEconomy(); calcBudget() })

// Items
const addItem = () => {
  items.value.push({ product_id: null, item_name: '', item_type: 'товар', quantity: null, unit: 'шт.', unit_price: null, total_price: null, final_unit_price: null, final_total: null })
}

const removeItem = (idx: number) => {
  items.value.splice(idx, 1)
}

const calcItemTotal = (idx: number) => {
  const item = items.value[idx]
  if (item.quantity != null && item.unit_price != null) {
    item.total_price = Math.round(item.quantity * item.unit_price * 100) / 100
  } else {
    item.total_price = null
  }
}

const onItemProductSelect = (idx: number, val: any) => {
  const item = items.value[idx]
  const name = typeof val === 'object' && val !== null ? val.name || val : val
  item.item_name = name || ''
  const prod = products.value.find(p => p.name === name)
  if (prod) {
    item.product_id = prod.id
    if (prod.product_type && !item.item_type) item.item_type = prod.product_type
    if (prod.price && !item.unit_price) {
      item.unit_price = Number(prod.price)
      calcItemTotal(idx)
    }
  } else {
    item.product_id = null
  }
}

// Date validation rules
const contractDateRules = computed(() => [
  (v: string) => !v || !form.execution_term || v <= form.execution_term
    || 'Дата договора не может быть позже срока исполнения',
])
const executionTermRules = computed(() => [
  (v: string) => !v || !form.execution_term_changed || v <= form.execution_term_changed
    || 'Срок исполнения не может быть позже изменённого срока',
])

const nextStatusTarget = computed(() => {
  if (!isEdit.value || !form.status) return null
  const idx = STATUS_ORDER.indexOf(form.status)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? STATUS_ORDER[idx + 1] : null
})

const needsContract = computed(() => form.status === 'confirmed')
const needsAcceptance = computed(() => form.status === 'contracted')
const needsPayment = computed(() => form.status === 'delivered')

const loadRefs = async () => {
  const [subs, cons, feos, prods] = await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/'),
    apiFetch<Contractor[]>('/contractors/'),
    apiFetch<FeoCategory[]>('/feo-categories/'),
    apiFetch<Product[]>('/products/'),
  ])
  subsidies.value = subs
  contractors.value = cons
  allFeoCategories.value = feos
  products.value = prods
}

const contractorFilter = (value: string, query: string, item?: any): boolean => {
  const q = query.toLowerCase()
  const name = (item?.raw?.name || '').toLowerCase()
  const inn = (item?.raw?.inn || '').toLowerCase()
  return name.includes(q) || inn.includes(q)
}

const onContractorSelect = (id: number | null) => {
  const c = contractors.value.find(c => c.id === id)
  contractorInn.value = c?.inn || ''
}

const onInnInput = (val: string) => {
  const c = contractors.value.find(c => c.inn === val.trim())
  if (c) form.contractor_id = c.id
}

const loadPurchase = async () => {
  const data = await apiFetch<any>(`/purchases/${purchaseId.value}`)
  Object.assign(form, {
    purchase_method: data.purchase_method || '',
    subsidy_id: data.subsidy_id ?? null,
    contractor_id: data.contractor_id ?? null,
    registry_number: data.registry_number || '',
    feo_category_id: data.feo_category_id ?? null,
    country_origin: data.country_origin || 'Российская Федерация',
    contract_price: data.contract_price ? Number(data.contract_price) : null,
    economy: data.economy ? Number(data.economy) : null,
    price_increase: data.price_increase ? Number(data.price_increase) : null,
    contract_number: data.contract_number || '',
    contract_date: data.contract_date || '',
    execution_term: data.execution_term || '',
    execution_term_changed: data.execution_term_changed || '',
    acceptance_doc_name: data.acceptance_doc_name || '',
    acceptance_doc_number: data.acceptance_doc_number || '',
    acceptance_doc_date: data.acceptance_doc_date || '',
    acceptance_doc_amount: data.acceptance_doc_amount ? Number(data.acceptance_doc_amount) : null,
    payment_doc_number: data.payment_doc_number || '',
    payment_doc_date: data.payment_doc_date || '',
    payment_amount: data.payment_amount ? Number(data.payment_amount) : null,
    payment_federal: data.payment_federal ? Number(data.payment_federal) : null,
    status: data.status || 'planned',
    purchase_number: data.purchase_number ?? null,
  })

  // Load items
  if (data.items && data.items.length) {
    items.value = data.items.map((i: any) => ({
      product_id: i.product_id ?? null,
      item_name: i.item_name || '',
      item_type: i.item_type || 'товар',
      quantity: i.quantity ? Number(i.quantity) : null,
      unit: i.unit || '',
      unit_price: i.unit_price ? Number(i.unit_price) : null,
      total_price: i.total_price ? Number(i.total_price) : null,
      final_unit_price: i.final_unit_price ? Number(i.final_unit_price) : null,
      final_total: i.final_total ? Number(i.final_total) : null,
    }))
  } else if (data.item_name) {
    // Migrate old single-item purchase
    items.value = [{
      product_id: null,
      item_name: data.item_name,
      item_type: data.item_type || 'товар',
      quantity: data.planned_quantity ? Number(data.planned_quantity) : null,
      unit: data.unit || '',
      unit_price: data.planned_unit_price ? Number(data.planned_unit_price) : null,
      total_price: data.planned_total_price ? Number(data.planned_total_price) : null,
      final_unit_price: data.final_unit_price ? Number(data.final_unit_price) : null,
      final_total: data.final_total_amount ? Number(data.final_total_amount) : null,
    }]
  }

  // Load uploaded files
  uploadedFiles.value = data.files || []

  // Auto-fill INN
  if (data.contractor_id) {
    const c = contractors.value.find(c => c.id === data.contractor_id)
    contractorInn.value = c?.inn || ''
  }

  calcBudget()
}

onMounted(async () => {
  await loadRefs()
  if (isEdit.value && purchaseId.value) await loadPurchase()
})

const save = async () => {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  if (budgetInfo.value?.exceeded) {
    if (!isAdmin.value) {
      showSnack('Превышение бюджета субсидии. Сохранение недоступно.', 'error')
      return
    }
    budgetOverrideDialog.value = true
    return
  }
  await doSave(false)
}

const doSave = async (adminOverride: boolean) => {
  budgetOverrideDialog.value = false
  saving.value = true
  try {
    const validItems = items.value.filter(i => i.item_name?.trim())
    const payload = {
      ...form,
      planned_total_price: totalNmck.value || null,
      total_nmck: totalNmck.value || null,
      contract_date: form.contract_date || null,
      execution_term: form.execution_term || null,
      execution_term_changed: form.execution_term_changed || null,
      acceptance_doc_date: form.acceptance_doc_date || null,
      payment_doc_date: form.payment_doc_date || null,
      items: validItems,
    }
    const qs = adminOverride ? '?admin_override=true' : ''
    if (isEdit.value) {
      await apiFetch(`/purchases/${purchaseId.value}${qs}`, { method: 'PUT', body: payload })
      showSnack('Сохранено')
    } else {
      const created = await apiFetch<any>(`/purchases/${qs}`, { method: 'POST', body: payload })
      showSnack('Закупка создана')
      router.push(`/orders/${created.id}/edit`)
    }
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

const doTransition = async () => {
  if (!nextStatusTarget.value || !purchaseId.value) return
  transitioning.value = true
  try {
    const updated = await apiFetch<any>(
      `/purchases/${purchaseId.value}/transition?status=${nextStatusTarget.value}`,
      { method: 'POST' }
    )
    form.status = updated.status
    showSnack(`Статус → ${STATUS_LABEL[updated.status]}`)
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка смены статуса', 'error')
  } finally {
    transitioning.value = false
  }
}

// File upload
const uploadFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || !purchaseId.value) return
  uploading.value = true
  try {
    const file = input.files[0]
    const fd = new FormData()
    fd.append('file', file)
    const token = localStorage.getItem('access_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/files`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json()
      showSnack(err.detail || 'Ошибка загрузки', 'error')
      return
    }
    const uploaded = await res.json()
    uploadedFiles.value.push(uploaded)
    showSnack('Файл загружен')
  } catch {
    showSnack('Ошибка загрузки файла', 'error')
  } finally {
    uploading.value = false
    if (fileInputEl.value) fileInputEl.value.value = ''
  }
}

const downloadFile = async (fid: number, filename: string) => {
  const token = localStorage.getItem('access_token')
  const res = await fetch(`/api/purchases/${purchaseId.value}/files/${fid}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) { showSnack('Ошибка скачивания', 'error'); return }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

const deleteFile = async (fid: number) => {
  try {
    await apiFetch(`/purchases/${purchaseId.value}/files/${fid}`, { method: 'DELETE' })
    uploadedFiles.value = uploadedFiles.value.filter(f => f.id !== fid)
    showSnack('Файл удалён')
  } catch {
    showSnack('Ошибка удаления', 'error')
  }
}

const downloadDoc = async (docType: string) => {
  if (!purchaseId.value) return
  docLoading.value = docType
  try {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token')
    const res = await fetch(`/api/purchases/${purchaseId.value}/documents/${docType}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Ошибка генерации документа' }))
      showSnack(err.detail || 'Ошибка генерации документа', 'error')
      return
    }
    const blob = await res.blob()
    const disposition = res.headers.get('Content-Disposition') || ''
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = match ? match[1] : `${docType}.docx`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  } catch {
    showSnack('Ошибка скачивания документа', 'error')
  } finally {
    docLoading.value = null
  }
}
</script>
