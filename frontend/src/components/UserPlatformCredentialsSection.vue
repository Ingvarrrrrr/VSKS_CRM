<template>
  <v-card variant="outlined" class="mt-4">
    <v-card-title class="pa-4 pb-2 d-flex align-center">
      <v-icon size="18" class="mr-2" color="primary">mdi-store-outline</v-icon>
      <span class="text-subtitle-1">Электронные площадки</span>
    </v-card-title>

    <v-card-text class="pa-4 pt-2">
      <!-- Fabrikant block -->
      <div class="mb-5">
        <div class="text-body-2 font-weight-medium mb-3 d-flex align-center">
          <v-icon size="15" class="mr-1" color="blue-grey">mdi-web</v-icon>
          Фабрикант
        </div>

        <v-row dense class="mb-2">
          <v-col cols="12">
            <v-text-field
              v-model="fab.form.login"
              label="Логин Фабрикант"
              variant="outlined"
              density="compact"
              hide-details="auto"
              autocomplete="off"
              :disabled="fab.saving.value"
            />
          </v-col>
          <v-col cols="12" class="mt-2">
            <v-text-field
              v-model="fab.form.password"
              label="Пароль"
              :placeholder="fab.cred.value && fab.cred.value.has_password ? '••• (задан)' : ''"
              type="password"
              variant="outlined"
              density="compact"
              autocomplete="new-password"
              :disabled="fab.saving.value"
              :hint="fab.cred.value && fab.cred.value.has_password ? 'Оставьте пустым, чтобы не менять пароль' : ''"
              persistent-hint
            />
          </v-col>
        </v-row>

        <div class="d-flex align-center gap-3 mt-2">
          <v-btn
            color="primary" variant="tonal" size="small"
            :loading="fab.saving.value"
            :disabled="!fab.form.login.trim()"
            prepend-icon="mdi-content-save-outline"
            @click="onSave(fab)"
          >Сохранить</v-btn>

          <v-btn
            v-if="fab.cred.value"
            color="error" variant="text" size="small"
            :loading="fab.deleting.value"
            :disabled="fab.saving.value"
            prepend-icon="mdi-delete-outline"
            @click="fab.confirmDelete()"
          >Удалить</v-btn>

          <v-progress-circular v-if="fab.loading.value" size="18" width="2" indeterminate color="primary" class="ml-2" />

          <v-spacer />

          <v-chip v-if="fab.cred.value" size="x-small" color="success" variant="tonal" prepend-icon="mdi-check-circle-outline">Учётка задана</v-chip>
          <v-chip v-else-if="!fab.loading.value" size="x-small" color="default" variant="tonal" prepend-icon="mdi-minus-circle-outline">Не задана</v-chip>
        </div>
      </div>

      <v-divider class="mb-5" />

      <!-- Roseltorg.Business block: только интеграционный токен, логина у площадки нет -->
      <div>
        <div class="text-body-2 font-weight-medium mb-3 d-flex align-center">
          <v-icon size="15" class="mr-1" color="blue-grey">mdi-web</v-icon>
          Росэлторг.Бизнес
        </div>

        <v-row dense class="mb-2">
          <v-col cols="12">
            <v-text-field
              v-model="ros.form.password"
              label="Интеграционный токен"
              :placeholder="ros.cred.value && ros.cred.value.has_password ? '••• (задан)' : ''"
              type="password"
              variant="outlined"
              density="compact"
              autocomplete="new-password"
              :disabled="ros.saving.value"
              hint="Выпускается в Росэлторг.ID → Компания → Управление правами доступа → Внешние интеграции → Создать токен"
              persistent-hint
            />
          </v-col>
        </v-row>

        <div class="d-flex align-center gap-3 mt-2">
          <v-btn
            color="primary" variant="tonal" size="small"
            :loading="ros.saving.value"
            :disabled="!ros.form.password.trim() && !ros.cred.value"
            prepend-icon="mdi-content-save-outline"
            @click="onSave(ros)"
          >Сохранить</v-btn>

          <v-btn
            v-if="ros.cred.value"
            color="error" variant="text" size="small"
            :loading="ros.deleting.value"
            :disabled="ros.saving.value"
            prepend-icon="mdi-delete-outline"
            @click="ros.confirmDelete()"
          >Удалить</v-btn>

          <v-progress-circular v-if="ros.loading.value" size="18" width="2" indeterminate color="primary" class="ml-2" />

          <v-spacer />

          <v-chip v-if="ros.cred.value" size="x-small" color="success" variant="tonal" prepend-icon="mdi-check-circle-outline">Токен задан</v-chip>
          <v-chip v-else-if="!ros.loading.value" size="x-small" color="default" variant="tonal" prepend-icon="mdi-minus-circle-outline">Не задан</v-chip>
        </div>
      </div>
    </v-card-text>

    <!-- Confirm delete dialogs -->
    <v-dialog v-model="fab.deleteConfirm.value" max-width="360">
      <v-card>
        <v-card-title class="pa-4">Удалить учётку Фабрикант?</v-card-title>
        <v-card-text class="pa-4 pt-0 text-body-2">
          Логин <strong>{{ fab.cred.value?.login }}</strong> будет удалён. Действие нельзя отменить.
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="fab.deleteConfirm.value = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="fab.deleting.value" @click="onDelete(fab)">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="ros.deleteConfirm.value" max-width="360">
      <v-card>
        <v-card-title class="pa-4">Удалить токен Росэлторг.Бизнес?</v-card-title>
        <v-card-text class="pa-4 pt-0 text-body-2">
          Интеграционный токен будет удалён. Действие нельзя отменить.
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="ros.deleteConfirm.value = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="ros.deleting.value" @click="onDelete(ros)">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup lang="ts">
import { usePlatformCredential } from '../composables/usePlatformCredential'

const props = defineProps<{
  userId: number
}>()

const emit = defineEmits<{
  (e: 'error', msg: string): void
}>()

// ПРАВИЛО №6: один и тот же composable (usePlatformCredential) для обеих
// площадок — разница только в platform/requireLogin, не второй механизм CRUD.
const fab = usePlatformCredential(() => props.userId, 'fabrikant', true)
const ros = usePlatformCredential(() => props.userId, 'roseltorg', false)

async function onSave(block: typeof fab | typeof ros) {
  try {
    await block.saveCred()
  } catch (e: any) {
    emit('error', e?.message || 'Ошибка сохранения')
  }
}

async function onDelete(block: typeof fab | typeof ros) {
  try {
    await block.doDelete()
  } catch (e: any) {
    emit('error', e?.message || 'Ошибка удаления')
  }
}
</script>
