<template>
  <v-container class="fill-height">
    <v-responsive class="align-center text-center fill-height">
      <v-card class="mx-auto pa-8" max-width="500" elevation="8">
        <v-card-title class="text-h4 mb-4">GALA</v-card-title>

        <!-- Forgot password mode -->
        <template v-if="forgotMode">
          <v-card-subtitle class="text-h6 mb-6">Восстановление пароля</v-card-subtitle>

          <div v-if="forgotSent" class="py-4">
            <v-icon icon="mdi-email-check-outline" size="64" color="success" class="mb-4" />
            <p class="text-body-1 mb-4">
              Если аккаунт с email <strong>{{ forgotEmail }}</strong> существует,
              на него отправлена ссылка для сброса пароля.
            </p>
            <v-btn color="primary" variant="text" @click="forgotMode = false; forgotSent = false">
              Вернуться ко входу
            </v-btn>
          </div>

          <v-form v-else @submit.prevent="sendReset">
            <v-text-field
              v-model="forgotEmail" label="Email" prepend-inner-icon="mdi-email"
              variant="outlined" class="mb-4" type="email" autocomplete="email"
            />
            <v-alert v-if="forgotError" type="error" class="mb-4" density="compact">{{ forgotError }}</v-alert>
            <v-btn type="submit" color="primary" size="large" block :loading="forgotLoading" class="mb-4">
              Отправить ссылку для сброса
            </v-btn>
            <v-btn variant="text" color="primary" block @click="forgotMode = false">
              Вернуться ко входу
            </v-btn>
          </v-form>
        </template>

        <!-- Login mode -->
        <template v-else>
          <v-card-subtitle class="text-h6 mb-8">Авторизация</v-card-subtitle>

          <v-form @submit.prevent="login">
            <v-text-field
              v-model="username" label="Email" prepend-inner-icon="mdi-email"
              variant="outlined" class="mb-4" :error-messages="errors.username"
              autocomplete="email" type="email"
            />
            <v-text-field
              v-model="password" label="Пароль" prepend-inner-icon="mdi-lock"
              variant="outlined" type="password" class="mb-2"
              :error-messages="errors.password" autocomplete="current-password"
            />

            <div class="text-right mb-4">
              <v-btn variant="text" color="primary" size="small" @click="forgotMode = true">
                Забыли пароль?
              </v-btn>
            </div>

            <v-alert v-if="error" type="error" class="mb-6">{{ error }}</v-alert>

            <v-btn type="submit" color="primary" size="large" block :loading="loading">
              Войти
            </v-btn>
          </v-form>

          <v-divider class="my-6" />

          <div class="text-center">
            <span class="text-body-2 text-medium-emphasis">Нет аккаунта?</span>
            <v-btn variant="text" color="primary" size="small" to="/register" class="ml-1">
              Зарегистрировать организацию
            </v-btn>
          </div>
        </template>

        <v-snackbar v-model="verifiedSnack" color="success" timeout="4000">
          Email подтверждён — можно войти!
        </v-snackbar>
      </v-card>
    </v-responsive>
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const verifiedSnack = ref(false)
const errors = ref({ username: '', password: '' })

// Forgot password state
const forgotMode = ref(false)
const forgotEmail = ref('')
const forgotLoading = ref(false)
const forgotError = ref('')
const forgotSent = ref(false)

const login = async () => {
  error.value = ''
  errors.value = { username: '', password: '' }

  if (!username.value) { errors.value.username = 'Обязательное поле'; return }
  if (!password.value) { errors.value.password = 'Обязательное поле'; return }

  loading.value = true
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.message || errorData.detail || `Ошибка ${response.status}`)
    }
    const data = await response.json()
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('user_role', data.role)
    localStorage.setItem('user_name', data.full_name || username.value)
    if (data.user_id) localStorage.setItem('user_id', String(data.user_id))
    if (data.org_id) {
      localStorage.setItem('user_org_id', String(data.org_id))
      // authoritative active org from JWT — overwrite any stale value from prior session
      localStorage.setItem('active_org_id', String(data.org_id))
    }
    if (data.org_name) localStorage.setItem('user_org_name', data.org_name)
    localStorage.setItem('can_publish', data.can_publish ? 'true' : 'false')
    try {
      await authStore.loadPermissions(localStorage.getItem('active_org_id') || localStorage.getItem('user_org_id'))
    } catch (e) {
      console.error('[login] loadPermissions failed, fail-open', e)
      authStore.loaded = true
    }
    window.location.href = '/'
  } catch (err: any) {
    error.value = err.message || 'Ошибка авторизации'
  } finally {
    loading.value = false
  }
}

const sendReset = async () => {
  forgotError.value = ''
  if (!forgotEmail.value) { forgotError.value = 'Введите email'; return }
  forgotLoading.value = true
  try {
    const res = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: forgotEmail.value }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.message || data.detail || `Ошибка ${res.status}`)
    }
    forgotSent.value = true
  } catch (e: any) {
    forgotError.value = e.message || 'Ошибка отправки'
  } finally {
    forgotLoading.value = false
  }
}

onMounted(() => {
  if (route.query.verified === '1') verifiedSnack.value = true
  const savedToken = localStorage.getItem('auth_token')
  if (savedToken && savedToken.startsWith('eyJ')) router.push('/')
})
</script>
