<template>
  <div class="purpose-cell-wrap">
    <div
      class="text-caption"
      :class="{ 'purpose-clamped': !expanded }"
      :title="text || ''"
      style="word-break: break-word; line-height: 1.35;"
    >
      {{ text || '—' }}
    </div>
    <div v-if="text && text.length > 45" class="d-flex align-center gap-2 mt-1">
      <v-btn
        size="x-small"
        variant="text"
        density="compact"
        class="pa-0 text-caption text-primary font-weight-medium"
        style="min-width:0; height:auto; text-transform:none;"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'свернуть' : 'показать полностью' }}
      </v-btn>
      <v-btn
        size="x-small"
        variant="text"
        density="compact"
        icon="mdi-open-in-new"
        class="pa-0 text-medium-emphasis"
        style="min-width:0; width:18px; height:18px;"
        title="Посмотреть всё назначение в отдельном окне"
        @click.stop="showDialog = true"
      />
    </div>

    <!-- Модальное окно просмотра назначения платежа целиком -->
    <v-dialog v-model="showDialog" max-width="620">
      <v-card>
        <v-card-title class="d-flex align-center pa-4 pb-2 text-subtitle-1 font-weight-bold">
          <v-icon start size="20" color="primary">mdi-text-box-search-outline</v-icon>
          Назначение платежа
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4 text-body-2" style="white-space: pre-wrap; word-break: break-word; user-select: text; line-height: 1.5;">
          {{ text }}
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-3">
          <v-btn
            size="small"
            variant="tonal"
            prepend-icon="mdi-content-copy"
            @click="copyText"
          >
            {{ copied ? 'Скопировано!' : 'Копировать' }}
          </v-btn>
          <v-spacer />
          <v-btn size="small" variant="text" @click="showDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
// Назначение платежа сворачивается до одной строки с кнопкой раскрытия —
// задание владельца 04.10.2026 (панель подтверждения оплаты по выписке).
// Отдельный файл по ПРАВИЛУ №5: используется и в PaidConfirmationsPanel.vue
// (страница «Субсидии»), и в плашке PaymentsBlock.vue (карточка закупки) —
// один компонент, не копия разметки.
import { ref } from 'vue'

const props = defineProps<{ text: string | null }>()

const expanded = ref(false)
const showDialog = ref(false)
const copied = ref(false)

function copyText() {
  if (!props.text) return
  navigator.clipboard.writeText(props.text).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  })
}
</script>

<style scoped>
.purpose-cell-wrap {
  width: 100%;
}
.purpose-clamped {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
</style>
