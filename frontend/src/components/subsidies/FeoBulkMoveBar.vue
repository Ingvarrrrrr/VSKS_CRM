<template>
  <!-- ── Прилипающая панель массового переноса плановых позиций (владелец,
       п.12, 13.10.2026): «выделить-то можно, а кнопки "Перенести в
       категорию" я не вижу» — кнопка внутри панели конкретной категории
       (FeoLevel5Panel.vue) уходит из виду при скролле или когда отмечены
       позиции в НЕСКОЛЬКИХ категориях сразу (общий Set выбора —
       selectedPlannedItemIds, см. useFeoLevel5.ts). Эта панель видна всегда,
       как только хоть что-то отмечено, прилипает к низу экрана, и считает
       ОБЩЕЕ число выбранного across all categories. Переносит той же
       submitBulkMove/openBulkMoveDialogGlobal, что и кнопка внутри панели —
       второй операции переноса не заводим (Правило №6). -->
  <div v-if="feoLevel5.selectedPlannedItemIds.value.size > 0" class="feo-bulk-move-bar">
    <v-chip size="small" color="orange" variant="tonal">
      Выбрано: {{ feoLevel5.selectedPlannedItemIds.value.size }}
    </v-chip>
    <v-btn size="small" variant="tonal" color="orange-darken-1" prepend-icon="mdi-folder-move-outline"
      @click="feoLevel5.openBulkMoveDialogGlobal()">
      Перенести в категорию…
    </v-btn>
    <v-btn size="small" variant="text" color="grey-darken-1"
      @click="feoLevel5.clearAllPlannedSelection()">
      Снять выделение
    </v-btn>
  </div>

  <!-- Диалог переноса для ГЛОБАЛЬНОГО случая (несколько категорий сразу или
       прокрученная панель) — служебный bulkMoveActiveNodeId === -1 не
       совпадает ни с одной настоящей категорией, поэтому с per-node
       диалогами в FeoLevel5Panel.vue открывается только один. Разметка —
       тот же FeoTreeSelect + submitBulkMove, что и там; второй диалог
       переноса по сути не заводим, дублируем только вёрстку v-dialog ради
       singleton-монтирования (тот же приём, что у FeoRowDrillDialog.vue/
       FeoPlannedItemPartEditDialog.vue в FeoTreeTable.vue). -->
  <v-dialog v-if="feoLevel5.bulkMoveActiveNodeId.value === feoLevel5.GLOBAL_BULK_MOVE_NODE_ID" v-model="feoLevel5.bulkMoveDialogOpen.value" max-width="640" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1">
        Перенести {{ feoLevel5.bulkMoveItemIds.value.length }} плановых позиций в другую категорию
      </v-card-title>
      <v-card-text>
        <div v-if="feoLevel5.bulkMoveLoadingTree.value" class="d-flex align-center" style="gap:8px;padding:8px 0">
          <v-progress-circular indeterminate size="16" color="orange-darken-1" />
          <span class="text-caption">Загрузка дерева категорий...</span>
        </div>
        <FeoTreeSelect
          v-else
          v-model="feoLevel5.bulkMoveTargetCategoryId.value"
          :nodes="feoLevel5.bulkMoveNodes.value"
          :leaves="feoLevel5.bulkMoveLeaves.value"
          label="Категория-приёмник"
          required
        />
        <div v-if="feoLevel5.bulkMoveFailures.value.length" class="mt-3 text-caption text-error">
          <div class="font-weight-medium mb-1">Не удалось перенести ({{ feoLevel5.bulkMoveFailures.value.length }}):</div>
          <div v-for="f in feoLevel5.bulkMoveFailures.value" :key="f.name">«{{ f.name }}» — {{ f.error }}</div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="feoLevel5.bulkMoveSubmitting.value" @click="feoLevel5.closeBulkMoveDialog()">Отмена</v-btn>
        <v-btn color="orange-darken-1" variant="tonal"
          :loading="feoLevel5.bulkMoveSubmitting.value"
          :disabled="!feoLevel5.bulkMoveTargetCategoryId.value"
          @click="feoLevel5.submitBulkMove()"
        >Перенести</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Прилипающая панель массового переноса — см. докстринг в <template> выше.
// Состояние/операции — целиком useFeoLevel5.ts (singleton, тот же экземпляр,
// что и у FeoLevel5Panel.vue), здесь только вёрстка.
import { useFeoLevel5Api } from '@/composables/subsidies/useFeoLevel5'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'

const feoLevel5 = useFeoLevel5Api()
</script>

<style scoped>
.feo-bulk-move-bar {
  position: sticky;
  bottom: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: #FFF7ED;
  border-top: 1px solid #FDBA74;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.08);
}
</style>
