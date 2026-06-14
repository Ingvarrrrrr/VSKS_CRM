<template>
  <v-dialog v-model="open" max-width="540" scrollable :fullscreen="mobile">
    <v-card v-if="user">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-account-circle-outline" color="primary" class="mr-2" />
        Карточка сотрудника
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="open = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <div class="d-flex flex-column flex-sm-row ga-4">
          <!-- Фото 160×200 -->
          <div class="staff-photo-wrap">
            <img v-if="user.photo_url" :src="user.photo_url" alt="" class="staff-photo" />
            <div v-else class="staff-photo-placeholder">
              <v-icon icon="mdi-account" size="80" color="grey-lighten-1" />
            </div>
          </div>
          <!-- Контакты -->
          <div class="flex-grow-1">
            <div class="text-h6">{{ user.full_name }}</div>
            <div v-if="user.position" class="text-body-2 text-medium-emphasis mt-1">{{ user.position }}</div>
            <div v-if="user.department" class="text-caption text-medium-emphasis">{{ user.department }}</div>
            <div v-if="user.org_name" class="text-caption text-medium-emphasis mt-2">
              <v-icon icon="mdi-office-building" size="14" /> {{ user.org_name }}
            </div>

            <v-divider class="my-3" />

            <div v-if="user.phone" class="d-flex align-center mb-2">
              <v-icon icon="mdi-cellphone" color="primary" size="20" class="mr-2" />
              <a :href="`tel:${rawPhone(user.phone)}`" class="text-decoration-none">
                {{ formatPhoneRu(user.phone) }}
              </a>
              <span class="text-caption text-medium-emphasis ml-2">мобильный</span>
            </div>

            <div v-if="user.work_phone" class="d-flex align-center mb-2">
              <v-icon icon="mdi-phone-classic" color="indigo" size="20" class="mr-2" />
              <a :href="`tel:${rawPhone(user.work_phone)}`" class="text-decoration-none">
                {{ formatPhoneRu(user.work_phone) }}
              </a>
              <span class="text-caption text-medium-emphasis ml-2">рабочий</span>
            </div>

            <div v-if="user.email" class="d-flex align-center">
              <v-icon icon="mdi-email-outline" color="teal" size="20" class="mr-2" />
              <a :href="`mailto:${user.email}`" class="text-decoration-none">{{ user.email }}</a>
            </div>
          </div>
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplay } from 'vuetify'
import { formatPhoneRu, unformatPhone } from '@/utils/phoneFormat'

const { mobile } = useDisplay()

interface DirectoryUser {
  id: number
  full_name: string
  position: string | null
  department: string | null
  phone: string | null
  work_phone: string | null
  email: string | null
  photo_url: string | null
  org_name: string | null
  org_id: number | null
}

const props = defineProps<{ modelValue: boolean; user: DirectoryUser | null }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean] }>()
const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

function rawPhone(s: string): string {
  const digits = unformatPhone(s)
  // Ensure +7 prefix for tel: links
  if (digits.length === 11 && (digits[0] === '7' || digits[0] === '8')) {
    return '+7' + digits.slice(1)
  }
  return '+' + digits
}
</script>

<style scoped>
.staff-photo-wrap {
  flex-shrink: 0;
  width: 160px;
  height: 200px;
  border-radius: 12px;
  overflow: hidden;
  background: #f5f5f5;
}
.staff-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.staff-photo-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
