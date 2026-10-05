<template>
  <div>
    <div class="d-flex flex-wrap align-center gap-2 mb-3">
      <v-btn size="small" variant="tonal" @click="markAll(true)">Отметить все</v-btn>
      <v-btn size="small" variant="tonal" @click="markAll(false)">Снять все</v-btn>
      <v-btn size="small" variant="text" :loading="resetting" @click="resetToDefault">Сбросить к умолчанию</v-btn>
      <v-spacer />
      <span v-if="codesData?.is_default" class="text-caption text-medium-emphasis">
        используется набор по умолчанию (все закупочные статьи)
      </span>
      <v-btn size="small" color="primary" variant="flat" :loading="saving" :disabled="!dirty" @click="save">
        Сохранить
      </v-btn>
    </div>

    <div v-if="loading" class="d-flex justify-center py-6">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else>
      <v-expansion-panels v-model="openGroups" multiple variant="accordion">
        <v-expansion-panel v-for="group in groups" :key="group.kind" :value="group.kind">
          <v-expansion-panel-title>
            <div class="d-flex align-center flex-wrap gap-2" style="width:100%">
              <span class="font-weight-medium text-capitalize">{{ group.kind }}</span>
              <v-chip size="x-small" variant="tonal">{{ group.articles.length }}</v-chip>
              <v-spacer />
              <span class="text-caption text-medium-emphasis mr-4">
                по выписке {{ formatCurrency(groupStatementTotal(group)) }}
              </span>
              <v-btn
                v-if="group.kind !== 'нет платежей'"
                size="x-small" variant="text"
                @click.stop="markGroup(group, true)"
              >все</v-btn>
              <v-btn
                v-if="group.kind !== 'нет платежей'"
                size="x-small" variant="text"
                @click.stop="markGroup(group, false)"
              >ни одной</v-btn>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-table density="compact">
              <thead>
                <tr>
                  <th style="width:40px"></th>
                  <th>Код</th>
                  <th>Наименование</th>
                  <th class="text-right">По выписке</th>
                  <th class="text-right">П/п</th>
                  <th class="text-right">Найдено в закупках</th>
                  <th class="text-right">Разница</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="a in group.articles" :key="a.code" :class="{ 'bg-amber-lighten-5': a.unknown }">
                  <td>
                    <v-checkbox-btn
                      :model-value="selected.has(a.code)"
                      density="compact"
                      @update:model-value="(v: boolean) => toggle(a.code, v)"
                    />
                  </td>
                  <td class="text-no-wrap">{{ a.code }}</td>
                  <td>
                    {{ a.name }}
                    <v-chip v-if="a.unknown" size="x-small" color="warning" variant="flat" class="ml-1">код не в справочнике</v-chip>
                  </td>
                  <td class="text-right text-no-wrap">{{ formatCurrency(a.statement_total) }}</td>
                  <td class="text-right">{{ a.statement_count }}</td>
                  <td class="text-right text-no-wrap">{{ formatCurrency(a.matched_total) }}</td>
                  <td class="text-right text-no-wrap" :class="a.difference ? 'text-error font-weight-medium' : ''">
                    {{ formatCurrency(a.difference) }}
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </div>
</template>

<script setup lang="ts">
// Вкладка «Статьи» диалога сверки — полный справочник статей расходов,
// сгруппированный по видам, с галочкой «искать закупку» (хранится у субсидии,
// GET/PUT /subsidies/{id}/payment-control/codes). Источник данных и действий —
// общий composable useSubsidyPaymentControl.ts (ПРАВИЛО №6), этот файл только
// рисует и собирает выбор пользователя.
import { computed, ref, watch } from 'vue'
import type { useSubsidyPaymentControl, PaymentControlArticle } from '@/composables/subsidies/useSubsidyPaymentControl'
import { formatCurrency } from '@/composables/subsidies/format'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

const props = defineProps<{
  subsidyId: number
  control: ReturnType<typeof useSubsidyPaymentControl>
}>()
const emit = defineEmits<{ (e: 'saved'): void }>()

const toast = useToast()
const { codesData, codesLoading: loading, codesSaving: saving } = props.control

const selected = ref<Set<string>>(new Set())
const openGroups = ref<string[]>([])
const resetting = ref(false)

interface ArticleGroup { kind: string; articles: PaymentControlArticle[] }

const groups = computed<ArticleGroup[]>(() => {
  const articles = props.control.data.value?.articles || []
  const withPayments = articles.filter(a => a.statement_count > 0)
  const withoutPayments = articles.filter(a => a.statement_count === 0)
  const byKind = new Map<string, PaymentControlArticle[]>()
  for (const a of withPayments) {
    if (!byKind.has(a.kind)) byKind.set(a.kind, [])
    byKind.get(a.kind)!.push(a)
  }
  const result: ArticleGroup[] = Array.from(byKind.entries()).map(([kind, arts]) => ({ kind, articles: arts }))
  if (withoutPayments.length) result.push({ kind: 'нет платежей', articles: withoutPayments })
  return result
})

function groupStatementTotal(g: ArticleGroup): number {
  return g.articles.reduce((s, a) => s + (a.statement_total || 0), 0)
}

function initSelectedFromArticles() {
  const articles = props.control.data.value?.articles || []
  selected.value = new Set(articles.filter(a => a.search_purchase).map(a => a.code))
}

watch(() => props.control.data.value?.articles, (arts) => {
  if (arts && !selected.value.size) initSelectedFromArticles()
}, { immediate: true })

// Разворачиваем группы с платежами по умолчанию, «нет платежей» — свёрнута.
watch(groups, (gs) => {
  if (!openGroups.value.length) openGroups.value = gs.filter(g => g.kind !== 'нет платежей').map(g => g.kind)
}, { immediate: true })

const dirty = computed(() => {
  const current = new Set((props.control.data.value?.articles || []).filter(a => a.search_purchase).map(a => a.code))
  if (current.size !== selected.value.size) return true
  for (const c of current) if (!selected.value.has(c)) return true
  return false
})

function toggle(code: string, value: boolean) {
  const next = new Set(selected.value)
  if (value) next.add(code)
  else next.delete(code)
  selected.value = next
}

function markAll(value: boolean) {
  if (!value) { selected.value = new Set(); return }
  const articles = props.control.data.value?.articles || []
  selected.value = new Set(articles.map(a => a.code))
}

function markGroup(g: ArticleGroup, value: boolean) {
  const next = new Set(selected.value)
  for (const a of g.articles) {
    if (value) next.add(a.code)
    else next.delete(a.code)
  }
  selected.value = next
}

async function save() {
  try {
    await props.control.saveCodes(props.subsidyId, Array.from(selected.value))
    toast.success('Набор статей для сверки сохранён')
    emit('saved')
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось сохранить набор статей' }), 'error')
  }
}

async function resetToDefault() {
  resetting.value = true
  try {
    const directory = codesData.value?.directory || []
    if (directory.length) {
      selected.value = new Set(directory.filter(d => d.is_procurement).map(d => d.code))
    } else {
      // Справочник ещё не загружен — отмечаем по is_procurement из уже
      // известных статей сверки (обычно совпадает с директорией).
      const articles = props.control.data.value?.articles || []
      selected.value = new Set(articles.filter(a => a.is_procurement).map(a => a.code))
    }
  } finally {
    resetting.value = false
  }
}

watch(() => props.subsidyId, (id) => { if (id) props.control.loadCodes(id) }, { immediate: true })
</script>
