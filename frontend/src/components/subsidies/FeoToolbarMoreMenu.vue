<template>
  <v-menu>
    <template #activator="{ props: moreMenuProps }">
      <v-btn size="small" variant="outlined" color="blue-grey" prepend-icon="mdi-dots-horizontal"
        append-icon="mdi-chevron-down" v-bind="moreMenuProps">
        Ещё
      </v-btn>
    </template>
    <v-list density="compact" style="max-width: 420px">
      <!-- Группа «Загрузка» -->
      <template v-if="ctx.canEditFeo.value">
        <v-list-subheader>Загрузка</v-list-subheader>
        <v-list-item prepend-icon="mdi-upload-outline" @click="feoImport.show = true">
          <v-list-item-title>Импорт ФЭО</v-list-item-title>
        </v-list-item>
        <v-list-item prepend-icon="mdi-file-swap-outline" @click="openFactImport">
          <v-list-item-title>Новый импорт факта</v-list-item-title>
        </v-list-item>
        <v-list-item prepend-icon="mdi-history" @click="openFactImportRuns">
          <v-list-item-title>Журнал импорта факта</v-list-item-title>
        </v-list-item>
        <v-list-item prepend-icon="mdi-download-outline"
          @click="ctx.downloadFeoTemplate(ctx.selectedSubsidy.value?.id, ctx.selectedSubsidy.value?.name)">
          <v-list-item-title>Шаблон старого импорта ФЭО</v-list-item-title>
          <v-list-item-subtitle style="white-space:normal">Если часть закупок уже прошла — заполните блок «Факт»: после загрузки плана система предложит загрузить их.</v-list-item-subtitle>
        </v-list-item>
        <v-list-item prepend-icon="mdi-file-upload-outline" @click="roundtripImportDialog?.open()">
          <v-list-item-title>Загрузить выгрузку ФЭО</v-list-item-title>
          <v-list-item-subtitle style="white-space:normal">Файл из «Выгрузить ФЭО»: изменённые суммы и названия, новые строки.</v-list-item-subtitle>
        </v-list-item>
        <v-list-item prepend-icon="mdi-file-document-outline" @click="downloadFeoRoundtripTemplate">
          <v-list-item-title>Шаблон выгрузки ФЭО (с примером)</v-list-item-title>
          <v-list-item-subtitle style="white-space:normal">Формат «Загрузить выгрузку ФЭО» с вымышленным примером и листом «Как заполнять».</v-list-item-subtitle>
        </v-list-item>
        <v-divider />
      </template>

      <!-- Группа «Выгрузка» -->
      <v-list-subheader>Выгрузка</v-list-subheader>
      <v-list-item prepend-icon="mdi-file-excel-outline" @click="openExportVersionsDialog">
        <v-list-item-title>Выгрузить ФЭО</v-list-item-title>
      </v-list-item>
      <v-list-item prepend-icon="mdi-microsoft-excel" @click="exportPlanGraphExcel">
        <v-list-item-title>Экспорт в Excel (.xlsx)</v-list-item-title>
      </v-list-item>
      <v-list-item prepend-icon="mdi-microsoft-word" @click="exportPlanGraphDocx">
        <v-list-item-title>Экспорт в Word (шаблон)</v-list-item-title>
      </v-list-item>
      <v-list-item prepend-icon="mdi-file-pdf-box" @click="exportFeoPdf">
        <v-list-item-title>Экспорт в PDF (как на экране)</v-list-item-title>
      </v-list-item>
      <v-list-item prepend-icon="mdi-upload-outline" @click="templateFileInput?.click()">
        <v-list-item-title>Загрузить шаблон .docx</v-list-item-title>
      </v-list-item>
      <v-divider />

      <!-- Группа «Прочее» -->
      <v-list-subheader>Прочее</v-list-subheader>
      <v-list-item v-if="feoCollapse.candidatesCount.value > 0" prepend-icon="mdi-arrow-collapse-up"
        @click="feoCollapse.openBulkDialog(ctx.selectedId.value!)">
        <v-list-item-title>Свернуть категории-дубли ({{ feoCollapse.candidatesCount.value }})</v-list-item-title>
      </v-list-item>
      <v-list-item prepend-icon="mdi-history" @click="openVersionHistory">
        <v-list-item-title>История</v-list-item-title>
      </v-list-item>
      <v-list-item v-if="canSaveVersion" prepend-icon="mdi-equal-box"
        @click="ctx.selectedId.value && alignAllDialog?.open(ctx.selectedId.value)">
        <v-list-item-title>Приравнять ФЭО к плану по всем статьям</v-list-item-title>
        <v-list-item-subtitle style="white-space:normal">ФЭО каждой статьи субсидии станет равным её полной плановой сумме</v-list-item-subtitle>
      </v-list-item>
      <v-list-item v-if="canSaveVersion" prepend-icon="mdi-content-save" @click="openSaveVersionDialog">
        <v-list-item-title>Сохранить редакцию</v-list-item-title>
      </v-list-item>
      <v-list-item v-if="canSaveVersion" prepend-icon="mdi-label-off-outline" @click="emit('clear-source-rows')">
        <v-list-item-title>Убрать номера строк файла</v-list-item-title>
      </v-list-item>
    </v-list>
  </v-menu>

  <input ref="templateFileInput" type="file" accept=".docx" style="display:none"
    @change="(e: any) => { if (e.target.files[0]) uploadTemplate(e.target.files[0]) }" />

  <FactImportWizard />
  <FactImportRunsPanel />
  <AlignBudgetAllDialog ref="alignAllDialog" />
  <SubsidyExportDialog
    ref="subsidyExportDialog"
    :subsidy-id="ctx.selectedId.value ?? null"
    :subsidy-name="ctx.selectedSubsidy.value?.name"
    :show-snack="(msg, col) => emit('snack', msg, col)"
  />
  <FeoRoundtripImportDialog
    ref="roundtripImportDialog"
    :subsidy-id="ctx.selectedId.value ?? null"
    :show-snack="(msg, col) => emit('snack', msg, col)"
    :on-applied="() => ctx.selectedId.value != null && ctx.loadFeo(ctx.selectedId.value)"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import { useRegistryExport } from '@/composables/useRegistryExport'
