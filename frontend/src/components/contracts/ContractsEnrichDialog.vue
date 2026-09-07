<template>
  <v-dialog v-model="enrichDialog" max-width="520">
    <v-card>
      <v-card-title>Обогатить договоры из связанных закупок</v-card-title>
      <v-card-text>
        <p v-if="!enrichResult">
          Найдёт все договоры где не заполнены поля (Предмет / Сумма / Даты / Способ / Товары-услуги),
          и подтянет значения из привязанных закупок.
          <br><br>
          <strong>Не перезаписывает</strong> уже заполненные поля.
          Безопасно запускать многократно.
        </p>
        <v-alert v-if="enrichResult" type="success" variant="tonal">
          Обогащено договоров: <strong>{{ enrichResult.enriched_existing }}</strong>
          (из {{ enrichResult.scanned_contracts }} проверенных).
          <br>
          Связей контракт↔закупка восстановлено: <strong>{{ enrichResult.purchases_linked || 0 }}</strong>
          <br>
          Связей позиций восстановлено: <strong>{{ enrichResult.relinked_orphans || 0 }}</strong>
          <br>
          Также создано {{ enrichResult.created }} новых договоров из чеков.
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-btn variant="text" @click="enrichDialog = false">Закрыть</v-btn>
        <v-btn v-if="!enrichResult" color="primary" variant="tonal"
          :loading="enriching" @click="onEnrich">
          Запустить обогащение
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const enrichDialog = defineModel<boolean>({ required: true })

defineProps<{
  enriching: boolean
  enrichResult: {
    created: number
    scanned_purchases: number
    enriched_existing: number
    scanned_contracts: number
    relinked_orphans?: number
    purchases_linked?: number
  } | null
  onEnrich: () => void
}>()
</script>
