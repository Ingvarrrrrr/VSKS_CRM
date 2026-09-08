<template>
  <!-- ── Import Dialog ── -->
  <v-dialog v-model="state.show" max-width="580" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-5 pb-2 d-flex align-center">
        <v-icon icon="mdi-file-import" color="blue" class="mr-2" />
        Импорт закупок из Excel
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="resetImport" />
      </v-card-title>
      <v-card-text class="pa-5 pt-2">

        <!-- Step 1: Setup -->
        <template v-if="state.step === 1">
          <!-- Format selection -->
          <v-radio-group v-model="state.format" inline class="mb-3" hide-details density="compact">
            <template #label><span class="text-body-2 font-weight-medium mr-3">Формат файла:</span></template>
            <v-radio value="standard" label="Универсальный" />
            <v-radio value="feo" label="ФЭО-формат (57 колонок)" />
          </v-radio-group>

          <!-- Standard: subsidy REQUIRED -->
          <v-select
            v-if="state.format === 'standard'"
            v-model="state.subsidyId"
            :items="subsidies"
            item-title="name" item-value="id"
            label="Субсидия *"
            variant="outlined" density="compact" class="mb-3"
            :rules="[(v: any) => !!v || 'Обязательное поле']"
          />

          <!-- Standard: format hint -->
          <v-alert
            v-if="state.format === 'standard'"
            type="info" variant="tonal" density="compact" class="mb-3"
            icon="mdi-information-outline"
          >
            <div class="text-body-2">
              <strong>Форматы:</strong> Excel (.xlsx, .xls)<br>
              <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
              <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
            </div>
          </v-alert>

          <!-- FEO: info banner -->
          <v-alert
            v-else
            type="info" variant="tonal" density="compact" class="mb-3"
            prepend-icon="mdi-information-outline"
          >
            Субсидия определяется автоматически по категории ФЭО (колонка 5). Заголовки — в строке 6.
          </v-alert>

          <!-- FEO: assigned user selector -->
          <v-autocomplete
            v-if="state.format === 'feo'"
            v-model="state.assignedUserId"
            :items="importUserItems"
            item-title="text"
            item-value="value"
            label="Ответственный исполнитель"
            hint="Все импортируемые закупки будут назначены на этого сотрудника"
            persistent-hint
            variant="outlined"
            density="compact"
            class="mb-3"
            :rules="[(v: any) => !!v || 'Обязательное поле']"
            clearable
          />

          <FileDropZone v-model="state.file"
            accept=".xlsx,.xls"
            hint="Excel (.xlsx, .xls) — перетащите или нажмите"
            class="mb-2" />

          <div v-if="state.format === 'standard'" class="mt-3 text-caption text-medium-emphasis">
            <div class="mb-1">Колонки листа 1 <span class="text-error">(*</span> — обязательны, красные в файле):</div>
            <span class="fz-11">
              Тип договора, Номер закупки, Номер заказа внутри закупки,
              Предмет договора (общий),
              <span class="text-error">Наименование товара*</span>,
              ФЭО Ур.1<span class="text-error">*</span>…Ур.5,
              Мероприятие, Контрагент,
              <span class="text-error">ИНН контрагента*</span>,
              Способ закупки, Реестровый №,
              <span class="text-error">№ договора*</span>,
              <span class="text-error">Дата договора*</span>,
              Максимальная цена договора, Срок исполнения, Статус,
              <span class="text-error">Количество (план)*</span>,
              Ед.изм.,
              <span class="text-error">Цена за ед. (план)*</span>,
              Сумма план, Кол-во факт, Цена за ед. (факт),
              <span class="text-error">Сумма факт*</span>,
              Страна, Ставка НДС, Год
            </span>
            <div class="mt-2 fz-11">
              <strong>Платежи</strong> заполняются прямо в строках листа «Закупки»: колонки
              «Номер платёжного документа», «Дата платёжного документа», «Сумма оплаты», «Назначение платежа».
              Помесячные / несколько платежей по одному договору — отдельная строка с тем же Номером закупки/заказа.
            </div>
            <div class="mt-1 fz-11">
              <strong>Заказы</strong> внутри одной закупки — отдельными строками с одним «Номер закупки» и разным «Номер заказа».
            </div>
            <div class="mt-1 fz-11">
              <strong>ФЭО</strong> — по уровням в отдельных колонках, заполняйте сколько есть.
            </div>
            <div class="mt-1 text-error fz-11">Красные колонки в шаблоне обязательны.</div>
          </div>
        </template>

        <!-- Step 'preview': Preview (standard only) -->
        <template v-else-if="state.step === 'preview'">
          <div class="text-body-2 font-weight-medium mb-2">
            Предпросмотр — {{ state.preview?.purchases?.length ?? 0 }} закупок
            <span v-if="previewPaymentsTotal > 0" class="text-medium-emphasis ml-2">/ {{ previewPaymentsTotal }} платежей</span>
          </div>
          <v-table density="compact" class="import-preview-table mb-3">
            <thead>
              <tr>
                <th>Закупка / Заказ</th>
                <th>№ договора</th>
                <th>Контрагент</th>
                <th>ФЭО путь</th>
                <th class="text-right">Позиций</th>
                <th class="text-right">Платежей</th>
                <th class="text-right">План</th>
                <th class="text-right">Факт</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="p in state.preview?.purchases" :key="p.group_key"
                :class="[p.skipped ? 'import-preview-skipped' : '', p.duplicate_matches?.length ? 'import-preview-dup' : '']"
              >
                <td class="fz-11">
                  <span v-if="(p as any).purchase_group || (p as any).order_number">
                    {{ (p as any).purchase_group || '—' }}<template v-if="(p as any).order_number"> / {{ (p as any).order_number }}</template>
                  </span>
                  <span v-else>—</span>
                </td>
                <td>
                  <span :class="p.skipped ? 'text-decoration-line-through text-medium-emphasis' : ''">{{ p.contract_number || '—' }}</span>
                </td>
                <td>{{ p.contractor || '—' }}</td>
                <td class="text-truncate" style="max-width:120px">
                  <v-tooltip v-if="p.feo_path" :text="p.feo_path" location="top">
                    <template #activator="{ props: tp }">
                      <span v-bind="tp">{{ p.feo_path }}</span>
                    </template>
                  </v-tooltip>
                  <span v-else>—</span>
                </td>
                <td class="text-right">{{ p.items_count }}</td>
                <td class="text-right">{{ (p as any).payments_count ?? '—' }}</td>
                <td class="text-right">{{ p.plan_total?.toLocaleString('ru-RU') ?? '—' }}</td>
                <td class="text-right">{{ p.fact_total?.toLocaleString('ru-RU') ?? '—' }}</td>
                <td>
                  <v-tooltip v-if="p.skipped && p.skip_reason" :text="p.skip_reason" location="top">
                    <template #activator="{ props: tp }">
                      <v-chip v-bind="tp" color="warning" size="x-small" label>Пропуск</v-chip>
                    </template>
                  </v-tooltip>
                  <v-chip v-else-if="!p.skipped" color="success" size="x-small" label>{{ p.status || 'OK' }}</v-chip>
                  <v-chip v-if="!p.skipped && p.duplicate_matches?.length" color="warning" size="x-small" label class="ml-1">
                    Возможный повтор
                  </v-chip>
                </td>
              </tr>
            </tbody>
          </v-table>
          <div v-if="(state.preview?.duplicates_count ?? 0) > 0" class="mb-3">
            <v-alert type="warning" variant="tonal" density="compact">
              <div class="text-caption font-weight-bold mb-1">
                Возможные повторы: {{ state.preview?.duplicates_count }}
              </div>
              <div class="text-caption mb-2">
                Разовые закупки с таким же контрагентом и суммой уже есть. Проверьте — это разные закупки или дубли.
              </div>
              <div v-for="p in state.preview?.purchases?.filter((x: any) => x.duplicate_matches?.length)" :key="'dup-' + p.group_key" class="mb-2">
                <div class="text-caption font-weight-medium">
                  {{ p.contractor || '—' }}<template v-if="p.contract_number"> · №{{ p.contract_number }}</template>
                  <template v-if="p.plan_total != null"> · {{ p.plan_total.toLocaleString('ru-RU') }} ₽</template>
                </div>
                <ul class="text-caption ml-4 mb-0">
                  <li v-for="(m, i) in p.duplicate_matches" :key="i">
                    <a v-if="m.source === 'db' && m.id" :href="`/orders/${m.id}/edit`" target="_blank" rel="noopener">
                      №{{ m.purchase_number ?? m.id }} — {{ m.name || 'без названия' }}
                    </a>
                    <span v-else>{{ m.name }} <em>(в этом же файле)</em></span>
                    <template v-if="m.amount != null"> · {{ m.amount.toLocaleString('ru-RU') }} ₽</template>
                    <template v-if="(m as any).match_reason"> · совпало по: {{ (m as any).match_reason }}</template>
                    <template v-if="m.status"> · {{ m.status }}</template>
                  </li>
                </ul>
              </div>
              <v-checkbox v-model="state.dupAck" density="compact" hide-details
                label="Я проверил повторы — это разные закупки, импортировать" class="mt-1" />
            </v-alert>
          </div>
          <div v-if="(state.preview?.feo_to_create?.length ?? 0) > 0" class="mb-3">
            <v-alert type="info" variant="tonal" density="compact">
              <div class="text-caption font-weight-bold mb-1">
                Будут созданы категории ФЭО ({{ state.preview!.feo_to_create!.length }})
              </div>
              <div class="text-caption mb-2">
                <template v-if="state.preview?.subsidy_has_feo === false">
                  В субсидии ещё нет дерева ФЭО — оно будет создано из файла.
                </template>
                <template v-else>
                  Этих категорий нет в дереве ФЭО субсидии. Проверьте, не опечатка ли это: при импорте они будут созданы как новые.
                </template>
              </div>
              <v-list density="compact" class="import-errors-list bg-transparent pa-0">
                <v-list-item
                  v-for="f in state.preview!.feo_to_create" :key="f.path"
                  :title="f.path"
                  prepend-icon="mdi-folder-plus-outline"
                  color="info"
                />
              </v-list>
              <v-checkbox
                v-if="state.preview?.subsidy_has_feo !== false"
                v-model="state.feoAck"
                density="compact" hide-details
                label="Я проверил список — создать эти категории"
                class="mt-1"
              />
            </v-alert>
          </div>
          <div v-if="(state.preview?.without_event ?? 0) > 0 || state.preview?.warnings?.length" class="mb-3">
            <v-alert type="warning" variant="tonal" density="compact">
              <div class="text-caption font-weight-bold mb-1">
                Без мероприятия: {{ state.preview?.without_event ?? 0 }}
              </div>
              <div class="text-caption mb-2">
                Эти закупки будут созданы без привязки к мероприятию — привяжите вручную в карточке закупки.
              </div>
              <v-list v-if="state.preview?.warnings?.length" density="compact" class="import-errors-list bg-transparent pa-0">
                <v-list-item
                  v-for="w in state.preview!.warnings" :key="'warn-' + w.row"
                  :title="`Строка ${w.row}: ${w.name}`"
                  :subtitle="w.message ?? ''"
                  prepend-icon="mdi-calendar-alert"
                  color="warning"
                />
              </v-list>
            </v-alert>
          </div>
          <div v-if="state.preview?.errors?.length || (state.preview as any)?.payments_errors?.length" class="mt-2">
            <v-alert type="error" variant="tonal" density="compact" class="mb-0">
              <div v-if="state.preview?.errors?.length">
                <div class="text-caption font-weight-bold mb-1">Ошибки в строках ({{ state.preview.errors.length }}):</div>
                <v-list density="compact" class="import-errors-list bg-transparent">
                  <v-list-item
                    v-for="e in state.preview.errors" :key="e.row"
                    :title="`Строка ${e.row}: ${e.name}`"
                    :subtitle="e.missing?.length ? 'не заполнено: ' + e.missing.join(', ') : (e.message ?? '')"
                    prepend-icon="mdi-alert-circle-outline"
                    color="error"
                  />
                </v-list>
              </div>
              <div v-if="(state.preview as any)?.payments_errors?.length" class="mt-2">
                <div class="text-caption font-weight-bold mb-1">Ошибки платежей ({{ (state.preview as any).payments_errors.length }}):</div>
                <v-list density="compact" class="import-errors-list bg-transparent">
                  <v-list-item
                    v-for="e in (state.preview as any).payments_errors" :key="e.row ?? e.contract_number"
                    :title="e.contract_number ? `№ договора ${e.contract_number}` : `Строка ${e.row}`"
                    :subtitle="e.message ?? ''"
                    prepend-icon="mdi-alert-circle-outline"
                    color="error"
                  />
                </v-list>
              </div>
            </v-alert>
          </div>
        </template>

        <!-- Step 2: Result -->
        <template v-else-if="state.step === 2">
          <div class="import-result-row">
            <div class="import-stat import-stat--ok">
              <div class="import-stat-val">{{ state.result?.created_purchases ?? 0 }}</div>
              <div class="import-stat-lbl">Закупок</div>
            </div>
            <div class="import-stat import-stat--ok" style="background:rgba(59,130,246,0.1)">
              <div class="import-stat-val">{{ state.result?.created_items ?? 0 }}</div>
              <div class="import-stat-lbl">Позиций</div>
            </div>
            <div class="import-stat import-stat--ok" style="background:rgba(20,184,166,0.1)">
              <div class="import-stat-val">{{ state.result?.created_payments ?? 0 }}</div>
              <div class="import-stat-lbl">Платежей</div>
            </div>
            <div class="import-stat import-stat--skip">
              <div class="import-stat-val">{{ state.result?.skipped ?? 0 }}</div>
              <div class="import-stat-lbl">Пропущено</div>
            </div>
            <div class="import-stat import-stat--err">
              <div class="import-stat-val">{{ state.result?.errors?.length ?? 0 }}</div>
              <div class="import-stat-lbl">Ошибок</div>
            </div>
          </div>
          <div v-if="state.result?.errors?.length" class="mt-4">
            <div class="text-caption font-weight-bold mb-2">Строки с ошибками:</div>
            <v-list density="compact" class="import-errors-list">
              <v-list-item
                v-for="e in state.result.errors" :key="e.row"
                :title="`Строка ${e.row}: ${e.name}`"
                :subtitle="e.missing?.length ? 'не заполнено: ' + e.missing.join(', ') : (e.message ?? '')"
                prepend-icon="mdi-alert-circle-outline"
                color="error"
              />
            </v-list>
          </div>
        </template>

      </v-card-text>
      <v-card-actions class="pa-5 pt-0">
        <div class="d-flex flex-column align-start">
          <v-btn variant="text" size="small" prepend-icon="mdi-download"
            :disabled="state.format === 'standard' && !state.subsidyId"
            @click="downloadTemplate">Скачать шаблон</v-btn>
          <span v-if="templateSubsidyHint" class="text-caption text-medium-emphasis ml-2">{{ templateSubsidyHint }}</span>
        </div>
        <v-spacer />
        <!-- Step 1: setup -->
        <template v-if="state.step === 1">
          <v-btn variant="text" @click="resetImport">Отмена</v-btn>
          <v-btn v-if="state.format === 'standard'" color="blue" variant="flat"
            :loading="state.loading"
            :disabled="!state.file || !state.subsidyId"
            @click="doPreview">
            Предпросмотр
          </v-btn>
          <v-btn v-else color="blue" variant="flat"
            :loading="state.loading" :disabled="!state.file"
            @click="doImport">
            Загрузить
          </v-btn>
        </template>
        <!-- Step 'preview' -->
        <template v-else-if="state.step === 'preview'">
          <v-btn variant="text" @click="state.step = 1">Назад</v-btn>
          <v-btn color="primary" variant="flat"
            :loading="state.loading"
            :disabled="!state.preview?.purchases?.filter((p: any) => !p.skipped).length || ((state.preview?.duplicates_count ?? 0) > 0 && !state.dupAck) || (state.preview?.subsidy_has_feo !== false && (state.preview?.feo_to_create?.length ?? 0) > 0 && !state.feoAck)"
            @click="doImport">
            Импортировать
          </v-btn>
        </template>
        <!-- Step 2: result -->
        <template v-else>
          <v-btn variant="text" @click="resetImport">Закрыть</v-btn>
          <v-btn color="primary" variant="flat" @click="resetImport">Готово</v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import FileDropZone from '@/components/FileDropZone.vue'