import { useFeoCategoryCollapse } from '@/composables/subsidies/useFeoCategoryCollapse'
import FactImportWizard from '@/components/subsidies/fact-import/FactImportWizard.vue'
import FactImportRunsPanel from '@/components/subsidies/fact-import/FactImportRunsPanel.vue'
import AlignBudgetAllDialog from '@/components/subsidies/AlignBudgetAllDialog.vue'
import SubsidyExportDialog from '@/components/subsidies/SubsidyExportDialog.vue'
import FeoRoundtripImportDialog from '@/components/subsidies/FeoRoundtripImportDialog.vue'
import { filenameFromContentDisposition } from '@/utils/contentDisposition'

const props = defineProps<{
  canSaveVersion: boolean
}>()

const emit = defineEmits<{
  'clear-source-rows': []
  snack: [msg: string, color?: string]
}>()

const ctx = useSubsidyDetailCtx()
const feoCollapse = useFeoCategoryCollapse()
const { openVersionHistory, openExportVersionsDialog, openSaveVersionDialog } = usePlanGraphVersions(ctx)
const { feoImport } = useFeoImport(ctx)
const { openWizard: openFactImportWizard, loadRuns: loadFactImportRuns, factImport: factImportState } = useFactImport()
const { exportScreenshotPdf: _exportFeoScreenshotPdf } = useRegistryExport()

const alignAllDialog = ref<InstanceType<typeof AlignBudgetAllDialog> | null>(null)
const subsidyExportDialog = ref<InstanceType<typeof SubsidyExportDialog> | null>(null)
const roundtripImportDialog = ref<InstanceType<typeof FeoRoundtripImportDialog> | null>(null)
const templateFileInput = ref<HTMLInputElement | null>(null)

function openFactImport() {
  if (ctx.selectedId.value != null) openFactImportWizard(ctx.selectedId.value)
}

function openFactImportRuns() {
  factImportState.subsidyId = ctx.selectedId.value ?? null
  factImportState.runsPanelShow = true
  void loadFactImportRuns()
}

function exportPlanGraphExcel() {
  if (!ctx.selectedId.value) return
  subsidyExportDialog.value?.open()
}

async function exportPlanGraphDocx() {
  const token = localStorage.getItem('auth_token') || ''
  const url = `/api/subsidies/${ctx.selectedId.value}/plan-graph/export-docx`
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    emit('snack', err.message || 'Шаблон не загружен', 'error')
    return
  }
  const blob = await r.blob()
  const bUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = bUrl
  const fallback = `План_график_${ctx.selectedSubsidy.value?.name ?? ''}.docx`.trim()
  a.download = filenameFromContentDisposition(r.headers.get('Content-Disposition'), fallback)
  a.click()
  URL.revokeObjectURL(bUrl)
}

async function exportFeoPdf() {
  const targetEl =
    ctx.feoItemsGroupBy.value === 'category_subsidy'
      ? (document.querySelector<HTMLElement>('.subsidy-category-panel') ?? ctx.feoTableArea.value)
      : (ctx.feoTableArea.value ?? document.querySelector<HTMLElement>('.feo-table-wrap'))
  if (!targetEl) { emit('snack', 'Таблица ФЭО не готова', 'error'); return }
  try {
    const name = `ФЭО_${ctx.selectedSubsidy.value?.name ?? ''}`.trim()
    await _exportFeoScreenshotPdf(targetEl, name, undefined, {
      hideSelectors: ['.feo-th-actions', '.feo-td-actions', '.scp-td-check'],
      extraCss: '.feo-table,.scp-table{table-layout:auto!important;width:100%!important}'
        + '.feo-th-name,.feo-td-name,.scp-td-name{min-width:280px!important;white-space:normal!important}'
        + '.feo-name,.scp-td-name{word-break:normal!important;overflow-wrap:anywhere!important}',
    })
  } catch (e: any) {
    emit('snack', e?.message ?? 'Ошибка экспорта PDF', 'error')
  }
}

async function downloadFeoRoundtripTemplate() {
  const token = localStorage.getItem('auth_token') || ''
  const r = await fetch('/api/feo-categories/roundtrip/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    emit('snack', err.message || err.detail || 'Не удалось скачать шаблон', 'error')
    return
  }
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filenameFromContentDisposition(r.headers.get('Content-Disposition'), 'Шаблон_выгрузки_ФЭО.xlsx')
  a.click()
  URL.revokeObjectURL(url)
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
    emit('snack', 'Шаблон загружен', 'success')
  } else {
    emit('snack', data.message || 'Ошибка загрузки', 'error')
  }
}
</script>
