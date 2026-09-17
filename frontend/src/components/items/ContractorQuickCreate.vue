<template>
  <!-- Presentational quick contractor-create dialog. Parent owns the reactive
       `form` object, the saving flag and the actual POST handler; this child
       renders the fields (mutating the passed-in reactive form in place) and
       emits save/cancel. Extracted from PurchaseItemsEditor.vue (Layer 2). -->
  <v-dialog :model-value="modelValue" max-width="480" persistent
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-4 d-flex align-center justify-space-between">
        <span><v-icon icon="mdi-store-plus" class="mr-2" />Новый контрагент</span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <v-alert type="info" density="compact" variant="tonal" class="mb-3 text-caption">
          Контрагент не найден в БД. Заполните минимальные данные для создания.
        </v-alert>
        <v-text-field
          v-model="form.name"
          label="Наименование *"
          variant="outlined" density="compact"
          :rules="[(v: string) => !!v || 'Обязательное поле']"
          class="mb-2"
        />
        <div class="d-flex align-start ga-2 mb-2">
          <v-text-field
            v-model="form.inn"
            label="ИНН"
            variant="outlined" density="compact" hide-details
            class="flex-grow-1"
          />
          <v-btn
            variant="tonal" color="primary" size="small"
            prepend-icon="mdi-database-search-outline"
            :loading="lookupLoading"
            :disabled="!innDigitsValid"
            style="margin-top:2px"
            @click="lookupInn"
          >
            Из налоговой
          </v-btn>
        </div>
        <v-alert v-if="lookupMessage" :type="lookupMessageType" variant="tonal" density="compact" class="mb-2 text-caption" closable @click:close="lookupMessage = ''">
          {{ lookupMessage }}
        </v-alert>
        <v-text-field
          v-model="form.kpp"
          label="КПП"
          variant="outlined" density="compact" class="mb-2"
        />
        <v-text-field
          v-model="form.address"
          label="Адрес"
          variant="outlined" density="compact"
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn color="primary" :loading="saving"
          :disabled="!form.name.trim()"
          @click="emit('save')">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Заполнение из налоговой (ЕГРЮЛ/ЕГРИП/НПД) по ИНН — переиспользует общий
// backend-механизм GET /contractors/lookup-inn/{inn}?force_egrul=1 (тот же,
// что в AddContractorDialog.vue/useContractorLookup.ts и ContractorEditDialog.vue).
// Второй механизм не заводим — только UI-обвязка вокруг существующего эндпоинта.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

interface ContractorForm {
  name: string
  inn: string
  kpp: string
  address: string
}

const props = defineProps<{
  modelValue: boolean
  /** Reactive form owned by the parent; mutated in place via v-model. */
  form: ContractorForm
  saving?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  save: []
}>()

const lookupLoading = ref(false)
const lookupMessage = ref('')
const lookupMessageType = ref<'success' | 'info' | 'error' | 'warning'>('info')

const innDigitsValid = computed(() => {
  const digits = (props.form.inn || '').replace(/\D/g, '')
  return digits.length === 10 || digits.length === 12
})

async function lookupInn() {
  const inn = (props.form.inn || '').replace(/\D/g, '')
  if (inn.length !== 10 && inn.length !== 12) return
  lookupLoading.value = true
  lookupMessage.value = ''
  try {
    const data = await apiFetch<Record<string, any>>(`/contractors/lookup-inn/${inn}?force_egrul=1`)
    // Самозанятые и физлица: в ЕГРЮЛ/ЕГРИП их нет, реестр НПД отдаёт только факт статуса.
    if (data?._source === 'npd') {
      lookupMessage.value = data._notice || `ИНН ${inn} — самозанятый. Сведения через налоговую получить нельзя, заполните данные вручную.`
      lookupMessageType.value = 'warning'
      return
    }
    const filled: string[] = []
    if (!props.form.name.trim() && data.name) { props.form.name = data.name; filled.push('название') }
    if (!props.form.kpp.trim() && data.kpp) { props.form.kpp = data.kpp; filled.push('КПП') }
    if (!props.form.address.trim() && data.address) { props.form.address = data.address; filled.push('адрес') }
    lookupMessage.value = filled.length
      ? `Заполнено из налоговой: ${filled.join(', ')}`
      : 'Данные из налоговой совпадают с уже введёнными — изменений нет'
    lookupMessageType.value = filled.length ? 'success' : 'info'
  } catch (e: any) {
    if (e?.payload?.code === 'INN_NOT_FOUND') {
      lookupMessage.value = e.payload.message
      lookupMessageType.value = 'warning'
    } else {
      lookupMessage.value = e?.message || 'Ошибка запроса к налоговой'
      lookupMessageType.value = 'error'
    }
  } finally {
    lookupLoading.value = false
  }
}
</script>
