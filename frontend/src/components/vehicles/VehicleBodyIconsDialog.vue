<template>
  <v-dialog v-model="internalOpen" max-width="900" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
        <v-icon icon="mdi-image-multiple-outline" color="primary" />
        Значки кузова ТС
      </v-card-title>

      <v-card-text class="px-5" style="max-height: 70vh">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Каждому значению поля «Кузов» назначен значок, который показывается в плашке карточки ТС.
          Замена значка применяется сразу и видна на всех карточках машин с этим кузовом.
        </v-alert>
        <v-alert v-if="loaded && !canManage" type="warning" variant="tonal" density="compact" class="mb-4">
          У вас нет прав менять значки кузова — раздел открыт только для просмотра.
        </v-alert>

        <div v-if="loading && !loaded" class="text-center py-10">
          <v-progress-circular indeterminate size="40" color="primary" />
        </div>

        <template v-else>
          <div v-for="group in groups" :key="group.key" class="mb-6">
            <div class="text-subtitle-2 font-weight-bold mb-2">{{ group.title }}</div>
            <v-divider class="mb-3" />
            <v-row dense>
              <v-col v-for="item in group.items" :key="item" cols="12" sm="6" md="4">
                <div class="vbi-row" :class="{ 'vbi-row--override': isOverridden(item) }">
                  <VehicleTypeIcon :body-type="item" :size="44" />
                  <div class="vbi-info">
                    <div class="text-body-2 font-weight-medium">{{ item }}</div>
                    <div class="text-caption" :class="isOverridden(item) ? 'text-primary font-weight-medium' : 'text-medium-emphasis'">
                      {{ isOverridden(item) ? 'Переопределено' : 'По умолчанию' }}
                    </div>
                  </div>
                  <div class="vbi-actions">
                    <v-btn size="small" variant="tonal" color="primary" :disabled="!canManage" @click="openPicker(item)">
                      Изменить
                    </v-btn>
                    <v-btn size="small" variant="text" :disabled="!canManage || !isOverridden(item)" @click="onReset(item)">
                      Сбросить
                    </v-btn>
                  </div>
                </div>
              </v-col>
            </v-row>
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-btn variant="text" color="error" :disabled="!canManage || loading" @click="confirmResetAll = true">
          Вернуть всё по умолчанию
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="internalOpen = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>

    <!-- Выбор значка для одного кузова -->
    <v-dialog v-model="pickerOpen" max-width="640" scrollable>
      <v-card v-if="pickerTarget">
        <v-card-title class="pa-5 pb-2">Значок для «{{ pickerTarget }}»</v-card-title>
        <v-card-text style="max-height: 60vh">
          <div class="text-caption text-medium-emphasis mb-2 text-uppercase">Силуэты</div>
          <div class="vbi-grid mb-4">
            <button
              v-for="opt in imgOptions" :key="'img-' + opt.value"
              type="button" class="vbi-swatch" :class="{ 'vbi-swatch--active': isCurrent(opt) }"
              :disabled="picking" @click="choose(opt)"
            >
              <img :src="`/vehicle-icons/${opt.value}.png`" :alt="opt.label" class="vbi-swatch-img" />
              <span>{{ opt.label }}</span>
            </button>
          </div>
          <div class="text-caption text-medium-emphasis mb-2 text-uppercase">Значки MDI</div>
          <div class="vbi-grid">
            <button
              v-for="opt in mdiOptions" :key="'mdi-' + opt.value"
              type="button" class="vbi-swatch" :class="{ 'vbi-swatch--active': isCurrent(opt) }"
              :disabled="picking" @click="choose(opt)"
            >
              <v-icon :icon="opt.value" size="32" />
              <span>{{ opt.label }}</span>
            </button>
          </div>
        </v-card-text>
        <v-card-actions class="px-5 pb-4">
          <v-spacer />
          <v-btn variant="text" :disabled="picking" @click="pickerOpen = false">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Подтверждение сброса всех -->
    <v-dialog v-model="confirmResetAll" max-width="440">
      <v-card>
        <v-card-title class="pa-5 pb-2 d-flex align-center gap-2">
          <v-icon icon="mdi-alert" color="warning" />
          Вернуть все значки к умолчанию?
        </v-card-title>
        <v-card-text class="px-5">
          Все переопределения значков кузова этой организации будут удалены. Действие можно отменить,
          заново назначив нужные значки вручную.
        </v-card-text>
        <v-card-actions class="px-5 pb-4">
          <v-btn color="warning" variant="flat" :loading="savingAll" @click="onResetAll">Вернуть всё</v-btn>
          <v-btn variant="text" :disabled="savingAll" @click="confirmResetAll = false">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useToast } from '@/composables/useToast'
