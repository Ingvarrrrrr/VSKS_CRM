<template>
  <v-container class="fill-height">
    <v-responsive class="align-center text-center fill-height">
      <v-card class="mx-auto pa-8" max-width="500" elevation="8">
        <v-card-title class="text-h5 mb-4">Новый пароль</v-card-title>

        <div v-if="success" class="py-4">
          <v-icon icon="mdi-check-circle-outline" size="64" color="success" class="mb-4" />
          <p class="text-body-1 mb-4">Пароль успешно изменён!</p>
          <v-btn color="primary" to="/login">Войти</v-btn>
        </div>

        <v-form v-else @submit.prevent="resetPassword">
          <v-text-field
            v-model="password" label="Новый пароль *" type="password" variant="outlined"
            density="compact" class="mb-3" autocomplete="new-password"
            :error-messages="passwordError"
          />
          <v-text-field
            v-model="passwordConfirm" label="Подтверждение пароля *" type="password" variant="outlined"
            density="compact" class="mb-4" :error-messages="confirmError"
          />
          <v-alert v-if="error" type="error" class="mb-4" density="compact">{{ error }}</v-alert>
          <v-btn type="submit" color="primary" size="large" block :loading="loading">
            Сохранить пароль
          </v-btn>
        </v-form>
      </v-card>
    </v-responsive>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const token = route.query.token as string

const password = ref('')
const passwordConfirm = ref('')
const loading = ref(false)
const error = ref('')
const success = ref(false)
const passwordError = ref('')

const confirmError = computed(() => {
  if (passwordConfirm.value && password.value !== passwordConfirm.value) return 'Пароли не совпадают'
  return ''
})

async function resetPassword() {
  error.value = ''
  passwordError.value = ''
  if (!password.value) { passwordError.value = 'Обязательное поле'; return }
  if (password.value.length < 6) { passwordError.value = 'Минимум 6 символов'; return }
  if (password.value !== passwordConfirm.value) return
  if (!token) { error.value = 'Ссылка повреждена — нет токена'; return }

  loading.value = true
  try {
    const res = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password: password.value }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.message || data.detail || `Ошибка ${res.status}`)
    }
    success.value = true
  } catch (e: any) {
    error.value = e.message || 'Ошибка сброса пароля'
  } finally {
    loading.value = false
  }
}
</script>
