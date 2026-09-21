<template>
  <!-- ── Delete confirm ── -->
  <v-dialog v-model="visible" max-width="520">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
        Удалить субсидию
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <template v-if="deleteErrorLinked || hasBlockingLinks">
          <v-alert type="error" variant="tonal" class="mb-3" style="white-space:pre-line">
            {{ deleteErrorMsg || blockingLinksMsg }}
          </v-alert>
          <div v-for="g in blockingGroups" :key="g.key" class="mb-3">
            <div class="d-flex align-center gap-2 mb-1">
              <span class="text-body-2 font-weight-medium">{{ g.label }} ({{ g.group!.count }})</span>
              <v-spacer />
              <v-btn v-if="g.goTo" size="small" color="primary" variant="tonal"
                :prepend-icon="g.icon" @click="g.goTo()">
                Перейти
              </v-btn>
            </div>
            <v-expansion-panels density="compact" variant="accordion">
              <v-expansion-panel :title="`Показать список (${g.group!.items.length}${g.group!.count > g.group!.items.length ? ` из ${g.group!.count}` : ''})`">
                <v-expansion-panel-text>
                  <div class="obj-list">
                    <div v-for="it in g.group!.items" :key="it.id" class="obj-row">
                      <span class="text-medium-emphasis">№{{ it.number ?? it.id }}</span>
                      <span class="obj-name">{{ it.name || '—' }}</span>
                      <v-chip size="x-small" variant="tonal">{{ statusLabel(it.status) }}</v-chip>
                    </div>
                    <div v-if="g.group!.count > g.group!.items.length" class="text-caption text-medium-emphasis mt-1">
                      и ещё {{ g.group!.count - g.group!.items.length }}
                    </div>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </div>
        </template>
        <template v-else>
          <div class="mb-2">Удалить <strong>{{ deleteTarget?.name }}</strong>? Действие нельзя отменить.</div>
          <v-alert v-if="deleteImpact && (deleteImpact.feo_categories > 0 || deleteImpact.planned_items > 0)"
            type="warning" variant="tonal" density="compact">
            Вместе с субсидией будет безвозвратно удалено:
            <ul class="mt-1 mb-0" style="padding-left:18px;">
              <li v-if="deleteImpact.feo_categories > 0">{{ deleteImpact.feo_categories }} категорий ФЭО</li>
              <li v-if="deleteImpact.planned_items > 0">{{ deleteImpact.planned_items }} плановых позиций</li>
            </ul>
          </v-alert>
        </template>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="visible = false">Отмена</v-btn>
        <v-btn v-if="!deleteErrorLinked && !hasBlockingLinks" color="error" :loading="saving" @click="deleteSubsidy">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { SubsidyDeleteImpact, SubsidyDeleteImpactGroup, SubsidyRow } from '@/composables/subsidies/types'
import { purchaseStatusLabel, purchaseHiddenStatusLabel } from '@/constants/purchaseStatus'

// Человеческие подписи статусов "служебных" групп — wishes/split не показывают
// стандартную метку статуса закупки для пользователя без жаргона (владелец,
// 2026-09-17: "никаких английских статусов в тексте"). Обычные закупки и
// договоры используют общий словарь purchaseStatusLabel (Правило №6 — не
// дублировать словарь статусов); подпись для 'split' тоже не копия — берётся
// из общего backend-словаря HIDDEN_STATUS_LABELS через
// purchaseHiddenStatusLabel (см. constants/purchaseStatus.ts), только 'wishes'
// здесь намеренно переопределён — контекстная формулировка отличается от
// основной подписи статуса «Желания сотрудников».
function statusLabel(status: string | null): string {
  if (status === 'wishes') return 'Не в работе'
  if (status === 'split') return purchaseHiddenStatusLabel('split')
  return purchaseStatusLabel(status) || status || '—'
}

const visible = defineModel<boolean>({ default: false })

const emit = defineEmits<{ (e: 'deleted', id: number): void }>()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}

const ctx = useSubsidyDetailCtx()

const saving = ref(false)
const deleteTarget = ref<SubsidyRow | null>(null)
const deleteErrorLinked = ref(false)
const deleteErrorMsg = ref('')
const deleteImpact = ref<SubsidyDeleteImpact | null>(null)

