<template>
  <div v-if="selectedCount > 0" class="d-flex align-center flex-wrap mb-3 pa-3 bg-blue-lighten-5 rounded-lg" style="gap:10px">
    <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedCount }}</span>
    <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="$emit('action', 'delete')">
      Удалить
    </v-btn>
    <v-btn size="small" variant="tonal" color="success" prepend-icon="mdi-send" @click="$emit('action', 'submit')">
      Отправить на согласование
    </v-btn>
    <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-cart-arrow-right" @click="$emit('action', 'convert')">
      Передать в план закупок
    </v-btn>
    <v-spacer />
    <v-btn size="small" variant="text" @click="$emit('clear')">Снять выделение</v-btn>
  </div>

  <!-- Подтверждение → прогресс → итог (один диалог, 29.10.2026). persistent —
       чтобы случайный клик вне окна не прервал выполняющееся массовое действие. -->
  <v-dialog :model-value="dialog.show" max-width="520" persistent @update:model-value="v => { if (!v) $emit('close') }">
    <v-card v-if="dialog.action">
      <v-card-title class="d-flex align-center ga-2">
        <v-icon :color="dialog.action === 'delete' ? 'error' : 'primary'">
          {{ dialog.action === 'delete' ? 'mdi-delete-outline' : dialog.action === 'submit' ? 'mdi-send' : 'mdi-cart-arrow-right' }}
        </v-icon>
        {{ titleFor(dialog.action) }}
      </v-card-title>
      <v-card-text>
        <template v-if="!dialog.running && dialog.progress === 0">
          <div v-if="dialog.action === 'delete'">
            Удалить {{ dialog.total }} заявок? Если у заявки есть закупки, не ушедшие дальше «Плана
            закупок», они будут удалены вместе с ней. Действие необратимо.
          </div>
          <div v-else-if="dialog.action === 'submit'">
            Отправить {{ dialog.total }} заявок на согласование? Действие применится только к черновикам
            из выбранных — остальные попадут в список «не обработано» с причиной.
          </div>
          <div v-else>
            Передать {{ dialog.total }} заявок в план закупок? Действие применится только к одобренным
            заявкам из выбранных.
          </div>
        </template>
        <template v-else>
          <v-progress-linear
            v-if="dialog.running"
            :model-value="dialog.total ? (dialog.progress / dialog.total) * 100 : 0"
            height="6"
            class="mb-3"
          />
          <div v-if="!dialog.running" class="mb-2">Готово: {{ dialog.done }} из {{ dialog.total }}</div>
          <!-- Превышение плана (владелец: не блокирует, но должно быть видно) —
               отдельный блок, окно из-за него не закрывается само (29.10.2026). -->
          <div v-if="dialog.excessWarnings.length" class="text-body-2 mb-3">
            <div class="font-weight-medium mb-1">
              Создано с превышением плана ({{ dialog.excessWarnings.length }}):
            </div>
            <ul class="pl-4">
              <li v-for="ew in dialog.excessWarnings" :key="ew.id">№{{ ew.id }} «{{ ew.title }}» — {{ ew.text }}</li>
            </ul>
          </div>
          <div v-if="dialog.failures.length" class="text-body-2">
            <div class="font-weight-medium mb-1">Не обработано ({{ dialog.failures.length }}):</div>
            <ul class="pl-4">
              <li v-for="f in dialog.failures" :key="f.id">№{{ f.id }} «{{ f.title }}» — {{ f.reason }}</li>
            </ul>
          </div>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <template v-if="!dialog.running && dialog.progress === 0">
          <v-btn variant="tonal" @click="$emit('close')">Отмена</v-btn>
          <v-btn variant="flat" :color="dialog.action === 'delete' ? 'error' : 'primary'" @click="$emit('confirm')">
            Подтвердить
          </v-btn>
        </template>
        <v-btn v-else-if="!dialog.running" variant="flat" color="primary" @click="$emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// WishBulkBar.vue — панель массовых действий над выбранными заявками + окно
// подтверждения/прогресса/итога. Общий компонент на все три вкладки списка
// заявок (My/Incoming/All) — ПРАВИЛО №5 (модульность), один файл вместо копии
// панели в каждой вкладке.
import type { BulkActionDialogState, BulkWishAction } from '@/composables/wishes/useWishBulkActions'

defineProps<{
  selectedCount: number
  dialog: BulkActionDialogState
}>()

defineEmits<{
  (e: 'action', action: BulkWishAction): void
  (e: 'confirm'): void
  (e: 'close'): void
  (e: 'clear'): void
}>()

function titleFor(action: BulkWishAction | null) {
  if (action === 'delete') return 'Удалить заявки'
  if (action === 'submit') return 'Отправить на согласование'
  if (action === 'convert') return 'Передать в план закупок'
  return ''
}
</script>
