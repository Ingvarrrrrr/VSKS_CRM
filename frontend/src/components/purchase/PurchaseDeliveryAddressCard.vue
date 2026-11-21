<template>
  <v-card id="section-delivery-address" variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
      <v-icon start color="indigo">mdi-map-marker-outline</v-icon>
      Адрес поставки
    </v-card-title>
    <v-card-text>
      <!-- Переключатель типа адреса / особая формулировка -->
      <div id="pub-target-address" style="position:relative">
        <div v-if="pointerTarget === 'address'" class="pub-pointer">
          <span class="mdi mdi-arrow-down-bold" />
        </div>
        <div :class="pointerTarget === 'address' ? 'pub-glow' : ''">
          <div class="mb-3 d-flex align-center flex-wrap ga-2">
            <v-btn-toggle
              v-model="form.delivery_location_kind"
              density="compact"
              mandatory
              color="primary"
              variant="outlined"
              @update:model-value="onKindChange"
            >
              <v-btn value="delivery" size="small">Адрес доставки</v-btn>
              <v-btn value="service" size="small">Место оказания услуг</v-btn>
            </v-btn-toggle>
            <v-btn
              size="small"
              density="compact"
              :variant="isSpecialLocation ? 'flat' : 'tonal'"
              :color="isSpecialLocation ? 'primary' : undefined"
              :prepend-icon="isSpecialLocation ? 'mdi-check' : undefined"
              @click="toggleSpecialLocation"
            >
              По месту нахождения подрядчика
            </v-btn>
          </div>

          <!-- Итоговая строка адреса -->
          <div class="text-body-2 mb-2" style="line-height:1.5">
            <span class="text-medium-emphasis">{{ displayLabel }} (подставится в документ):</span>
            <strong class="ml-1">{{ form.delivery_location || form.delivery_address || '—' }}</strong>
          </div>
        </div>
      </div>

      <template v-if="!isSpecialLocation">
        <!-- Поиск адреса одной строкой с подсказками из истории / организаций -->
        <v-row dense class="mb-2">
          <v-col cols="12">
            <v-combobox
              v-model="searchAddressModel"
              :items="deliveryAddressSuggestions || []"
              label="Быстрый поиск адреса (одной строкой)"
              variant="outlined"
              density="compact"
              clearable
              hide-no-data
              no-filter
              :custom-filter="() => true"
              placeholder="Начните вводить адрес (индекс, город, улица, дом)..."
              hint="При выборе или вводе строки адрес автоматически разбирается на индекс, город, улицу и дом"
              persistent-hint
              @update:search="onDeliveryAddressSearch"
              @update:model-value="onAddressSelect"
            />
          </v-col>
        </v-row>

        <!-- Регион поставки (субъект РФ) -->
        <v-row dense class="mb-2">
          <v-col cols="12" md="6">
            <div id="pub-target-region" style="position:relative">
              <div v-if="pointerTarget === 'region'" class="pub-pointer">
                <span class="mdi mdi-arrow-down-bold" />
              </div>
              <div :class="pointerTarget === 'region' ? 'pub-glow' : ''">
                <v-autocomplete
                  v-model="form.delivery_region"
                  :items="DELIVERY_REGIONS"
                  label="Регион поставки (субъект РФ)"
                  density="compact"
                  variant="outlined"
                  clearable
                  hint="Определяет ОКАТО/федеральный округ места поставки для Фабриканта"
                  persistent-hint
                  @update:model-value="onRegionChange"
                />
              </div>
            </div>
          </v-col>
          <v-col cols="12" md="6">
            <v-autocomplete
              v-model="form.region"
              :items="RUSSIAN_REGIONS"
              label="Регион проведения мероприятия"
              density="compact"
              variant="outlined"
              clearable
              hint='Включая вариант "Федеральное мероприятие"'
              persistent-hint
              @update:model-value="flushAutosaveOnBlur"
            />
          </v-col>
        </v-row>

        <!-- Структурированный разбор адреса -->
        <v-row dense>
          <v-col cols="12" sm="3" md="2">
            <v-text-field
              v-model="form.delivery_postcode"
              label="Индекс"
              variant="outlined"
              density="compact"
              maxlength="6"
              hide-details
              @blur="flushAutosaveOnBlur"
            />
          </v-col>
          <v-col cols="12" sm="5" md="4">
            <div id="pub-target-city" style="position:relative">
              <div v-if="pointerTarget === 'city'" class="pub-pointer">
                <span class="mdi mdi-arrow-down-bold" />
              </div>
              <div :class="pointerTarget === 'city' ? 'pub-glow' : ''">
                <v-text-field
                  v-model="form.delivery_city"
                  label="Город / населённый пункт"
                  variant="outlined"
                  density="compact"
                  hide-details
                  @update:model-value="onCityChange"
                />
              </div>
            </div>
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-text-field
              v-model="form.delivery_street"
              label="Улица"
              variant="outlined"
              density="compact"
              hide-details
              @blur="flushAutosaveOnBlur"
            />
          </v-col>
          <v-col cols="6" sm="6" md="2">
            <v-text-field
              v-model="form.delivery_house"
              label="Дом"
              variant="outlined"
              density="compact"
              hide-details
              @blur="flushAutosaveOnBlur"
            />
          </v-col>
          <v-col cols="6" sm="6" md="1">
            <v-text-field
              v-model="form.delivery_building"
              label="Корпус"
              variant="outlined"
              density="compact"
              hide-details
              @blur="flushAutosaveOnBlur"
            />
          </v-col>
        </v-row>
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { RUSSIAN_REGIONS, DELIVERY_REGIONS } from '@/constants/russian_regions'
import { parseAddress } from '@/utils/addressCompose'

