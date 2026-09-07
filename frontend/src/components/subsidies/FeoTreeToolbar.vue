<template>
  <!-- Контрагент -->
  <div v-if="ctx.selectedSubsidy.value?.contractor_name" class="detail-contractor mt-2 mb-3">
    <v-icon icon="mdi-account-tie" size="16" color="teal" class="mr-1" />
    <span class="text-body-2 font-weight-medium">{{ ctx.selectedSubsidy.value?.contractor_name }}</span>
    <span v-if="ctx.selectedSubsidy.value?.contractor_inn" class="text-caption text-medium-emphasis ml-2">ИНН {{ ctx.selectedSubsidy.value?.contractor_inn }}</span>
    <v-btn
      icon="mdi-pencil-outline" size="x-small" variant="text" color="teal" class="ml-2"
      title="Реквизиты контрагента для этой субсидии"
      @click="ctx.openContractorOverride(ctx.selectedSubsidy.value!)"
    />
  </div>

  <div class="detail-feo-header">
    <span class="chart-card-title">Направления ФЭО</span>
    <div class="d-flex align-center ml-4" style="gap:6px" title="Группировка позиций «из заявок» при раскрытии направления">
      <span class="text-caption text-medium-emphasis">Позиции:</span>
      <v-btn-toggle v-model="ctx.feoItemsGroupBy.value" density="compact" mandatory variant="outlined" color="teal" style="height:26px" :disabled="ctx.plannedBase.value === 'purchases'">
        <v-btn size="x-small" value="none">Нет</v-btn>
        <v-btn size="x-small" value="category">По категориям</v-btn>
        <v-btn size="x-small" value="category_type">Категории + виды</v-btn>
      </v-btn-toggle>
    </div>
    <div class="d-flex align-center ml-auto" style="gap:8px">
      <v-btn size="small" variant="outlined" color="success" prepend-icon="mdi-file-excel-outline" @click="openExportVersionsDialog">Выгрузить ФЭО</v-btn>
      <template v-if="ctx.canEditFeo.value">
        <v-btn size="small" variant="outlined" prepend-icon="mdi-download-outline" @click="ctx.downloadFeoTemplate(ctx.selectedSubsidy.value?.id, ctx.selectedSubsidy.value?.name)">Шаблон</v-btn>
        <v-btn size="small" variant="outlined" color="secondary" prepend-icon="mdi-upload-outline" @click="feoImport.show = true">Импорт</v-btn>
      </template>
      <!-- 12-04: Version history -->
      <v-btn size="small" variant="text" color="blue-grey" prepend-icon="mdi-history" @click="openVersionHistory">
        История
      </v-btn>
      <!-- 12-05: Save version -->
      <v-btn
        v-if="canSaveVersion"
        size="small"
        variant="text"
        color="success"
        prepend-icon="mdi-content-save"
        @click="openSaveVersionDialog"
      >
        Сохранить редакцию
      </v-btn>
      <!-- 12-04: Export dropdown -->
      <v-menu>
        <template #activator="{ props: menuProps }">
          <v-btn size="small" variant="outlined" color="teal" prepend-icon="mdi-export" append-icon="mdi-chevron-down" v-bind="menuProps">
            Экспорт
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item prepend-icon="mdi-microsoft-excel" @click="exportPlanGraphExcel">
            <v-list-item-title>Excel (.xlsx)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-microsoft-word" @click="exportPlanGraphDocx">
            <v-list-item-title>Word (шаблон)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-file-pdf-box" @click="exportFeoPdf">
            <v-list-item-title>PDF (как на экране)</v-list-item-title>
          </v-list-item>
          <v-divider />
          <v-list-item prepend-icon="mdi-upload-outline">
            <v-list-item-title>
              <label style="cursor:pointer">
                Загрузить шаблон .docx
                <input type="file" accept=".docx" style="display:none"
                  @change="(e: any) => { if (e.target.files[0]) uploadTemplate(e.target.files[0]) }" />
              </label>
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
      <v-btn v-if="ctx.canEditFeo.value" size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="ctx.openAddFeoDialog(null)">Добавить</v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { useRegistryExport } from '@/composables/useRegistryExport'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

// Тот же гейт, что и в SubsidyEditDialog.vue (canSaveVersion) — вычисляется
// независимо здесь же (см. комментарий там же: используется в нескольких
// местах вне диалога, которые остаются вне общего ctx — простая проверка роли
// из localStorage, не формула, дублирование не нарушает Правило №6).
const userRoleRaw = localStorage.getItem('user_role') || ''
const canSaveVersion = computed(() => ['superadmin', 'org_admin', 'admin', 'account_owner'].includes(userRoleRaw))

const { openVersionHistory, openExportVersionsDialog, openSaveVersionDialog } = usePlanGraphVersions(ctx)
const { feoImport } = useFeoImport(ctx)

const { exportScreenshotPdf: _exportFeoScreenshotPdf } = useRegistryExport()

function exportPlanGraphExcel() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${ctx.selectedId.value}/plan-graph/export`
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(r => r.blob())
    .then(blob => {
      const bUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = bUrl
      a.click()
      URL.revokeObjectURL(bUrl)
    })
}

async function exportPlanGraphDocx() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${ctx.selectedId.value}/plan-graph/export-docx`
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    showSnack(err.message || 'Шаблон не загружен', 'error')
    return
  }
  const blob = await r.blob()
  const bUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = bUrl
  a.click()
  URL.revokeObjectURL(bUrl)
}

async function exportFeoPdf() {
  if (!ctx.feoTableArea.value) { showSnack('Таблица ФЭО не готова', 'error'); return }
  try {
    const name = `ФЭО_${ctx.selectedSubsidy.value?.name ?? ''}`.trim()
    await _exportFeoScreenshotPdf(ctx.feoTableArea.value, name, undefined, {
      // Колонка «Действия» нефункциональна в PDF и съедает место — скрыть.
      hideSelectors: ['.feo-th-actions', '.feo-td-actions'],
      // С table-layout:fixed «Наименование» ужимается в столбик; auto + перенос по словам.
      extraCss: '.feo-table{table-layout:auto!important;width:100%!important}'
        + '.feo-th-name,.feo-td-name{min-width:280px!important;white-space:normal!important}'
        + '.feo-name{word-break:normal!important;overflow-wrap:anywhere!important}',
    })
  } catch (e: any) {
    showSnack(e?.message ?? 'Ошибка экспорта PDF', 'error')
  }
}

async function uploadTemplate(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const token = localStorage.getItem('auth_token') || ''
  const r = await fetch(`/api/subsidies/${ctx.selectedId.value}/plan-graph/template`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  })
  const data = await r.json()
  if (r.ok) {
    showSnack('Шаблон загружен')
  } else {
    showSnack(data.message || 'Ошибка загрузки', 'error')
  }
}
</script>
