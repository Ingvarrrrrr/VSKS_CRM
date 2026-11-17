<template>
  <!-- Диалог просмотра истории корректировок категории ФЭО и мероприятия -->
  <v-dialog
    :model-value="modelValue"
    max-width="760"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span class="d-flex align-center ga-2">
          <v-icon icon="mdi-history" color="warning" />
          История корректировок закупки
        </span>
        <v-btn icon="mdi-close" size="small" variant="text" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4" style="max-height: 75vh; overflow-y: auto;">
        <v-card
          v-if="corrections?.category_corrected || corrections?.event_corrected"
          variant="tonal"
          color="warning"
          class="pa-3 mb-4"
        >
          <div v-if="corrections?.category_corrected" class="text-body-2 mb-2">
            <div class="font-weight-bold mb-1">Категория ФЭО</div>
            <div>
              <span class="text-medium-emphasis">Первоначальная:</span>
              {{ corrections.initial_feo_category_name || 'Не была указана' }}
            </div>
            <div>
              <span class="text-medium-emphasis">Текущая:</span>
              {{ corrections.current_feo_category_name || 'Не указана' }}
            </div>
          </div>
          <div v-if="corrections?.event_corrected" class="text-body-2">
            <div class="font-weight-bold mb-1">Мероприятие</div>
            <div>
              <span class="text-medium-emphasis">Первоначальное:</span>
              {{ corrections.initial_event_name || 'Не было указано' }}
            </div>
            <div>
              <span class="text-medium-emphasis">Текущее:</span>
              {{ corrections.current_event_name || 'Не указано' }}
            </div>
          </div>
        </v-card>

        <div v-if="!corrections?.history?.length" class="text-body-2 text-medium-emphasis">
          Корректировок пока не было.
        </div>

        <v-card
          v-for="entry in (corrections?.history || [])"
          :key="entry.id"
          variant="outlined"
          class="pa-3 mb-3"
        >
          <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-2">
            <span class="font-weight-bold text-body-2">{{ entry.user_name }}</span>
            <span class="text-caption text-medium-emphasis">{{ formatDateTime(entry.created_at) }}</span>
          </div>

          <div v-if="entry.category_changed" class="text-body-2 mb-1">
            <strong>Категория ФЭО (шапка):</strong>
            {{ entry.old_feo_category_name || 'Не указана' }}
            →
            {{ entry.new_feo_category_name || 'Не указана' }}
          </div>

          <div v-if="entry.event_changed" class="text-body-2 mb-1">
            <strong>Мероприятие:</strong>
            {{ entry.old_event_name || 'Не указано' }}
            →
            {{ entry.new_event_name || 'Не указано' }}
          </div>

          <div v-if="entry.items_changes?.length" class="mt-2">
            <div class="text-caption font-weight-bold text-medium-emphasis mb-1">
              Изменения по позициям:
            </div>
            <div
              v-for="ch in entry.items_changes"
              :key="ch.item_id"
              class="text-caption mb-1 pl-2"
              style="border-left: 2px solid rgba(var(--v-theme-warning), 0.5);"
            >
              <div class="font-weight-medium">{{ ch.item_name }}</div>
              <div v-if="ch.old_feo_category_id !== ch.new_feo_category_id">
                Категория: {{ ch.old_feo_category_name || '—' }} → {{ ch.new_feo_category_name || '—' }}
              </div>
              <div v-if="ch.old_planned_item_id !== ch.new_planned_item_id">
                Плановая позиция: {{ ch.old_planned_item_name || 'Не привязана' }} → {{ ch.new_planned_item_name || 'Не привязана' }}
              </div>
            </div>
          </div>

          <div v-if="entry.comment" class="text-caption text-medium-emphasis mt-2">
            Комментарий: {{ entry.comment }}
          </div>
        </v-card>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-3 justify-end">
        <v-btn variant="text" @click="emit('update:modelValue', false)">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
export interface PurchaseCorrectionsSummary {
  category_corrected: boolean
  event_corrected: boolean
  planned_corrected?: boolean
  initial_feo_category_name: string | null
  current_feo_category_name: string | null
  initial_event_name: string | null
  current_event_name: string | null
  history: Array<any>
}

defineProps<{
  modelValue: boolean
  corrections: PurchaseCorrectionsSummary | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}
</script>
