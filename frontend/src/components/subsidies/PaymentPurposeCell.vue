<template>
  <div>
    <div
      class="text-caption"
      :class="{ 'purpose-clamped': !expanded }"
      :title="text || ''"
    >
      {{ text || '—' }}
    </div>
    <v-btn
      v-if="text && text.length > 60"
      size="x-small"
      variant="text"
      density="compact"
      class="pa-0 text-caption"
      style="min-width:0; height:auto"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'свернуть' : 'показать полностью' }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
// Назначение платежа сворачивается до одной строки с кнопкой раскрытия —
// задание владельца 04.10.2026 (панель подтверждения оплаты по выписке).
// Отдельный файл по ПРАВИЛУ №5: используется и в PaidConfirmationsPanel.vue
// (страница «Субсидии»), и в плашке PaymentsBlock.vue (карточка закупки) —
// один компонент, не копия разметки.
import { ref } from 'vue'

defineProps<{ text: string | null }>()

const expanded = ref(false)
</script>

<style scoped>
.purpose-clamped {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
</style>