const SPECIAL_LOCATION_TEXT = 'По месту нахождения подрядчика'

const props = defineProps<{
  form: Record<string, any>
  deliveryAddressSuggestions?: string[]
  onDeliveryAddressSearch?: (q: string) => void
  onDeliveryAddressSelect?: (val: string | null) => void
  saveDeliveryAddressIfNew?: (addr: string) => void
  flushAutosaveOnBlur?: () => void
  clearGuideArrow?: () => void
}>()

const pointerTarget = defineModel<string | null>('pointerTarget', { default: null })

const searchAddressModel = ref<string>(props.form.delivery_address || props.form.delivery_location || '')

const isSpecialLocation = computed(() => props.form.delivery_location === SPECIAL_LOCATION_TEXT)

const displayLabel = computed(() => {
  if (props.form.delivery_location_kind === 'service') return 'Место оказания услуг'
  if (props.form.delivery_location_kind === 'delivery') return 'Адрес доставки'
  return props.form.item_type === 'услуга' ? 'Место оказания услуг' : 'Адрес доставки'
})

// Сборка адреса из покомпонентных полей
const assembledAddress = computed(() => {
  const f = props.form
  const parts: string[] = []
  if ((f.delivery_postcode || '').trim()) parts.push(f.delivery_postcode.trim())
  if ((f.delivery_region || '').trim()) parts.push(f.delivery_region.trim())
  if ((f.delivery_city || '').trim()) parts.push(f.delivery_city.trim())
  if ((f.delivery_street || '').trim()) parts.push(f.delivery_street.trim())
  if ((f.delivery_house || '').trim()) parts.push('д. ' + f.delivery_house.trim())
  if ((f.delivery_building || '').trim()) parts.push('к. ' + f.delivery_building.trim())
  return parts.join(', ')
})

// Синхронизация assembledAddress -> delivery_location и delivery_address
watch(assembledAddress, (val) => {
  if (!isSpecialLocation.value) {
    if (val) {
      props.form.delivery_location = val
      props.form.delivery_address = val
    }
  }
}, { immediate: true })

function toggleSpecialLocation() {
  if (isSpecialLocation.value) {
    props.form.delivery_location = assembledAddress.value || ''
    props.form.delivery_address = assembledAddress.value || ''
  } else {
    props.form.delivery_location = SPECIAL_LOCATION_TEXT
    props.form.delivery_address = SPECIAL_LOCATION_TEXT
  }
  if (pointerTarget.value === 'address') {
    pointerTarget.value = null
  }
  props.clearGuideArrow?.()
  props.flushAutosaveOnBlur?.()
}

function onKindChange() {
  props.flushAutosaveOnBlur?.()
}

function onAddressSelect(val: string | null) {
  if (!val || typeof val !== 'string') return
  const raw = val.trim()
  if (!raw) return
  if (raw === SPECIAL_LOCATION_TEXT) {
    toggleSpecialLocation()
    return
  }

  props.onDeliveryAddressSelect?.(raw)
  props.saveDeliveryAddressIfNew?.(raw)

  // Разбор строки через проверенный утилит parseAddress
  const parsed = parseAddress(raw)
  if (parsed.postal_code) props.form.delivery_postcode = parsed.postal_code
  if (parsed.region) {
    // Подбор субъекта РФ в DELIVERY_REGIONS
    const matchedRegion = DELIVERY_REGIONS.find(
      r => r.toLowerCase() === parsed.region.toLowerCase() || parsed.region.toLowerCase().includes(r.toLowerCase())
    )
    if (matchedRegion) props.form.delivery_region = matchedRegion
    else props.form.delivery_region = parsed.region
  }
  if (parsed.settlement) props.form.delivery_city = parsed.settlement
  if (parsed.street) props.form.delivery_street = parsed.street
  if (parsed.house) props.form.delivery_house = parsed.house
  if (parsed.building) props.form.delivery_building = parsed.building

  props.form.delivery_location = raw
  props.form.delivery_address = raw

  if (pointerTarget.value === 'address') pointerTarget.value = null
  props.clearGuideArrow?.()
  props.flushAutosaveOnBlur?.()
}

function onRegionChange() {
  if (pointerTarget.value === 'region') pointerTarget.value = null
  props.clearGuideArrow?.()
  props.flushAutosaveOnBlur?.()
}

function onCityChange() {
  if (pointerTarget.value === 'city') pointerTarget.value = null
  props.clearGuideArrow?.()
  props.flushAutosaveOnBlur?.()
}
</script>

<style scoped>
.pub-pointer {
  position: absolute;
  top: -24px;
  left: 20px;
  color: #ff5722;
  font-size: 24px;
  animation: bounce 1s infinite alternate;
  z-index: 5;
}
@keyframes bounce {
  from { transform: translateY(0); }
  to { transform: translateY(-8px); }
}
.pub-glow {
  box-shadow: 0 0 12px rgba(255, 87, 34, 0.4);
  border-radius: 8px;
  transition: box-shadow 0.3s ease;
}
</style>
