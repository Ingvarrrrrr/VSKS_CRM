<template>
  <!-- ── Scans Bulk Upload Dialog ── -->
  <v-dialog v-model="state.show" max-width="640" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-5 pb-2 d-flex align-center">
        <v-icon icon="mdi-folder-upload" color="teal" class="mr-2" />
        Загрузить сканы пачкой
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="resetScans" />
      </v-card-title>
      <v-card-text class="pa-5 pt-2">

        <!-- Setup step -->
        <template v-if="state.step === 'setup'">
          <v-select
            v-model="state.subsidyId"
            :items="subsidies"
            item-title="name" item-value="id"
            label="Субсидия *"
            variant="outlined" density="compact" class="mb-3"
            :rules="[(v: any) => !!v || 'Обязательное поле']"
          />

          <v-radio-group v-model="state.uploadMode" inline class="mb-3" hide-details density="compact">
            <template #label><span class="text-body-2 font-weight-medium mr-3">Режим загрузки:</span></template>
            <v-radio value="zip" label="ZIP-архив" />
            <v-radio value="folder" label="Папку с подпапками" />
          </v-radio-group>

          <!-- ZIP mode -->
          <FileDropZone
            v-if="state.uploadMode === 'zip'"
            v-model="state.zipFile"
            accept=".zip"
            hint="ZIP-архив — перетащите или нажмите"
            class="mb-3"
          />

          <!-- Folder mode -->
          <div v-else class="mb-3">
            <label class="scans-folder-label" :class="{ 'scans-folder-label--active': state.files.length }">
              <v-icon icon="mdi-folder-open" class="mr-1" />
              <span v-if="!state.files.length">Выберите папку</span>
              <span v-else>{{ state.files.length }} файл(ов) из папки</span>
              <input
                type="file"
                webkitdirectory
                multiple
                style="display:none"
                @change="onFolderSelect"
              />
            </label>
          </div>

          <v-alert type="info" variant="tonal" density="compact" icon="mdi-information-outline" class="text-body-2">
            Имя каждой папки должно содержать ИНН (10 или 12 цифр) и сумму договора. Файлы приложатся к закупке по совпадению.
          </v-alert>
        </template>

        <!-- Preview step -->
        <template v-else-if="state.step === 'preview'">
          <div class="text-body-2 font-weight-medium mb-2">
            Предпросмотр — {{ state.previewResult?.folders?.length ?? 0 }} папок
            ({{ state.previewResult?.attached ?? 0 }} совпадений,
            {{ state.previewResult?.skipped ?? 0 }} пропущено)
          </div>
          <div v-for="folder in state.previewResult?.folders" :key="folder.folder" class="scans-folder-row mb-2">
            <div class="d-flex align-center gap-2 flex-wrap">
              <v-icon icon="mdi-folder" color="amber" size="small" />
              <span class="text-body-2 font-weight-medium">{{ folder.folder }}</span>
              <span class="text-caption text-medium-emphasis">ИНН: {{ folder.inn || '?' }}, Сумма: {{ folder.sum?.toLocaleString('ru-RU') ?? '?' }}</span>
              <v-chip v-if="folder.status === 'attached'" color="success" size="x-small" label>
                → Договор {{ folder.contract_number }} (#{{ folder.purchase_id }})
              </v-chip>
              <v-chip v-else color="error" size="x-small" label>
                <v-tooltip :text="folder.reason || 'Нет совпадения'" location="top">
                  <template #activator="{ props: tp }">
                    <span v-bind="tp">Пропущено</span>
                  </template>
                </v-tooltip>
              </v-chip>
            </div>
            <div v-if="folder.files?.length" class="d-flex flex-wrap gap-1 ml-6 mt-1">
              <v-chip
                v-for="f in folder.files" :key="f.name"
                size="x-small" variant="tonal" color="teal" class="mr-1 mb-1"
              >
                {{ f.name }}
                <span v-if="f.file_type" class="ml-1 text-medium-emphasis">· {{ f.file_type }}</span>
                <span v-if="f.doc_format" class="ml-1 text-medium-emphasis">· {{ f.doc_format }}</span>
              </v-chip>
            </div>
          </div>
        </template>

        <!-- Result step -->
        <template v-else-if="state.step === 'result'">
          <div class="import-result-row">
            <div class="import-stat import-stat--ok">
              <div class="import-stat-val">{{ state.result?.attached ?? 0 }}</div>
              <div class="import-stat-lbl">Прикреплено</div>
            </div>
            <div class="import-stat import-stat--skip">
              <div class="import-stat-val">{{ state.result?.skipped ?? 0 }}</div>
              <div class="import-stat-lbl">Пропущено</div>
            </div>
          </div>
        </template>

      </v-card-text>
      <v-card-actions class="pa-5 pt-0">
        <v-spacer />
        <template v-if="state.step === 'setup'">
          <v-btn variant="text" @click="resetScans">Отмена</v-btn>
          <v-btn color="teal" variant="flat"
            :loading="state.loading"
            :disabled="!state.subsidyId || (state.uploadMode === 'zip' ? !state.zipFile : !state.files.length)"
            @click="doScanPreview">
            Предпросмотр
          </v-btn>
        </template>
        <template v-else-if="state.step === 'preview'">
          <v-btn variant="text" @click="state.step = 'setup'">Назад</v-btn>
          <v-btn color="teal" variant="flat"
            :loading="state.loading"
            :disabled="!(state.previewResult?.attached ?? 0)"
            @click="doScanUpload">
            Прикрепить
          </v-btn>
        </template>
        <template v-else>
          <v-btn variant="text" @click="resetScans">Закрыть</v-btn>
          <v-btn color="primary" variant="flat" @click="resetScans">Готово</v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useDisplay } from 'vuetify'
