<template>
  <v-dialog v-model="show" max-width="520">
    <v-card>
      <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
        <v-icon icon="mdi-alert-circle-outline" color="error" />
        Ошибка
      </v-card-title>
      <v-card-text class="px-5">
        <p class="mb-2">{{ message }}</p>
        <div v-if="code" class="text-caption text-medium-emphasis">Код: {{ code }}</div>
        <div v-if="correlationId" class="text-caption text-medium-emphasis">ID: {{ correlationId }}</div>
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-btn size="small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyError">
          Скопировать
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const props = defineProps<{
  message: string
  code: string
  correlationId: string
}>()

const show = defineModel<boolean>({ default: false })

function copyError() {
  const text = [
    props.message,
    props.code ? `Код: ${props.code}` : '',
    props.correlationId ? `ID: ${props.correlationId}` : '',
  ].filter(Boolean).join('\n')
  navigator.clipboard.writeText(text).catch(() => {})
}
</script>
