<template>
  <!-- Phase 23: диалог «Доступные переменные шаблонов».
       Владелец (14.10.2026): список переменных был захардкожен здесь отдельной
       копией и расходился с тем, что реально кладётся в контекст документа —
       единственный источник теперь TEMPLATE_VARIABLES на бэке (ПРАВИЛО №6),
       тот же справочник отдаёт GET /documents/template-vars и показывает
       SubsidyTemplatesDialog.vue. -->
  <v-dialog v-model="open" max-width="960" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-code-braces" class="mr-2" />Доступные переменные шаблонов
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>
      <v-divider />
      <v-card-text style="max-height:70vh">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          label="Поиск по переменной или описанию..."
          density="compact"
          hide-details
          clearable
          class="mb-3"
        />
        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />
        <template v-for="grp in filteredGroups" :key="grp.title">
          <div v-if="grp.items.length" class="mb-5">
            <div class="text-subtitle-2 font-weight-bold mb-2" style="color:#6200ea">{{ grp.title }}</div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="width:260px">Переменная</th>
                  <th>Описание</th>
                  <th style="width:220px">Пример</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in grp.items" :key="item.var + idx">
                  <td><code style="font-size:11px">{{ item.var }}</code></td>
                  <td class="text-body-2">{{ item.description }}</td>
                  <td class="text-caption text-medium-emphasis">{{ item.example_result || item.example_template }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </template>
        <v-alert v-if="!loading && !filteredGroups.some(g => g.items.length)" type="info" variant="tonal" density="compact">
          Ничего не найдено по запросу «{{ search }}»
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn @click="open = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

interface TemplateVar { var: string; description: string; example_template: string; example_result: string }

const open = defineModel<boolean>({ default: false })
const { mobile } = useDisplay()

const search = ref('')
const loading = ref(false)
const rawVars = ref<TemplateVar[]>([])
let loaded = false

async function loadTemplateVars() {
  loading.value = true
  try {
    rawVars.value = await apiFetch<TemplateVar[]>('/documents/template-vars')
    loaded = true
  } catch (e) {
    console.error('PlaceholdersDialog: loadTemplateVars failed', e)
    loaded = false
  } finally {
    loading.value = false
  }
}

// Диалог открывают и программным v-model (родитель), и через Vuetify —
// @update:model-value на программное открытие не срабатывает (14.10.2026),
// поэтому грузим по факту открытия, однократно, с повтором при ошибке.
watch(open, (val) => {
  if (val && !loaded) loadTemplateVars()
}, { immediate: true })

// Группы — строки-заголовки из справочника (var === '', description = заголовок
// группы), как и в backend/app/services/documents/template_variables.py.
interface Group { title: string; items: TemplateVar[] }

const groups = computed<Group[]>(() => {
  const result: Group[] = []
  let current: Group = { title: 'Общие', items: [] }
  for (const v of rawVars.value) {
    if (!v.var) {
      if (v.description) {
        if (current.items.length || result.length === 0) result.push(current)
        current = { title: v.description, items: [] }
      }
      continue
    }
    current.items.push(v)
  }
  result.push(current)
  return result.filter(g => g.items.length)
})

const filteredGroups = computed<Group[]>(() => {
  if (!search.value) return groups.value
  const q = search.value.toLowerCase()
  return groups.value
    .map(g => ({
      title: g.title,
      items: g.items.filter(v =>
        v.var.toLowerCase().includes(q) ||
        v.description.toLowerCase().includes(q) ||
        v.example_template.toLowerCase().includes(q)
      ),
    }))
    .filter(g => g.items.length)
})
</script>