import { useBodyTypeIconOverrides } from '@/composables/useBodyTypeIconOverrides'
import { BODY_TYPE_GROUPS } from './bodyTypeIcon'
import { IMG_ICON_OPTIONS, MDI_ICON_OPTIONS, type IconOption } from './bodyIconPickerOptions'
import VehicleTypeIcon from './VehicleTypeIcon.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const internalOpen = ref(props.modelValue)
watch(() => props.modelValue, v => { internalOpen.value = v })
watch(internalOpen, v => emit('update:modelValue', v))

const {
  overrides, canManage, loading, loaded,
  loadOverrides, isOverridden, saveOverride, resetOverride, resetAllOverrides,
} = useBodyTypeIconOverrides()
const toast = useToast()

const groups = BODY_TYPE_GROUPS
const imgOptions = IMG_ICON_OPTIONS
const mdiOptions = MDI_ICON_OPTIONS

watch(internalOpen, async (open) => {
  if (!open) return
  await loadOverrides()
})

const pickerOpen = ref(false)
const pickerTarget = ref<string | null>(null)
const picking = ref(false)

function openPicker(bodyType: string) {
  pickerTarget.value = bodyType
  pickerOpen.value = true
}

function isCurrent(opt: IconOption): boolean {
  const t = pickerTarget.value
  if (!t) return false
  const ov = overrides.value[t]
  if (!ov) return false
  return ov.icon_kind === opt.kind && ov.icon_value === opt.value
}

async function choose(opt: IconOption) {
  if (!pickerTarget.value) return
  picking.value = true
  try {
    await saveOverride(pickerTarget.value, { icon_kind: opt.kind, icon_value: opt.value })
    toast.success(`Значок «${pickerTarget.value}» изменён`)
    pickerOpen.value = false
  } catch {
    // saveOverride уже показал error-тост с распакованным сообщением сервера
  } finally {
    picking.value = false
  }
}

async function onReset(bodyType: string) {
  try {
    await resetOverride(bodyType)
    toast.success(`Значок «${bodyType}» возвращён к умолчанию`)
  } catch {
    // тост уже показан
  }
}

const confirmResetAll = ref(false)
const savingAll = ref(false)
async function onResetAll() {
  savingAll.value = true
  try {
    await resetAllOverrides()
    toast.success('Все значки кузова возвращены к умолчанию')
    confirmResetAll.value = false
  } catch {
    // тост уже показан
  } finally {
    savingAll.value = false
  }
}
</script>

<style scoped>
.vbi-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid rgba(128, 128, 128, 0.2);
  border-radius: 8px;
  min-height: 68px;
}
.vbi-row--override {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
}
.vbi-info {
  flex: 1 1 auto;
  min-width: 0;
}
.vbi-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.vbi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
}
.vbi-swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px;
  border: 1px solid rgba(128, 128, 128, 0.25);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  line-height: 1.2;
  text-align: center;
  color: inherit;
}
.vbi-swatch:hover:not(:disabled) {
  border-color: rgb(var(--v-theme-primary));
}
.vbi-swatch--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
}
.vbi-swatch:disabled {
  opacity: 0.6;
  cursor: default;
}
.vbi-swatch-img {
  width: 40px;
  height: 40px;
  object-fit: contain;
}
.v-theme--dark .vbi-swatch-img {
  filter: invert(1) brightness(0.95);
}
</style>
