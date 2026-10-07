<template>
  <div class="subsidies-grid">
    <div
      v-for="(s, idx) in subPaged" :key="s.id"
      class="subsidy-card"
      :class="{ 'subsidy-card--active': ctx.selectedId.value === s.id, 'subsidy-card--drag-over': cardDragOverIdx === idx, 'subsidy-card--dragging': cardDragIdx === idx }"
      draggable="true"
      @click="ctx.toggleSelect(s.id)"
      @dragstart="onCardDragStart($event, idx)"
      @dragover.prevent="onCardDragOver(idx)"
      @dragleave="cardDragOverIdx = -1"
      @drop.prevent="onCardDrop(idx)"
      @dragend="cardDragIdx = -1; cardDragOverIdx = -1"
    >
      <div class="sc-title-band">
        <div v-fit-text class="sc-name" :title="s.name">{{ s.name }}</div>
        <v-chip v-if="s.status === 'draft'" size="x-small" color="warning" variant="flat" class="ml-2">Черновик</v-chip>
        <!-- «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б) -->
        <v-chip
          v-if="s.is_sandbox" size="x-small" color="deep-purple" variant="flat" class="ml-2"
          prepend-icon="mdi-flask-outline"
          title="Копия для эксперимента — не входит в итоги дашборда/аккаунта, не шлёт уведомления"
        >Копия для эксперимента</v-chip>
        <div class="sc-actions">
          <v-btn
            v-if="ctx.canApproveSubsidy(s)"
            icon="mdi-check-decagram" size="x-small" variant="text" color="success"
            title="Утвердить черновик субсидии"
            :loading="ctx.approvingSubsidyId.value === s.id"
            @click.stop="ctx.approveSubsidy(s)"
          />
          <v-btn icon="mdi-account-group" size="x-small" variant="text" color="deep-purple" title="Участники (соредакторы)" @click.stop="ctx.openMembersDialog(s)" />
          <v-btn
            icon="mdi-file-document-multiple-outline"
            size="x-small" variant="text"
            :color="contractTemplates[s.id] ? 'indigo' : 'grey-lighten-1'"
            :title="contractTemplates[s.id] ? 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант) — есть свои' : 'Шаблоны документов (договоры, СЗ, ТЗ, Фабрикант)'"
            @click.stop="openTemplateDialog(s)"
          />
          <v-btn icon="mdi-account-multiple" size="x-small" variant="text" color="teal" title="Согласующие" @click.stop="openApproversDialog(s)" />
          <v-btn icon="mdi-history" size="x-small" variant="text" color="blue-grey" title="История бюджета" @click.stop="ctx.openHistoryDialog(s)" />
          <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="ctx.startEdit(s)" />
          <template v-if="s.is_sandbox">
            <v-btn icon="mdi-swap-horizontal-bold" size="x-small" variant="text" color="warning" title="Сделать настоящей" @click.stop="ctx.openSandboxPromote(s)" />
            <v-btn icon="mdi-delete-sweep" size="x-small" variant="text" color="error" title="Удалить копию целиком" @click.stop="ctx.openSandboxDelete(s)" />
          </template>
          <template v-else>
            <v-btn icon="mdi-content-copy" size="x-small" variant="text" color="deep-purple" title="Скопировать для эксперимента" @click.stop="ctx.openSandboxCopy(s)" />
            <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click.stop="ctx.confirmDelete(s)" />
          </template>
        </div>
      </div>

      <!-- «ФЭО не введено» (владелец 07.10.2026, план .planning/quick/2026-10-
           07-dnr-feo-cards/PLAN.md шаг 1, решение №3) — проверяется ПЕРВЫМ:
           не путать с isBudgetUndefined (та же пустая плитка, но другая
           причина — бюджет честно не задан, а не «ФЭО вообще не вводили»). -->
      <div class="sc-budget" :class="{ 'sc-budget--undefined': isFeoNotEntered(s) || isBudgetUndefined(s) }">
        {{ isFeoNotEntered(s) ? 'ФЭО не введено' : (isBudgetUndefined(s) ? 'Бюджет не определён' : formatCurrencyShort(displayBudget(s))) }}
      </div>
      <div v-if="!isFeoNotEntered(s) && !isBudgetUndefined(s)" class="sc-budget-label">{{ (s.feo_budget_total || 0) > 0 ? 'Бюджет ФЭО (расчёт)' : 'Бюджет' }}</div>

      <div class="sc-mini-row">
        <div class="sc-mini" title="Запланировано (план ФЭО + заявки) — то же, что «Запланировано» на шкале ниже">
          <div class="sc-mini-label">Запланировано</div>
          <div class="sc-mini-val" style="color:#F59E0B">{{ formatCurrencyShort(s.planned) }}</div>
        </div>
        <div class="sc-mini" title="Закупки в статусе «Заказано» — заказ размещён, поставка не завершена">
          <div class="sc-mini-label">Заказано</div>
          <div class="sc-mini-val" style="color:#3B82F6">{{ formatCurrencyShort(s.ordered) }}</div>
        </div>
        <div class="sc-mini" title="Закупки в статусе «Оплачено» — фактически оплаченные суммы">
          <div class="sc-mini-label">Оплачено</div>
          <div class="sc-mini-val" style="color:var(--color-paid)">{{ formatCurrencyShort(s.paid) }}</div>
        </div>
      </div>

      <v-progress-linear
        :model-value="pct(s.planned, displayBudget(s))"
        :color="progressColor(pct(s.planned, displayBudget(s)))"
        height="6" rounded class="mt-3"
      />
      <BudgetBar
        class="mt-3"
        hide-legend
        hide-name
        :subsidy="{
          id: s.id,
          name: s.name,
          budget: displayBudget(s),
          planned: s.planned,
          contracted: s.contracted,
          paid: s.paid,
        }"
      />
      <!-- Кликабельна (владелец 07.10.2026, решение №6, план .planning/quick/
           2026-10-07-dnr-feo-cards/PLAN.md шаг 5): выбирает субсидию и
           включает «Где превышение» (useExcessDrilldown.ts) по всей субсидии
           целиком — стрелки ведут к статьям, где план и ФЭО расходятся.
           @click.stop — иначе клик всплыл бы на @click карточки (toggleSelect,
           который может СНЯТЬ выбор, если субсидия уже выбрана). Скрыта вместе
           с cardDelta при feo_entered=false (cardDelta возвращает 0, см.
           useSubsidyList.ts) — её незачем нажимать, превышения без ФЭО нет. -->
      <v-chip
        v-if="Math.abs(cardDelta(s)) > 0.01"
        :color="cardDelta(s) > 0 ? '#fb923c' : '#ef4444'"
        size="small"
        class="mt-1 sc-delta-chip sc-delta-chip--clickable"
        prepend-icon="mdi-alert"
        :title="cardDelta(s) > 0
          ? `Бюджет ${Math.round(displayBudget(s)).toLocaleString('ru-RU')} ₽ − запланировано (план ФЭО + заявки) ${Math.round(s.planned || 0).toLocaleString('ru-RU')} ₽ = можно допланировать ${Math.round(cardDelta(s)).toLocaleString('ru-RU')} ₽ · нажмите, чтобы увидеть где`
          : `Запланировано (план ФЭО + заявки) ${Math.round(s.planned || 0).toLocaleString('ru-RU')} ₽ — больше бюджета ${Math.round(displayBudget(s)).toLocaleString('ru-RU')} ₽ на ${Math.round(-cardDelta(s)).toLocaleString('ru-RU')} ₽ · нажмите, чтобы увидеть где`"
        @click.stop="openExcessOnTile(s)"
      >ФЭО {{ cardDelta(s) > 0 ? '>' : '<' }} план: {{ cardDelta(s) > 0 ? 'допланировать' : 'урезать' }} {{ formatCurrencyShort(Math.abs(cardDelta(s))) }}</v-chip>
      <v-chip
        v-else-if="(displayBudget(s)) > 0 && (s.planned || 0) > 0"
        color="success"
        size="small"
        class="mt-1 sc-delta-chip"
        prepend-icon="mdi-check"
        :title="`Бюджет ФЭО и запланировано (план ФЭО + заявки) совпадают: ${Math.round(s.planned).toLocaleString('ru-RU')} ₽`"
      >ФЭО = план</v-chip>
      <v-chip
        v-if="s.ceiling_exceeded || s.ceiling_near_warning"
        :color="s.ceiling_exceeded ? '#ef4444' : '#f59e0b'"
        size="small"
        class="mt-1 sc-delta-chip"
        prepend-icon="mdi-alert-octagon"
        :title="`Заказано ${formatCurrencyShort(s.ceiling_committed_total || 0)} из потолка ${formatCurrencyShort(s.ceiling_total || 0)} — ${s.ceiling_committed_percent}% (порог предупреждения ${s.ceiling_warn_percent}%)`"
      >{{ s.ceiling_exceeded ? 'Потолок превышен' : 'Близко к потолку' }}: {{ s.ceiling_committed_percent }}%</v-chip>
      <div v-if="s.contractor_name" class="sc-contractor">
        <v-icon icon="mdi-account-tie" size="13" class="mr-1" />
        <span>{{ s.contractor_name }}</span>
      </div>
      <div class="sc-footer">
        <div class="sc-pct">{{ pct(s.planned, displayBudget(s)) }}% запланировано</div>
        <div class="sc-feo-badge" :class="s.feo_filled ? 'sc-feo-badge--ok' : 'sc-feo-badge--no'">
          <v-icon :icon="s.feo_filled ? 'mdi-check-circle' : 'mdi-circle-outline'" size="14" class="mr-1" />
          ФЭО
        </div>
      </div>
    </div>
  </div>
  <!-- cards pagination -->
  <div v-if="subTotalPages > 1" class="d-flex justify-center mt-3">
    <v-pagination v-model="subPage" :length="subTotalPages" density="comfortable" />
  </div>
