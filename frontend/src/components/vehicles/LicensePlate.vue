<template>
  <!-- Российский гос. номер ГОСТ Р 50577-2018: белый фон, тонкая чёрная рамка,
       основная секция + региональная (с RUS и флагом РФ). Если plate не
       распознан как РФ-формат (украинский ЛНР/ДНР и т.п.) — рендерится
       целиком в одной секции без разделителя. -->
  <span class="ru-plate" :class="{ 'ru-plate--sm': size === 'sm', 'ru-plate--lg': size === 'lg' }">
    <span class="ru-plate__main">{{ mainPart }}</span>
    <span v-if="regionPart" class="ru-plate__region">
      <span class="ru-plate__region-num">{{ regionPart }}</span>
      <span class="ru-plate__rus-row">
        <span class="ru-plate__rus">RUS</span>
        <span class="ru-plate__flag" aria-hidden="true">
          <span class="ru-plate__flag-stripe ru-plate__flag-white"></span>
          <span class="ru-plate__flag-stripe ru-plate__flag-blue"></span>
          <span class="ru-plate__flag-stripe ru-plate__flag-red"></span>
        </span>
      </span>
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: string
  readonly?: boolean
  size?: 'sm' | 'md' | 'lg'
}>()

// ГОСТ Р 50577-2018: разрешённые кириллические буквы (АВЕКМНОРСТУХ).
// Дополнительно принимаем визуально-эквивалентные латинские (ABEKMHOPCTYX) —
// в БД часто хранится транслит после импорта из xlsx Excel.
const RU_LETTERS = 'АВЕКМНОРСТУХABEKMHOPCTYX'
// 1 буква + 3 цифры + 2 буквы + 2 или 3 цифры региона
const RU_PLATE_RE = new RegExp(`^([${RU_LETTERS}])(\\d{3})([${RU_LETTERS}]{2})(\\d{2,3})$`, 'i')

const parsed = computed(() => {
  const raw = (props.modelValue || '').replace(/\s+/g, '').toUpperCase()
  const m = raw.match(RU_PLATE_RE)
  if (m) {
    return { main: `${m[1]} ${m[2]} ${m[3]}`, region: m[4] }
  }
  // Fallback: всё одной строкой (укр./донецкие номера, спецтехника, прицепы)
  return { main: props.modelValue || '—', region: null }
})

const mainPart = computed(() => parsed.value.main)
const regionPart = computed(() => parsed.value.region)
</script>

<style scoped>
.ru-plate {
  display: inline-flex;
  align-items: stretch;
  background: #fff;
  border: 2px solid #111;
  border-radius: 6px;
  font-family: 'Road UA Cyrillic', 'PT Sans Narrow', 'Arial Narrow', Impact, sans-serif;
  font-weight: 800;
  color: #111;
  overflow: hidden;
  height: 34px;
  line-height: 1;
  vertical-align: middle;
  user-select: none;
}
.ru-plate--sm { height: 26px; font-size: 14px; }
.ru-plate__main {
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  font-size: 20px;
  letter-spacing: 1.5px;
  white-space: nowrap;
}
.ru-plate--sm .ru-plate__main { font-size: 14px; padding: 0 10px; letter-spacing: 1px; }
.ru-plate--lg { height: 44px; }
.ru-plate--lg .ru-plate__main { font-size: 26px; padding: 0 18px; letter-spacing: 2px; }
.ru-plate__region {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3px 9px 3px 9px;
  border-left: 2px solid #111;
  background: #fff;
  min-width: 42px;
}
.ru-plate--sm .ru-plate__region { padding: 2px 6px; min-width: 34px; }
.ru-plate--lg .ru-plate__region { padding: 4px 14px; min-width: 56px; }
.ru-plate__region-num {
  font-size: 17px;
  font-weight: 800;
  line-height: 1;
}
.ru-plate--sm .ru-plate__region-num { font-size: 13px; }
.ru-plate--lg .ru-plate__region-num { font-size: 22px; }
.ru-plate__rus-row {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-top: 2px;
}
.ru-plate__rus {
  font-size: 8px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1;
}
.ru-plate--sm .ru-plate__rus { font-size: 6px; }
.ru-plate--lg .ru-plate__rus { font-size: 10px; }
.ru-plate__flag {
  display: inline-flex;
  flex-direction: column;
  width: 11px;
  height: 7px;
  border: 0.5px solid #888;
  overflow: hidden;
  border-radius: 1px;
}
.ru-plate--sm .ru-plate__flag { width: 9px; height: 6px; }
.ru-plate--lg .ru-plate__flag { width: 14px; height: 9px; }
.ru-plate__flag-stripe { flex: 1; display: block; }
.ru-plate__flag-white { background: #fff; }
.ru-plate__flag-blue  { background: #0033A0; }
.ru-plate__flag-red   { background: #DA291C; }
</style>
