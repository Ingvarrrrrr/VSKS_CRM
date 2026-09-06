<template>
  <!-- Phase 23.2: диалог ошибки генерации документа -->
  <v-dialog v-model="open" max-width="640">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 bg-error-lighten-5">
        <v-icon icon="mdi-alert-circle" color="error" class="mr-2" />
        <span class="text-error">Ошибка генерации документа</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>
      <v-card-text class="pt-4" v-if="info">
        <div class="text-body-1 font-weight-medium mb-2">{{ info.message }}</div>
        <div v-if="info.template" class="text-caption text-medium-emphasis mb-3">
          <v-icon size="14" class="mr-1">mdi-file-document-outline</v-icon>
          {{ info.template_source }}: <code>{{ info.template }}</code>
        </div>
        <div class="text-caption text-medium-emphasis mb-3">
          <span v-if="info.code">Код: <code>{{ info.code }}</code></span>
          <span v-if="info.code && info.correlation_id"> · </span>
          <span v-if="info.correlation_id">ID: <code>{{ info.correlation_id }}</code></span>
        </div>
        <v-alert v-if="info.hint" type="info" variant="tonal" density="compact" class="mb-3">
          <div class="text-body-2" style="white-space: pre-line">{{ info.hint }}</div>
        </v-alert>
        <v-expansion-panels v-if="info.error_raw || info.error_class" variant="accordion" :model-value="[]" class="mt-2">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-caption">
              Технические детали ({{ info.error_class }})
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre class="text-caption" style="white-space: pre-wrap; max-height: 200px; overflow: auto">{{ info.error_raw }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
      <v-card-actions class="pa-4 flex-wrap">
        <v-btn variant="tonal" color="primary" prepend-icon="mdi-content-copy"
          @click="copyDocError">
          Скопировать ошибку
        </v-btn>
        <v-btn variant="text" prepend-icon="mdi-file-document-edit-outline"
          :href="subsidyId ? `/subsidies?openTemplates=${subsidyId}` : '/subsidies'"
          target="_self" @click="open = false"
          v-if="info?.template_source?.includes('субсидии') || info?.code === 'TEMPLATE_RENDER_ERROR'">
          Редактор шаблонов субсидии
        </v-btn>
        <v-btn variant="tonal" color="primary" prepend-icon="mdi-format-list-bulleted"
          @click="open = false; $emit('reveal-field', 'items')"
          v-if="info?.code === 'CONTRACT_ITEMS_REQUIRED'">
          Показать позиции
        </v-btn>
        <v-spacer />
        <v-btn @click="open = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useToast, type ToastType } from '@/composables/useToast'

const open = defineModel<boolean>({ default: false })

const props = defineProps<{
  info: any
  purchaseId: number | null
  subsidyId: number | null
}>()

defineEmits<{ (e: 'reveal-field', target: string): void }>()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { duration?: number }) {
  toast.addToast(text, color, opts)
}

const copyDocError = async () => {
  if (!props.info) return
  const i = props.info as any
  const lines = [
    'Ошибка генерации документа',
    `Покупка: #${props.purchaseId} (субсидия id=${props.subsidyId ?? '—'})`,
    `Шаблон: ${i.template ?? ''} (${i.template_source ?? ''})`,
    `Код: ${i.code ?? ''}${i.correlation_id ? ` · correlation_id=${i.correlation_id}` : ''}`,
    `Класс: ${i.error_class ?? ''}`,
    '',
    'Сообщение:',
    i.message ?? '',
    '',
    'Сырой текст:',
    i.error_raw ?? '',
  ]
  if (i.hint) {
    lines.push('', 'Подсказка:', i.hint)
  }
  if (i.traceback) {
    lines.push('', 'Traceback:', String(i.traceback).slice(0, 4000))
  }
  const txt = lines.join('\n')
  try {
    await navigator.clipboard.writeText(txt)
    showSnack('Текст ошибки скопирован в буфер обмена', 'success', { duration: 2500 })
  } catch {
    // Fallback для http-контекста или ограничений permission
    try {
      const ta = document.createElement('textarea')
      ta.value = txt
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      showSnack('Текст ошибки скопирован', 'success', { duration: 2500 })
    } catch {
      showSnack('Не удалось скопировать. Выделите текст в блоке «Технические детали» и Ctrl+C', 'error')
    }
  }
}
</script>
