<template>
  <v-dialog v-model="show" max-width="560" persistent>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-alert-circle" color="error" class="mr-2" />
        Ошибка
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="show = false" />
      </v-card-title>
      <v-card-text>
        <div class="mb-2">
          <span class="text-caption text-medium-emphasis">Код: </span>
          <code>{{ error?.code }}</code>
          <span v-if="error?.correlation_id" class="ml-3 text-caption text-medium-emphasis">
            ID: <code>{{ error.correlation_id }}</code>
          </span>
        </div>
        <div class="mb-3 text-body-1">{{ error?.message }}</div>
        <v-expansion-panels v-if="error?.details" v-model="techExpanded" class="text-caption">
          <v-expansion-panel value="details">
            <v-expansion-panel-title class="text-caption">
              <v-icon icon="mdi-code-tags" size="14" class="mr-1" />
              Технические детали
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre style="white-space: pre-wrap; max-height: 240px; overflow: auto; font-size: 11px; margin: 0">{{ error.details }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
      <v-card-actions>
        <v-btn
          variant="text"
          :prepend-icon="copied ? 'mdi-check' : 'mdi-content-copy'"
          :color="copied ? 'success' : undefined"
          @click="copyDetails">
          {{ copied ? 'Скопировано!' : 'Скопировать' }}
        </v-btn>
        <v-spacer />
        <v-btn color="primary" variant="tonal" @click="show = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface ErrorPayload {
  code: string
  message: string
  details?: string
  correlation_id?: string
}

const show = ref(false)
const error = ref<ErrorPayload | null>(null)
const copied = ref(false)
const techExpanded = ref<string | null>(null)  // collapsed by default

function handleApiError(e: Event) {
  error.value = (e as CustomEvent<ErrorPayload>).detail
  show.value = true
  copied.value = false
  techExpanded.value = null  // reset to collapsed on each error
}

function handleJsError(e: ErrorEvent) {
  // Истинно JS-ошибки (ReferenceError, TypeError, рантайм-исключения).
  // api-ошибки уже отлавливаются через api-error event из apiFetch.
  const err = e.error
  if (!err) return
  if (show.value) return  // не перебиваем уже открытый диалог
  error.value = {
    code: err.name || 'JS_ERROR',
    message: err.message || String(err),
    details: err.stack || '',
    correlation_id: '',
  }
  show.value = true
  copied.value = false
  techExpanded.value = null
}

function handleUnhandledRejection(e: PromiseRejectionEvent) {
  const reason: any = e.reason
  if (!reason) return
  if (show.value) return
  // Если это apiFetch error с payload — он уже сработал через api-error event
  if (reason.payload) return
  error.value = {
    code: reason.name || 'UNHANDLED_REJECTION',
    message: reason.message || String(reason),
    details: reason.stack || '',
    correlation_id: '',
  }
  show.value = true
  copied.value = false
  techExpanded.value = null
}

onMounted(() => {
  window.addEventListener('api-error', handleApiError)
  window.addEventListener('error', handleJsError)
  window.addEventListener('unhandledrejection', handleUnhandledRejection)
})
onUnmounted(() => {
  window.removeEventListener('api-error', handleApiError)
  window.removeEventListener('error', handleJsError)
  window.removeEventListener('unhandledrejection', handleUnhandledRejection)
})

async function copyDetails() {
  const text = [
    `Код: ${error.value?.code}`,
    `Сообщение: ${error.value?.message}`,
    error.value?.correlation_id ? `Correlation ID: ${error.value.correlation_id}` : '',
    error.value?.details ? `\nДетали:\n${error.value.details}` : '',
  ].filter(Boolean).join('\n')

  let ok = false
  try {
    await navigator.clipboard.writeText(text)
    ok = true
  } catch {
    // fallback for HTTP / no clipboard permissions
  }
  if (!ok) {
    try {
      const el = document.createElement('textarea')
      el.value = text
      el.style.position = 'fixed'
      el.style.top = '0'
      el.style.left = '0'
      el.style.opacity = '0'
      document.body.appendChild(el)
      el.focus()
      el.select()
      ok = document.execCommand('copy')
      document.body.removeChild(el)
    } catch { /* ignore */ }
  }

  if (ok) {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
}
</script>