// Владелец (2026-09-15, боевой инцидент): узнать про связанные закупки/договоры
// нужно ДО клика «Удалить», по данным delete-impact — а не только из отказа 409
// (тот суперадмину раньше не приходил вовсе, backend/app/routers/subsidies.py
// delete_subsidy). Если delete-impact не загрузился (:77 глушит ошибку) —
// deleteImpact остаётся null, hasBlockingLinks = false: кнопку не блокируем,
// но и не утверждаем, что связей нет (см. deleteErrorLinked/409 — запасной путь).
// Группы, ЧЬЁ количество отдал бэкенд (app/services/subsidy_delete_impact.py) —
// единственный источник разбивки (Правило №6): диалог не пересчитывает и не
// дублирует формулировки, только раскладывает готовые данные по строкам с
// человеческой подписью и правильной ссылкой на реестр (?status=wishes для
// скрытой группы «заявки не в работе» — обычный реестр закупок этот статус не
// показывает никаким фильтром, см. backend/app/routers/purchases.py).
// 'split' — без goTo (владелец, решение 21.09, corrections-21-09.md П1):
// родительские записи разделённых закупок скрыты из реестра СОВСЕМ, включая
// явный ?status=split (см. purchases.py) — переход туда вёл бы в пустой
// список, поэтому у этой группы остаётся только счётчик-информация, без
// кнопки «Перейти».
const GROUP_META: Record<string, { label: string; icon: string; goTo?: (id: number) => void }> = {
  purchases: {
    label: 'Закупки', icon: 'mdi-cart-outline',
    goTo: (id) => ctx.router.push(`/orders?subsidy_id=${id}`),
  },
  wishes: {
    label: 'Заявки, не переданные в работу', icon: 'mdi-hand-heart-outline',
    goTo: (id) => ctx.router.push(`/orders?subsidy_id=${id}&status=wishes`),
  },
  split: {
    label: 'Разделённые закупки (родительские записи)', icon: 'mdi-call-split',
  },
  contracts: {
    label: 'Договоры', icon: 'mdi-file-document-outline',
    goTo: (id) => ctx.router.push(`/contracts?subsidy_id=${id}`),
  },
}
const blockingGroups = computed(() => {
  const d = deleteImpact.value
  const id = deleteTarget.value?.id
  if (!d || !id) return []
  return (['purchases', 'wishes', 'split', 'contracts'] as const)
    .filter(key => (d[key]?.count ?? 0) > 0)
    .map(key => {
      const meta = GROUP_META[key]! // все 4 ключа определены в GROUP_META статически
      const metaGoTo = meta.goTo
      return {
        key,
        label: meta.label,
        icon: meta.icon,
        group: d[key] as SubsidyDeleteImpactGroup,
        goTo: metaGoTo ? () => { visible.value = false; metaGoTo(id) } : null,
      }
    })
})
const hasBlockingLinks = computed(() => blockingGroups.value.length > 0)
const blockingLinksMsg = computed(() => {
  const d = deleteImpact.value
  if (!d) return 'Нельзя удалить субсидию: есть связанные записи. Сначала удалите или перепривяжите их.'
  const parts = blockingGroups.value.map(g => `${g.group!.count} ${g.label.toLowerCase()}`)
  if (!parts.length) return ''
  return `Нельзя удалить субсидию: связано ${parts.join(', ')}. Сначала удалите или перепривяжите их.`
})

async function open(s: SubsidyRow) {
  deleteTarget.value = s
  deleteErrorLinked.value = false
  deleteErrorMsg.value = ''
  deleteImpact.value = null
  visible.value = true
  try {
    deleteImpact.value = await apiFetch<any>(`/subsidies/${s.id}/delete-impact`)
  } catch { /* предупреждение опционально */ }
}

// Удаляет карточку из ЕДИНСТВЕННОГО источника списка (ctx.allSubsidies — тот же
// ref, что читают SubsidyCardsGrid.vue/SubsidyListTable.vue/SubsidySummaryBar.vue
// через useSubsidyList(), см. useSubsidyDetail.ts, Правило №6). removeLocally
// используется и на успехе, и на «уже удалена» (404) — иначе после первого
// успешного DELETE карточка остаётся видимой до следующего loadAll(), и владелец
// жмёт «Удалить» ещё раз на уже удалённой строке (лог прода: 200, затем 404 ×3).
function removeLocally(id: number) {
  ctx.allSubsidies.value = ctx.allSubsidies.value.filter((s: SubsidyRow) => s.id !== id)
  if (ctx.selectedId.value === id) ctx.selectedId.value = null
}

async function deleteSubsidy() {
  if (!deleteTarget.value) return
  const targetId = deleteTarget.value.id
  saving.value = true
  try {
    await apiFetch(`/subsidies/${targetId}`, { method: 'DELETE' })
    removeLocally(targetId)
    visible.value = false
    showSnack('Субсидия удалена', 'warning')
    emit('deleted', targetId)
  } catch (e: any) {
    if (e?.status === 409) {
      deleteErrorLinked.value = true
      deleteErrorMsg.value = e?.detail || e?.payload?.message || ''
    } else if (e?.status === 404) {
      // Уже удалена раньше (повторный клик по карточке, которая не пропала визуально,
      // или гонка с параллельной сессией) — не показывать модалку ошибки поверх
      // диалога подтверждения: просто закрыть его и убрать строку из списка.
      removeLocally(targetId)
      visible.value = false
      showSnack('Субсидия уже была удалена', 'info')
      emit('deleted', targetId)
    } else {
      showSnack(e?.detail || e?.payload?.message || 'Ошибка удаления', 'error')
    }
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
.obj-list { max-height: 240px; overflow-y: auto; }
.obj-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 0; font-size: 13px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.obj-name { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
