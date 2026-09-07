<template>
  <!-- 7. Файлы (скрыто для employee, если нет права purchase_files.upload и не участник/согласующий) -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Документы к закупке</v-card-title>
    <v-card-text>
      <!-- Phase 26-ppp: typed-upload секции перенесены сюда из «Закрывающие
           документы» — единая точка загрузки всех файлов закупки.
           Каждая кнопка «Загрузить» назначает file_type (contract/act/upd/
           invoice/order/etc) при upload. Файлы списком ниже. -->
      <div class="doc-upload-grid mb-4">
        <FileDropZone v-for="sec in docUploadSections" :key="sec.type"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" :multiple="true" :disabled="!purchaseId"
          class="doc-upload-tile" style="min-height:140px; align-items:flex-start; padding:12px"
          @files="(files: File[]) => uploadFilesForType(files, sec.type)">
          <template #default="{ dragging }">
            <div class="doc-upload-tile-inner" :class="{ 'doc-upload-tile-inner--dragging': dragging && purchaseId }">
              <div class="d-flex align-center gap-2 mb-1">
                <v-icon size="20" :color="sec.color">{{ sec.icon }}</v-icon>
                <span class="text-body-2 font-weight-medium">{{ sec.label }}</span>
                <v-spacer />
                <v-progress-circular v-if="uploading && pendingSectionUpload === sec.type"
                  indeterminate size="16" width="2" :color="sec.color" />
              </div>
              <div class="text-caption text-medium-emphasis mb-2">
                {{ purchaseId ? 'Перетащите файл сюда или нажмите' : 'Сначала сохраните закупку' }}
              </div>
              <div v-if="filesByType(sec.type).length" class="d-flex flex-wrap gap-1" @click.stop>
                <template v-for="f in filesByType(sec.type)" :key="f.id">
                  <v-chip size="small" :color="f.is_active ? sec.color : 'grey'" :variant="f.is_active ? 'tonal' : 'outlined'"
                    closable @click:close="deleteFile(f.id)" @click="downloadFile(f.id, f.filename)">
                    <v-icon start size="14">mdi-file</v-icon>
                    {{ f.filename.length > 20 ? f.filename.slice(0, 17) + '...' : f.filename }}
                    <template #append>
                      <v-tooltip :text="f.is_active ? 'Актуальный — нажмите чтобы деактивировать' : 'Не актуальный — нажмите чтобы активировать'" location="top">
                        <template #activator="{ props: tp }">
                          <v-icon v-bind="tp" size="14" class="ml-1" :color="f.is_active ? 'success' : 'grey'"
                            @click.stop="toggleFileActive(f)">{{ f.is_active ? 'mdi-check-circle' : 'mdi-close-circle-outline' }}</v-icon>
                        </template>
                      </v-tooltip>
                    </template>
                  </v-chip>
                </template>
              </div>
            </div>
          </template>
        </FileDropZone>
      </div>

      <v-list v-if="uploadedFiles.length" density="compact">
        <v-list-item v-for="f in uploadedFiles" :key="f.id"
          :prepend-icon="fileIcon(f.mime_type)"
        >
          <template #title>
            <span class="text-body-2">{{ f.filename }}</span>
            <v-chip size="x-small" class="ml-2" :color="fileTypeColor(f.file_type)" variant="tonal"
              style="cursor:pointer" @click="openFileTypeEdit(f)">
              {{ fileTypeLabels[f.file_type || 'other'] || 'Прочее' }}
              <v-icon size="10" class="ml-1">mdi-pencil</v-icon>
            </v-chip>
            <v-chip size="x-small" class="ml-1"
              :color="f.doc_format === 'editable' ? 'blue' : 'grey'"
              :prepend-icon="f.doc_format === 'editable' ? 'mdi-file-edit-outline' : 'mdi-scanner'"
              variant="tonal" style="cursor:pointer" @click="toggleDocFormat(f)">
              {{ f.doc_format === 'editable' ? 'Ред.' : 'Скан' }}
            </v-chip>
          </template>
          <template #subtitle>
            {{ formatSize(f.size) }}
            <span v-if="f.uploaded_by_name || f.created_at" class="text-medium-emphasis ml-2">
              · {{ f.uploaded_by_name || '' }}{{ f.created_at ? ' · ' + formatDate(f.created_at) : '' }}
            </span>
          </template>
          <template #append>
            <v-btn v-if="isPreviewable(f.mime_type)" icon="mdi-eye-outline" variant="text" size="small" color="primary"
              @click="openPreview(f)" />
            <v-btn icon="mdi-download" variant="text" size="small" @click="downloadFile(f.id, f.filename)" />
            <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
              @click="deleteFile(f.id)" />
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="text-caption text-medium-emphasis">Нет загруженных файлов</div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Карточка «Документы к закупке». Вынесено из CreateOrderView.vue (рефакторинг
// без изменения поведения, часть 3). Все данные/функции — из
// composables/purchase/usePurchaseFiles.ts, вызываемого в родителе (там же
// нужны PurchaseFileDialogs/Payment/Acceptance секциям) — приходят пропами.
// Скрытые <input ref="fileInputEl"/"sectionFileInputEl"> элементы намеренно
// ОСТАВЛЕНЫ в CreateOrderView.vue (не перенесены сюда): их DOM-ref привязан
// автосвязыванием Vue к переменным в script родителя (fileInputEl?.click() в
// PurchaseFileDialogs) — перенос узла в дочерний компонент сломал бы это
// автосвязывание без ref-форвардинга; т.к. inputs display:none, расположение
// в DOM визуально не отличимо.
import FileDropZone from '@/components/FileDropZone.vue'

defineProps<{
  purchaseId: number | null
  uploading: boolean
  pendingSectionUpload: string | null
  docUploadSections: Array<{ type: string; label: string; icon: string; color: string }>
  uploadedFiles: any[]
  fileTypeLabels: Record<string, string>
  uploadFilesForType: (files: File[], type: string) => void
  filesByType: (type: string) => any[]
  deleteFile: (id: number) => void
  downloadFile: (id: number, filename: string) => void
  toggleFileActive: (f: any) => void
  fileIcon: (mime: string) => string
  openFileTypeEdit: (f: any) => void
  fileTypeColor: (type?: string) => string
  toggleDocFormat: (f: any) => void
  formatSize: (size: number) => string
  formatDate: (iso: string) => string
  isPreviewable: (mime: string) => boolean
  openPreview: (f: any) => void
}>()
</script>

<style scoped>
.doc-upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .doc-upload-grid {
    grid-template-columns: 1fr;
  }
}
.doc-upload-tile-inner {
  width: 100%;
  display: flex;
  flex-direction: column;
}
.doc-upload-tile-inner--dragging {
  transform: scale(1.01);
}
</style>
