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
      <span v-if="isBudgetUndefined(item)" class="text-medium-emphasis font-italic">Бюджет не определён</span>
      <span v-else>{{ formatCurrencyShort(displayBudget(item)) }}</span>
    </template>
    <template #item.planned="{ item }">
      <span style="color:#F59E0B">{{ formatCurrencyShort(item.planned) }}</span>
    </template>
    <template #item.ordered="{ item }">
      <span style="color:#3B82F6">{{ formatCurrencyShort(item.ordered) }}</span>
    </template>
    <template #item.paid="{ item }">
      <div class="d-flex flex-column">
        <span style="color:var(--color-paid)">{{ formatCurrencyShort(item.paid) }}</span>
        <!-- «по отметке» (item.paid) против «подтверждено выпиской» — та же
             пара чисел, что и карточка «Оплачено» (SubsidyKpiCards.vue), один
             источник — backend/app/services/subsidy_paid_breakdown.py. -->
        <span v-if="item.paid_confirmed != null" class="text-caption text-medium-emphasis" style="font-size:10px">
          выпиской: {{ formatCurrencyShort(item.paid_confirmed) }}
        </span>
      </div>
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
      <!-- «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б) -->
      <v-chip
        v-if="item.is_sandbox" size="x-small" color="deep-purple" variant="flat" class="ml-2"
        prepend-icon="mdi-flask-outline"
        title="Копия для эксперимента — не входит в итоги дашборда/аккаунта, не шлёт уведомления"
      >копия</v-chip>
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
        <template v-if="item.is_sandbox">
          <v-btn icon="mdi-swap-horizontal-bold" size="x-small" variant="text" color="warning" title="Сделать настоящей" @click.stop="ctx.openSandboxPromote(item)" />
          <v-btn icon="mdi-delete-sweep" size="x-small" variant="text" color="error" title="Удалить копию целиком" @click.stop="ctx.openSandboxDelete(item)" />
        </template>
        <template v-else>
          <v-btn icon="mdi-content-copy" size="x-small" variant="text" color="deep-purple" title="Скопировать для эксперимента" @click.stop="ctx.openSandboxCopy(item)" />
          <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="ctx.confirmDelete(item)" />
        </template>
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
// useSubsidyList() без ctx — переиспользует singleton SubsidiesView.vue, см.
// докстринг в SubsidyListHeader.vue (владелец, 29.09: переключатель вид не
// работал до F5, т.к. этот вызов с другим ctx пересобирал отдельный API).
const { filteredSubsidies, subsidyTableHeaders, displayBudget, isBudgetUndefined } = useSubsidyList()
const { openApproversDialog } = useSubsidyApprovers()
const { openTemplateDialog, contractTemplates } = useSubsidyTemplates()
</script>
