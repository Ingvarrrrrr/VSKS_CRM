<template>
  <div>
    <div class="d-flex align-center mb-4">
      <h3 class="text-h6">Чек-листы</h3>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewDialog">Новый чек-лист</v-btn>
    </div>

    <v-progress-circular v-if="loading" indeterminate />
    <v-alert v-else-if="checklists.length === 0" type="info" variant="tonal">
      Чек-листов пока нет. Создайте первый через «Новый чек-лист».
    </v-alert>
    <v-card v-for="cl in checklists" :key="cl.id" class="mb-3" variant="outlined">
      <v-card-text>
        <div class="d-flex align-center mb-2">
          <v-chip :color="typeColor(cl.type)" size="small" class="mr-2">{{ typeLabel(cl.type) }}</v-chip>
          <v-chip v-if="cl.overall_state" :color="stateColor(cl.overall_state)" size="small">
            {{ stateLabel(cl.overall_state) }}
          </v-chip>
          <v-spacer />
          <span class="text-caption text-medium-emphasis">{{ formatDate(cl.created_at) }}</span>
        </div>
        <div v-if="cl.fuel_level" class="mb-2">
          <strong>Топливо:</strong> {{ fuelLabel(cl.fuel_level) }}
        </div>
        <div v-if="cl.paint_condition" class="mb-2">
          <strong>ЛКП:</strong> {{ cl.paint_condition }}
        </div>
        <div v-if="cl.items?.length" class="d-flex flex-wrap gap-2 mb-2">
          <v-chip v-for="item in cl.items" :key="item.id"
                  size="small" :color="itemStatusColor(item.status)" variant="tonal">
            {{ itemKeyLabel(item.key) }}: {{ itemStatusLabel(item.status) }}
          </v-chip>
        </div>
        <div v-if="cl.notes" class="text-body-2 text-medium-emphasis">{{ cl.notes }}</div>
      </v-card-text>
    </v-card>

    <!-- New checklist dialog -->
    <v-dialog v-model="newDialog" max-width="700" :fullscreen="mobile">
      <v-card>
        <v-card-title>Новый чек-лист</v-card-title>
        <v-card-text>
          <v-select v-model="form.type" :items="typeOptions" item-title="label" item-value="value" label="Тип" />
          <v-select v-model="form.overall_state" :items="stateOptions" item-title="label" item-value="value" label="Общее состояние" />
          <v-select v-model="form.fuel_level" :items="fuelOptions" item-title="label" item-value="value" label="Уровень топлива" />
          <v-text-field v-model="form.paint_condition" label="Состояние ЛКП" />

          <!-- 4×2 grid пунктов -->
          <div class="text-subtitle-2 mt-3 mb-2">Пункты:</div>
          <v-row dense>
            <v-col v-for="key in CHECKLIST_KEYS" :key="key" cols="6" sm="3">
              <v-select v-model="form.items[key]"
                        :items="[{value:'ok',label:'OK'},{value:'issue',label:'Проблема'},{value:'missing',label:'Нет'}]"
                        item-title="label" item-value="value"
                        :label="itemKeyLabel(key)" density="compact" />
            </v-col>
          </v-row>

          <v-textarea v-model="form.notes" label="Замечания" rows="2" class="mt-3" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="newDialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveChecklist">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

const { mobile } = useDisplay()

const props = defineProps<{ vehicleId: number }>()

interface ChecklistItem { id: number; key: string; status: string; note?: string }
interface Checklist {
  id: number; vehicle_id: number; type: string; overall_state?: string;
  fuel_level?: string; paint_condition?: string; notes?: string;
  created_at: string; items?: ChecklistItem[]
}

const checklists = ref<Checklist[]>([])
const loading = ref(false)
const saving = ref(false)
const newDialog = ref(false)
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') { toast.addToast(text, color) }

const CHECKLIST_KEYS = ['akb', 'tires', 'mirrors', 'radio', 'firstaid', 'extinguisher', 'spare', 'lkp']
const KEY_LABELS: Record<string, string> = {
  akb: 'АКБ', tires: 'Резина', mirrors: 'Зеркала', radio: 'Радио',
  firstaid: 'Аптечка', extinguisher: 'Огнет.', spare: 'Запаска', lkp: 'ЛКП',
}