</template>

<script setup lang="ts">
import BudgetBar from '@/components/BudgetBar.vue'
import { formatCurrencyShort } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useSubsidyList } from '@/composables/subsidies/useSubsidyList'
import { useSubsidyApprovers } from '@/composables/subsidies/useSubsidyApprovers'
import { useSubsidyTemplates } from '@/composables/subsidies/useSubsidyTemplates'
// «Где превышение» по всей субсидии (владелец 07.10.2026, план .planning/
// quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 5) — singleton уже построен
// SubsidiesView.vue с ctx (см. её докстринг про порядок монтирования), здесь
// переиспользуется без аргумента, как в FeoTreeRow.vue/SubsidyKpiCards.vue/
// ExcessDrilldownBar.vue (Правило №6 — второй механизм поиска не заводим).
import { useExcessDrilldown } from '@/composables/subsidies/useExcessDrilldown'
import type { SubsidyRow } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()
// useSubsidyList() без ctx — переиспользует singleton SubsidiesView.vue, см.
// докстринг в SubsidyListHeader.vue (владелец, 29.09: переключатель вид не
// работал до F5, т.к. этот вызов с другим ctx пересобирал отдельный API).
const {
  subPaged, subTotalPages, subPage, cardDragIdx, cardDragOverIdx,
  onCardDragStart, onCardDragOver, onCardDrop, pct, progressColor, cardDelta,
  displayBudget, isBudgetUndefined, isFeoNotEntered,
} = useSubsidyList()
const { openApproversDialog } = useSubsidyApprovers()
const { openTemplateDialog, contractTemplates } = useSubsidyTemplates()
const excessDrilldown = useExcessDrilldown()

