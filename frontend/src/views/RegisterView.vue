<template>
  <v-container class="fill-height">
    <v-responsive class="align-center text-center fill-height">
      <v-card class="mx-auto pa-8" max-width="560" elevation="8">

        <!-- Success state -->
        <div v-if="success" class="py-4">
          <v-icon icon="mdi-email-check-outline" size="72" color="success" class="mb-4" />
          <h2 class="text-h5 mb-2">Проверьте почту!</h2>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Письмо с ссылкой для подтверждения отправлено на <strong>{{ form.email }}</strong>.
            Перейдите по ссылке в письме, чтобы активировать аккаунт.
          </p>
          <p class="text-body-2 mb-4">
            <strong>Ваш логин для входа:</strong> {{ form.email }}
          </p>
          <v-btn color="primary" variant="text" to="/login">Перейти ко входу</v-btn>
        </div>

        <!-- Registration form -->
        <div v-else>
          <v-card-title class="text-h5 mb-2">Регистрация организации</v-card-title>
          <v-card-subtitle class="mb-6">Создайте аккаунт для вашей организации</v-card-subtitle>

          <v-form @submit.prevent="register">
            <div class="text-left text-caption text-medium-emphasis mb-2 font-weight-medium text-uppercase">Организация</div>
            <v-text-field
              v-model="form.org_name" label="Название организации *" variant="outlined"
              density="compact" class="mb-3" :error-messages="fieldError('org_name')"
            />
            <v-text-field
              v-model="form.org_inn" label="ИНН (необязательно)" variant="outlined"
              density="compact" class="mb-4"
            />

            <div class="text-left text-caption text-medium-emphasis mb-2 font-weight-medium text-uppercase">Учётная запись администратора</div>
            <v-text-field
              v-model="form.full_name" label="Ваше имя" variant="outlined"
              density="compact" class="mb-3"
            />
            <v-text-field
              v-model="form.email" label="Email (он же логин) *" variant="outlined"
              density="compact" class="mb-3" :error-messages="fieldError('email')"
              autocomplete="email" type="email"
              hint="Этот email будет использоваться для входа в систему"
              persistent-hint
            />
            <v-text-field
              v-model="form.password" label="Пароль *" type="password" variant="outlined"
              density="compact" class="mb-3" :error-messages="fieldError('password')"
              autocomplete="new-password"
            />
            <v-text-field
              v-model="passwordConfirm" label="Подтверждение пароля *" type="password" variant="outlined"
              density="compact" class="mb-4" :error-messages="confirmError"
            />

            <v-alert v-if="error" type="error" class="mb-4" density="compact">{{ error }}</v-alert>

            <v-btn type="submit" color="primary" size="large" block :loading="loading">
              Зарегистрироваться
            </v-btn>
          </v-form>

          <v-divider class="my-6" />
          <div class="text-center">
            <span class="text-body-2 text-medium-emphasis">Уже есть аккаунт?</span>
            <v-btn variant="text" color="primary" size="small" to="/login" class="ml-1">Войти</v-btn>
          </div>
        </div>

      </v-card>
    </v-responsive>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'

const success = ref(false)
const loading = ref(false)
const error = ref('')
const validationErrors = ref<Record<string, string>>({})
const passwordConfirm = ref('')

const form = reactive({
  org_name: '',
  org_inn: '',
  full_name: '',
  email: '',
  password: '',
})

const confirmError = computed(() => {
  if (passwordConfirm.value && form.password !== passwordConfirm.value) {
    return 'Пароли не совпадают'
  }
  return ''
})

function fieldError(field: string): string {
  return validationErrors.value[field] || ''
}

async function register() {
  error.value = ''
  validationErrors.value = {}

  if (!form.org_name) { validationErrors.value.org_name = 'Обязательное поле'; return }
  if (!form.email) { validationErrors.value.email = 'Обязательное поле'; return }
  if (!form.password) { validationErrors.value.password = 'Обязательное поле'; return }
  if (form.password.length < 6) { validationErrors.value.password = 'Минимум 6 символов'; return }
  if (form.password !== passwordConfirm.value) { return }

  loading.value = true
  try {
    const res = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        org_name: form.org_name,
        org_inn: form.org_inn || null,
        full_name: form.full_name || null,
        email: form.email,
        password: form.password,
      }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.message || data.detail || `Ошибка ${res.status}`)
    }
    success.value = true
  } catch (e: any) {
    error.value = e.message || 'Ошибка регистрации'
  } finally {
    loading.value = false
  }
}
</script>
