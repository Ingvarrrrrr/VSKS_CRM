<template>
  <v-row v-if="loading" class="kpi-row" style="margin:0">
    <v-col cols="6" sm="4" lg="3" xl="auto" style="flex:1" v-for="n in 9" :key="'skel-'+n">
      <v-skeleton-loader type="card" height="100" class="rounded-lg" />
    </v-col>
  </v-row>
  <v-row v-else class="kpi-row" style="margin:0">
    <v-col cols="6" sm="4" lg="3" xl="auto" style="flex:1" v-for="card in kpiCards" :key="card.key">
      <v-tooltip :text="card.tooltip ?? undefined" location="bottom" :disabled="!card.tooltip">
        <template #activator="{ props: tip }">
          <div v-bind="tip" class="kpi-card" :class="['kpi-' + card.key, { 'kpi-over': card.over }]" @click="$emit('kpi-click', card.key)">
            <div class="kpi-icon-box">
              <v-icon :icon="card.icon" size="26" />
            </div>
            <div class="kpi-body">
              <div class="kpi-value">{{ mobile ? formatCurrencyShort(card.amount) : formatCurrency(card.amount) }}</div>
              <div class="kpi-label">{{ card.label }}</div>
              <div class="kpi-count" v-if="card.count > 0">{{ card.count }} {{ card.countLabel }}</div>
              <div class="kpi-monthly" v-if="card.monthly !== null">
                в т.ч. ежемесячные платежи: {{ formatCurrencyShort(card.monthly!) }} /мес
              </div>
            </div>
          </div>
        </template>
      </v-tooltip>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
defineProps<{
  loading: boolean
  mobile: boolean
  kpiCards: any[]
  formatCurrency: (v: number) => string
  formatCurrencyShort: (v: number) => string
}>()

defineEmits<{
  (e: 'kpi-click', key: string): void
}>()
</script>
