<template>
  <!-- 12-04/12-05: Version Snapshot Dialog -->
  <v-dialog v-model="v.showVersionSnapshotDialog.value" max-width="960" scrollable :fullscreen="mobile">
    <v-card v-if="v.selectedVersionSnapshot.value">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-database-eye" size="20" color="blue" class="mr-2" />
        <div>
          Снимок версии v{{ v.selectedVersionSnapshot.value.version_number }}
          <span v-if="v.selectedVersionSnapshot.value.effective_date" class="text-body-2 text-medium-emphasis ml-2">
            (дата редакции: {{ new Date(v.selectedVersionSnapshot.value.effective_date).toLocaleDateString('ru-RU') }})
          </span>
          <div v-if="v.selectedVersionSnapshot.value.note" class="text-caption text-medium-emphasis mt-1">
            {{ v.selectedVersionSnapshot.value.note }}
          </div>
        </div>
        <v-spacer />
        <v-btn icon="mdi-close" size="x-small" variant="text" @click="v.showVersionSnapshotDialog.value = false" />
      </v-card-title>
      <v-divider />
      <v-card-text>
        <!-- v2 snapshot с tree -->
        <table v-if="v.selectedVersionSnapshot.value.snapshot?.tree?.length" class="snapshot-tree-table">
          <thead>
            <tr>
              <th>Наименование</th>
              <th class="text-right">План (snapshot) ₽</th>
              <th class="text-right">Факт (текущий) ₽</th>
              <th class="text-right">Остаток ₽</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="node in v.flattenedSnapshotTree.value" :key="node._key">
              <tr :class="`level-${node.level} status-${v.getReconStatus(node)}`">
                <td :style="`padding-left:${(node.level - 1) * 20 + 8}px`">
                  <v-icon v-if="node.children?.length" icon="mdi-folder-outline" size="14" class="mr-1" />
                  {{ node.name }}
                </td>
                <td class="text-right">{{ formatCurrency(node.budget || 0) }}</td>
                <td class="text-right">{{ formatCurrency(v.getActualUsed(node.id)) }}</td>
                <td class="text-right" :class="v.getActualResidual(node) < 0 ? 'text-error' : ''">
                  {{ formatCurrency(v.getActualResidual(node)) }}
                </td>
                <td>
                  <v-chip v-if="v.getReconStatus(node) === 'moved'" size="x-small" color="info" variant="tonal">переименован</v-chip>
                  <v-chip v-else-if="v.getReconStatus(node) === 'orphan'" size="x-small" color="warning" variant="tonal">не сматчился</v-chip>
                  <v-chip v-else-if="v.getReconStatus(node) === 'matched'" size="x-small" color="success" variant="tonal">✓</v-chip>
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot>
            <tr>
              <td><b>Итого</b></td>
              <td class="text-right"><b>{{ formatCurrency(v.selectedVersionSnapshot.value.snapshot?.total_planned || 0) }}</b></td>
              <td class="text-right"><b>{{ formatCurrency(v.snapshotTotalActual.value) }}</b></td>
              <td class="text-right"><b>{{ formatCurrency((v.selectedVersionSnapshot.value.snapshot?.total_planned || 0) - v.snapshotTotalActual.value) }}</b></td>
              <td></td>
            </tr>
          </tfoot>
        </table>
        <!-- v1 snapshot — fallback на flat items -->
        <v-table v-else density="compact" style="font-size:12px">
          <thead>
            <tr style="background:#EFF6FF">
              <th>Наименование</th>
              <th class="text-right">Планово, ₽</th>
              <th class="text-right">Факт, ₽</th>
              <th class="text-right">Остаток, ₽</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in v.selectedVersionSnapshot.value.snapshot?.items || []" :key="item.feo_item_id">
              <td>{{ item.name }}</td>
              <td class="text-right">{{ formatCurrency(item.planned_amount) }}</td>
              <td class="text-right">{{ formatCurrency(item.used_amount) }}</td>
              <td class="text-right"
                :style="item.residual < 0 ? 'color:#EF4444;font-weight:bold' : item.residual === 0 ? 'color:#22C55E' : ''">
                {{ formatCurrency(item.residual) }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr style="background:#EFF6FF;font-weight:bold">
              <td>Итого</td>
              <td class="text-right">{{ formatCurrency(v.selectedVersionSnapshot.value.snapshot?.total_planned || 0) }}</td>
              <td class="text-right">{{ formatCurrency(v.selectedVersionSnapshot.value.snapshot?.total_used || 0) }}</td>
              <td class="text-right">{{ formatCurrency((v.selectedVersionSnapshot.value.snapshot?.total_planned || 0) - (v.selectedVersionSnapshot.value.snapshot?.total_used || 0)) }}</td>
            </tr>
          </tfoot>
        </v-table>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Снимок версии план-графика — вынесен из SubsidiesView.vue. Состояние/логика —
// в usePlanGraphVersions.ts (singleton, общий с остальными диалогами версий).
import { useDisplay } from 'vuetify'
import { formatCurrency } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'

const { mobile } = useDisplay()
const v = usePlanGraphVersions(useSubsidyDetailCtx())
</script>

<style scoped>
.snapshot-tree-table { width: 100%; border-collapse: collapse; }
.snapshot-tree-table th, .snapshot-tree-table td { padding: 6px 8px; border-bottom: 1px solid rgba(0,0,0,0.08); font-size: 13px; }
.snapshot-tree-table .level-1 td { font-weight: 600; background: rgba(33,150,243,0.06); }
.snapshot-tree-table .level-2 td { background: rgba(33,150,243,0.03); }
.snapshot-tree-table tfoot td { background: rgba(0,0,0,0.05); padding: 8px; border-top: 2px solid rgba(0,0,0,0.15); }
.snapshot-tree-table .status-orphan td:first-child { color: rgb(180,120,0); }
</style>
