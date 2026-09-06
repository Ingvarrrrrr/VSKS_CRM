<template>
  <!-- ── Мероприятия ── -->
  <div class="mt-4">
    <div class="detail-feo-header">
      <span class="chart-card-title">Мероприятия</span>
      <div class="d-flex gap-2">
        <v-btn v-if="subsidyId" size="small" variant="tonal" color="success" prepend-icon="mdi-microsoft-excel"
          @click="downloadReport(subsidyId)">
          Приложение №3
        </v-btn>
        <v-btn v-if="isAdminLevel" size="small" variant="tonal" prepend-icon="mdi-plus" @click="showAddEventDialog = true">
          Добавить
        </v-btn>
      </div>
    </div>
    <div v-if="subsidyEvents.length === 0" class="feo-empty">
      <v-icon icon="mdi-calendar-blank" size="40" color="grey-lighten-2" />
      <div class="text-caption text-medium-emphasis mt-2">Нет мероприятий</div>
    </div>
    <v-list v-else density="compact" class="pa-0">
      <v-list-item v-for="ev in subsidyEvents" :key="ev.id" class="px-2">
        <template #prepend>
          <v-icon :icon="ev.is_active ? 'mdi-calendar-check' : 'mdi-calendar-remove'" :color="ev.is_active ? 'success' : 'grey'" size="18" />
        </template>
        <v-list-item-title class="text-body-2">{{ ev.name }}</v-list-item-title>
        <v-list-item-subtitle v-if="ev.region || ev.date_from" class="text-caption">
          <span v-if="ev.region">{{ ev.region }}</span>
          <span v-if="ev.region && ev.date_from"> · </span>
          <span v-if="ev.date_from">{{ ev.date_from }} — {{ ev.date_to }}</span>
        </v-list-item-subtitle>
        <template v-if="isAdminLevel" #append>
          <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="openEditEventDialog(ev)" />
          <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteEvent(ev.id)" />
        </template>
      </v-list-item>
    </v-list>
  </div>

  <!-- ── Add Event Dialog ── -->
  <v-dialog v-model="showAddEventDialog" max-width="640" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-calendar-plus" color="primary" class="mr-2" />
        Добавить мероприятие
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showAddEventDialog = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3">
          Это единственное место, где заводятся мероприятия. В заявках, закупках и импорте
          они только выбираются из этого списка — не создавайте копию с другим написанием.
        </v-alert>
        <v-text-field v-model="newEventName" label="Название мероприятия *" variant="outlined" density="compact" class="mb-3" />
        <v-row dense>
          <v-col cols="12" md="6">
            <v-text-field v-model="newEventRegion" label="Регион проведения" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="newEventDateFrom" label="Дата начала" type="date" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="newEventDateTo" label="Дата окончания" type="date" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-text-field v-model="newEventOrderDecree" label="Реквизиты приказа" variant="outlined" density="compact" class="mt-3" hide-details />
        <v-textarea v-model="newEventPlannedIndicators" label="Плановые показатели (KPI)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-textarea v-model="newEventActualIndicators" label="Фактически достигнутые показатели" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-text-field v-model="newEventMediaLink1" label="Ссылка на СМИ 1" variant="outlined" density="compact" class="mt-3" hide-details />
        <v-text-field v-model="newEventMediaLink2" label="Ссылка на СМИ 2" variant="outlined" density="compact" class="mt-2" hide-details />
        <v-text-field v-model="newEventMediaLink3" label="Ссылка на СМИ 3" variant="outlined" density="compact" class="mt-2" hide-details />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="showAddEventDialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!newEventName.trim()" @click="addEvent">Добавить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── Edit Event Dialog ── -->
  <v-dialog v-model="showEditEventDialog" max-width="640" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-calendar-edit" color="primary" class="mr-2" />
        Редактировать мероприятие
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showEditEventDialog = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <v-text-field v-model="editEventForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" />
        <v-row>
          <v-col cols="12" md="6">
            <v-text-field v-model="editEventForm.region" label="Регион проведения" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="editEventForm.date_from" label="Дата начала" type="date" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="editEventForm.date_to" label="Дата окончания" type="date" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-text-field v-model="editEventForm.order_decree" label="Реквизиты приказа (номер, дата)" variant="outlined" density="compact" class="mt-3" hide-details />
        <v-textarea v-model="editEventForm.planned_indicators" label="Плановые показатели (KPI)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-textarea v-model="editEventForm.actual_indicators" label="Фактически достигнутые показатели" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-text-field v-model="editEventForm.media_link_1" label="Ссылка на СМИ 1" variant="outlined" density="compact" class="mt-3" hide-details />
        <v-text-field v-model="editEventForm.media_link_2" label="Ссылка на СМИ 2" variant="outlined" density="compact" class="mt-2" hide-details />
        <v-text-field v-model="editEventForm.media_link_3" label="Ссылка на СМИ 3" variant="outlined" density="compact" class="mt-2" hide-details />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="showEditEventDialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="savingEvent" @click="saveEditEvent">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { EventItem } from '@/composables/subsidies/types'

const props = defineProps<{ subsidyId: number | null }>()

const { mobile } = useDisplay()
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}

