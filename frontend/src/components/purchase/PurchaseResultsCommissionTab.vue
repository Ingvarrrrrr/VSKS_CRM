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
      <div class="d-flex align-center justify-space-between mb-2">
        <span class="text-subtitle-2 font-weight-bold">
          Состав комиссии для протокола (Таблица 1.4 и подписи)
        </span>
        <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-plus" @click="addMember">
          Добавить члена комиссии
        </v-btn>
      </div>

      <div
        v-for="(m, mIdx) in results.commission_members"
        :key="mIdx"
        class="d-flex align-center gap-2 mb-2"
      >
        <v-text-field
          v-model="m.full_name"
          placeholder="ФИО полностью (напр. Цыганов Игорь Александрович)"
          density="compact"
          variant="outlined"
          hide-details
          style="flex: 2"
        />
        <v-combobox
          v-model="m.role"
          :items="COMMISSION_ROLES"
          density="compact"
          variant="outlined"
          hide-details
          style="flex: 1.5"
        />
        <v-btn
          icon="mdi-delete-outline"
          size="small"
          variant="text"
          color="error"
          @click="removeMember(mIdx)"
        />
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
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

function addMember() {
  if (!Array.isArray(props.results.commission_members)) {
    props.results.commission_members = []
  }
  const len = props.results.commission_members.length
  props.results.commission_members.push({
    full_name: '',
    role: len === 0 ? 'Председатель Комиссии' : 'Член Комиссии',
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
          props.results.commission_members = JSON.parse(JSON.stringify(sub.commission_members))
        }
        toast.addToast('Реквизиты комиссии скопированы из субсидии', 'success')
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