import FileDropZone from '@/components/FileDropZone.vue'
import type { ToastType } from '@/composables/useToast'
import type { ScanPreviewResult, ScanResult, Subsidy } from '@/composables/orders/ordersTypes'

const props = defineProps<{
  subsidies: Subsidy[]
  showSnack: (text: string, color?: ToastType) => void
}>()

const { mobile } = useDisplay()

const state = reactive({
  show: false,
  step: 'setup' as 'setup' | 'preview' | 'result',
  subsidyId: null as number | null,
  uploadMode: 'zip' as 'zip' | 'folder',
  zipFile: null as File | null,
  files: [] as File[],
  loading: false,
  previewResult: null as ScanPreviewResult | null,
  result: null as ScanResult | null,
})

const onFolderSelect = (e: Event) => {
  const input = e.target as HTMLInputElement
  state.files = input.files ? Array.from(input.files) : []
}

const buildScansFormData = (): FormData => {
  const fd = new FormData()
  if (state.uploadMode === 'zip') {
    fd.append('archive', state.zipFile as File)
  } else {
    for (const f of state.files) {
      fd.append('files', f)
      fd.append('paths', (f as any).webkitRelativePath || f.name)
    }
  }
  return fd
}

const doScanPreview = async () => {
  if (!state.subsidyId) return
  if (state.uploadMode === 'zip' && !state.zipFile) return
  if (state.uploadMode === 'folder' && !state.files.length) return
  state.loading = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = buildScansFormData()
    const response = await fetch(`/api/purchases/files/bulk-upload?subsidy_id=${state.subsidyId}&dry_run=true`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка предпросмотра сканов' }))
      props.showSnack(`[${response.status}] ${err.detail || err.message || 'Ошибка предпросмотра сканов'}`, 'error')
      return
    }
    state.previewResult = await response.json()
    state.step = 'preview'
  } catch (e: any) {
    props.showSnack(e.message || 'Ошибка предпросмотра сканов', 'error')
  } finally {
    state.loading = false
  }
}

const doScanUpload = async () => {
  if (!state.subsidyId) return
  state.loading = true
  try {
    const token = localStorage.getItem('auth_token')
    const fd = buildScansFormData()
    const response = await fetch(`/api/purchases/files/bulk-upload?subsidy_id=${state.subsidyId}&dry_run=false`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Ошибка загрузки сканов' }))
      props.showSnack(`[${response.status}] ${err.detail || err.message || 'Ошибка загрузки сканов'}`, 'error')
      return
    }
    state.result = await response.json()
    state.step = 'result'
  } catch (e: any) {
    props.showSnack(e.message || 'Ошибка загрузки сканов', 'error')
  } finally {
    state.loading = false
  }
}

const resetScans = () => {
  state.show = false
  state.step = 'setup'
  state.subsidyId = null
  state.uploadMode = 'zip'
  state.zipFile = null
  state.files = []
  state.loading = false
  state.previewResult = null
  state.result = null
}

function open() { state.show = true }
defineExpose({ open })
</script>

<style scoped>
.import-result-row {
  display: flex; gap: 16px; justify-content: center; margin: 16px 0;
}
.import-stat {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px 24px; border-radius: 10px; min-width: 100px;
}
.import-stat--ok   { background: rgba(34,197,94,0.1); }
.import-stat--skip { background: rgba(245,158,11,0.1); }
.scans-folder-label {
  display: flex; align-items: center; gap: 6px;
  padding: 12px 16px; border: 2px dashed var(--crm-border);
  border-radius: 8px; cursor: pointer; color: var(--crm-text-muted);
  transition: border-color 0.2s, color 0.2s;
}
.scans-folder-label:hover { border-color: teal; color: teal; }
.scans-folder-label--active { border-color: teal; color: teal; }
.scans-folder-row { border: 1px solid var(--crm-border); border-radius: 8px; padding: 8px 12px; }
</style>
