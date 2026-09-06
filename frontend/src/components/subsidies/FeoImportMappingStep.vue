<template>
  <!-- Step 2: Column mapping — вынесен из FeoImportWizard.vue отдельным
       подкомпонентом (файл мастера целиком превышал 600 строк, см. задание
       волны 5a-2). Состояние — тот же singleton useFeoImport.ts, что и у
       родителя (FeoImportWizard.vue) — не копия. -->
  <v-alert v-if="feoCurrentSheet" type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
    <strong>Лист:</strong> {{ feoCurrentSheet.name }} ({{ feoCurrentSheet.total_rows }} строк данных)
  </v-alert>
  <v-select
    v-if="feoImport.previewData.sheets.length > 1"
    v-model="feoImport.selectedSheet"
    :items="feoImport.previewData.sheets.map((s: any) => ({ title: `${s.name} (${s.total_rows} строк)`, value: s.name }))"
    label="Сменить лист" variant="outlined" density="compact" class="mb-3"
    @update:model-value="feoAutoMap(feoCurrentSheet?.headers || [])"
  />
  <v-select
    v-model="feoImportTargetSubsidy"
    :items="allSubsidies"
    item-title="name" item-value="id"
    label="Субсидия назначения (для строк без столбца «Субсидия»)"
    variant="outlined" density="compact" clearable class="mb-3"
    hint="Если в файле колонка «Субсидия» пустая — все строки будут отнесены к выбранной субсидии"
    persistent-hint />

  <div class="feo-imap-grid">
    <div v-for="target in FEO_TARGET_FIELDS" :key="target.value"
      class="feo-imap-col"
      :class="{
        'feo-imap-col--over': feoDragOverTarget === target.value,
        'feo-imap-col--filled': feoIsTargetFilled(target.value),
        'feo-imap-col--required': target.required && !feoIsTargetFilled(target.value),
      }"
      @dragover.prevent="feoDragOverTarget = target.value"
      @dragleave="feoDragOverTarget = null"
      @drop.prevent="feoOnDropToTarget(target.value, $event)">
      <div class="feo-imap-col-hdr">{{ target.title }}<span v-if="target.required" style="color:#e53935">*</span></div>
      <div class="feo-imap-col-body">
        <div v-if="feoIsTargetFilled(target.value)"
          class="feo-imap-card"
          draggable="true"
          @dragstart="feoOnDragStart(feoDragMapping[target.value] as number, $event)">
          <div class="feo-imap-card-row">
            <span class="feo-imap-card-name">{{ feoGetColumnLabel(feoDragMapping[target.value] as number) }}</span>
            <button class="feo-imap-card-x" @click.stop="feoUnmapTarget(target.value)">×</button>
          </div>
          <div class="feo-imap-card-samples">{{ feoGetSamples(feoDragMapping[target.value] as number).join(', ') || '—' }}</div>
        </div>
        <div v-else class="feo-imap-col-empty">—</div>
      </div>
    </div>
  </div>

  <div class="feo-imap-unresolved mt-3"
    :class="{ 'feo-imap-unresolved--over': feoDragOverTarget === '_unresolved' }"
    @dragover.prevent="feoDragOverTarget = '_unresolved'"
    @dragleave="feoDragOverTarget = null"
    @drop.prevent="feoOnDropToUnresolved($event)">
    <span class="feo-imap-unresolved-label">Не определилось</span>
    <div class="d-flex gap-2 flex-wrap mt-1">
      <template v-for="(_, idx) in feoCurrentHeaders" :key="idx">
        <div v-if="!feoIsMapped(idx) && !feoIsIgnored(idx)"
          class="feo-imap-card feo-imap-card--free"
          draggable="true"
          @dragstart="feoOnDragStart(idx, $event)">
          <div class="feo-imap-card-row">
            <span class="feo-imap-card-name">{{ feoGetColumnLabel(idx) }}</span>
            <button class="feo-imap-card-x feo-imap-card-x--grey" title="Убрать" @click.stop="feoIgnoreColumn(idx)">×</button>
          </div>
          <div class="feo-imap-card-samples">{{ feoGetSamples(idx).join(', ') || '—' }}</div>
        </div>
      </template>
      <span v-if="feoUnmappedCount === 0" style="font-size:11px;color:#888;align-self:center">все распределены ✓</span>
    </div>
  </div>

  <v-alert v-if="!feoMappingValid" type="warning" density="compact" icon="mdi-alert" class="mt-3">
    Укажите столбцы «Субсидия» и «Уровень 2 / Направление»
  </v-alert>
</template>

<script setup lang="ts">
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useFeoImport } from '@/composables/subsidies/useFeoImport'

const {
  feoImport, feoImportTargetSubsidy, FEO_TARGET_FIELDS, feoDragMapping, feoDragOverTarget,
  feoCurrentSheet, feoCurrentHeaders, feoMappingValid, feoUnmappedCount, feoIsMapped, feoIsIgnored,
  feoIsTargetFilled, feoGetColumnLabel, feoGetSamples, feoOnDragStart, feoOnDropToTarget,
  feoOnDropToUnresolved, feoUnmapTarget, feoIgnoreColumn, feoAutoMap, allSubsidies,
} = useFeoImport(useSubsidyDetailCtx())
</script>

<style scoped>
.feo-imap-grid {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.feo-imap-col {
  flex: 1;
  min-width: 130px;
  border: 1px dashed #ccc;
  border-radius: 6px;
  background: #fafafa;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-col--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-col--filled {
  border-style: solid;
  border-color: #43A047;
  background: #f6fff6;
}
.feo-imap-col--required {
  border-color: #ef9a9a;
  background: #fff8f8;
}
.feo-imap-col-hdr {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: #555;
  padding: 5px 7px 3px;
  border-bottom: 1px solid #e8e8e8;
  white-space: normal;
  word-break: break-word;
}
.feo-imap-col-body {
  padding: 5px;
  min-height: 58px;
}
.feo-imap-col-empty {
  font-size: 10px;
  color: #ccc;
  text-align: center;
  margin-top: 10px;
  font-style: italic;
}
.feo-imap-card {
  border-radius: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  padding: 4px 6px;
  cursor: grab;
  user-select: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.feo-imap-card:hover {
  border-color: #1976D2;
  box-shadow: 0 1px 5px rgba(25, 118, 210, 0.15);
}
.feo-imap-card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
}
.feo-imap-card-name {
  font-size: 11px;
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.feo-imap-card-x {
  font-size: 14px;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #aaa;
  padding: 0 2px;
  flex-shrink: 0;
}
.feo-imap-card-x:hover { color: #e53935; }
.feo-imap-card-x--grey { color: #bbb; }
.feo-imap-card-samples {
  font-size: 10px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.3;
}
.feo-imap-card--free {
  background: #fafafa;
}
.feo-imap-unresolved {
  border: 1px dashed #ccc;
  border-radius: 6px;
  padding: 6px 10px;
  min-height: 44px;
  transition: border-color 0.15s, background 0.15s;
}
.feo-imap-unresolved--over {
  border-color: #1976D2;
  background: rgba(25, 118, 210, 0.04);
}
.feo-imap-unresolved-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #aaa;
  letter-spacing: 0.3px;
}
</style>
