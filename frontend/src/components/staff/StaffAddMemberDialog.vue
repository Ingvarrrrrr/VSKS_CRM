<template>
  <v-dialog v-model="show" max-width="500" :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center">
        Добавить сотрудника в отдел
        <v-spacer />
        <v-chip v-if="selectedDept" size="small" variant="tonal" color="primary">{{ selectedDept.name }}</v-chip>
      </v-card-title>
      <v-card-text>
        <!-- Toggle: existing or new -->
        <v-btn-toggle v-model="addMemberMode" mandatory density="compact" color="primary" class="mb-3" style="width:100%">
          <v-btn value="existing" size="small" style="flex:1"><v-icon icon="mdi-account-search" class="mr-1" size="16"/>Существующий</v-btn>
          <v-btn value="new" size="small" style="flex:1"><v-icon icon="mdi-account-plus" class="mr-1" size="16"/>Создать нового</v-btn>
        </v-btn-toggle>

        <!-- Existing user -->
        <template v-if="addMemberMode === 'existing'">
          <v-select v-model="memberForm.user_id" :items="userDropdownItems" item-title="text" item-value="value"
            label="Сотрудник *" variant="outlined" density="compact" class="mb-3"
            hint="Список пользователей вашей организации" persistent-hint />
          <v-combobox v-model="memberForm.position" :items="getPositionsForOrg(selectedDept?.org_id)" label="Должность в отделе" variant="outlined" density="compact"
            hint="Выберите из списка или введите свою" persistent-hint />
        </template>

        <!-- New user (inline creation) -->
        <template v-if="addMemberMode === 'new'">
          <v-text-field v-model="newMemberForm.last_name" label="Фамилия *" variant="outlined" density="compact" class="mb-2"
            prepend-inner-icon="mdi-account" />
          <v-text-field v-model="newMemberForm.first_name" label="Имя *" variant="outlined" density="compact" class="mb-2"
            prepend-inner-icon="mdi-account" />
          <v-text-field v-model="newMemberForm.middle_name" label="Отчество" variant="outlined" density="compact" class="mb-2"
            prepend-inner-icon="mdi-account" hint="Необязательно" persistent-hint />
          <v-text-field v-model="newMemberForm.email" label="Email *" variant="outlined" density="compact" class="mb-2"
            type="email" prepend-inner-icon="mdi-email-outline"
            :rules="[v => !!v || 'Обязательное поле', v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Введите корректный email (например, ivanov@company.ru)']" />
          <v-text-field
            :model-value="formatPhoneRu(newMemberForm.phone)"
            @update:model-value="newMemberForm.phone = $event"
            label="Телефон" variant="outlined" density="compact" class="mb-2"
            prepend-inner-icon="mdi-phone" placeholder="8-999-999-99-99"
            hint="Формат: 8-999-999-99-99" persistent-hint
          />
          <v-text-field v-model="newMemberForm.password" label="Пароль *" type="password" variant="outlined" density="compact" class="mb-2"
            :rules="[v => !!v || 'Обязательное поле', v => v.length >= 6 || 'Минимум 6 символов']" />
          <v-text-field v-model="newMemberForm.password_confirm" label="Подтвердите пароль *" type="password" variant="outlined" density="compact" class="mb-2"
            :error="!!newMemberForm.password_confirm && newMemberForm.password !== newMemberForm.password_confirm"
            :error-messages="newMemberForm.password_confirm && newMemberForm.password !== newMemberForm.password_confirm ? 'Пароли не совпадают' : ''" />
          <v-select v-model="newMemberForm.role" :items="roleItems" item-title="label" item-value="value"
            label="Роль" variant="outlined" density="compact" class="mb-2" />
          <v-combobox v-model="newMemberForm.position" :items="getPositionsForOrg(selectedDept?.org_id)" label="Должность" variant="outlined" density="compact" class="mb-2"
            hint="Выберите из списка или введите свою" persistent-hint />
          <v-text-field v-model="newMemberForm.city" label="Город" variant="outlined" density="compact" />
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn v-if="addMemberMode === 'existing'" color="primary" :disabled="!memberForm.user_id" @click="$emit('add')">Добавить</v-btn>
        <v-btn v-else color="primary"
          :disabled="!newMemberForm.email || !newMemberForm.password || !newMemberForm.last_name || !newMemberForm.first_name || newMemberForm.password.length < 6 || newMemberForm.password !== newMemberForm.password_confirm || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newMemberForm.email)"
          :loading="newMemberSaving" @click="$emit('create-and-add')">Создать и добавить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { formatPhoneRu } from '@/utils/phoneFormat'

defineProps<{
  selectedDept: any
  memberForm: { user_id: number | null; position: string }
  newMemberForm: { email: string; last_name: string; first_name: string; middle_name: string; password: string; password_confirm: string; phone: string; role: string; position: string; city: string }
  userDropdownItems: { text: string; value: number }[]
  roleItems: { value: string; label: string }[]
  getPositionsForOrg: (orgId?: number | null) => string[]
  newMemberSaving: boolean
  mobile: boolean
}>()
defineEmits<{ (e: 'add'): void; (e: 'create-and-add'): void }>()
const show = defineModel<boolean>('show', { required: true })
const addMemberMode = defineModel<'existing' | 'new'>('addMemberMode', { required: true })
</script>
