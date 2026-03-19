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
        <v-textarea
          v-if="error?.details"
          :model-value="error.details"
          label="Технические детали"
          readonly auto-grow rows="4" variant="outlined" density="compact"
          hide-details class="text-caption"
        />
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

function handleApiError(e: Event) {
  error.value = (e as CustomEvent<ErrorPayload>).detail
  show.value = true
  copied.value = false
}

onMounted(() => window.addEventListener('api-error', handleApiError))
onUnmounted(() => window.removeEventListener('api-error', handleApiError))

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
