<template>
  <v-container fluid class="pa-3">
    <div class="d-flex align-center mb-3">
      <v-icon size="32" class="mr-2">mdi-view-dashboard</v-icon>
      <h2 class="text-h5">{{ configName || 'Новый дашборд' }}</h2>
      <v-chip v-if="configId" size="small" color="primary" class="ml-3">{{ configId }}</v-chip>
      <v-spacer />
      <v-btn-toggle v-model="editMode" mandatory density="compact" class="mr-2">
        <v-btn :value="false" size="small">Просмотр</v-btn>
        <v-btn :value="true" size="small">Редактировать</v-btn>
      </v-btn-toggle>
      <v-btn color="primary" prepend-icon="mdi-plus" v-if="editMode" @click="openAddWidget" class="mr-2">Виджет</v-btn>
      <v-btn color="success" prepend-icon="mdi-file-excel" @click="exportExcel" class="mr-2" :disabled="!widgets.length">Excel</v-btn>
      <v-btn color="primary" prepend-icon="mdi-content-save" @click="saveDialog = true">Сохранить</v-btn>
    </div>

    <!-- Парам-форма (если есть) -->
    <v-card v-if="parameters.length" class="pa-3 mb-3">
      <div class="d-flex align-center mb-2">
        <v-icon size="20" class="mr-1">mdi-tune</v-icon>
        <strong>Параметры</strong>
      </div>
      <v-row dense>
        <v-col cols="3" v-for="p in parameters" :key="p.key">
          <v-autocomplete
            v-if="p.type === 'subsidy_select'"
            v-model="paramValues[p.key]"
            :items="subsidies"
            item-title="name"
            item-value="id"
            :label="p.label"
            density="compact"
            hide-details
            multiple
            chips
            closable-chips
          />
          <v-text-field
            v-else
            v-model="paramValues[p.key]"
            :label="p.label"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
    </v-card>

    <!-- Grid -->
    <grid-layout
      v-model:layout="layout"
      :col-num="12"
      :row-height="40"
      :is-draggable="editMode"
      :is-resizable="editMode"
      :margin="[8, 8]"
      :vertical-compact="true"
      :use-css-transforms="true"
    >
      <grid-item
        v-for="w in widgets"
        :key="w.i"
        :x="w.x" :y="w.y" :w="w.w" :h="w.h" :i="w.i"
        :min-w="2" :min-h="3"
      >
        <v-card style="height: 100%; overflow: hidden">
          <WidgetRenderer
            :widget="w"
            :edit-mode="editMode"
            :parameters="paramValues"
            @edit="editWidget(w)"
            @remove="removeWidget(w.i)"
          />
        </v-card>
      </grid-item>
    </grid-layout>

    <div v-if="!widgets.length" class="text-center text-grey pa-8">
      Дашборд пуст. Включите режим «Редактировать» и нажмите «Виджет».
    </div>

    <!-- Add/edit widget dialog -->
    <v-dialog v-model="widgetDialog" max-width="600">
      <v-card>
        <v-card-title>{{ editingWidget?.i ? 'Изменить' : 'Добавить' }} виджет</v-card-title>
        <v-card-text>
          <v-text-field v-model="widgetForm.title" label="Заголовок" autofocus />
          <v-select
            v-model="widgetForm.source_config_id"
            :items="sourceConfigs"
            item-title="display_name"
            item-value="id"
            label="Источник данных (сохранённый шаблон)"
            :hint="sourceHint"
            persistent-hint
          />
          <v-select
            v-model="widgetForm.viz_type"
            :items="vizOptions"
            item-title="title"
            item-value="value"
            label="Тип визуализации"
          />
          <v-text-field
            v-if="widgetForm.viz_type === 'kpi'"
            v-model="widgetForm.kpi_field"
            label="Поле для KPI (ключ measure)"
            hint="Например: sum_planned_total_price"
          />
          <v-row v-if="['bar', 'line', 'pie', 'donut', 'area'].includes(widgetForm.viz_type)">
            <v-col cols="6">
              <v-text-field v-model="widgetForm.dimension_key" label="Поле X (опц.)" hint="auto" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="widgetForm.measure_key" label="Поле Y (опц.)" hint="auto" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="widgetDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveWidget">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Save dashboard dialog -->
    <v-dialog v-model="saveDialog" max-width="500">
      <v-card>
        <v-card-title>Сохранить дашборд</v-card-title>
        <v-card-text>
          <v-text-field v-model="configName" label="Название" autofocus />
          <v-textarea v-model="configDescription" label="Описание" rows="2" />
          <v-checkbox v-model="isShared" label="Доступно всем в организации" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="saveDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveConfig">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import WidgetRenderer from '@/components/WidgetRenderer.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const configId = ref<number | null>(null)
const configName = ref('')
const configDescription = ref('')
const isShared = ref(true)
const editMode = ref(true)
const saveDialog = ref(false)

const widgets = ref<any[]>([])
const layout = computed({
  get: () => widgets.value.map((w) => ({ x: w.x, y: w.y, w: w.w, h: w.h, i: w.i })),
  set: (newLayout) => {
    for (const item of newLayout) {
      const widget = widgets.value.find((w) => w.i === item.i)
      if (widget) {
        widget.x = item.x; widget.y = item.y; widget.w = item.w; widget.h = item.h
      }
    }
  },
})

