<template>
  <div>
    <!-- Status filter chips (накопительные — см. wish_tab_statuses на бэке) -->
    <div class="d-flex flex-wrap ga-2 mb-4">
      <v-chip
        v-for="f in allFilters"
        :key="f.value"
        :color="allFilter === f.value ? 'primary' : undefined"
        :variant="allFilter === f.value ? 'flat' : 'outlined'"
        size="small"
        @click="$emit('filter-change', f.value)"
      >
        {{ f.label }}<template v-if="wishCounts[f.value] !== undefined"> ({{ wishCounts[f.value] }})</template>
      </v-chip>
    </div>
    <div v-if="allWishesTruncated" class="text-caption text-medium-emphasis mb-4">
      Показаны первые {{ items.length }} из {{ allWishesTruncated }} — уточните фильтры, чтобы увидеть остальные
    </div>

    <v-data-table
      v-resizable-columns="'wishes-all'"
      :headers="headers"
      :items="items"
      :loading="loading"
      density="compact"
      hover
      items-per-page="25"
      :items-per-page-options="[25, 50, 100, -1]"
      @click:row="(_: any, { item }: any) => $emit('open-edit', item)"
    >
      <!-- B7: column header menus -->
      <template #header.status="{ column }">
        <ColumnHeaderMenu col-key="status" :title="column.title || ''" col-type="enum"
          :items="Object.keys(statusLabel)"
          :item-labels="statusLabel"
          :model-value="colFilters.status"
          :sort-by="colSort.status"
          @update:model-value="v => colFilters.status = v"
          @sort="dir => colSort.status = dir" />
      </template>
      <template #header.title_col="{ column }">
        <ColumnHeaderMenu col-key="title_col" :title="column.title || ''" col-type="text"
          :model-value="colFilters.title_col"
          :sort-by="colSort.title_col"
          @update:model-value="v => colFilters.title_col = v"
          @sort="dir => colSort.title_col = dir" />
      </template>
      <template #header.creator_name="{ column }">
        <ColumnHeaderMenu col-key="creator_name" :title="column.title || ''" col-type="text"
          :model-value="colFilters.creator_name"
          :sort-by="colSort.creator_name"
          @update:model-value="v => colFilters.creator_name = v"
          @sort="dir => colSort.creator_name = dir" />
      </template>
      <template #header.approver_names="{ column }">
        <ColumnHeaderMenu col-key="approver_names" :title="column.title || ''" col-type="text"
          :model-value="colFilters.approver_names"
          :sort-by="colSort.approver_names"
          @update:model-value="v => colFilters.approver_names = v"
          @sort="dir => colSort.approver_names = dir" />
      </template>
      <template #header.created_at="{ column }">
        <ColumnHeaderMenu col-key="created_at" :title="column.title || ''" col-type="date"
          :model-value="colFilters.created_at"
          :sort-by="colSort.created_at"
          @update:model-value="v => colFilters.created_at = v"
          @sort="dir => colSort.created_at = dir" />
      </template>
      <template #header.desired_date="{ column }">
        <ColumnHeaderMenu col-key="desired_date" :title="column.title || ''" col-type="date"
          :model-value="colFilters.desired_date"
          :sort-by="colSort.desired_date"
          @update:model-value="v => colFilters.desired_date = v"
          @sort="dir => colSort.desired_date = dir" />
      </template>
      <template #header.executor_name="{ column }">
        <ColumnHeaderMenu col-key="executor_name" :title="column.title || ''" col-type="text"
          :model-value="colFilters.executor_name"
          :sort-by="colSort.executor_name"
          @update:model-value="v => colFilters.executor_name = v"
          @sort="dir => colSort.executor_name = dir" />
      </template>
      <template #header.execution_deadline="{ column }">
        <ColumnHeaderMenu col-key="execution_deadline" :title="column.title || ''" col-type="date"
          :model-value="colFilters.execution_deadline"
          :sort-by="colSort.execution_deadline"
          @update:model-value="v => colFilters.execution_deadline = v"
          @sort="dir => colSort.execution_deadline = dir" />
      </template>
      <template #item.status="{ item }">
        <v-chip
          :color="statusColor[item.status]"
          size="small"
          variant="tonal"
          :title="item.status === 'rejected' ? rejectedByLine(item) : undefined"
        >
          {{ statusLabel[item.status] }}
        </v-chip>
      </template>
      <template #item.title_col="{ item }">
        <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт на всю строку -->
        <div v-if="item.stopped_at" class="wish-stopped-banner">
          <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
          <span class="wish-stopped-banner__title">{{ item.stopped_partial ? 'ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</span>
          <span class="wish-stopped-banner__meta">{{ stoppedByLine(item) }}</span>
        </div>
        <div class="d-flex align-center flex-wrap" style="gap:6px">
          <span class="font-weight-medium">{{ item.title }}</span>
          <!-- Phase 31-06: badge for unseen changes -->
          <v-chip
            v-if="(item.unseen_changes_count ?? 0) > 0"
            size="x-small"
            variant="tonal"
            :color="GALA_ORANGE"
            :title="`${item.unseen_changes_count} чужих правок с последнего просмотра`"
          >+{{ item.unseen_changes_count }}</v-chip>
        </div>
        <div class="text-caption text-medium-emphasis">
          <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
        </div>
      </template>
      <template #item.creator_name="{ item }">
        <span class="font-weight-medium">{{ shortName(item.creator_name) || '—' }}</span><span
          v-if="wishCoAuthors(item).length" class="text-medium-emphasis">, {{ wishCoAuthors(item).join(', ') }}</span>
      </template>
      <template #item.approver_names="{ item }">
        <span v-if="wishRecipients(item)">{{ wishRecipients(item) }}</span>
        <span v-else class="text-medium-emphasis">—</span>
      </template>
      <template #item.event_name="{ item }">
        {{ item.event_name || '—' }}
      </template>
      <template #header.event_name="{ column }">
        <ColumnHeaderMenu col-key="event_name" :title="column.title || ''" col-type="text"
          :model-value="colFilters.event_name"
          :sort-by="colSort.event_name"
          @update:model-value="v => colFilters.event_name = v"
          @sort="dir => colSort.event_name = dir" />
      </template>
      <!-- Владелец, 2026-09-02: колонка «Субсидия» — subsidy_name уже приходит в WishOut -->
      <template #item.subsidy_name="{ item }">
        {{ (item as any).subsidy_name || '—' }}
      </template>
      <template #header.subsidy_name="{ column }">
        <ColumnHeaderMenu col-key="subsidy_name" :title="column.title || ''" col-type="enum"
          :items="subsidyNameOptions"
          :model-value="colFilters.subsidy_name"
          :sort-by="colSort.subsidy_name"
          @update:model-value="v => colFilters.subsidy_name = v"
          @sort="dir => colSort.subsidy_name = dir" />
      </template>
      <!-- Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) -->
      <template #item.wish_total="{ item }">
        {{ wishItemsTotal(item) != null ? formatPrice(wishItemsTotal(item)!) : '—' }}
      </template>
      <template #header.wish_total="{ column }">
        <ColumnHeaderMenu col-key="wish_total" :title="column.title || ''" col-type="number"
          align="end"
          :model-value="colFilters.wish_total"
          :sort-by="colSort.wish_total"
          @update:model-value="v => colFilters.wish_total = v"
          @sort="dir => colSort.wish_total = dir" />
      </template>
      <template #item.created_at="{ item }">
        {{ formatDate(item.created_at) }}
      </template>
      <template #item.desired_date="{ item }">
        {{ item.desired_date ? formatDate(item.desired_date) : '—' }}
      </template>
      <template #item.executor_name="{ item }">
        {{ item.executor_name || '—' }}
      </template>
      <template #item.execution_deadline="{ item }">
        {{ item.execution_deadline ? formatDate(item.execution_deadline) : '—' }}
      </template>
      <template #item.actions="{ item }">
        <div class="d-flex align-center" style="gap:4px" @click.stop>
          <v-menu>
            <template #activator="{ props: menuProps }">
              <v-btn v-bind="menuProps" icon="mdi-microsoft-excel" size="x-small" variant="text" color="green-darken-1" :loading="downloadingExcelId === item.id" title="Скачать в Excel" @click.stop />
            </template>
            <v-list density="compact">
              <v-list-item prepend-icon="mdi-image" title="С фото" @click="$emit('download-excel', item, true)" />
              <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="$emit('download-excel', item, false)" />
            </v-list>
          </v-menu>
          <template v-if="item.status === 'submitted'">
            <v-btn size="x-small" variant="tonal" color="primary" @click="$emit('kanban', item)">
              Распределить
            </v-btn>
            <v-btn size="x-small" variant="tonal" color="success" :loading="approvingId === item.id" @click="$emit('approve', item)">
              Одобрить
            </v-btn>
            <v-btn size="x-small" variant="tonal" color="error" @click="$emit('reject', item)">
              Отклонить
            </v-btn>
          </template>
          <v-btn
            v-if="item.status === 'approved' && ctx.isManagerOrAdmin.value"
            size="x-small"
            variant="flat"
            color="primary"
            @click="$emit('convert', item)"
          >
            Закупку
          </v-btn>
          <v-menu v-if="item.status === 'converted' && item.purchase_id && (item.purchases?.length || 0) > 1">
            <template #activator="{ props: menuProps }">
              <v-btn v-bind="menuProps" size="x-small" variant="tonal" color="purple">
                {{ wishPurchasesLabel(item) }}
              </v-btn>
            </template>
            <v-list density="compact">
              <v-list-item v-for="p in item.purchases" :key="p.id" @click="ctx.goToPurchase(p.id)">
                <v-list-item-title>
                  {{ purchaseMenuLabel(p) }}
                  <v-chip v-if="p.stopped_at" size="x-small" color="error" variant="tonal" class="ml-1">остановлена</v-chip>
                </v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
          <v-btn
            v-else-if="item.status === 'converted' && item.purchase_id"
            size="x-small"
            variant="tonal"
            color="purple"
            @click="ctx.goToWishPurchases(item)"
          >
            {{ wishPurchasesLabel(item) }}
          </v-btn>
        </div>
      </template>
      <template #no-data>
        <div class="text-center py-10">
          <v-icon icon="mdi-hand-heart-outline" size="48" color="grey-lighten-1" class="mb-3" />
          <div class="text-medium-emphasis">Нет заявок от подчинённых</div>
        </div>
      </template>
    </v-data-table>
  </div>
</template>

<script setup lang="ts">
// WishAllTab.vue — вкладка «Заявки сотрудников» (менеджер/админ). Дословный перенос
// шаблона (797-1036) из WishesView.vue.
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import {
  useWishesContext, statusColor, statusLabel, GALA_ORANGE,
  shortName, wishCoAuthors, wishRecipients, wishItemsTotal, formatDate, formatPrice,
  stoppedByLine, rejectedByLine, purchaseMenuLabel, wishPurchasesLabel,
} from '@/composables/wishes/useWishesContext'
import type { Wish } from '@/composables/wishes/wishTypes'

defineProps<{
  items: Wish[]
  headers: any[]
  loading: boolean
  colFilters: Record<string, any>
  colSort: Record<string, any>
  subsidyNameOptions: (string | number | null)[]
  downloadingExcelId: number | null
  approvingId: number | null
  allFilter: string
  allFilters: { value: string; label: string }[]
  wishCounts: Record<string, number>
  allWishesTruncated: number | null
}>()

defineEmits<{
  (e: 'filter-change', value: string): void
  (e: 'open-edit', item: Wish): void
  (e: 'kanban', item: Wish): void
  (e: 'approve', item: Wish): void
  (e: 'reject', item: Wish): void
  (e: 'convert', item: Wish): void
  (e: 'download-excel', item: Wish, withPhotos: boolean): void
}>()

const ctx = useWishesContext()
</script>
