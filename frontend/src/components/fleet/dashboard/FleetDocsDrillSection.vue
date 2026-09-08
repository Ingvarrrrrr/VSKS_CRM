<template>
  <section v-if="open" class="docs-drill-section">
    <div class="docs-drill-header">
      <h3 class="text-h6">Истекают документы (горизонт {{ horizon }} дней)</h3>
      <v-spacer />
      <v-select
        :model-value="horizon"
        :items="[7, 14, 30, 60, 90]"
        label="Дней"
        density="compact"
        style="max-width: 120px"
        hide-details
        @update:model-value="$emit('update:horizon', $event)"
      />
      <v-btn variant="text" size="small" @click="$emit('close')">Закрыть</v-btn>
    </div>

    <v-progress-linear v-if="loading" indeterminate />

    <div v-if="!loading" class="docs-drill-content">
      <!-- ТС секция -->
      <div class="docs-drill-block">
        <div class="docs-drill-block__title">
          <v-icon size="small">mdi-car</v-icon>
          Машины ({{ vehicles.length }})
        </div>
        <div v-if="!vehicles.length" class="text-grey">Нет ТС с истекающими документами</div>
        <div v-else class="docs-drill-rows">
          <router-link
            v-for="v in vehicles"
            :key="v.id"
            :to="`/property/vehicles/${v.id}`"
            class="docs-drill-row"
          >
            <div class="docs-drill-row__main">
              <div class="docs-drill-row__plate">{{ v.plate }}</div>
              <div class="docs-drill-row__name">{{ v.brand }} {{ v.model }}</div>
            </div>
            <div class="docs-drill-row__docs">
              <v-chip
                v-for="d in v.expiring_docs"
                :key="d.type"
                size="x-small"
                :color="d.days_left < 0 ? 'error' : d.days_left <= 7 ? 'warning' : 'default'"
                variant="tonal"
              >
                {{ d.label }}: {{ d.days_left < 0 ? `просрочен ${-d.days_left}д` : `${d.days_left}д` }}
              </v-chip>
            </div>
          </router-link>
        </div>
      </div>

      <!-- Водители секция -->
      <div class="docs-drill-block">
        <div class="docs-drill-block__title">
          <v-icon size="small">mdi-account</v-icon>
          Водители ({{ drivers.length }})
        </div>
        <div v-if="!drivers.length" class="text-grey">Нет водителей с истекающими документами</div>
        <div v-else class="docs-drill-rows">
          <div
            v-for="u in drivers"
            :key="u.id"
            class="docs-drill-row docs-drill-row--user"
          >
            <div class="docs-drill-row__main">
              <div class="docs-drill-row__plate">{{ u.full_name }}</div>
              <div class="docs-drill-row__name">{{ u.fleet_role || '—' }}</div>
            </div>
            <div class="docs-drill-row__docs">
              <v-chip
                v-for="d in u.expiring_docs"
                :key="d.type"
                size="x-small"
                :color="d.days_left < 0 ? 'error' : d.days_left <= 7 ? 'warning' : 'default'"
                variant="tonal"
              >
                {{ d.label }}: {{ d.days_left < 0 ? `просрочен ${-d.days_left}д` : `${d.days_left}д` }}
              </v-chip>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  open: boolean
  loading: boolean
  horizon: number
  vehicles: any[]
  drivers: any[]
}>()

defineEmits<{
  (e: 'update:horizon', value: number): void
  (e: 'close'): void
}>()
</script>

<style scoped></style>
