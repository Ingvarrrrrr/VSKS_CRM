<template>
  <!-- 6. Платёж (admin+) -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold px-4 pt-4">
      Платёж
    </v-card-title>
    <v-card-text>
      <!-- Загрузка платёжных документов -->
      <div v-if="isEdit && purchaseId" class="mb-4">
        <div class="d-flex align-center gap-2 py-2 border-b">
          <v-icon size="18" color="orange">mdi-cash-check</v-icon>
          <span class="text-body-2 font-weight-medium" style="min-width:120px">Платёжка</span>
          <v-btn size="x-small" variant="tonal" color="orange" prepend-icon="mdi-upload"
            :loading="uploading && pendingSectionUpload === 'invoice'" @click="uploadForSection('invoice')">
            Загрузить
          </v-btn>
          <v-spacer />
          <div class="d-flex flex-wrap gap-1">
            <template v-for="f in paymentFiles" :key="f.id">
              <v-chip size="small" :color="f.is_active ? 'orange' : 'grey'" :variant="f.is_active ? 'tonal' : 'outlined'"
                closable @click:close="deleteFile(f.id)" @click="downloadFile(f.id, f.filename)">
                <v-icon start size="14">mdi-file</v-icon>
                {{ f.filename.length > 25 ? f.filename.slice(0, 22) + '...' : f.filename }}
                <template #append>
                  <v-tooltip :text="f.is_active ? 'Актуальный' : 'Не актуальный'" location="top">
                    <template #activator="{ props: tp }">
                      <v-icon v-bind="tp" size="14" class="ml-1" :color="f.is_active ? 'success' : 'grey'"
                        @click.stop="toggleFileActive(f)">{{ f.is_active ? 'mdi-check-circle' : 'mdi-close-circle-outline' }}</v-icon>
                    </template>
                  </v-tooltip>
                </template>
              </v-chip>
            </template>
          </div>
        </div>
      </div>
      <v-row>
        <v-col cols="12" md="4" data-field-name="payment_doc_number">
          <v-text-field v-model="form.payment_doc_number" label="Номер платёжного поручения" variant="outlined" density="compact"
            readonly hint="Заполняется автоматически из платежей. См. раздел Платежи ниже" persistent-hint />
        </v-col>
        <v-col cols="12" md="4" data-field-name="payment_doc_date">
          <v-text-field v-model="form.payment_doc_date" label="Дата ПП" variant="outlined" density="compact" type="date"
            readonly hint="Заполняется автоматически из платежей" persistent-hint />
        </v-col>
        <v-col cols="12" md="4" data-field-name="payment_amount">
          <v-text-field v-model.number="form.payment_amount" label="Сумма платежа" variant="outlined"
            density="compact" type="number" suffix="₽" readonly hint="Заполняется автоматически из платежей" persistent-hint />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field v-model.number="form.payment_federal" label="в т.ч. федеральный бюджет" variant="outlined"
            density="compact" type="number" suffix="₽" />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field v-model="form.treasury_code" label="Казначейский код" variant="outlined" density="compact"
            hint="Код для Приложения №3, колонка S" persistent-hint />
        </v-col>
        <v-col cols="12" md="4">
          <v-checkbox v-model="form.has_pretension" label="Претензионная работа" density="compact"
            hint="Колонка U в Приложении №3" persistent-hint />
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Блок «Платёж». Вынесено из CreateOrderView.vue (рефакторинг без изменения
// поведения, часть 3). form — reactive-объект родителя (мутируется напрямую
// v-model). paymentFiles/uploading/pendingSectionUpload и функции загрузки —
// из composables/purchase/usePurchaseFiles.ts, вызываемого в родителе (там же
// используется секцией «Документы к закупке») — приходят пропами.
defineProps<{
  form: any
  isEdit: boolean
  purchaseId: number | null
  uploading: boolean
  pendingSectionUpload: string | null
  paymentFiles: any[]
  uploadForSection: (sectionType: string) => void
  deleteFile: (id: number) => void
  downloadFile: (id: number, filename: string) => void
  toggleFileActive: (f: any) => void
}>()
</script>
