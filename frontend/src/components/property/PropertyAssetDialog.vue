<template>
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="700" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span class="text-h6">{{ isEdit ? 'Редактировать имущество' : (category === 'equipment' ? 'Новое оборудование' : 'Новое имущество') }}</span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-form ref="formRef" v-model="formValid">
          <v-row dense>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.brand"
                label="Наименование / Марка *"
                :rules="[v => !!v || 'Обязательно к заполнению']"
                variant="outlined"
                density="compact"
                placeholder="Например: Ноутбук Lenovo ThinkPad"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.model"
                label="Модель / Характеристики"
                variant="outlined"
                density="compact"
                placeholder="T14 Gen 2"
              />
            </v-col>

            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.vin"
                label="Серийный номер"
                variant="outlined"
                density="compact"
                placeholder="S/N: PF-2ABC123"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.plate"
                label="Инвентарный номер"
                variant="outlined"
                density="compact"
                placeholder="ИНВ-000452"
              />
            </v-col>

            <v-col cols="12" sm="6">
              <v-select
                v-model="form.owner_org_id"
                :items="orgsList"
                item-title="name"
                item-value="id"
                label="Организация-собственник *"
                :rules="[v => !!v || 'Обязательно']"
                variant="outlined"
                density="compact"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-select
                v-model="form.assigned_org_id"
                :items="orgsList"
                item-title="name"
                item-value="id"
                label="В эксплуатации (орг.)"
                clearable
                variant="outlined"
                density="compact"
              />
            </v-col>

            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.responsible_name"
                label="Ответственное лицо (ФИО)"
                variant="outlined"
                density="compact"
                placeholder="Иванов И.И."
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.assigned_text"
                label="Подразделение / Отдел"
                variant="outlined"
                density="compact"
                placeholder="Склад / ИТ-отдел"
              />
            </v-col>

            <v-col cols="12" sm="6">
              <v-text-field
                v-model="form.location_city"
                label="Город / Местоположение"
                variant="outlined"
                density="compact"
                placeholder="г. Москва"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-select
                v-model="form.state"
                :items="stateOptions"
                item-title="label"
                item-value="value"
                label="Состояние"
                variant="outlined"
                density="compact"
              />
            </v-col>

            <v-col cols="12">
              <v-text-field
                v-model="form.location_address"
                label="Точный адрес / Кабинет"
                variant="outlined"
                density="compact"
                placeholder="ул. Ленина, д. 10, каб. 302"
              />
            </v-col>

            <v-col cols="12">
              <v-textarea
                v-model="formNote"
                label="Примечание"
                variant="outlined"
                density="compact"
                rows="2"
                placeholder="Дополнительные сведения, комплектация..."
              />
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="close">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!formValid" @click="save">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { apiFetch } from '@/api'
import type { OrgItem } from '@/composables/fleet/vehicle-list/vehicleListTypes'

const props = defineProps<{
  modelValue: boolean
  category: 'equipment' | 'other'
  initialData?: any | null
  orgsList: OrgItem[]
  stateOptions: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'saved': [item: any]
  'error': [err: any]
}>()

const formRef = ref<any>(null)
const formValid = ref(false)
const saving = ref(false)

const isEdit = computed(() => !!props.initialData?.id)

const form = ref<any>({
  brand: '',
  model: '',
  vin: '',
  plate: '',
  owner_org_id: null,
  assigned_org_id: null,
  responsible_name: '',
  assigned_text: '',
  location_city: '',
  location_address: '',
  state: 'working',
  type: props.category,
  props: {},
})

const formNote = ref('')

watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    if (props.initialData) {
      form.value = {
        ...props.initialData,
        type: props.initialData.type || props.category,
      }
      formNote.value = props.initialData.props?.note || ''
    } else {
      form.value = {
        brand: '',
        model: '',
        vin: '',
        plate: '',
        owner_org_id: props.orgsList.length > 0 ? props.orgsList[0].id : null,
        assigned_org_id: null,
        responsible_name: '',
        assigned_text: '',
        location_city: '',
        location_address: '',
        state: 'working',
        type: props.category,
        props: {},
      }
      formNote.value = ''
    }
  }
})

function close() {
  emit('update:modelValue', false)
}

async function save() {
  if (!formRef.value) return
  const valid = await formRef.value.validate()
  if (!valid.valid) return

  saving.value = true
  try {
    const payload = {
      ...form.value,
      type: props.category,
      props: {
        ...(form.value.props || {}),
        note: formNote.value || undefined,
      },
    }
    let res: any
    if (isEdit.value) {
      res = await apiFetch(`/vehicles/${props.initialData.id}`, {
        method: 'PATCH',
        body: payload,
      })
    } else {
      res = await apiFetch('/vehicles', {
        method: 'POST',
        body: payload,
      })
    }
    emit('saved', res)
    close()
  } catch (err: any) {
    emit('error', err)
  } finally {
    saving.value = false
  }
}
</script>
