<template>
  <v-container class="fill-height">
    <v-responsive class="align-center text-center fill-height">
      <v-card class="mx-auto pa-8" max-width="500" elevation="8">
        <v-card-title class="text-h4 mb-4">VSKS CRM</v-card-title>
        <v-card-subtitle class="text-h6 mb-8">Авторизация</v-card-subtitle>
        
        <v-form @submit.prevent="login">
          <v-text-field
            v-model="username"
            label="Имя пользователя"
            prepend-inner-icon="mdi-account"
            variant="outlined"
            class="mb-4"
            :error-messages="errors.username"
            autocomplete="username"
          />
          
          <v-text-field
            v-model="password"
            label="Пароль"
            prepend-inner-icon="mdi-lock"
            variant="outlined"
            type="password"
            class="mb-6"
            :error-messages="errors.password"
            autocomplete="current-password"
          />
          
          <v-alert
            v-if="error"
            type="error"
            class="mb-6"
          >
            {{ error }}
          </v-alert>
          
          <v-btn
            type="submit"
            color="primary"
            size="large"
            block
            :loading="loading"
          >
            Войти
          </v-btn>
        </v-form>
        
        <v-divider class="my-8" />
        
        <div class="text-caption text-medium-emphasis">
          <p>Тестовые учетные данные:</p>
          <p><strong>admin</strong> / <strong>admin</strong> – Администратор</p>
          <p class="mt-2">Система подключена к реальному API бэкенда</p>
        </div>
      </v-card>
    </v-responsive>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const errors = ref({
  username: '',
  password: ''
})

const login = async () => {
  error.value = ''
  errors.value = { username: '', password: '' }
  
  if (!username.value) {
    errors.value.username = 'Обязательное поле'
    return
  }
  if (!password.value) {
    errors.value.password = 'Обязательное поле'
    return
  }
  
  loading.value = true
  
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: username.value,
        password: password.value
      })
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Ошибка ${response.status}: ${response.statusText}`)
    }
    
    const data = await response.json()
    
    // Сохраняем токен и данные пользователя
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('user_role', data.role)
    localStorage.setItem('user_name', data.full_name || username.value)
    
    // Перенаправляем на главную страницу
    router.push('/')
    
  } catch (err: any) {
    console.error('Login error:', err)
    
    // Проверяем различные типы ошибок
    if (err.message?.includes('401') || err.message?.includes('Неверные учетные данные')) {
      error.value = 'Неверное имя пользователя или пароль'
    } else if (err.message?.includes('NetworkError') || err.message?.includes('Failed to fetch')) {
      error.value = 'Ошибка подключения к серверу. Проверьте интернет-соединение.'
    } else {
      error.value = err.message || 'Ошибка авторизации. Попробуйте еще раз.'
    }
  } finally {
    loading.value = false
  }
}

// Автоматический вход для демо (можно удалить в продакшене)
const autoLogin = () => {
  const savedToken = localStorage.getItem('auth_token')
  if (savedToken && savedToken.startsWith('eyJ')) { // Проверяем, что это JWT токен
    router.push('/')
  }
}

// Проверяем авторизацию при загрузке компонента
autoLogin()
</script>