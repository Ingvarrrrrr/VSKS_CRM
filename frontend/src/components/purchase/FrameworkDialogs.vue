<template>
  <!-- Framework contracts dialog -->
  <v-dialog v-model="frameworkOpen" max-width="860" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6 d-flex align-center justify-space-between">
        <span>Рамочные договоры</span>
        <v-btn color="primary" prepend-icon="mdi-plus" size="small"
          @click="newFrameworkOpen = true">
          Создать новый
        </v-btn>
      </v-card-title>
      <v-card-text class="px-6">
        <v-text-field v-model="frameworkSearch" prepend-inner-icon="mdi-magnify"
          label="Поиск по номеру, контрагенту, ИНН, предмету"
          variant="outlined" density="compact" clearable hide-details class="mb-4" />
        <v-progress-linear v-if="frameworkLoading" indeterminate color="primary" class="mb-3" />
        <div v-if="!frameworkLoading && !filteredFrameworkContracts.length" class="text-center text-medium-emphasis py-6">
          Рамочных договоров по данной субсидии не найдено
        </div>
        <v-table v-else density="compact">
          <thead>
            <tr>
              <th>Номер</th>
              <th>Дата</th>
              <th>Контрагент</th>
              <th>ИНН</th>
              <th>Предмет договора</th>
              <th>Макс. сумма</th>
              <th>Остаток</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filteredFrameworkContracts" :key="c.id"
              :class="{ 'bg-blue-lighten-5': selectedFrameworkContract?.id === c.id }"
              style="cursor:pointer" @click="$emit('select', c)">
              <td class="font-weight-medium">{{ c.number }}</td>
              <td>{{ c.date || '—' }}</td>
              <td>{{ c.contractor_name || '—' }}</td>
              <td class="text-caption">{{ c.contractor_inn || '—' }}</td>
              <td style="max-width:220px;white-space:normal;font-size:12px">{{ c.subject || '—' }}</td>
              <td class="text-right">{{ c.max_amount ? Number(c.max_amount).toLocaleString('ru-RU') + ' ₽' : '—' }}</td>
              <td class="text-right" :class="c.remaining_ordered != null && c.remaining_ordered < 0 ? 'text-error' : 'text-success'">
                {{ c.remaining_ordered != null ? Number(c.remaining_ordered).toLocaleString('ru-RU') + ' ₽' : '—' }}
              </td>
              <td>
                <v-btn variant="tonal" color="primary" size="x-small"
                  @click.stop="$emit('select', c)">Выбрать</v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="frameworkOpen = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- New framework contract dialog -->
  <v-dialog v-model="newFrameworkOpen" max-width="520" @after-enter="focusNewContractNumber" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Новый рамочный договор</v-card-title>
      <v-card-text class="px-6 pb-2">
        <v-text-field ref="newContractNumberRef" v-model="newFrameworkForm.number" label="Номер договора *" variant="outlined"
          density="compact" class="mb-3" />
        <v-text-field v-model="newFrameworkForm.date" label="Дата договора" variant="outlined"
          density="compact" type="date" class="mb-3" />
        <v-autocomplete v-model="newFrameworkForm.contractor_id"
          :items="contractors" item-title="name" item-value="id"
          label="Контрагент" variant="outlined" density="compact" clearable
          :custom-filter="contractorFilter" :no-data-text="contractorsNoDataText" class="mb-3">
          <template #item="{ item, props }">
            <v-list-item v-bind="props">
              <template #subtitle>
                <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
              </template>
            </v-list-item>
          </template>
        </v-autocomplete>
        <v-textarea v-model="newFrameworkForm.subject" label="Предмет договора" variant="outlined"
          density="compact" rows="2" auto-grow class="mb-3" />
        <v-text-field v-model.number="newFrameworkForm.max_amount" label="Максимальная сумма, ₽"
          variant="outlined" density="compact" type="number" />
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="newFrameworkOpen = false">Отмена</v-btn>
        <v-btn color="primary" :loading="newFrameworkSaving" @click="$emit('save-new')">Создать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useDisplay } from 'vuetify'

const frameworkOpen = defineModel<boolean>('frameworkOpen', { default: false })
const newFrameworkOpen = defineModel<boolean>('newFrameworkOpen', { default: false })
const frameworkSearch = defineModel<string>('frameworkSearch', { default: '' })

defineProps<{
  frameworkLoading: boolean
  filteredFrameworkContracts: any[]
  selectedFrameworkContract: { id: number } | null
  newFrameworkForm: { number: string; date: string; contractor_id: number | null; subject: string; max_amount: number | null }
  newFrameworkSaving: boolean
  contractors: { id: number; name: string; inn?: string }[]
  contractorFilter: (value: string, query: string, item?: any) => boolean
  contractorsNoDataText: string
}>()

defineEmits<{
  (e: 'select', c: any): void
  (e: 'save-new'): void
}>()

const { mobile } = useDisplay()

const newContractNumberRef = ref<any>(null)
function focusNewContractNumber() {
  nextTick(() => newContractNumberRef.value?.focus())
}
</script>
