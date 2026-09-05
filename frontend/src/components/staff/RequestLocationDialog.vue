<template>
  <v-dialog :model-value="modelValue" max-width="640" scrollable @update:model-value="onToggle">
    <v-card class="rounded-xl">
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-map-marker-radius" class="mr-2" />
        Запросить местоположение
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="onToggle(false)" />
      </v-card-title>
      <v-card-subtitle class="px-4 pb-2">
        Сотруднику придёт push-уведомление с экраном подтверждения (если он включил уведомления) —
        а если push не дойдёт, запасной вариант — сообщение в мессенджер. Разово, не постоянная трансляция.
      </v-card-subtitle>

      <v-card-text class="pa-2 pa-sm-4 pt-0">
        <div v-if="loading" class="text-center pa-6">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else-if="!roster.length" class="text-medium-emphasis text-body-2 pa-4 text-center">
          В ваших организациях нет других сотрудников.
        </div>
        <div v-else class="rld-list">
          <div v-for="row in roster" :key="row.user_id" class="rld-row">
            <div class="rld-row__main">
              <div class="rld-row__nm">{{ row.full_name }}</div>
              <div class="rld-row__ds">{{ row.org_name || '—' }}</div>
              <div class="rld-row__badges">
                <!-- Порядок = приоритет каналов: push первый (основной), Telegram/MAX — запасные. -->
                <v-icon
                  size="16" :color="row.has_push ? 'green' : 'grey'"
                  icon="mdi-bell-ring"
                  :style="{ opacity: row.has_push ? 1 : 0.3 }"
                  title="Push-уведомления"
                />
                <v-icon
                  size="16" :color="row.has_telegram ? 'blue' : 'grey'"
                  icon="mdi-telegram"
                  :style="{ opacity: row.has_telegram ? 1 : 0.3 }"
                  title="Telegram"
                />
                <v-icon
                  size="16" :color="row.has_max ? 'orange' : 'grey'"
                  icon="mdi-chat-processing"
                  :style="{ opacity: row.has_max ? 1 : 0.3 }"
                  title="MAX"
                />
              </div>
            </div>

            <div class="rld-row__status">
              <template v-if="!row.can_request">
                <span class="rld-status rld-status--none">
                  <v-icon size="14" icon="mdi-cellphone-off" /> нет доступных каналов
                </span>
              </template>
              <template v-else-if="row.latest_request && row.latest_request.status === 'sent'">
                <span class="rld-status rld-status--sent">
                  <v-icon size="14" icon="mdi-clock-outline" />
                  запрос отправлен, ждём ответа ({{ formatRelativeTime(row.latest_request.created_at) }})
                </span>
                <v-btn size="x-small" variant="text" color="error" @click="cancel(row)">Отменить</v-btn>
              </template>
              <template v-else-if="row.latest_request && row.latest_request.status === 'answered'">
                <span class="rld-status rld-status--answered">
                  <v-icon size="14" icon="mdi-check-circle-outline" />
                  получено {{ formatRelativeTime(row.latest_request.responded_at) }}
                </span>
                <v-btn size="x-small" variant="tonal" color="primary" :loading="sending === row.user_id" @click="request(row)">
                  Запросить ещё раз
                </v-btn>
              </template>
              <template v-else-if="row.latest_request && row.latest_request.status === 'declined'">
                <span class="rld-status rld-status--declined">
                  <v-icon size="14" icon="mdi-close-circle-outline" />
                  отказался {{ formatRelativeTime(row.latest_request.responded_at) }}
                </span>
                <v-btn size="x-small" variant="tonal" color="primary" :loading="sending === row.user_id" @click="request(row)">
                  Запросить ещё раз
                </v-btn>
              </template>
              <template v-else-if="row.latest_request && row.latest_request.status === 'expired'">
                <span class="rld-status rld-status--expired">
                  <v-icon size="14" icon="mdi-timer-off-outline" /> истёк, ответа не было
                </span>
                <v-btn size="x-small" variant="tonal" color="primary" :loading="sending === row.user_id" @click="request(row)">
                  Запросить ещё раз
                </v-btn>
              </template>
              <template v-else>
                <v-btn size="small" variant="tonal" color="primary" :loading="sending === row.user_id" @click="request(row)">
                  Запросить местоположение
                </v-btn>
              </template>
            </div>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime } from '@/utils/relativeTime'

interface LocationRequest {
  id: number
  status: 'sent' | 'answered' | 'declined' | 'expired' | 'cancelled'
  created_at: string
  responded_at: string | null
}
interface RosterEntry {
  user_id: number
  full_name: string
  org_id: number | null
  org_name: string | null
  has_push: boolean
  has_telegram: boolean
  has_max: boolean
  can_request: boolean
  latest_request: LocationRequest | null
}

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'requested'): void
}>()

const toast = useToast()
const loading = ref(false)
const sending = ref<number | null>(null)
const roster = ref<RosterEntry[]>([])

function onToggle(v: boolean) {
  emit('update:modelValue', v)
}

async function load() {
  loading.value = true
  try {
    const data = await apiFetch<RosterEntry[]>('/staff-location/roster')
    roster.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    toast.error(`Не удалось загрузить список сотрудников: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  } finally {
    loading.value = false
  }
}

async function request(row: RosterEntry) {
  sending.value = row.user_id
  try {
    const req = await apiFetch<LocationRequest>('/staff-location/requests', {
      method: 'POST',
      body: { user_id: row.user_id } as any,
    })
    row.latest_request = req
    toast.success(`Запрос отправлен: ${row.full_name}`)
    emit('requested')
  } catch (e: any) {
    toast.error(`Не удалось отправить запрос: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  } finally {
    sending.value = null
  }
}

async function cancel(row: RosterEntry) {
  if (!row.latest_request) return
  const id = row.latest_request.id
  try {
    const req = await apiFetch<LocationRequest>(`/staff-location/requests/${id}/cancel`, { method: 'POST' })
    row.latest_request = req
    toast.success('Запрос отменён')
  } catch (e: any) {
    toast.error(`Не удалось отменить запрос: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  }
}

watch(() => props.modelValue, (open) => {
  if (open) load()
})
</script>

<style scoped>
.rld-list { display: flex; flex-direction: column; }
.rld-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 8px; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  flex-wrap: wrap;
}
.rld-row:last-child { border-bottom: none; }
.rld-row__main { min-width: 180px; }
.rld-row__nm { font-weight: 600; font-size: 13.5px; }
.rld-row__ds { font-size: 11.5px; opacity: 0.65; }
.rld-row__badges { display: flex; gap: 6px; margin-top: 2px; }
.rld-row__status { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.rld-status { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; white-space: nowrap; }
.rld-status--none { opacity: 0.55; }
.rld-status--sent { color: #f6b34a; }
.rld-status--answered { color: #22c997; }
.rld-status--declined { color: #ff5b6a; }
.rld-status--expired { color: #8a93a8; }
</style>