const widgetDialog = ref(false)
const editingWidget = ref<any>(null)
const widgetForm = reactive<any>({
  title: '',
  source_config_id: null,
  viz_type: 'bar',
  kpi_field: '',
  dimension_key: '',
  measure_key: '',
})

const sourceConfigs = ref<any[]>([])
const subsidies = ref<any[]>([])
const parameters = ref<any[]>([])
const paramValues = ref<Record<string, any>>({})

const vizOptions = [
  { value: 'kpi', title: 'KPI' },
  { value: 'bar', title: 'Бар-чарт' },
  { value: 'line', title: 'Линия' },
  { value: 'area', title: 'Area' },
  { value: 'pie', title: 'Pie' },
  { value: 'donut', title: 'Donut' },
  { value: 'table', title: 'Таблица' },
]

const sourceHint = computed(() => {
  const s = sourceConfigs.value.find((c) => c.id === widgetForm.source_config_id)
  return s ? `${s.kind}: ${s.name}` : ''
})

function openAddWidget() {
  editingWidget.value = null
  Object.assign(widgetForm, {
    title: 'Новый виджет', source_config_id: null, viz_type: 'bar', kpi_field: '',
    dimension_key: '', measure_key: '',
  })
  widgetDialog.value = true
}
function editWidget(w: any) {
  editingWidget.value = w
  Object.assign(widgetForm, {
    title: w.title, source_config_id: w.source_config_id, viz_type: w.viz_type,
    kpi_field: w.kpi_field || '', dimension_key: w.dimension_key || '', measure_key: w.measure_key || '',
  })
  widgetDialog.value = true
}
function saveWidget() {
  if (!widgetForm.source_config_id) {
    toast.warning('Выберите источник')
    return
  }
  if (editingWidget.value) {
    Object.assign(editingWidget.value, widgetForm)
  } else {
    const nextI = widgets.value.length ? String(Math.max(...widgets.value.map((w) => Number(w.i) || 0)) + 1) : '1'
    widgets.value.push({
      i: nextI,
      x: (widgets.value.length * 4) % 12,
      y: Math.floor(widgets.value.length / 3) * 6,
      w: 4,
      h: 6,
      ...JSON.parse(JSON.stringify(widgetForm)),
    })
  }
  widgetDialog.value = false
}
function removeWidget(i: string) {
  const idx = widgets.value.findIndex((w) => w.i === i)
  if (idx >= 0) widgets.value.splice(idx, 1)
}

async function exportExcel() {
  try {
    const token = localStorage.getItem('auth_token')
    const resp = await fetch('/api/analytics/export.xlsx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        config: { kind: 'dashboard', widgets: widgets.value, parameters: parameters.value },
        name: configName.value || 'Дашборд',
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${configName.value || 'Дашборд'}_${new Date().toISOString().slice(0, 10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Excel выгружен')
  } catch (e: any) {
    toast.error('Excel: ' + (e?.message || e))
  }
}

async function saveConfig() {
  if (!configName.value.trim()) {
    toast.warning('Введите название')
    return
  }
  const body = {
    kind: 'dashboard',
    name: configName.value,
    description: configDescription.value || null,
    config_json: {
      widgets: widgets.value,
      parameters: parameters.value,
    },
    parameters_json: parameters.value,
    is_shared: isShared.value,
  }
  try {
    if (configId.value) {
      await apiFetch(`/api/report-configs/${configId.value}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: configName.value,
          description: body.description,
          config_json: body.config_json,
          parameters_json: body.parameters_json,
          is_shared: body.is_shared,
        }),
      })
      toast.success('Обновлено')
    } else {
      const created = await apiFetch<any>('/api/report-configs/', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      configId.value = created.id
      router.replace(`/dashboards/${created.id}/edit`)
      toast.success('Сохранено')
    }
    saveDialog.value = false
  } catch (e: any) {
    toast.error('Ошибка: ' + (e?.message || e))
  }
}

onMounted(async () => {
  try {
    const [list, pivots, subs] = await Promise.all([
      apiFetch<any>('/api/report-configs/?kind=list'),
      apiFetch<any>('/api/report-configs/?kind=pivot'),
      apiFetch<any>('/api/subsidies/'),
    ])
    const allConfigs = [
      ...(Array.isArray(list) ? list : []).map((c: any) => ({ ...c, display_name: `[Реестр] ${c.name}` })),
      ...(Array.isArray(pivots) ? pivots : []).map((c: any) => ({ ...c, display_name: `[Сводная] ${c.name}` })),
    ]
    sourceConfigs.value = allConfigs
    subsidies.value = Array.isArray(subs) ? subs : subs.items || []

    const idParam = route.params.id
    if (idParam) {
      const cfg = await apiFetch<any>(`/api/report-configs/${idParam}`)
      configId.value = cfg.id
      configName.value = cfg.name
      configDescription.value = cfg.description || ''
      isShared.value = cfg.is_shared
      widgets.value = cfg.config_json?.widgets || []
      parameters.value = cfg.parameters_json || []
      editMode.value = false
    }
  } catch (e: any) {
    toast.error('Load: ' + (e?.message || e))
  }
})
</script>
