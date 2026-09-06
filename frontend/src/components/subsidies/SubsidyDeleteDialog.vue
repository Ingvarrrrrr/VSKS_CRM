<template>
  <!-- ── Delete confirm ── -->
  <v-dialog v-model="visible" max-width="420">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
        Удалить субсидию
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <template v-if="deleteErrorLinked">
          <v-alert type="error" variant="tonal" class="mb-3" style="white-space:pre-line">
            {{ deleteErrorMsg || 'Нельзя удалить субсидию: есть связанные записи. Сначала удалите или перепривяжите их.' }}
          </v-alert>
          <v-btn v-if="(deleteImpact?.purchases ?? 0) > 0" block color="primary" variant="tonal"
            prepend-icon="mdi-cart-outline" class="mb-2" @click="goToLinkedPurchases">
            Перейти к закупкам ({{ deleteImpact?.purchases }})
          </v-btn>
          <v-btn v-if="(deleteImpact?.contracts ?? 0) > 0" block color="primary" variant="tonal"
            prepend-icon="mdi-file-document-outline" @click="goToLinkedContracts">
            Перейти к договорам ({{ deleteImpact?.contracts }})
          </v-btn>
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
        <v-btn v-if="!deleteErrorLinked" color="error" :loading="saving" @click="deleteSubsidy">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { SubsidyDeleteImpact, SubsidyRow } from '@/composables/subsidies/types'

const visible = defineModel<boolean>({ default: false })

const emit = defineEmits<{ (e: 'deleted'): void }>()

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

async function deleteSubsidy() {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    await apiFetch(`/subsidies/${deleteTarget.value.id}`, { method: 'DELETE' })
    ctx.allSubsidies.value = ctx.allSubsidies.value.filter((s: SubsidyRow) => s.id !== deleteTarget.value!.id)
    if (ctx.selectedId.value === deleteTarget.value.id) ctx.selectedId.value = null
    visible.value = false
    showSnack('Субсидия удалена', 'warning')
    emit('deleted')
  } catch (e: any) {
    if (e?.status === 409) {
      deleteErrorLinked.value = true
      deleteErrorMsg.value = e?.detail || e?.payload?.message || ''
    } else {
      showSnack(e?.detail || e?.payload?.message || 'Ошибка удаления', 'error')
    }
  } finally {
    saving.value = false
  }
}

function goToLinkedPurchases() {
  visible.value = false
  ctx.router.push(`/orders?subsidy_id=${deleteTarget.value?.id}`)
}

function goToLinkedContracts() {
  visible.value = false
  ctx.router.push(`/contracts?subsidy_id=${deleteTarget.value?.id}`)
}

defineExpose({ open })
</script>