// Плашка «ФЭО > план / ФЭО < план» на плитке (владелец 07.10.2026, решение
// №6) — выбирает субсидию (если ещё не выбрана — ctx.toggleSelect переключает,
// поэтому вызываем его только когда карточка ДРУГОЙ субсидии; иначе повторный
// клик по уже выбранной карточке снял бы выбор) и, после загрузки дерева ФЭО
// этой субсидии, включает режим «план против ФЭО целиком»
// (excessDrilldown.activate('total') — расширение существующего activate(),
// второй механизм поиска виновника не заводится).
async function openExcessOnTile(s: SubsidyRow) {
  if (ctx.selectedId.value !== s.id) ctx.toggleSelect(s.id)
  await ctx.loadFeo(s.id)
  excessDrilldown.activate('total')
}

// Название карточки в одну строку: базовый крупный шрифт, ужимается пока не влезет.
// Используется только здесь (карточки списка субсидий) — перенесено из
// SubsidiesView.vue вместе с шаблоном карточки (волна 5b).
function fitTextToWidth(el: HTMLElement) {
  const base = 30
  el.style.fontSize = `${base}px`
  const cw = el.clientWidth
  if (cw > 0 && el.scrollWidth > cw) {
    el.style.fontSize = `${Math.max(13, Math.floor((base * cw) / el.scrollWidth))}px`
  }
}
const vFitText = {
  mounted: fitTextToWidth,
  updated: fitTextToWidth,
}
</script>
