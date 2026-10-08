<template>
  <v-container class="fill-height">
    <v-responsive class="align-center text-center fill-height">
      <v-card class="mx-auto pa-8 text-left" max-width="560" elevation="8">
        <v-card-title class="text-h5 mb-2 text-center">Подтвердите согласие</v-card-title>
        <p class="text-body-2 text-medium-emphasis mb-6 text-center">
          Мы опубликовали правила обработки персональных данных. Чтобы продолжить работу, подтвердите согласие.
        </p>

        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate color="primary" />
        </div>

        <div v-else-if="!status" class="text-center py-2">
          <v-alert type="error" density="compact" class="mb-4">
            Не удалось проверить статус согласия — проверьте соединение и попробуйте ещё раз.
          </v-alert>
          <v-btn color="primary" variant="tonal" class="mr-2" @click="retry">Повторить</v-btn>
          <v-btn variant="text" @click="logout">Выйти</v-btn>
        </div>

        <template v-else>
          <div v-if="status.pd_consent_required" class="mb-4">
            <v-checkbox v-model="pdAccepted" density="compact" hide-details color="primary">
              <template #label>
                <span class="gate-label">
                  Я даю <a href="/legal/consent" target="_blank" rel="noopener noreferrer" @click.stop>согласие</a>
                  на обработку персональных данных и подтверждаю, что ознакомлен с
                  <a href="/legal/privacy" target="_blank" rel="noopener noreferrer" @click.stop>политикой обработки персональных данных</a>
                </span>
              </template>
            </v-checkbox>
          </div>

          <div v-if="status.poruchenie_required" class="mb-4">
            <v-checkbox v-model="poruchenieAccepted" density="compact" hide-details color="primary">
              <template #label>
                <span class="gate-label">
                  Организация «{{ status.poruchenie_org?.name }}» поручает обработку персональных
                  данных своих сотрудников и контрагентов на
                  <a href="/legal/poruchenie" target="_blank" rel="noopener noreferrer" @click.stop>условиях поручения</a>
                  — подтвердите как владелец организации
                </span>
              </template>
            </v-checkbox>
          </div>

          <v-alert v-if="error" type="error" class="mb-4" density="compact">{{ error }}</v-alert>

          <div class="d-flex ga-2 mt-2">
            <v-btn
              color="primary" :disabled="!canContinue" :loading="submitting"
              @click="submit"
            >
              Продолжить
            </v-btn>
            <v-btn variant="text" :disabled="submitting" @click="logout">Выйти</v-btn>
          </div>
        </template>
      </v-card>
    </v-responsive>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import {
  consentGateRequired,
  ensureConsentGateLoaded,
  resetConsentGate,
  type ConsentStatus,
} from '@/composables/useConsentGate'

const router = useRouter()
const route = useRoute()

const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const status = ref<ConsentStatus | null>(null)
// Чекбоксы — по умолчанию всегда сняты, ни при каких условиях не предзаполняются.
const pdAccepted = ref(false)
const poruchenieAccepted = ref(false)

const canContinue = computed(() => {
  if (!status.value) return false
  if (status.value.pd_consent_required && !pdAccepted.value) return false
  if (status.value.poruchenie_required && !poruchenieAccepted.value) return false
  return true
})

async function load() {
  loading.value = true
  status.value = await ensureConsentGateLoaded()
  loading.value = false
}

async function retry() {
  resetConsentGate()
  await load()
}

onMounted(load)

async function submit() {
  if (!status.value) return
  submitting.value = true
  error.value = ''
  try {
    if (status.value.pd_consent_required) {
      await apiFetch('/legal/consent', {
        method: 'POST',
        body: JSON.stringify({ kind: 'pd', accepted: true }),
        suppressErrorDialog: true,
      })
    }
    if (status.value.poruchenie_required && status.value.poruchenie_org) {
      await apiFetch('/legal/consent', {
        method: 'POST',
        body: JSON.stringify({ kind: 'poruchenie', accepted: true, org_id: status.value.poruchenie_org.id }),
        suppressErrorDialog: true,
      })
    }
    resetConsentGate()
    const fresh = await ensureConsentGateLoaded()
    if (consentGateRequired(fresh)) {
      // Владелец нескольких организаций без поручения — consent-status
      // отдаёт только первую; остаётся на странице со свежим состоянием
      // (следующая организация) вместо редиректа с незакрытым требованием.
      status.value = fresh
      pdAccepted.value = false
      poruchenieAccepted.value = false
      return
    }
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    error.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось сохранить согласие'
  } finally {
    submitting.value = false
  }
}

function logout() {
  resetConsentGate()
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_role')
  window.location.href = '/login'
}
</script>

<style scoped>
.gate-label {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.gate-label a {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}
.gate-label a:hover {
  text-decoration: none;
}
</style>
