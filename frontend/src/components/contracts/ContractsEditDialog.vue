<template>
  <v-dialog v-model="dialog.show" max-width="680" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        {{ dialog.id ? 'Редактировать документ' : 'Новый документ' }}
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <v-row dense>
          <v-col cols="12" md="6">
            <v-text-field v-model="dialog.form.number" label="Номер *" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="dialog.form.date" label="Дата" type="date" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-select v-model="dialog.form.contract_type"
              :items="contractTypeItems" item-title="label" item-value="value"
              label="Тип документа *" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="4">
            <v-select v-model="dialog.form.purchase_method"
              :items="purchaseMethodItems" item-title="label" item-value="value"
              label="Способ закупки" variant="outlined" density="compact" clearable />
          </v-col>
          <v-col cols="12" md="4">
            <v-select v-model="dialog.form.item_type"
              :items="[
                { title: 'Товары', value: 'товар' },
                { title: 'Услуги', value: 'услуга' },
                { title: 'Товары и услуги', value: 'товар_и_услуга' },
              ]"
              label="Товары / Услуги" variant="outlined" density="compact" clearable />
          </v-col>
          <v-col cols="12" md="4">
            <ContractorPicker
              v-model="dialog.form.contractor_id"
              :initial-contractor="dialogInitialContractor"
              @select="onContractorPicked" />
          </v-col>
          <v-col cols="12" md="6">
            <v-select v-model="dialog.form.subsidy_id"
              :items="subsidies" item-title="name" item-value="id"
              label="Основная субсидия" variant="outlined" density="compact" clearable />
          </v-col>
          <v-col cols="12">
            <v-autocomplete v-model="dialog.form.extra_subsidy_ids"
              :items="subsidies.filter(s => s.id !== dialog.form.subsidy_id)"
              item-title="name" item-value="id"
              label="Дополнительные субсидии" variant="outlined" density="compact"
              multiple chips closable-chips clearable
              hint="Договор может быть привязан к нескольким субсидиям одной организации"
              persistent-hint />
          </v-col>
          <v-col cols="12">
            <v-text-field v-model="dialog.form.subject" label="Предмет" variant="outlined" density="compact" />
          </v-col>
          <v-col v-if="dialog.form.contract_type !== 'framework_cumulative'" cols="12" md="6">
            <v-text-field v-model.number="dialog.form.max_amount" label="Предельная сумма, ₽" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model.number="dialog.form.planned_monthly" label="Плановый ежемесячный платёж, ₽" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="dialog.form.start_date" label="Дата начала" type="date" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="dialog.form.end_date" label="Дата окончания" type="date" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-select v-model="dialog.form.status"
              :items="statusItems" item-title="label" item-value="value"
              label="Статус" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12">
            <v-textarea v-model="dialog.form.notes" label="Примечания" variant="outlined" density="compact" rows="2" />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-btn v-if="isAdmin && dialog.id" color="error" variant="text" prepend-icon="mdi-delete"
          @click="onDeleteFromDialog">Удалить</v-btn>
        <v-btn
          v-if="dialog.id && dialog.form.contract_type && dialog.form.contract_type.startsWith('framework_')"
          color="teal" variant="tonal" prepend-icon="mdi-plus"
          @click="onOpenMonthlyStages"
        >
          Создать ежемесячные этапы
        </v-btn>
        <v-btn
          v-if="dialog.id && (dialog.form.contract_type === 'framework_cumulative' || dialog.form.contract_type === 'framework_with_amount')"
          color="indigo" variant="tonal" prepend-icon="mdi-file-check-outline"
          :loading="approvalPurchaseLoading"
          @click="onOpenApprovalPurchase"
        >
          Согласование и документы
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="dialog.saving" @click="onSave">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import ContractorPicker from '@/components/ContractorPicker.vue'
import { contractTypeItems, purchaseMethodItems, statusItems } from '@/composables/contracts/contractsLabels'
import type { Subsidy } from '@/composables/contracts/contractsTypes'

defineProps<{
  dialog: {
    show: boolean
    saving: boolean
    id: number
    form: {
      number: string; date: string; contract_type: string; purchase_method: string | null; item_type: string | null
      contractor_id: number | null; contractor_name: string; contractor_inn: string
      subsidy_id: number | null; extra_subsidy_ids: number[]
      subject: string; max_amount: number | null; planned_monthly: number | null
      start_date: string; end_date: string; status: string; notes: string
    }
  }
  dialogInitialContractor: { id: number; name: string; inn?: string } | null
  onContractorPicked: (c: { id: number; name: string; inn?: string } | null) => void
  subsidies: Subsidy[]
  isAdmin: boolean
  mobile: boolean
  approvalPurchaseLoading: boolean
  onSave: () => void
  onDeleteFromDialog: () => void
  onOpenMonthlyStages: () => void
  onOpenApprovalPurchase: () => void
}>()
</script>
