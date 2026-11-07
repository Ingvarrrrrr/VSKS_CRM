<template>
  <div class="commission-tab">
    <v-row dense>
      <v-col cols="12" md="6">
        <v-card variant="outlined" class="pa-3 mb-3">
          <div class="text-subtitle-2 font-weight-bold mb-2">Реквизиты заседания</div>
          <v-text-field
            v-model="results.protocol_number"
            label="Номер протокола"
            placeholder="Напр. №B3004261856309-1"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-text-field
            v-model="results.protocol_date"
            label="Дата проведения заседания"
            type="date"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-text-field
            v-model="results.meeting_time"
            label="Время проведения заседания"
            placeholder="16:30"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-text-field
            v-model="results.meeting_address"
            label="Место проведения заседания"
            placeholder="119454, город Москва, пр-кт Вернадского..."
            variant="outlined"
            density="compact"
          />
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card variant="outlined" class="pa-3 mb-3">
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-subtitle-2 font-weight-bold">Приказ об утверждении комиссии</span>
            <v-btn
              size="x-small"
              variant="text"
              color="deep-purple"
              prepend-icon="mdi-content-copy"
              @click="copyFromSubsidy"
            >
              Скопировать из субсидии
            </v-btn>
          </div>
          <v-text-field
            v-model="results.commission_order_number"
            label="Номер приказа о комиссии"
            placeholder="Напр. 86"
            variant="outlined"
            density="compact"
            class="mb-2"
          />
          <v-text-field
            v-model="results.commission_order_date"
            label="Дата приказа о комиссии"
            type="date"
            variant="outlined"
            density="compact"
          />
        </v-card>
      </v-col>
    </v-row>

    <!-- Состав комиссии -->
    <v-card variant="outlined" class="pa-3">
      <div class="d-flex align-center justify-space-between flex-wrap gap-2 mb-3">
        <div>
          <span class="text-subtitle-2 font-weight-bold">
            Состав комиссии для протокола (Таблица 1.4 и подписи)
          </span>
          <div class="text-caption text-medium-emphasis">
            По умолчанию заполняются стандартные члены комиссии из субсидии. Для данной закупки можно скорректировать состав, должности или присутствие.
          </div>
        </div>
        <div class="d-flex align-center gap-2">
          <v-btn
            size="small"
            variant="tonal"
            color="deep-purple"
            prepend-icon="mdi-content-copy"
            @click="copyFromSubsidy"
          >
            Подгрузить из субсидии
          </v-btn>
          <v-btn
            size="small"
            variant="flat"
            color="primary"
            prepend-icon="mdi-plus"
            @click="addMember"
          >
            + Добавить человека в закупку
          </v-btn>
        </div>
      </div>

      <div v-if="!results.commission_members || !results.commission_members.length" class="text-caption text-medium-emphasis py-4 text-center">
        Члены комиссии ещё не добавлены. Нажмите «Подгрузить из субсидии» или «+ Добавить человека в закупку».
      </div>

      <div
        v-for="(m, mIdx) in results.commission_members"
        :key="mIdx"
        class="d-flex align-center gap-2 mb-2 pa-2 rounded"
        :style="{ background: m.present === false ? 'rgba(var(--v-theme-error), 0.06)' : 'rgba(var(--v-theme-surface-variant), 0.3)' }"
      >
        <v-checkbox-btn
          v-model="m.present"
          color="primary"
          density="compact"
          hide-details
          title="Присутствует на заседании комиссии"
        />

        <v-chip
          size="x-small"
          :color="m.from_subsidy ? 'deep-purple' : 'teal'"
          variant="flat"
          class="font-weight-medium"
          style="min-width: 90px; justify-content: center"
        >
          {{ m.from_subsidy ? 'Из субсидии' : 'В закупку' }}
        </v-chip>

        <v-combobox
          :model-value="m.full_name"
          :items="staffNames"
          placeholder="ФИО сотрудника"
          density="compact"
          variant="outlined"
          hide-details
          style="flex: 2; min-width: 180px"
          @update:model-value="val => onMemberNameChange(m, val)"
        />

        <v-text-field
          v-model="m.position"
          placeholder="Должность"
          density="compact"
          variant="outlined"
          hide-details
          style="flex: 1.8; min-width: 150px"
        />

        <v-combobox
          v-model="m.role"
          :items="COMMISSION_ROLES"
          density="compact"
          variant="outlined"
          hide-details
          style="flex: 1.5; min-width: 160px"
        />

        <v-btn
          icon="mdi-delete-outline"
          size="small"
          variant="text"
          color="error"
          title="Удалить из комиссии"
          @click="removeMember(mIdx)"
        />
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  results: Record<string, any>
  purchaseId: number
}>()

