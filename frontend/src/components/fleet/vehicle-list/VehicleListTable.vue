<template>
  <!-- Bulk actions bar -->
  <div v-if="selected.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
    <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
    <span class="text-body-2 font-weight-medium">Выбрано: {{ selected.length }}</span>
    <v-spacer />
    <v-btn variant="text" size="small" @click="emit('update:selected', [])">Снять выделение</v-btn>
  </div>

  <v-data-table-server
    v-resizable-columns="'vehicle-list'"
    :headers="headers"
    :items="Array.isArray(items) ? items : []"
    :loading="loading"
    :items-length="total"
    item-value="id"
    density="compact"
    hover
    show-expand
    show-select
    :model-value="selected"
    :expanded="expanded"
    :page="page"
    :items-per-page="itemsPerPage"
    :items-per-page-options="[25, 50, 100]"
    return-object
    class="vlist-table__data-table"
    @update:model-value="emit('update:selected', $event)"
    @update:expanded="emit('update:expanded', $event)"
    @update:page="emit('update:page', $event)"
    @update:items-per-page="emit('update:itemsPerPage', $event)"
    @click:row="(event: Event, row: any) => emit('row-click', event, row)"
    @update:options="(opts: any) => emit('table-options', opts)"
  >
    <!-- ColumnHeaderMenu slots -->
    <template #header.plate="{ column }">
      <ColumnHeaderMenu col-key="plate" :title="column.title" col-type="text"
        :model-value="filtersState['plate'] ?? null"
        :sort-by="getSortBy('plate')"
        @update:model-value="v => emit('set-filter', 'plate', v)"
        @sort="dir => emit('sort', 'plate', dir)"
        @hide="emit('hide-column', 'plate')" />
    </template>
    <template #header.brand_model="{ column }">
      <ColumnHeaderMenu col-key="brand_model" :title="column.title" col-type="text"
        :model-value="filtersState['brand_model'] ?? null"
        :sort-by="getSortBy('brand_model')"
        @update:model-value="v => emit('set-filter', 'brand_model', v)"
        @sort="dir => emit('sort', 'brand_model', dir)"
        @hide="emit('hide-column', 'brand_model')" />
    </template>
    <template #header.type_label="{ column }">
      <ColumnHeaderMenu col-key="type_label" :title="column.title" col-type="enum"
        :items="typeOptions.map(o => o.value)"
        :item-labels="Object.fromEntries(typeOptions.map(o => [o.value, o.label]))"
        :model-value="filtersState['type_label'] ?? null"
        :sort-by="getSortBy('type_label')"
        @update:model-value="v => emit('set-filter', 'type_label', v)"
        @sort="dir => emit('sort', 'type_label', dir)"
        @hide="emit('hide-column', 'type_label')" />
    </template>
    <template #header.state_label="{ column }">
      <ColumnHeaderMenu col-key="state_label" :title="column.title" col-type="enum"
        :items="stateOptions.map(o => o.value)"
        :item-labels="Object.fromEntries(stateOptions.map(o => [o.value, o.label]))"
        :model-value="filtersState['state_label'] ?? null"
        :sort-by="getSortBy('state_label')"
        @update:model-value="v => emit('set-filter', 'state_label', v)"
        @sort="dir => emit('sort', 'state_label', dir)"
        @hide="emit('hide-column', 'state_label')" />
    </template>
    <template #header.owner_org_name="{ column }">
      <ColumnHeaderMenu col-key="owner_org_name" :title="column.title" col-type="text"
        :model-value="filtersState['owner_org_name'] ?? null"
        :sort-by="getSortBy('owner_org_name')"
        @update:model-value="v => emit('set-filter', 'owner_org_name', v)"
        @sort="dir => emit('sort', 'owner_org_name', dir)"
        @hide="emit('hide-column', 'owner_org_name')" />
    </template>
    <template #header.assigned_label="{ column }">
      <ColumnHeaderMenu col-key="assigned_label" :title="column.title" col-type="text"
        :model-value="filtersState['assigned_label'] ?? null"
        :sort-by="getSortBy('assigned_label')"
        @update:model-value="v => emit('set-filter', 'assigned_label', v)"
        @sort="dir => emit('sort', 'assigned_label', dir)"
        @hide="emit('hide-column', 'assigned_label')" />
    </template>
    <template #header.insurance_until="{ column }">
      <ColumnHeaderMenu col-key="insurance_until" :title="column.title" col-type="date"
        :model-value="filtersState['insurance_until'] ?? null"
        :sort-by="getSortBy('insurance_until')"
        @update:model-value="v => emit('set-filter', 'insurance_until', v)"
        @sort="dir => emit('sort', 'insurance_until', dir)"
        @hide="emit('hide-column', 'insurance_until')" />
    </template>

    <!-- item.data-table-expand: показываем expand для всех строк -->
    <template #item.data-table-expand="{ internalItem, isExpanded, toggleExpand }">
      <v-btn
        :icon="isExpanded(internalItem) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        variant="text"
        size="small"
        @click.stop="toggleExpand(internalItem)"
      />
    </template>

    <!-- plate column: визуальный номерной знак + подсветка истекающей страховки -->
    <template #item.plate="{ item }">
      <div class="d-flex align-center gap-1">
        <LicensePlate :model-value="item.plate" :readonly="true" size="sm" />
        <v-icon v-if="isInsuranceExpiring(item)" icon="mdi-alert-circle" size="x-small"
          color="warning" title="ОСАГО истекает менее чем через 30 дней" />
      </div>
    </template>

    <!-- brand_model computed cell -->
    <template #item.brand_model="{ item }">
      <span>{{ [item.brand, item.model].filter(Boolean).join(' ') || '—' }}</span>
      <div v-if="item.color" class="text-caption text-medium-emphasis">{{ item.color }}</div>
    </template>

    <!-- type_label -->
    <template #item.type_label="{ item }">
      <v-chip size="x-small" variant="tonal" :color="typeColor(item.type)">
        {{ typeLabel(item.type) }}
      </v-chip>
    </template>

    <!-- state_label -->
    <template #item.state_label="{ item }">
      <v-chip size="x-small" variant="tonal" :color="stateColor(item.state)">
        {{ stateLabel(item.state) }}
      </v-chip>
    </template>

    <!-- owner_org_name — 2026-09 (правка после ревью #2): полное юрлицо-название
         («ДОНЕЦКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ МОЛОДЕЖНОЙ
         ОРГАНИЗАЦИИ "...») раньше выводилось целиком и переносилось на 8 строк,
         раздувая высоту строки таблицы (242px вместо обычных ~40px). Короткой
         формы у организации в модели нет (нет short_name) — обрезаем визуально
         до 2 строк с многоточием, полное название — во всплывающей подсказке. -->
    <template #item.owner_org_name="{ item }">
      <v-tooltip :text="item.owner_org_name || '—'" location="top" :disabled="!item.owner_org_name">
        <template #activator="{ props: tip }">
          <span v-bind="tip" class="text-body-2 vlist-table__clamp-2">{{ item.owner_org_name || '—' }}</span>
        </template>
      </v-tooltip>
    </template>

    <!-- assigned_label: org name OR text — та же проблема раздувания строки -->
    <template #item.assigned_label="{ item }">
      <v-tooltip :text="item.assigned_org_name || item.assigned_text || '—'" location="top" :disabled="!(item.assigned_org_name || item.assigned_text)">
        <template #activator="{ props: tip }">
          <span v-bind="tip" class="text-body-2 vlist-table__clamp-2">{{ item.assigned_org_name || item.assigned_text || '—' }}</span>
        </template>
      </v-tooltip>
    </template>

    <!-- insurance_until with color warning -->
    <template #item.insurance_until="{ item }">
      <span :class="insuranceClass(item)">{{ formatDate(item.insurance_until) }}</span>
    </template>

    <!-- odometer -->
    <template #item.current_odometer_km="{ item }">
      <span>{{ item.current_odometer_km != null ? item.current_odometer_km.toLocaleString('ru-RU') : '—' }}</span>
    </template>

    <!-- fuel_type -->
    <template #item.fuel_type="{ item }">
      <span class="text-caption">{{ fuelTypeLabel(item.fuel_type) }}</span>
    </template>

    <!-- next_to_km with warning -->
    <template #item.next_to_km="{ item }">
      <span :class="nextToClass(item)">
        {{ item.next_to_km != null ? item.next_to_km.toLocaleString('ru-RU') : '—' }}
      </span>
    </template>

    <!-- actions: compare layouts button -->
    <template #item.actions="{ item }">
      <v-tooltip text="Сравнить layouts" location="top">
        <template #activator="{ props: tip }">
          <v-btn
            v-bind="tip"
            icon="mdi-compare"
            size="x-small"
            variant="text"
            :to="`/property/vehicles/${item.id}/preview`"
            @click.stop
          />
        </template>
      </v-tooltip>
    </template>

    <!-- Expanded row: краткие детали из props JSONB -->
    <template #expanded-row="{ columns, item }">
      <tr>
        <td :colspan="columns.length" class="pa-0 bg-grey-lighten-5">
          <div class="pa-4 d-flex flex-wrap gap-6">
            <div>
              <div class="text-caption text-medium-emphasis mb-1">VIN</div>
              <div class="text-body-2 font-weight-medium">{{ item.vin || '—' }}</div>
            </div>
            <div v-if="item.props?.branding">
              <div class="text-caption text-medium-emphasis mb-1">Брендирование</div>
              <div class="text-body-2">{{ item.props.branding }}</div>
            </div>
            <div v-if="item.props?.paint_condition">
              <div class="text-caption text-medium-emphasis mb-1">Лакокрасочное покрытие</div>
              <div class="text-body-2">{{ item.props.paint_condition }}</div>
            </div>
            <div v-if="item.props?.tires_type">
              <div class="text-caption text-medium-emphasis mb-1">Авторезина</div>
              <div class="text-body-2">{{ item.props.tires_type }}</div>
            </div>
            <div v-if="item.props?.defect_description">
              <div class="text-caption text-medium-emphasis mb-1">Неисправность</div>
              <div class="text-body-2 text-error">{{ item.props.defect_description }}</div>
            </div>
            <div v-if="item.props?.note">
              <div class="text-caption text-medium-emphasis mb-1">Примечание</div>
              <div class="text-body-2">{{ item.props.note }}</div>
            </div>
            <div class="d-flex align-end ml-auto">
              <v-btn size="small" variant="tonal" color="primary"
                :to="`/property/vehicles/${item.id}`"
                prepend-icon="mdi-open-in-new"
                @click.stop>
                Открыть карточку
              </v-btn>
            </div>
          </div>
        </td>
      </tr>
    </template>

    <template #no-data>
      <div class="text-center py-10">
        <v-icon icon="mdi-car-off" size="48" color="grey-lighten-1" class="mb-3" />
        <div class="text-medium-emphasis">ТС не найдены</div>
      </div>
    </template>
  </v-data-table-server>
</template>

<script setup lang="ts">
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { VehicleListItem } from '@/composables/fleet/vehicle-list/vehicleListTypes'
import {
  typeLabel, typeColor, stateLabel, stateColor, fuelTypeLabel,
  formatDate, isInsuranceExpiring, insuranceClass, nextToClass,
} from '@/composables/fleet/vehicle-list/vehicleListLookups'

defineProps<{
  headers: any[]
  items: VehicleListItem[]
  loading: boolean
  total: number
  selected: VehicleListItem[]
  expanded: VehicleListItem[]
  page: number
  itemsPerPage: number
  filtersState: Record<string, any>
  getSortBy: (key: string) => 'asc' | 'desc' | null
  typeOptions: { value: string; label: string }[]
  stateOptions: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  (e: 'update:selected', value: VehicleListItem[]): void
  (e: 'update:expanded', value: VehicleListItem[]): void
  (e: 'update:page', value: number): void
  (e: 'update:itemsPerPage', value: number): void
  (e: 'set-filter', key: string, value: any): void
  (e: 'sort', key: string, dir: 'asc' | 'desc' | null): void
  (e: 'hide-column', key: string): void
  (e: 'table-options', opts: { page: number; itemsPerPage: number; sortBy: any[] }): void
  (e: 'row-click', event: Event, row: { item: VehicleListItem }): void
}>()
</script>

<style scoped>
.vlist-table__data-table :deep(tbody tr) {
  cursor: pointer;
}

/* Владелец/Эксплуатант: полные юрлица-названия могут быть очень длинными
   ("ДОНЕЦКОЕ РЕГИОНАЛЬНОЕ ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ МОЛОДЕЖНОЙ
   ОРГАНИЗАЦИИ ...") — без ограничения строка таблицы раздувалась на весь экран.
   Зажимаем визуально до 2 строк с многоточием, полный текст — в v-tooltip. */
.vlist-table__clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.3;
  max-height: 2.6em;
}
</style>
