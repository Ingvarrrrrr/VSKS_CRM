<template>
  <div class="mb-3">
    <div class="text-caption text-medium-emphasis mb-1">{{ item.item_name }}</div>

    <!-- Текст из каталога, своего ТЗ у позиции нет — показываем обычным текстом
         (не placeholder'ом, иначе владелец его не видит, жалоба 26.10.2026),
         правка — по кнопке «изменить», которая переносит этот же текст в
         tz_description (автосейв формы подхватывает как обычную правку). -->
    <div v-if="showCatalogReadOnly" class="hv-tz-catalog-block">
      <div class="hv-tz-catalog-text">{{ catalogText }}</div>
      <div class="d-flex align-center ga-2 mt-1">
        <span class="text-caption text-medium-emphasis">из каталога товара</span>
        <v-btn
          size="x-small" variant="text" color="primary" density="compact"
          prepend-icon="mdi-pencil-outline"
          @click="startEditingFromCatalog"
        >
          изменить
        </v-btn>
      </div>
    </div>

    <!-- Ни своего ТЗ, ни каталожного текста нет вовсе — честная надпись,
         а не пустое поле, которое можно спутать с placeholder'ом. -->
    <template v-else>
      <div v-if="noDescriptionAnywhere" class="text-caption text-error mb-1">
        Описания нет в каталоге — введите характеристики
      </div>
      <v-textarea
        v-model="item.tz_description"
        density="compact" variant="outlined" hide-details
        rows="2" max-rows="6" auto-grow
        label="Характеристики (ТЗ) этой позиции"
        placeholder="Характеристики не заданы"
      />
      <div class="d-flex align-center ga-2 mt-1">
        <v-btn
          v-if="(item.tz_description || '').trim() && catalogTextRaw"
          size="x-small" variant="text" color="primary" density="compact"
          prepend-icon="mdi-restore"
          @click="resetTzToCatalog(item)"
        >
          вернуть из каталога
        </v-btn>
        <!-- «Предложить в каталог» (план item-tz-description.md, Этап В, п.4) —
             только если позиция привязана к товару каталога И своё ТЗ реально
             отличается от каталожного (tzTextsDiffer, ПРАВИЛО №6 — тот же
             критерий, что у окна сравнения импорта). -->
        <v-btn
          v-if="item.product_id && item.id && tzTextsDiffer(item.tz_description, catalogTextRaw)"
          size="x-small" variant="text" color="teal" density="compact"
          prepend-icon="mdi-upload-outline"
          @click="$emit('propose', item)"
        >
          предложить в каталог
        </v-btn>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// Строка ТЗ одной позиции заявки — вынесена из WishTzSection.vue (ПРАВИЛО №5,
// модульность), владелец 26.10.2026: текст каталога должен быть виден как
// обычный текст, а не как placeholder пустого поля. Формула «действующее
// ТЗ» — effectiveTz (utils/itemTz.ts), ЕДИНСТВЕННАЯ, не дублируется здесь.
import { computed } from 'vue'
import { effectiveTz, resetTzToCatalog, tzTextsDiffer } from '@/utils/itemTz'

type EditorItem = any

const props = defineProps<{
  item: EditorItem
  mode: 'exact' | '44fz'
}>()

defineEmits<{ propose: [item: EditorItem] }>()

function trimmed(v: string | null | undefined): string {
  return (v || '').trim()
}

const ownText = computed(() => trimmed(props.item.tz_description))

// Каталожный текст в текущем режиме (Точное/44-ФЗ) — effectiveTz уже
// возвращает именно его, когда своего ТЗ нет (та же формула, что у бэкенда
// item_tz.py::effective_item_tz, ПРАВИЛО №6).
const effective = computed(() => effectiveTz(props.item, props.mode))
const catalogTextRaw = computed(() =>
  props.mode === '44fz' ? props.item._description_44fz : props.item._description
)

const showCatalogReadOnly = computed(() => !ownText.value && !!effective.value)
const catalogText = computed(() => effective.value)
const noDescriptionAnywhere = computed(() => !ownText.value && !effective.value)

function startEditingFromCatalog() {
  props.item.tz_description = catalogText.value
}
</script>

<style scoped>
.hv-tz-catalog-block {
  padding: 8px 12px;
  background: rgba(59, 130, 246, 0.06);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 6px;
}
.hv-tz-catalog-text {
  white-space: pre-wrap;
  font-size: 0.875rem;
  color: rgba(0, 0, 0, 0.87);
}
</style>