import type { ToastType } from '@/composables/useToast'
import type { ImportPreview, ImportResult, Subsidy } from '@/composables/orders/ordersTypes'
import '@/styles/orders-import.css'

const props = defineProps<{
  subsidies: Subsidy[]
  showSnack: (text: string, color?: ToastType) => void
  onImported: () => void
}>()

const { mobile } = useDisplay()

const _importCurrentUserId = parseInt(localStorage.getItem('user_id') || '0')
const importUserItems = ref<{ text: string; value: number }[]>([])

const state = reactive({
  show: false,
  step: 1 as number | 'preview',
  format: 'standard' as 'standard' | 'feo',
  subsidyId: null as number | null,
  assignedUserId: _importCurrentUserId || null as number | null,
  file: null as File | null,
  loading: false,
  preview: null as ImportPreview | null,
  result: null as ImportResult | null,
  dupAck: false,
  feoAck: false,
})

const previewPaymentsTotal = computed(() =>
  (state.preview?.purchases ?? []).reduce((s, p) => s + (p.payments_count ?? 0), 0)
)

// Подсказка у кнопки «Скачать шаблон»: без субсидии в шаблоне не будет каскада ФЭО-списков —
// об этом надо сказать явно, а не молча отдавать урезанный файл.
const templateSubsidyHint = computed(() => {
  if (state.format !== 'standard') return ''
  if (!state.subsidyId) return 'Выберите субсидию — в шаблон подставятся её направления расходов'
  const s = props.subsidies.find(x => x.id === state.subsidyId)
  return `Шаблон с направлениями расходов субсидии «${s?.name ?? state.subsidyId}»`
})

