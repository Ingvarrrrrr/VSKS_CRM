<template>
  <v-card variant="outlined" class="mt-4">
    <v-card-title class="pa-4 pb-2 d-flex align-center">
      <v-icon size="18" class="mr-2" color="primary">mdi-store-outline</v-icon>
      <span class="text-subtitle-1">Электронные площадки</span>
    </v-card-title>

    <v-card-text class="pa-4 pt-2">
      <!-- Fabrikant block -->
      <div class="mb-1">
        <div class="text-body-2 font-weight-medium mb-3 d-flex align-center">
          <v-icon size="15" class="mr-1" color="blue-grey">mdi-web</v-icon>
          Фабрикант
        </div>

        <v-row dense class="mb-2">
          <v-col cols="12">
            <v-text-field
              v-model="form.login"
              label="Логин Фабрикант"
              variant="outlined"
              density="compact"
              hide-details="auto"
              autocomplete="off"
              :disabled="saving"
            />
          </v-col>
          <v-col cols="12" class="mt-2">
            <v-text-field
              v-model="form.password"
              label="Пароль"
              :placeholder="cred && cred.has_password ? '••• (задан)' : ''"
              type="password"
              variant="outlined"
              density="compact"
              autocomplete="new-password"
              :disabled="saving"
              :hint="cred && cred.has_password ? 'Оставьте пустым, чтобы не менять пароль' : ''"
              persistent-hint
            />
          </v-col>
        </v-row>

        <div class="d-flex align-center gap-3 mt-2">
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            :loading="saving"
            :disabled="!form.login.trim()"
            prepend-icon="mdi-content-save-outline"
            @click="saveCred"
          >Сохранить</v-btn>

          <v-btn
            v-if="cred"
            color="error"
            variant="text"
            size="small"
            :loading="deleting"
            :disabled="saving"
            prepend-icon="mdi-delete-outline"
            @click="confirmDelete"
          >Удалить</v-btn>

          <v-progress-circular
            v-if="loading"
            size="18"
            width="2"
            indeterminate
            color="primary"
            class="ml-2"
          />

          <v-spacer />

          <v-chip
            v-if="cred"
            size="x-small"
            color="success"
            variant="tonal"
            prepend-icon="mdi-check-circle-outline"
          >Учётка задана</v-chip>
          <v-chip
            v-else-if="!loading"
            size="x-small"
            color="default"
            variant="tonal"
            prepend-icon="mdi-minus-circle-outline"
          >Не задана</v-chip>
        </div>
      </div>
    </v-card-text>

    <!-- Confirm delete dialog -->
    <v-dialog v-model="deleteConfirm" max-width="360">
      <v-card>
        <v-card-title class="pa-4">Удалить учётку Фабрикант?</v-card-title>
        <v-card-text class="pa-4 pt-0 text-body-2">
          Логин <strong>{{ cred?.login }}</strong> будет удалён. Действие нельзя отменить.
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteConfirm = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { apiFetch } from '../api'

const props = defineProps<{
  userId: number
}>()

const emit = defineEmits<{
  (e: 'error', msg: string): void
}>()

interface PlatformCred {
  platform: string
  login: string
  has_password: boolean
}

const PLATFORM = 'fabrikant'

const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const deleteConfirm = ref(false)

const cred = ref<PlatformCred | null>(null)
const form = reactive({ login: '', password: '' })

async function loadCreds() {
  loading.value = true
  try {
    const data = await apiFetch<PlatformCred[]>(`/users/${props.userId}/platform-credentials`)
    const found = data.find(c => c.platform === PLATFORM) ?? null
    cred.value = found
    form.login = found?.login ?? ''
    form.password = ''
  } catch (e: any) {
    const msg = e?.payload?.message || e?.message || 'Ошибка загрузки учётки'
    emit('error', msg)
  } finally {
    loading.value = false
  }
}

async function saveCred() {
  if (!form.login.trim()) return
  saving.value = true
  try {
    const body: Record<string, string> = { login: form.login.trim() }
    if (form.password) body.password = form.password
    await apiFetch(`/users/${props.userId}/platform-credentials/${PLATFORM}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
    form.password = ''
    await loadCreds()
  } catch (e: any) {
    const msg = e?.payload?.message || e?.message || 'Ошибка сохранения'
    emit('error', msg)
  } finally {
    saving.value = false
  }
}

function confirmDelete() {
  deleteConfirm.value = true
}

async function doDelete() {
  deleting.value = true
  try {
    await apiFetch(`/users/${props.userId}/platform-credentials/${PLATFORM}`, {
      method: 'DELETE',
    })
    cred.value = null
    form.login = ''
    form.password = ''
    deleteConfirm.value = false
  } catch (e: any) {
    const msg = e?.payload?.message || e?.message || 'Ошибка удаления'
    emit('error', msg)
    deleteConfirm.value = false
  } finally {
    deleting.value = false
  }
}

// Load when userId changes (dialog reused for different users)
watch(() => props.userId, (id) => {
  if (id) loadCreds()
}, { immediate: true })
</script>
