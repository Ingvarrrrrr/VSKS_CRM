<template>
  <v-data-table
    :headers="subsidyTableHeaders"
    :items="filteredSubsidies"
    density="compact"
    :items-per-page="25"
    hover
    class="subsidy-main-table mb-3"
  >
    <template #item.feo_budget_total="{ item }">
      {{ formatCurrencyShort(item.feo_budget_total || item.budget) }}
    </template>
    <template #item.planned="{ item }">
      <span style="color:#F59E0B">{{ formatCurrencyShort(item.planned) }}</span>
    </template>
    <template #item.ordered="{ item }">
      <span style="color:#3B82F6">{{ formatCurrencyShort(item.ordered) }}</span>
    </template>
    <template #item.paid="{ item }">
      <span style="color:var(--color-paid)">{{ formatCurrencyShort(item.paid) }}</span>
    </template>
    <template #item.contractor_name="{ item }">
      <span v-if="item.contractor_name" class="d-flex align-center">
        <v-icon icon="mdi-account-tie" size="13" class="mr-1" color="teal" />
        {{ item.contractor_name }}
      </span>
      <span v-else class="text-medium-emphasis">—</span>
    </template>
    <template #item.feo_filled="{ item }">
      <v-icon
        :icon="item.feo_filled ? 'mdi-check-circle' : 'mdi-circle-outline'"
        :color="item.feo_filled ? 'success' : 'grey-lighten-1'"
        size="18"
      />
    </template>
    <template #item.ceiling_committed_percent="{ item }">
      <v-chip
        v-if="item.ceiling_exceeded || item.ceiling_near_warning"
        size="x-small"
        :color="item.ceiling_exceeded ? 'error' : 'warning'"
        variant="flat"
        :title="`Заказано ${formatCurrency(item.ceiling_committed_total || 0)} из потолка ${formatCurrency(item.ceiling_total || 0)} — ${item.ceiling_committed_percent}% (порог предупреждения ${item.ceiling_warn_percent}%)`"
      >{{ item.ceiling_committed_percent }}%</v-chip>
      <span v-else class="text-medium-emphasis">—</span>
    </template>
    <template #item.name="{ item }">
      <span class="font-weight-medium cursor-pointer" @click="ctx.toggleSelect(item.id)">{{ item.name }}</span>
      <v-chip v-if="item.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
    </template>
    <template #item.actions="{ item }">
      <div class="d-flex align-center justify-end" style="gap:2px">
        <v-btn
          v-if="ctx.canApproveSubsidy(item)"
          icon="mdi-check-decagram" size="x-small" variant="text" color="success"
          title="Утвердить черновик субсидии"
          :loading="ctx.approvingSubsidyId.value === item.id"
          @click.stop="ctx.approveSubsidy(item)"
        />
        <v-btn icon="mdi-account-group" size="x-small" variant="text" color="deep-purple" title="Участники (соредакторы)" @click.stop="ctx.openMembersDialog(item)" />
        <v-btn
          icon="mdi-file-document-multiple-outline"
          size="x-small" variant="text"
          :color="contractTemplates[item.id] ? 'indigo' : 'grey-lighten-1'"
          :title="contractTemplates[item.id] ? 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант) — есть свои' : 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант)'"
          @click.stop="openTemplateDialog(item)"
        />
        <v-btn icon="mdi-account-multiple" size="x-small" variant="text" color="teal" title="Согласующие" @click.stop="openApproversDialog(item)" />
        <v-btn icon="mdi-history" size="x-small" variant="text" color="blue-grey" title="История бюджета" @click.stop="ctx.openHistoryDialog(item)" />
        <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="ctx.startEdit(item)" />
        <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="ctx.confirmDelete(item)" />
      </div>
    </template>
  </v-data-table>
</template>

<script setup lang="ts">
import { formatCurrency, formatCurrencyShort } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useSubsidyList } from '@/composables/subsidies/useSubsidyList'
import { useSubsidyApprovers } from '@/composables/subsidies/useSubsidyApprovers'
import { useSubsidyTemplates } from '@/composables/subsidies/useSubsidyTemplates'

const ctx = useSubsidyDetailCtx()
const { filteredSubsidies, subsidyTableHeaders } = useSubsidyList(ctx)
const { openApproversDialog } = useSubsidyApprovers()
const { openTemplateDialog, contractTemplates } = useSubsidyTemplates()
</script>
