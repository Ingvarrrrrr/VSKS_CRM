<template>
  <div>
    <!-- Organization cards grid -->
    <div v-if="orgCardsOpen && orgSummary.length > 1" class="mb-6">
      <div class="text-subtitle-1 font-weight-medium mb-3">Выберите организацию</div>
      <div class="org-cards-grid">
        <div
          v-for="org in visibleOrgSummary"
          :key="org.org_id ?? 'all'"
          class="org-sel-card"
          :class="{ 'org-sel-card--all': org.org_id === null }"
          @click="$emit('select-org', org.org_id)"
        >
          <div class="osc-icon-box">
            <v-icon :icon="org.org_id === null ? 'mdi-domain-plus' : 'mdi-domain'" size="22" />
          </div>
          <div class="osc-body">
            <div class="osc-name">{{ org.org_name }}</div>
            <div class="osc-stats">
              <span class="osc-stat-clickable" @click.stop="$emit('click-stat', { orgId: org.org_id, tab: 'general' })">
                <v-icon size="12" class="mr-1">mdi-clipboard-check</v-icon>{{ org.task_count }} <span class="osc-stat-label">задач</span>
              </span>
              <span class="osc-stat-clickable" @click.stop="$emit('click-stat', { orgId: org.org_id, tab: 'purchases' })">
                <v-icon size="12" class="mr-1">mdi-cart</v-icon>{{ org.purchase_count }} <span class="osc-stat-label">закупок</span>
              </span>
            </div>
          </div>
          <div v-if="org.unseen_count > 0" class="osc-badge">{{ org.unseen_count }}</div>
        </div>
      </div>
    </div>

    <!-- Back to org selection button -->
    <v-btn
      v-if="orgSummary.length > 1 && !orgCardsOpen"
      variant="text"
      size="small"
      color="primary"
      prepend-icon="mdi-arrow-left"
      class="mb-3"
      @click="$emit('update:orgCardsOpen', true)"
    >
      К выбору организации
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface OrgSummaryItem {
  org_id: number | null
  org_name: string
  task_count: number
  purchase_count: number
  unseen_count: number
}

interface Props {
  orgSummary: OrgSummaryItem[]
  selectedOrgId: number | null
  orgCardsOpen: boolean
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'select-org', orgId: number | null): void
  (e: 'update:orgCardsOpen', value: boolean): void
  (e: 'click-stat', payload: { orgId: number | null; tab: 'general' | 'purchases' }): void
}>()

// Keep the "Все организации" aggregator even when empty, and show any org
// where the user has either tasks OR purchases.
const visibleOrgSummary = computed(() =>
  props.orgSummary.filter(o => o.org_id === null || o.task_count > 0 || o.purchase_count > 0)
)
</script>

<style scoped>
.org-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.org-sel-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border-radius: 12px;
  border: 1.5px solid rgba(0,0,0,0.12);
  background: #fff;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
  min-height: 88px;
}
.org-sel-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0,0,0,0.12);
  border-color: #2563EB;
}
.org-sel-card--all {
  border-color: #2563EB;
  background: #EFF6FF;
}
.osc-icon-box {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: #EFF6FF;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #2563EB;
}
.org-sel-card--all .osc-icon-box {
  background: #2563EB;
  color: #fff;
}
.osc-body {
  flex: 1;
  min-width: 0;
}
.osc-name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #1e293b;
}
.osc-stats {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 14px;
  font-weight: 700;
  color: #334155;
}
.osc-stat-label {
  font-size: 13px;
  font-weight: 600;
  opacity: 0.9;
}
.osc-stat-clickable {
  cursor: pointer;
  border-radius: 4px;
  padding: 1px 4px;
  transition: background 0.15s;
}
.osc-stat-clickable:hover {
  background: rgba(99, 102, 241, 0.12);
  color: #4f46e5;
}
.osc-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 10px;
  background: #F59E0B;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