const userRoleRaw = localStorage.getItem('user_role') || ''
const isAdminLevel = ['superadmin', 'org_admin', 'admin'].includes(userRoleRaw)

const subsidyEvents = ref<EventItem[]>([])
const showAddEventDialog = ref(false)
const newEventName = ref('')
const newEventRegion = ref('')
const newEventDateFrom = ref('')
const newEventDateTo = ref('')
const newEventOrderDecree = ref('')
const newEventPlannedIndicators = ref('')
const newEventActualIndicators = ref('')
const newEventMediaLink1 = ref('')
const newEventMediaLink2 = ref('')
const newEventMediaLink3 = ref('')
const showEditEventDialog = ref(false)
const savingEvent = ref(false)
const editEventForm = ref<EventItem>({
  id: 0, subsidy_id: 0, name: '', is_active: true,
  region: '', date_from: '', date_to: '',
  order_decree: '', planned_indicators: '', actual_indicators: '',
  media_link_1: '', media_link_2: '', media_link_3: '',
})

// ── Events (Мероприятия) CRUD ──
async function loadEvents(subsidyId: number) {
  try {
    subsidyEvents.value = await apiFetch<EventItem[]>(`/events/?subsidy_id=${subsidyId}`)
  } catch {
    subsidyEvents.value = []
  }
}

async function addEvent() {
  if (!newEventName.value.trim() || !props.subsidyId) return
  try {
    await apiFetch('/events/', {
      method: 'POST',
      body: JSON.stringify({
        subsidy_id: props.subsidyId,
        name: newEventName.value.trim(),
        is_active: true,
        region: newEventRegion.value.trim() || null,
        date_from: newEventDateFrom.value || null,
        date_to: newEventDateTo.value || null,
        order_decree: newEventOrderDecree.value.trim() || null,
        planned_indicators: newEventPlannedIndicators.value.trim() || null,
        actual_indicators: newEventActualIndicators.value.trim() || null,
        media_link_1: newEventMediaLink1.value.trim() || null,
        media_link_2: newEventMediaLink2.value.trim() || null,
        media_link_3: newEventMediaLink3.value.trim() || null,
      }),
    })
    showAddEventDialog.value = false
    newEventName.value = ''
    newEventRegion.value = ''
    newEventDateFrom.value = ''
    newEventDateTo.value = ''
    newEventOrderDecree.value = ''
    newEventPlannedIndicators.value = ''
    newEventActualIndicators.value = ''
    newEventMediaLink1.value = ''
    newEventMediaLink2.value = ''
    newEventMediaLink3.value = ''
    await loadEvents(props.subsidyId)
    showSnack('Мероприятие добавлено')
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  }
}

function openEditEventDialog(ev: EventItem) {
  editEventForm.value = {
    id: ev.id,
    subsidy_id: ev.subsidy_id,
    name: ev.name,
    is_active: ev.is_active,
    region: ev.region || '',
    date_from: ev.date_from || '',
    date_to: ev.date_to || '',
    order_decree: ev.order_decree || '',
    planned_indicators: ev.planned_indicators || '',
    actual_indicators: ev.actual_indicators || '',
    media_link_1: ev.media_link_1 || '',
    media_link_2: ev.media_link_2 || '',
    media_link_3: ev.media_link_3 || '',
  }
  showEditEventDialog.value = true
}

async function saveEditEvent() {
  if (!editEventForm.value.name.trim() || !props.subsidyId) return
  savingEvent.value = true
  try {
    const f = editEventForm.value
    await apiFetch(`/events/${f.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        subsidy_id: f.subsidy_id,
        name: f.name.trim(),
        is_active: f.is_active,
        region: f.region || null,
        date_from: f.date_from || null,
        date_to: f.date_to || null,
        order_decree: f.order_decree || null,
        planned_indicators: f.planned_indicators || null,
        actual_indicators: f.actual_indicators || null,
        media_link_1: f.media_link_1 || null,
        media_link_2: f.media_link_2 || null,
        media_link_3: f.media_link_3 || null,
      }),
    })
    showEditEventDialog.value = false
    await loadEvents(props.subsidyId)
    showSnack('Мероприятие обновлено')
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  } finally {
    savingEvent.value = false
  }
}

async function downloadReport(subsidyId: number) {
  try {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token') || ''
    const resp = await fetch(`/api/reports/subsidy/${subsidyId}/xlsx`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!resp.ok) throw new Error(`Ошибка ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Приложение_3_субсидия_${subsidyId}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка скачивания', 'error')
  }
}

async function deleteEvent(eventId: number) {
  if (!props.subsidyId) return
  try {
    await apiFetch(`/events/${eventId}`, { method: 'DELETE' })
    await loadEvents(props.subsidyId)
    showSnack('Мероприятие удалено')
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  }
}

// Родитель вызывает reload() через template ref вместо прямого владения
// subsidyEvents — так watcher'ы globalSubsidyId/toggleSelect (не в этой волне
// рефакторинга) остаются текстуально нетронутыми: они по-прежнему вызывают
// loadEvents(id), которая теперь просто проксирует сюда.
defineExpose({ reload: loadEvents })
</script>
