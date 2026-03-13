<template>
  <v-dialog v-model="visible" max-width="860" persistent>
    <v-card>
      <v-card-title class="text-h6 d-flex align-center">
        <v-icon color="error" class="mr-2">mdi-alert-circle-outline</v-icon>
        Подробности ошибки
      </v-card-title>
      <v-card-text>
        <div class="text-body-1 mb-2"><strong>{{ payload.message || 'Ошибка запроса' }}</strong></div>
        <div class="text-caption text-medium-emphasis mb-3">
          Код: {{ payload.code || 'UNKNOWN' }}
          <span v-if="payload.correlation_id"> • Correlation ID: {{ payload.correlation_id }}</span>
        </div>
        <v-textarea
          :model-value="detailsText"
          rows="8"
          readonly
          auto-grow
          variant="outlined"
          label="Технические детали"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="tonal" prepend-icon="mdi-content-copy" @click="copyDetails">Скопировать</v-btn>
        <v-btn color="primary" variant="flat" @click="visible = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

type ApiErrorPayload = {
  code?: string
  message?: string
  details?: string
  correlation_id?: string
}

const visible = ref(false)
const payload = reactive<ApiErrorPayload>({})

const detailsText = computed(() => {
  const lines = [
    `Сообщение: ${payload.message || 'Ошибка запроса'}`,
    `Код: ${payload.code || 'UNKNOWN'}`,
    payload.correlation_id ? `Correlation ID: ${payload.correlation_id}` : '',
    '',
    payload.details || 'Подробности отсутствуют',
  ].filter(Boolean)
  return lines.join('\n')
})

function onApiError(ev: Event) {
  const custom = ev as CustomEvent<ApiErrorPayload>
  payload.code = custom.detail?.code || 'UNKNOWN'
  payload.message = custom.detail?.message || 'Ошибка запроса'
  payload.details = custom.detail?.details || ''
  payload.correlation_id = custom.detail?.correlation_id || ''
  visible.value = true
}

function copyDetails() {
  navigator.clipboard.writeText(detailsText.value).catch(() => undefined)
}

onMounted(() => window.addEventListener('api-error', onApiError as EventListener))
onUnmounted(() => window.removeEventListener('api-error', onApiError as EventListener))
</script>
