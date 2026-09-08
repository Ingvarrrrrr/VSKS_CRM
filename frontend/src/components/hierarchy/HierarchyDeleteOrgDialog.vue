<template>
  <v-dialog v-model="show" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-domain-remove" color="error" class="mr-2" />
        Удалить организацию
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        Удалить организацию <strong>«{{ name }}»</strong>?

        <!-- Загрузка impact -->
        <div v-if="loadingImpact" class="d-flex align-center mt-3 ga-2">
          <v-progress-circular size="18" width="2" indeterminate color="warning" />
          <span class="text-caption text-medium-emphasis">Проверяем зависимости…</span>
        </div>

        <!-- Есть зависимости — предупреждение -->
        <template v-else-if="impact?.has_dependencies">
          <v-alert type="warning" variant="tonal" class="mt-3 mb-2" density="compact">
            В организации:
            сотрудников — <strong>{{ impact.employee_count }}</strong>,
            отделов — <strong>{{ impact.department_count }}</strong>,
            субсидий — <strong>{{ impact.subsidy_count }}</strong>.<br/>
            При удалении сотрудники потеряют привязку, субсидии и отделы будут удалены безвозвратно.
          </v-alert>

          <!-- Список затронутых сотрудников -->
          <v-expansion-panels v-if="impact.employees?.length" variant="accordion" class="mb-2">
            <v-expansion-panel>
              <v-expansion-panel-title class="text-body-2 py-2">
                Сотрудники, которые будут затронуты ({{ impact.employees.length }})
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-list density="compact" max-height="180" style="overflow-y:auto">
                  <v-list-item
                    v-for="emp in impact.employees"
                    :key="emp.id"
                    :title="emp.full_name || emp.username"
                    :subtitle="emp.role"
                    prepend-icon="mdi-account"
                    density="compact"
                  />
                </v-list>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>

          <v-checkbox
            v-model="forceAck"
            label="Понимаю последствия и хочу удалить организацию"
            color="error"
            density="compact"
            hide-details
            class="mt-1"
          />
        </template>

        <!-- Нет зависимостей -->
        <template v-else-if="!loadingImpact">
          <div class="text-caption text-medium-emphasis mt-2">
            Все отделы, сотрудники и связи будут удалены (CASCADE).
            Действие необратимо.
          </div>
        </template>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn
          v-if="impact?.has_dependencies"
          color="error"
          variant="flat"
          :loading="loading"
          :disabled="!forceAck"
          @click="emit('confirm')"
        >Всё равно удалить</v-btn>
        <v-btn
          v-else
          color="error"
          variant="flat"
          :loading="loading"
          :disabled="loadingImpact"
          @click="emit('confirm')"
        >Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  name: string
  loading: boolean
  loadingImpact: boolean
  impact: any | null
}>()
const emit = defineEmits<{ confirm: [] }>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
const forceAck = defineModel<boolean>('forceAck', { default: false })
</script>
