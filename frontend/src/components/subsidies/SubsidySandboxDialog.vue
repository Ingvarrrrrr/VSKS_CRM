<template>
  <!-- «Копия субсидии для экспериментов» (план breezy-mixing-lovelace.md, Часть Б).
       Один диалог на три действия (копировать/удалить копию/сделать настоящей) —
       тот же приём самодостаточного диалога, что SubsidyDeleteDialog.vue. -->
  <v-dialog v-model="visible" max-width="520" persistent>
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon :icon="icon" :color="iconColor" class="mr-2" />
        {{ title }}
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <template v-if="mode === 'copy'">
          <div v-if="!copying">
            Создать копию субсидии «{{ target?.name }}» для эксперимента — дерево ФЭО,
            план, доступы, шаблоны и ВСЕ закупки с договорами/позициями/чеками/платежами/файлами.
            Заявки и история согласований не копируются.
          </div>
          <div v-else class="d-flex align-center gap-3 py-2">
            <v-progress-circular indeterminate color="primary" size="28" />
            <span>Копируем — на субсидии с сотнями закупок это может занять минуту…</span>
          </div>
        </template>
        <template v-else-if="mode === 'delete'">
          <div v-if="dryRunCounts">
            <div class="mb-2">Удалить копию «{{ target?.name }}» целиком? Действие нельзя отменить.</div>
            <v-alert type="warning" variant="tonal" density="compact">
              Вместе с копией будет безвозвратно удалено:
              <ul class="mt-1 mb-0" style="padding-left:18px;">
                <li>{{ dryRunCounts.purchases }} закупок</li>
                <li>{{ dryRunCounts.contracts }} договоров</li>
                <li>{{ dryRunCounts.payments }} платежей</li>
              </ul>
            </v-alert>
          </div>
          <div v-else class="d-flex align-center gap-3 py-2">
            <v-progress-circular indeterminate color="primary" size="28" />
            <span>Считаем, что уйдёт…</span>
          </div>
        </template>
        <template v-else-if="mode === 'promote'">
          <v-alert type="warning" variant="tonal" density="compact">
            Копия «{{ target?.name }}» станет настоящей субсидией и начнёт учитываться в итогах
            дашборда/аккаунта. Если оригинал ещё существует — оригинал и копия будут считаться
            ДВАЖДЫ.
          </v-alert>
        </template>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" :disabled="copying" @click="visible = false">Отмена</v-btn>
        <v-btn
          v-if="mode === 'copy'"
          color="primary" :loading="copying" @click="doCopy"
        >Скопировать</v-btn>
        <v-btn
          v-else-if="mode === 'delete'"
          color="error" :loading="saving" :disabled="!dryRunCounts" @click="doDelete"
        >Удалить целиком</v-btn>
        <v-btn
          v-else-if="mode === 'promote'"
          color="warning" :loading="saving" @click="doPromote"
        >Сделать настоящей</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { SubsidyRow } from '@/composables/subsidies/types'

const visible = ref(false)
const mode = ref<'copy' | 'delete' | 'promote'>('copy')
const target = ref<SubsidyRow | null>(null)
const copying = ref(false)
const saving = ref(false)
const dryRunCounts = ref<{ purchases: number; contracts: number; payments: number } | null>(null)

const emit = defineEmits<{ (e: 'changed'): void }>()
const ctx = useSubsidyDetailCtx()
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const title = computed(() => ({
  copy: 'Скопировать для эксперимента',
  delete: 'Удалить копию целиком',
  promote: 'Сделать копию настоящей',
}[mode.value]))
const icon = computed(() => ({
  copy: 'mdi-content-copy', delete: 'mdi-delete-sweep', promote: 'mdi-swap-horizontal-bold',
}[mode.value]))
const iconColor = computed(() => (mode.value === 'delete' ? 'error' : 'warning'))

async function openCopy(s: SubsidyRow) {
  mode.value = 'copy'
  target.value = s
  copying.value = false
  visible.value = true
}

async function openDelete(s: SubsidyRow) {
  mode.value = 'delete'
  target.value = s
  dryRunCounts.value = null
  visible.value = true
  try {
    dryRunCounts.value = await apiFetch<any>(`/subsidies/${s.id}/sandbox?dry_run=true`, { method: 'DELETE' })
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Не удалось посчитать, что будет удалено', 'error')
    visible.value = false
  }
}

async function openPromote(s: SubsidyRow) {
  mode.value = 'promote'
  target.value = s
  visible.value = true
}

async function doCopy() {
  if (!target.value) return
  copying.value = true
  try {
    const created = await apiFetch<{ id: number; name: string }>(`/subsidies/${target.value.id}/copy`, { method: 'POST' })
    showSnack(`Копия «${created.name}» создана`, 'success')
    visible.value = false
    emit('changed')
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Ошибка копирования', 'error')
  } finally {
    copying.value = false
  }
}

async function doDelete() {
  if (!target.value) return
  saving.value = true
  try {
    await apiFetch(`/subsidies/${target.value.id}/sandbox`, { method: 'DELETE' })
    ctx.allSubsidies.value = ctx.allSubsidies.value.filter((s: SubsidyRow) => s.id !== target.value!.id)
    if (ctx.selectedId.value === target.value.id) ctx.selectedId.value = null
    showSnack('Копия удалена целиком', 'warning')
    visible.value = false
    emit('changed')
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Ошибка удаления копии', 'error')
  } finally {
    saving.value = false
  }
}

async function doPromote() {
  if (!target.value) return
  saving.value = true
  try {
    await apiFetch(`/subsidies/${target.value.id}/sandbox/promote`, { method: 'POST' })
    showSnack('Копия теперь настоящая субсидия', 'success')
    visible.value = false
    emit('changed')
  } catch (e: any) {
    showSnack(e?.detail || e?.payload?.message || 'Ошибка', 'error')
  } finally {
    saving.value = false
  }
}

defineExpose({ openCopy, openDelete, openPromote })
</script>

<style scoped>
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
