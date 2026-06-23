<template>
  <v-menu>
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        size="small"
        variant="outlined"
        color="teal"
        prepend-icon="mdi-download"
        append-icon="mdi-chevron-down"
        :loading="exporting"
        :disabled="props.disabled"
      >
        Экспорт
      </v-btn>
    </template>
    <v-list density="compact">
      <v-list-item
        prepend-icon="mdi-microsoft-excel"
        title="Excel (.xlsx)"
        @click="handleExport('xlsx')"
      />
      <v-list-item
        prepend-icon="mdi-file-pdf-box"
        title="PDF"
        @click="handleExport('pdf')"
      />
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import { useRegistryExport, type ExportColumn } from '@/composables/useRegistryExport'

const props = defineProps<{
  title: string
  getColumns: () => ExportColumn[]
  getRows: () => Array<Record<string, any>>
  filename?: string
  disabled?: boolean
  // Элемент для WYSIWYG-PDF «как на экране». Если задан — PDF снимается с этого DOM,
  // иначе используется табличный backend-PDF.
  getCaptureEl?: () => HTMLElement | null | undefined
}>()

const emit = defineEmits<{
  error: [message: string]
}>()

const { exportTable, exportScreenshotPdf, exporting } = useRegistryExport()

async function handleExport(format: 'xlsx' | 'pdf') {
  try {
    if (format === 'pdf' && props.getCaptureEl) {
      const el = props.getCaptureEl()
      if (el) {
        await exportScreenshotPdf(el, props.title, props.filename)
        return
      }
    }
    await exportTable({
      title: props.title,
      columns: props.getColumns(),
      rows: props.getRows(),
      format,
      filename: props.filename,
    })
  } catch (e: any) {
    emit('error', e?.message ?? 'Ошибка экспорта')
  }
}
</script>
