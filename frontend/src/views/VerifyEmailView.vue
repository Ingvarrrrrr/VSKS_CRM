<template>
  <v-container class="fill-height">
    <v-responsive class="align-center text-center fill-height">
      <v-card class="mx-auto pa-8" max-width="460" elevation="8">
        <div v-if="loading" class="py-6">
          <v-progress-circular indeterminate size="64" color="primary" class="mb-4" />
          <p class="text-body-1">Проверяем ссылку...</p>
        </div>
        <div v-else-if="verified" class="py-4">
          <v-icon icon="mdi-check-circle-outline" size="72" color="success" class="mb-4" />
          <h2 class="text-h5 mb-2">Email подтверждён!</h2>
          <p class="text-body-2 text-medium-emphasis mb-6">Теперь вы можете войти в систему.</p>
          <v-btn color="primary" to="/login?verified=1" size="large">Войти</v-btn>
        </div>
        <div v-else class="py-4">
          <v-icon icon="mdi-alert-circle-outline" size="72" color="error" class="mb-4" />
          <h2 class="text-h5 mb-2">Ссылка недействительна</h2>
          <p class="text-body-2 text-medium-emphasis mb-6">{{ errorMsg }}</p>
          <v-btn variant="text" to="/login">Перейти ко входу</v-btn>
        </div>
      </v-card>
    </v-responsive>
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const loading = ref(true)
const verified = ref(false)
const errorMsg = ref('Ссылка недействительна или уже использована.')

onMounted(async () => {
  const token = route.query.token as string
  if (!token) {
    errorMsg.value = 'Токен не указан.'
    loading.value = false
    return
  }
  try {
    // The backend returns a redirect — fetch manually to catch the result
    const res = await fetch(`/api/verify-email?token=${encodeURIComponent(token)}`, {
      redirect: 'manual',
    })
    // 3xx redirect = success (redirected to /login?verified=1)
    if (res.status === 200 || res.status === 302 || res.type === 'opaqueredirect') {
      verified.value = true
    } else {
      const data = await res.json().catch(() => ({}))
      errorMsg.value = data.message || data.detail || 'Ссылка недействительна или уже использована.'
    }
  } catch {
    errorMsg.value = 'Ошибка сети. Попробуйте ещё раз.'
  } finally {
    loading.value = false
  }
})
</script>