apiFetch<any[]>('/users/in-my-orgs').then(users => {
  importUserItems.value = users.map(u => ({ text: u.full_name || u.username, value: u.id }))
}).catch(() => {})

const resetImport = () => {
  state.show = false
  state.step = 1
  state.format = 'standard'
  state.file = null
  state.subsidyId = null
  state.assignedUserId = _importCurrentUserId || null
  state.preview = null
  state.result = null
  state.dupAck = false
  state.feoAck = false
}

const downloadTemplate = async () => {
  if (state.format === 'standard' && !state.subsidyId) {
    props.showSnack('Сначала выберите субсидию: без неё в шаблоне не будет связанных списков направлений расходов (ФЭО)', 'error')
    return
  }
  const token = localStorage.getItem('auth_token')
  const url = state.format === 'feo'
    ? '/api/purchases/import/feo-format/template'
    : state.subsidyId
      ? `/api/purchases/import/template?subsidy_id=${state.subsidyId}`
      : '/api/purchases/import/template'
  const filename = state.format === 'feo' ? 'Шаблон_импорта_закупок_формат_ФЭО.xlsx' : 'Шаблон_импорта_закупок.xlsx'
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) {
    let detail = 'Не удалось скачать шаблон'
    try {
      const err = await response.json()
      detail = err?.detail || err?.message || detail
    } catch {
      // тело не JSON — оставляем причину по умолчанию
    }
    props.showSnack(`Не удалось скачать шаблон (HTTP ${response.status}): ${detail}`, 'error')
    return
  }
  const blob = await response.blob()
  const blobUrl = window.URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = blobUrl; a.download = filename
  document.body.appendChild(a); a.click()
  window.URL.revokeObjectURL(blobUrl); document.body.removeChild(a)
}