const toast = useToast()

const COMMISSION_ROLES = [
  'Председатель Комиссии',
  'Заместитель председателя Комиссии',
  'Член Комиссии',
  'Секретарь Комиссии',
]

const staffDirectory = ref<Array<{ id: number; full_name: string; position?: string }>>([])
const staffNames = computed(() => staffDirectory.value.map(s => s.full_name).filter(Boolean))

async function loadStaffDirectory() {
  if (staffDirectory.value.length) return
  try {
    const list = await apiFetch<any[]>('/staff-directory/')
    if (Array.isArray(list)) {
      staffDirectory.value = list.map(u => ({
        id: u.id,
        full_name: u.full_name || '',
        position: u.position || '',
      }))
    }
  } catch {}
}

async function autoInitFromSubsidy() {
  if (Array.isArray(props.results.commission_members) && props.results.commission_members.length > 0) return
  try {
    const pur = await apiFetch<any>(`/purchases/${props.purchaseId}`)
    if (pur?.subsidy_id) {
      const sub = await apiFetch<any>(`/subsidies/${pur.subsidy_id}`)
      if (sub) {
        if (!props.results.commission_order_number && sub.commission_order_number) {
          props.results.commission_order_number = sub.commission_order_number
        }
        if (!props.results.commission_order_date && sub.commission_order_date) {
          props.results.commission_order_date = sub.commission_order_date
        }
        if (Array.isArray(sub.commission_members) && sub.commission_members.length) {
          props.results.commission_members = sub.commission_members.map((m: any) => ({
            user_id: m.user_id || null,
            full_name: m.full_name || m.name || '',
            position: m.position || '',
            role: m.role || 'Член Комиссии',
            present: true,
            from_subsidy: true,
          }))
        }
      }
    }
  } catch {}
}

onMounted(async () => {
  await loadStaffDirectory()
  await autoInitFromSubsidy()
})

function onMemberNameChange(m: any, val: any) {
  if (typeof val === 'string') {
    m.full_name = val
    const found = staffDirectory.value.find(s => s.full_name.toLowerCase() === val.trim().toLowerCase())
    if (found) {
      if (!m.position) m.position = found.position || ''
      m.user_id = found.id
    }
  } else if (val && typeof val === 'object') {
    m.full_name = val.full_name || ''
    if (val.position && !m.position) m.position = val.position
    if (val.id) m.user_id = val.id
  }
}

function addMember() {
  if (!Array.isArray(props.results.commission_members)) {
    props.results.commission_members = []
  }
  const len = props.results.commission_members.length
  props.results.commission_members.push({
    user_id: null,
    full_name: '',
    position: '',
    role: len === 0 ? 'Председатель Комиссии' : 'Член Комиссии',
    present: true,
    from_subsidy: false,
  })
}

function removeMember(idx: number) {
  if (Array.isArray(props.results.commission_members)) {
    props.results.commission_members.splice(idx, 1)
  }
}

async function copyFromSubsidy() {
  try {
    const pur = await apiFetch<any>(`/purchases/${props.purchaseId}`)
    if (pur?.subsidy_id) {
      const sub = await apiFetch<any>(`/subsidies/${pur.subsidy_id}`)
      if (sub) {
        if (sub.commission_order_number) props.results.commission_order_number = sub.commission_order_number
        if (sub.commission_order_date) props.results.commission_order_date = sub.commission_order_date
        if (Array.isArray(sub.commission_members) && sub.commission_members.length) {
          if (!Array.isArray(props.results.commission_members)) {
            props.results.commission_members = []
          }
          const existingNames = new Set(
            props.results.commission_members.map((m: any) => (m.full_name || '').toLowerCase().trim())
          )
          let addedCount = 0
          for (const sm of sub.commission_members) {
            const name = (sm.full_name || sm.name || '').trim()
            if (name && !existingNames.has(name.toLowerCase())) {
              props.results.commission_members.push({
                user_id: sm.user_id || null,
                full_name: name,
                position: sm.position || '',
                role: sm.role || 'Член Комиссии',
                present: true,
                from_subsidy: true,
              })
              existingNames.add(name.toLowerCase())
              addedCount++
            }
          }
          if (addedCount > 0) {
            toast.addToast(`Добавлено ${addedCount} членов комиссии из субсидии`, 'success')
          } else {
            toast.addToast('Все члены комиссии из субсидии уже присутствуют в списке', 'info')
          }
        }
      }
    }
  } catch (e: any) {
    toast.addToast(e?.detail || 'Не удалось загрузить данные субсидии', 'error')
  }
}
</script>

<style scoped>
.commission-tab {
  display: flex;
  flex-direction: column;
}
</style>
