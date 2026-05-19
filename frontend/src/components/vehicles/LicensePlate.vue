<template>
  <div class="license-plate" :class="{ invalid: !isValid }">
    <div class="plate-main">
      <input
        v-if="!readonly"
        v-model="mainPart"
        class="plate-input"
        :maxlength="6"
        @blur="emitUpdate"
        @input="onMainInput"
      />
      <span v-else>{{ mainPart || '\u2014' }}</span>
    </div>
    <div class="plate-region">
      <input
        v-if="!readonly"
        v-model="regionPart"
        class="region-input"
        :maxlength="3"
        @blur="emitUpdate"
      />
      <span v-else>{{ regionPart || '\u2014' }}</span>
      <div class="rus-stripes">
        <div class="stripe white"></div>
        <div class="stripe blue"></div>
        <div class="stripe red"></div>
      </div>
      <div class="rus-label">RUS</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: string
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

// Regex: кириллические буквы А В Е К М Н О Р С Т У Х + цифры
const PLATE_RE = /^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$/

const isValid = computed(() => {
  if (!props.modelValue) return true // пустое — не помечаем невалидным
  return PLATE_RE.test(props.modelValue.toUpperCase())
})

// Разбиваем на основную часть (первые 6 символов) и регион (остаток)
function parsePlate(value: string): { main: string; region: string } {
  const v = value ?? ''
  if (v.length <= 6) return { main: v, region: '' }
  return { main: v.slice(0, 6), region: v.slice(6) }
}

const parsed = computed(() => parsePlate(props.modelValue ?? ''))

const mainPart = ref(parsed.value.main)
const regionPart = ref(parsed.value.region)

watch(() => props.modelValue, (val) => {
  const p = parsePlate(val ?? '')
  mainPart.value = p.main
  regionPart.value = p.region
})

function onMainInput() {
  // Автоперевод в верхний регистр
  mainPart.value = mainPart.value.toUpperCase()
}

function emitUpdate() {
  const combined = (mainPart.value + regionPart.value).toUpperCase()
  emit('update:modelValue', combined)
}
</script>

<style scoped>
.license-plate {
  display: inline-flex;
  border: 2px solid #000;
  border-radius: 4px;
  background: #fff;
  font-family: 'Courier New', monospace;
  font-weight: 700;
  height: 40px;
  user-select: text;
  vertical-align: middle;
}

.plate-main {
  padding: 0 8px;
  display: flex;
  align-items: center;
  font-size: 22px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: #000;
  min-width: 110px;
  justify-content: center;
}

.plate-input {
  background: transparent;
  border: none;
  outline: none;
  font: inherit;
  width: 100px;
  text-align: center;
  text-transform: uppercase;
  color: #000;
}

.plate-region {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-left: 2px solid #000;
  padding: 0 6px;
  min-width: 36px;
  background: #fff;
  font-size: 14px;
  color: #000;
  font-weight: 700;
}

.region-input {
  background: transparent;
  border: none;
  outline: none;
  font: inherit;
  width: 28px;
  text-align: center;
  color: #000;
}

.rus-stripes {
  display: flex;
  gap: 1px;
  height: 6px;
  margin-top: 2px;
}

.stripe {
  width: 8px;
  height: 6px;
}

.stripe.white {
  background: #fff;
  border: 1px solid #aaa;
}

.stripe.blue {
  background: #0d3a8b;
}

.stripe.red {
  background: #c8102e;
}

.rus-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1px;
  color: #000;
}

.license-plate.invalid {
  border-color: #ff5252;
}
</style>
