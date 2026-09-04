<template>
  <v-dialog v-model="internalOpen" max-width="680" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
        <v-icon icon="mdi-tune-variant" color="primary" />
        Состав полей карточки ТС
      </v-card-title>

      <v-card-text class="px-5" style="max-height: 65vh">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Скрытые поля не удаляются — данные сохраняются в базе и вернутся, если поле снова включить.
        </v-alert>

        <div v-if="loading" class="text-center py-10">
          <v-progress-circular indeterminate size="40" color="primary" />
        </div>

        <template v-else-if="groups.length === 0">
          <div class="text-medium-emphasis text-body-2 py-4">
            Не удалось загрузить реестр полей. Попробуйте открыть диалог ещё раз.
          </div>
        </template>

        <template v-else>
          <div v-for="group in groups" :key="group.key" class="mb-5">
            <div class="text-subtitle-2 font-weight-bold mb-1">{{ group.title }}</div>
            <v-divider class="mb-2" />
            <v-row dense>
              <v-col v-for="f in group.fields" :key="f.key" cols="12" sm="6">
                <div class="d-flex align-center justify-space-between vfd-row">
                  <span class="text-body-2" :class="{ 'text-medium-emphasis': localHidden.has(f.key) }">
                    {{ f.label }}
                    <v-tooltip v-if="!f.lockable" location="top" text="Обязательное поле — без него карточка ТС не работает">
                      <template #activator="{ props: tprops }">
                        <v-icon v-bind="tprops" icon="mdi-lock-outline" size="14" class="ml-1 text-medium-emphasis" />
                      </template>
                    </v-tooltip>
                  </span>
                  <v-switch
                    :model-value="!localHidden.has(f.key)"
                    :disabled="!f.lockable || saving"
                    color="primary"
                    hide-details
                    density="compact"
                    @update:model-value="(v: boolean) => onToggle(f, v)"
                  />
                </div>
              </v-col>
            </v-row>
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-btn variant="text" :disabled="loading || saving" @click="showAll">Показать все</v-btn>
        <v-spacer />
        <v-btn variant="text" :disabled="saving" @click="internalOpen = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" prepend-icon="mdi-content-save" :loading="saving" :disabled="loading" @click="onSave">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useVehicleFields, type VehicleFieldDescriptor } from '@/composables/useVehicleFields'
import { useToast } from '@/composables/useToast'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const internalOpen = ref(props.modelValue)
watch(() => props.modelValue, v => { internalOpen.value = v })
watch(internalOpen, v => emit('update:modelValue', v))

const { groups, loading, hiddenKeys, loadFields, saveFields } = useVehicleFields()
const toast = useToast()

const localHidden = ref<Set<string>>(new Set())
const saving = ref(false)

watch(internalOpen, async (open) => {
  if (!open) return
  await loadFields()
  localHidden.value = new Set(hiddenKeys.value)
})

function onToggle(f: VehicleFieldDescriptor, visible: boolean) {
  if (!f.lockable) return
  const next = new Set(localHidden.value)
  if (visible) next.delete(f.key)
  else next.add(f.key)
  localHidden.value = next
}

function showAll() {
  localHidden.value = new Set()
}

async function onSave() {
  saving.value = true
  try {
    const items = Array.from(localHidden.value).map(field_key => ({ field_key, is_hidden: true }))
    await saveFields(items)
    toast.success('Состав полей карточки ТС сохранён')
    internalOpen.value = false
  } catch {
    // saveFields уже показал error-тост с распакованным сообщением сервера
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.vfd-row {
  min-height: 40px;
}
</style>