const doPreview = async () => {
  if (!state.file || !state.subsidyId) return
  state.loading = true
  try {
    const formData = new FormData()
    formData.append('file', state.file)
    const token = localStorage.getItem('auth_token')
    const response = await fetch(`/api/purchases/import/preview?subsidy_id=${state.subsidyId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка предпросмотра' }))
      props.showSnack(`[${response.status}] ${err.detail || err.message || 'Ошибка предпросмотра'}`, 'error')
      return
    }
    state.preview = await response.json()
    state.dupAck = false
    state.feoAck = false
    state.step = 'preview'
  } catch (e: any) {
    props.showSnack(e.message || 'Ошибка предпросмотра', 'error')
  } finally {
    state.loading = false
  }
}

const doImport = async () => {
  if (!state.file) return
  state.loading = true
  try {
    const formData = new FormData()
    formData.append('file', state.file)
    const token = localStorage.getItem('auth_token')
    let endpoint: string
    if (state.format === 'feo') {
      const qs = state.assignedUserId ? `?assigned_user_id=${state.assignedUserId}` : ''
      endpoint = `/api/purchases/import/feo-format${qs}`
    } else {
      const qs = state.subsidyId ? `?subsidy_id=${state.subsidyId}` : ''
      endpoint = `/api/purchases/import${qs}`
    }
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка импорта' }))
      props.showSnack(`[${response.status}] ${err.detail || err.message || 'Ошибка импорта'}`, 'error')
      return
    }
    state.result = await response.json()
    state.step = 2
    if ((state.result?.created_purchases ?? 0) > 0) props.onImported()
  } catch (e: any) {
    props.showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    state.loading = false
  }
}

function open() { state.show = true }
defineExpose({ open, downloadTemplate })
</script>

<style scoped>
.import-errors-list { max-height: 200px; overflow-y: auto; border: 1px solid var(--crm-border); border-radius: 8px; }
.fz-11 { font-size: 11px; }
.import-preview-table { border: 1px solid var(--crm-border); border-radius: 8px; max-height: 280px; overflow-y: auto; }
.import-preview-skipped { opacity: 0.55; }
.import-preview-dup { background: rgba(251, 146, 60, 0.08); }
</style>
