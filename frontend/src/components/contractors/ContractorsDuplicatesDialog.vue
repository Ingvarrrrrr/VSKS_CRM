<template>
  <v-dialog :model-value="modelValue" max-width="900" scrollable :fullscreen="mobile" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-content-duplicate" color="warning" class="mr-2" />
        Дубликаты контрагентов по ИНН
        <v-chip size="small" class="ml-2" v-if="data">
          {{ data.total_groups }} групп / {{ data.total_extra }} лишних строк
        </v-chip>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="pa-4">
        <v-progress-circular v-if="loading" indeterminate color="warning" class="d-block mx-auto my-6" />
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact">
          {{ error }}
        </v-alert>
        <v-alert v-else-if="data && data.groups.length === 0" type="success" variant="tonal" density="compact">
          Дубликатов по ИНН не найдено
        </v-alert>
        <div v-else-if="data">
          <v-expansion-panels variant="accordion" multiple>
            <v-expansion-panel v-for="group in data.groups" :key="group.inn">
              <v-expansion-panel-title>
                <div class="d-flex align-center" style="width:100%">
                  <v-chip color="warning" size="small" class="mr-2">ИНН {{ group.inn }}</v-chip>
                  <span>{{ group.count }} записей</span>
                </div>
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Краткое</th>
                      <th>Полное</th>
                      <th>КПП</th>
                      <th>Адрес</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="c in group.contractors" :key="c.id">
                      <td>{{ c.id }}</td>
                      <td>{{ c.name }}</td>
                      <td class="text-caption">{{ c.full_name }}</td>
                      <td>{{ c.kpp }}</td>
                      <td class="text-caption">{{ c.address }}</td>
                      <td>
                        <v-btn size="x-small" variant="text" color="primary"
                               prepend-icon="mdi-open-in-new"
                               @click="$emit('open-contractor', c.id)">
                          Открыть
                        </v-btn>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { DuplicatesData } from '@/composables/contractors/useContractorsDuplicates'

defineProps<{
  modelValue: boolean
  loading: boolean
  error: string
  data: DuplicatesData | null
  mobile: boolean
}>()
defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'open-contractor', id: number): void
}>()
</script>
