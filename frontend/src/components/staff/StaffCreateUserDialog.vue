<template>
  <v-dialog v-model="dialog.show" max-width="440" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">Добавить сотрудника</v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-form ref="createFormRef">
        <v-text-field v-model="dialog.last_name" label="Фамилия *" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-account" :rules="[v => !!v || 'Фамилия обязательна']" />
        <v-text-field v-model="dialog.first_name" label="Имя *" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-account" :rules="[v => !!v || 'Имя обязательно']" />
        <v-text-field v-model="dialog.middle_name" label="Отчество" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-account" hint="Необязательно — не у всех есть отчество" persistent-hint />
        <v-text-field v-model="dialog.email" label="Email *" variant="outlined" density="compact" class="mb-3"
          hint="Используется для входа в систему" persistent-hint prepend-inner-icon="mdi-email-outline"
          type="email" :rules="[v => !!v || 'Email обязателен', v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Введите корректный email (например, ivanov@company.ru)']" />
        <v-text-field
          :model-value="formatPhoneRu(dialog.phone)"
          @update:model-value="dialog.phone = $event"
          label="Телефон" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-phone" placeholder="8-999-999-99-99"
          hint="Формат: 8-999-999-99-99. Для связи и интеграции с Telegram" persistent-hint
        />
        <v-text-field
          :model-value="formatPhoneRu(dialog.work_phone)"
          @update:model-value="dialog.work_phone = unformatPhone($event)"
          label="Рабочий телефон" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-phone-classic" placeholder="8-999-999-99-99"
        />
        <v-text-field v-model="dialog.telegram_id" label="Telegram Chat ID" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-send" placeholder="123456789"
          hint="Числовой ID чата Telegram (узнать: написать боту @userinfobot)" persistent-hint />
        <v-text-field v-model="dialog.max_chat_id" label="MAX (VK) Chat ID" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-message-processing" placeholder="123456789"
          hint="Числовой ID для уведомлений через MAX-бот" persistent-hint />
        <v-select
          v-model="dialog.role"
          :items="roleItems"
          item-title="label" item-value="value"
          label="Роль"
          variant="outlined" density="compact" class="mb-3"
        />
        <v-autocomplete v-if="canPickOrg" v-model="dialog.org_id" :items="assignableOrganizations" item-title="name" item-value="id"
          label="Организация *" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-domain" :rules="[v => !!v || 'Организация обязательна']" />
        <v-text-field v-else label="Организация" variant="outlined" density="compact" class="mb-3"
          :model-value="currentOrgName" disabled prepend-inner-icon="mdi-domain" />
        <v-combobox v-model="dialog.department" :items="getDepartmentsForOrg(dialog.org_id)" label="Отдел" variant="outlined" density="compact" clearable class="mb-3"
          :hint="dialog.org_id ? 'Введите новый отдел или выберите из списка' : 'Сначала выберите организацию — покажем её отделы'" persistent-hint
          :no-data-text="dialog.org_id ? 'Введите название нового отдела' : 'Сначала выберите организацию'" prepend-inner-icon="mdi-office-building-outline" />
        <v-combobox v-model="dialog.position" :items="getPositionsForOrg(dialog.org_id)" label="Должность" variant="outlined" density="compact" clearable class="mb-3"
          hint="Введите новую должность или выберите из списка" persistent-hint
          no-data-text="Введите название новой должности" prepend-inner-icon="mdi-briefcase-outline" />
        <v-autocomplete v-model="dialog.subsidy_id" :items="subsidies" item-title="name" item-value="id"
          label="Субсидия" variant="outlined" density="compact" clearable class="mb-3"
          prepend-inner-icon="mdi-cash-multiple" hint="Необязательно" persistent-hint />
        <!-- Avatar picker -->
        <div class="mb-3">
          <div class="text-caption text-medium-emphasis mb-1">Аватарка</div>
          <div class="d-flex flex-wrap" style="gap:8px">
            <div v-for="av in AVATARS" :key="av.id"
              class="avatar-pick"
              :class="{ 'avatar-pick-active': dialog.avatar === av.id }"
              @click="dialog.avatar = av.id">
              <v-avatar :color="av.color" size="40">
                <v-icon :icon="av.icon" size="22" color="white" />
              </v-avatar>
            </div>
          </div>
        </div>
        <v-text-field v-model="dialog.city" label="Город" variant="outlined" density="compact" />
        </v-form>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat"
          :loading="dialog.saving"
          :disabled="!dialog.email || !dialog.password || dialog.password !== dialog.password_confirm || (canPickOrg && !dialog.org_id)"
          @click="$emit('save')">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { formatPhoneRu, unformatPhone } from '@/utils/phoneFormat'
import { AVATARS } from '@/composables/staff/staffLabels'

defineProps<{
  dialog: {
    show: boolean; last_name: string; first_name: string; middle_name: string; email: string
    password: string; password_confirm: string; role: string; city: string; department: string
    position: string; phone: string; work_phone: string; telegram_id: string; avatar: string
    saving: boolean; org_id: number | null; subsidy_id: number | null
  }
  roleItems: { value: string; label: string }[]
  canPickOrg: boolean
  assignableOrganizations: any[]
  currentOrgName: string
  getDepartmentsForOrg: (orgId?: number | null) => string[]
  getPositionsForOrg: (orgId?: number | null) => string[]
  subsidies: any[]
  mobile: boolean
}>()
defineEmits<{ (e: 'save'): void }>()

// Форма живёт внутри диалога — наружу отдаём только validate(), чтобы
// useStaffCreateUser::saveUser() мог подсветить невалидные поля перед сохранением
// (ref="createFormRef" в оригинале жил в том же файле, что и <v-form>).
const createFormRef = ref<any>(null)
defineExpose({ validate: () => createFormRef.value?.validate?.() })
</script>

<style scoped>
/* Avatar picker styles — перенесено из StaffView.vue */
.avatar-pick { cursor: pointer; border-radius: 50%; padding: 2px; border: 2px solid transparent; transition: all 0.2s; }
.avatar-pick:hover { border-color: rgba(var(--v-theme-primary), 0.3); transform: scale(1.1); }
.avatar-pick-active { border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.4); }
</style>
