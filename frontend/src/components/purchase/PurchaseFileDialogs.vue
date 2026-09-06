<template>
  <!-- Диалог загрузки файла -->
  <v-dialog v-model="uploadOpen" max-width="420" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 pt-4 px-4">Загрузить файл</v-card-title>
      <v-card-text class="pb-0">
        <v-select v-model="uploadFileType"
          :items="fileTypeOptions" item-title="title" item-value="value"
          label="Тип документа" variant="outlined" density="compact" class="mb-3" />
        <div class="text-body-2 mb-2">Формат файла</div>
        <v-btn-toggle v-model="uploadDocFormat" mandatory density="compact" color="primary" class="mb-1">
          <v-btn value="scan" prepend-icon="mdi-scanner">Скан</v-btn>
          <v-btn value="editable" prepend-icon="mdi-file-edit-outline">Редактируемый</v-btn>
        </v-btn-toggle>
        <div class="text-caption text-medium-emphasis mb-2">
          Редактируемый — только Word и Excel. PDF и изображения всегда скан.
        </div>
        <div class="text-caption text-medium-emphasis">PDF, Word, Excel, JPEG, PNG</div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="uploadOpen = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" @click="$emit('choose-file')">
          Выбрать файл
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Диалог смены типа файла -->
  <v-dialog v-model="fileTypeEditOpen" max-width="380">
    <v-card>
      <v-card-title class="text-subtitle-1 pt-4 px-4">Тип документа</v-card-title>
      <v-card-text>
        <v-select v-model="fileTypeEditValue"
          :items="fileTypeOptions" item-title="title" item-value="value"
          label="Тип" variant="outlined" density="compact" class="mb-3" />
        <div class="text-body-2 mb-2">Формат файла</div>
        <v-btn-toggle v-model="fileDocFormatEditValue" mandatory density="compact" color="primary">
          <v-btn value="scan" prepend-icon="mdi-scanner">Скан</v-btn>
          <v-btn value="editable" prepend-icon="mdi-file-edit-outline"
            :disabled="fileTypeEditTarget ? !editableMime.has(fileTypeEditTarget.mime_type || '') : false">
            Редактируемый
          </v-btn>
        </v-btn-toggle>
        <div v-if="fileTypeEditTarget && !editableMime.has(fileTypeEditTarget.mime_type || '')"
          class="text-caption text-orange mt-1">
          Только Word/Excel могут быть редактируемыми
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="fileTypeEditOpen = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="savingFileType" @click="$emit('save-file-type')">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- File preview dialog -->
  <v-dialog v-model="previewOpen" max-width="900" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon :icon="fileIcon(previewFile?.mime_type)" class="mr-2" />
        {{ previewFile?.filename }}
        <v-spacer />
        <v-btn icon="mdi-download" variant="text" size="small" @click="previewFile && $emit('download', previewFile.id, previewFile.filename)" />
        <v-btn icon="mdi-close" variant="text" size="small" @click="previewOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-0" style="min-height:500px">
        <iframe v-if="previewFile?.mime_type === 'application/pdf'"
          :src="previewUrl" style="width:100%;height:600px;border:none" />
        <div v-else-if="previewFile?.mime_type?.startsWith('image/')" class="d-flex justify-center pa-4">
          <img :src="previewUrl" style="max-width:100%;max-height:600px;object-fit:contain" />
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const uploadOpen = defineModel<boolean>('uploadOpen', { default: false })
const fileTypeEditOpen = defineModel<boolean>('fileTypeEditOpen', { default: false })
const previewOpen = defineModel<boolean>('previewOpen', { default: false })
const uploadFileType = defineModel<string>('uploadFileType', { default: 'other' })
const uploadDocFormat = defineModel<string>('uploadDocFormat', { default: 'scan' })
const fileTypeEditValue = defineModel<string>('fileTypeEditValue', { default: 'other' })
const fileDocFormatEditValue = defineModel<string>('fileDocFormatEditValue', { default: 'scan' })

defineProps<{
  fileTypeOptions: { value: string; title: string }[]
  fileTypeEditTarget: { mime_type?: string } | null
  editableMime: Set<string>
  savingFileType: boolean
  previewFile: { id: number; filename: string; mime_type?: string } | null
  previewUrl: string
  fileIcon: (mime?: string) => string
}>()

defineEmits<{
  (e: 'choose-file'): void
  (e: 'save-file-type'): void
  (e: 'download', id: number, filename: string): void
}>()

const { mobile } = useDisplay()
</script>
