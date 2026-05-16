<template>
  <v-container fluid class="pa-4">
    <h1 class="text-h5 mb-4 d-flex align-center">
      <v-icon icon="mdi-account-multiple-outline" class="mr-2" />
      Справочник сотрудников
      <v-chip v-if="!loading" size="small" variant="tonal" class="ml-3">{{ filtered.length }}</v-chip>
    </h1>

    <!-- Поиск + фильтры -->
    <v-row class="mb-2" dense>
      <v-col cols="12" md="6">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          label="Поиск по любому полю"
          variant="outlined"
          density="compact"
          hide-details
          clearable
        />
      </v-col>
      <v-col cols="12" md="3">
        <v-select
          v-model="filterDepts"
          :items="departments"
          label="Отдел"
          variant="outlined"
          density="compact"
          hide-details
          multiple
          chips
          closable-chips
          clearable
        />
      </v-col>
      <v-col v-if="orgs.length >= 2" cols="12" md="3">
        <v-select
          v-model="filterOrgs"
          :items="orgs"
          item-title="name"
          item-value="id"
          label="Организация"
          variant="outlined"
          density="compact"
          hide-details
          multiple
          chips
          closable-chips
          clearable
        />
      </v-col>
    </v-row>

    <!-- Grid карточек -->
    <v-row v-if="loading">
      <v-col cols="12" class="text-center pa-8">
        <v-progress-circular indeterminate color="primary" />
      </v-col>
    </v-row>

    <v-row v-else-if="filtered.length === 0">
      <v-col cols="12" class="text-center pa-8 text-medium-emphasis">
        <v-icon icon="mdi-account-search-outline" size="64" class="mb-2 d-block mx-auto" />
        Сотрудники не найдены
      </v-col>
    </v-row>

    <v-row v-else dense>
      <v-col v-for="u in filtered" :key="u.id" cols="12" md="6" lg="4">
        <v-card variant="outlined" class="pa-3 staff-card cursor-pointer" @click="openCard(u)">
          <div class="d-flex ga-3">
            <!-- Фото 4:5 — 80×100 -->
            <div class="staff-card-photo">
              <img v-if="u.photo_url" :src="u.photo_url" alt="" />
              <div v-else class="staff-card-photo-placeholder">
                <v-icon icon="mdi-account" size="40" color="grey-lighten-1" />
              </div>
            </div>
            <!-- Инфо -->
            <div class="flex-grow-1 staff-card-info">
              <div class="text-subtitle-2 font-weight-bold">{{ u.full_name }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ u.position || '—' }}<span v-if="u.department"> · {{ u.department }}</span>
              </div>
              <div v-if="u.phone" class="text-caption mt-1">
                <v-icon icon="mdi-cellphone" size="12" /> {{ formatPhoneRu(u.phone) }}
              </div>
              <div v-if="u.work_phone" class="text-caption">
                <v-icon icon="mdi-phone-classic" size="12" /> {{ formatPhoneRu(u.work_phone) }}
              </div>
              <div v-if="u.email" class="text-caption text-truncate">
                <v-icon icon="mdi-email-outline" size="12" /> {{ u.email }}
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <StaffMemberDialog v-model="dialogOpen" :user="selectedUser" />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { formatPhoneRu } from '@/utils/phoneFormat'
import StaffMemberDialog from '@/components/StaffMemberDialog.vue'

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

const users = ref<DirectoryUser[]>([])
const loading = ref(true)
const search = ref('')
const filterDepts = ref<string[]>([])
const filterOrgs = ref<number[]>([])
const dialogOpen = ref(false)
const selectedUser = ref<DirectoryUser | null>(null)

const departments = computed(() => {
  const set = new Set<string>()
  for (const u of users.value) if (u.department) set.add(u.department)
  return Array.from(set).sort()
})

const orgs = computed(() => {
  const map = new Map<number, string>()
  for (const u of users.value) if (u.org_id && u.org_name) map.set(u.org_id, u.org_name)
  return Array.from(map.entries()).map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return users.value.filter((u) => {
    if (filterDepts.value.length && !filterDepts.value.includes(u.department || '')) return false
    if (filterOrgs.value.length && !filterOrgs.value.includes(u.org_id || -1)) return false
    if (!q) return true
    const haystack = [u.full_name, u.position, u.department, u.phone, u.work_phone, u.email]
      .filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(q)
  })
})

function openCard(u: DirectoryUser) {
  selectedUser.value = u
  dialogOpen.value = true
}

onMounted(async () => {
  try {
    users.value = await apiFetch<DirectoryUser[]>('/staff-directory/')
  } catch (e) {
    console.error('staff directory load failed', e)
    users.value = []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.staff-card { transition: box-shadow 0.15s; }
.staff-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.cursor-pointer { cursor: pointer; }
.staff-card-photo {
  width: 80px;
  height: 100px;
  border-radius: 8px;
  overflow: hidden;
  background: #f5f5f5;
  flex-shrink: 0;
}
.staff-card-photo img { width: 100%; height: 100%; object-fit: cover; }
.staff-card-photo-placeholder {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
}
.staff-card-info { min-width: 0; }
</style>