const form = ref({
  type: 'pre_trip',
  overall_state: 'ok',
  fuel_level: 'half',
  paint_condition: '',
  notes: '',
  items: Object.fromEntries(CHECKLIST_KEYS.map(k => [k, 'ok'])) as Record<string, string>,
})

const typeOptions = [
  { value: 'pre_trip', label: 'Предрейсовый' },
  { value: 'post_trip', label: 'Послерейсовый' },
  { value: 'weekly', label: 'Еженедельный' },
  { value: 'monthly', label: 'Ежемесячный' },
]
const stateOptions = [
  { value: 'ok', label: 'Рабочее' },
  { value: 'with_remarks', label: 'С замечаниями' },
  { value: 'not_running', label: 'Не на ходу' },
]
const fuelOptions = [
  { value: 'quarter', label: '1/4 бака' },
  { value: 'half', label: '1/2 бака' },
  { value: 'threequarter', label: '3/4 бака' },
  { value: 'full', label: 'Полный' },
]

function typeLabel(t: string) { return typeOptions.find(o => o.value === t)?.label || t }
function typeColor(t: string) { return t.includes('pre') || t.includes('post') ? 'primary' : 'info' }
function stateLabel(s: string) { return stateOptions.find(o => o.value === s)?.label || s }
function stateColor(s: string) { return s === 'ok' ? 'success' : s === 'with_remarks' ? 'warning' : 'error' }
function fuelLabel(f: string) { return fuelOptions.find(o => o.value === f)?.label || f }
const EXTRA_KEY_LABELS: Record<string, string> = {
  battery: 'АКБ', tires: 'Резина', mirrors: 'Зеркала', radio: 'Радиостанция',
  first_aid: 'Аптечка', fire_ext: 'Огнетушитель', spare_wheel: 'Запаска',
  tools: 'Ключи', branding: 'Брендирование',
  tires_season: 'Тип резины', radio_working: 'Радио (рабочая)',
}
function itemKeyLabel(k: string) { return EXTRA_KEY_LABELS[k] || KEY_LABELS[k] || k }
function itemStatusLabel(s: string) {
  return ({ ok: 'Хорошее', warn: 'Удовл.', fail: 'Отсутствует', issue: 'Проблема', missing: 'Нет',
            summer: 'Летняя', winter: 'Зимняя' }[s] || s)
}
function itemStatusColor(s: string) {
  return ({ ok: 'success', warn: 'warning', fail: 'error', issue: 'warning', missing: 'error',
            summer: 'orange', winter: 'blue' }[s] || 'grey')
}
function formatDate(iso: string) { return new Date(iso).toLocaleString('ru-RU') }

async function loadChecklists() {
  loading.value = true
  try {
    checklists.value = await apiFetch<Checklist[]>(`/checklists/?vehicle_id=${props.vehicleId}`)
  } catch (e: any) {
    console.error('[VehicleChecklistsTab]', e)
    showSnack('Ошибка загрузки чек-листов', 'error')
  } finally { loading.value = false }
}

function openNewDialog() {
  form.value = {
    type: 'pre_trip', overall_state: 'ok', fuel_level: 'half',
    paint_condition: '', notes: '',
    items: Object.fromEntries(CHECKLIST_KEYS.map(k => [k, 'ok'])) as Record<string, string>,
  }
  newDialog.value = true
}

async function saveChecklist() {
  saving.value = true
  try {
    const payload = {
      vehicle_id: props.vehicleId,
      type: form.value.type,
      overall_state: form.value.overall_state,
      fuel_level: form.value.fuel_level,
      paint_condition: form.value.paint_condition || null,
      notes: form.value.notes || null,
      items: CHECKLIST_KEYS.map(k => ({ key: k, status: form.value.items[k] })),
    }
    await apiFetch('/checklists/', { method: 'POST', body: JSON.stringify(payload) })
    newDialog.value = false
    showSnack('Чек-лист создан', 'success')
    await loadChecklists()
  } catch (e: any) {
    showSnack('Ошибка сохранения: ' + (e?.message || e), 'error')
  } finally { saving.value = false }
}

onMounted(loadChecklists)
</script>
