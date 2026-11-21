<template>
  <!-- Phase 23: диалог «Доступные переменные шаблонов».
       Владелец (14.10.2026): список переменных был захардкожен здесь отдельной
       копией и расходился с тем, что реально кладётся в контекст документа —
       единственный источник теперь TEMPLATE_VARIABLES на бэке (ПРАВИЛО №6),
       тот же справочник отдаёт GET /documents/template-vars и показывает
       SubsidyTemplatesDialog.vue. -->
  <v-dialog v-model="open" max-width="1150" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-code-braces" class="mr-2" />Доступные переменные шаблонов
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </v-card-title>
      <v-divider />
      <v-card-text style="max-height:75vh">
        <div class="d-flex flex-wrap align-center justify-space-between gap-2 mb-3">
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по переменной, описанию или примеру..."
            density="compact"
            hide-details
            clearable
            style="min-width: 320px; max-width: 500px;"
          />
          <v-chip-group v-model="sectionFilter" mandatory class="py-0">
            <v-chip value="all" size="small" filter variant="tonal">Все разделы</v-chip>
            <v-chip value="customer" size="small" filter variant="tonal" color="indigo">Заказчик</v-chip>
            <v-chip value="contractor" size="small" filter variant="tonal" color="teal">Подрядчик</v-chip>
          </v-chip-group>
        </div>
        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />
        <template v-for="grp in filteredGroups" :key="grp.title">
          <div v-if="grp.items.length" class="mb-5">
            <div class="d-flex align-center mb-2">
              <v-chip
                v-if="grp.title.toUpperCase().includes('ЗАКАЗЧИК') || grp.title.toUpperCase().includes('БУХГАЛТЕР')"
                size="small"
                color="indigo"
                variant="flat"
                class="mr-2 font-weight-bold"
              >
                Заказчик
              </v-chip>
              <v-chip
                v-else-if="grp.title.toUpperCase().includes('ПОДРЯДЧИК')"
                size="small"
                color="teal"
                variant="flat"
                class="mr-2 font-weight-bold"
              >
                Подрядчик
              </v-chip>
              <span class="text-subtitle-2 font-weight-bold" :style="{ color: groupColor(grp.title) }">
                {{ grp.title }}
              </span>
            </div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="width:320px; min-width:300px">Переменная (клик — скопировать)</th>
                  <th>Описание</th>
                  <th style="width:240px">Пример</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in grp.items" :key="item.var + idx">
                  <td
                    class="cursor-pointer"
                    style="white-space: nowrap"
                    title="Нажмите, чтобы скопировать {{переменную}}"
                    @click="copyVar(item.var)"
                  >
                    <code class="text-caption px-1 rounded font-weight-bold" style="background-color: rgba(98, 0, 234, 0.08); user-select: all;">
                      {{ item.var }}
                    </code>
                    <v-icon size="x-small" icon="mdi-content-copy" class="ml-1 text-medium-emphasis" />
                  </td>
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
import { useToast } from '@/composables/useToast'

interface TemplateVar { var: string; description: string; example_template: string; example_result: string }

const open = defineModel<boolean>({ default: false })
const { mobile } = useDisplay()
const toast = useToast()

const search = ref('')
const sectionFilter = ref<string>('all')
const loading = ref(false)
const rawVars = ref<TemplateVar[]>([])
let loaded = false

async function copyVar(text: string) {
  let ok = false
  try {
    if (window.isSecureContext && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      ok = true
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      ta.style.top = '0'
      ta.style.left = '0'
      document.body.appendChild(ta)
      ta.focus()
      ta.select()
      try { ok = document.execCommand('copy') } catch { ok = false }
      document.body.removeChild(ta)
    }
  } catch { ok = false }
  if (ok) toast.addToast(`Скопировано: ${text}`, 'success', { duration: 2500 })
  else toast.addToast(`Не удалось скопировать. Выделите и нажмите Ctrl+C: ${text}`, 'error')
}

function groupColor(title: string): string {
  const t = title.toUpperCase()
  if (t.includes('ЗАКАЗЧИК') || t.includes('БУХГАЛТЕР')) return '#3f51b5'
  if (t.includes('ПОДРЯДЧИК')) return '#00897b'
  return '#6200ea'
}

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

// Владелец (28.10.2026): поиск по названию РАЗДЕЛА тоже — «заказчик»/
// «подписант» должен находить раздел «Подписант Заказчика» целиком, даже
// если слово не повторено в описании каждой строки внутри него.
const filteredGroups = computed<Group[]>(() => {
  let base = groups.value

  if (sectionFilter.value === 'customer') {
    base = base.filter(g => {
      const t = g.title.toUpperCase()
      return t.includes('ЗАКАЗЧИК') || t.includes('БУХГАЛТЕР') ||
        g.items.some(i => i.var.toLowerCase().includes('customer'))
    })
  } else if (sectionFilter.value === 'contractor') {
    base = base.filter(g => {
      const t = g.title.toUpperCase()
      return t.includes('ПОДРЯДЧИК') ||
        g.items.some(i => i.var.toLowerCase().includes('contractor'))
    })
  }

  if (!search.value) return base
  const q = search.value.toLowerCase().trim()
  return base
    .map(g => {
      const titleMatches = g.title.toLowerCase().includes(q)
      return {
        title: g.title,
        items: titleMatches
          ? g.items
          : g.items.filter(v =>
              v.var.toLowerCase().includes(q) ||
              (v.description && v.description.toLowerCase().includes(q)) ||
              (v.example_template && v.example_template.toLowerCase().includes(q)) ||
              (v.example_result && v.example_result.toLowerCase().includes(q))
            ),
      }
    })
    .filter(g => g.items.length)
})
</script>
