<template>
  <!-- ── Delete FEO category dialog ── -->
  <v-dialog v-model="visible" max-width="440">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
        Удалить направление?
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="visible = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="mb-2">«{{ feoDeleteTarget?.name }}»</div>
        <v-alert v-if="feoDeleteChildrenCount > 0" type="warning" density="compact" variant="tonal" class="mb-3">
          Будет удалено вместе с {{ feoDeleteChildrenCount }}
          {{ feoDeleteChildrenCount === 1 ? 'дочерней категорией' : 'дочерними категориями' }}
        </v-alert>
        <v-alert v-if="feoDeleteError" type="error" variant="tonal" class="mb-3">
          {{ feoDeleteError }}
          <div class="mt-2">
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-arrow-right"
              @click="visible = false; ctx.router.push(`/orders?feo_category_id=${feoDeleteTarget?.id}`)">
              Перейти к закупкам этой категории
            </v-btn>
          </div>
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="visible = false">Отмена</v-btn>
        <v-btn v-if="!feoDeleteError" color="error" :loading="savingFeo" @click="deleteFeoCategory">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { collectSubtreeIds } from '@/composables/subsidies/feoCategoryUtils'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { FeoCategory } from '@/composables/subsidies/types'

const visible = defineModel<boolean>({ default: false })

const emit = defineEmits<{ (e: 'deleted'): void }>()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}

const ctx = useSubsidyDetailCtx()

const savingFeo = ref(false)
const feoDeleteTarget = ref<FeoCategory | null>(null)
const feoDeleteError = ref('')
// Не используется в шаблоне (тот же пробел был и до рефакторинга — см. отчёт),
// оставлено как есть, чтобы не менять поведение.
const feoDeleteLinkedIds = ref<number[]>([])

const feoDeleteChildrenCount = computed(() => {
  if (!feoDeleteTarget.value) return 0
  return collectSubtreeIds(ctx.feoCategories.value, feoDeleteTarget.value.id).length - 1
})

function open(node: FeoCategory) {
  feoDeleteTarget.value = node
  feoDeleteError.value = ''
  visible.value = true
}

async function deleteFeoCategory() {
  if (!feoDeleteTarget.value) return
  savingFeo.value = true
  feoDeleteError.value = ''
  try {
    await apiFetch(`/feo-categories/${feoDeleteTarget.value.id}`, { method: 'DELETE' })
    visible.value = false
    showSnack('Направление удалено', 'warning')
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
    ctx.syncFeoFilled()
    emit('deleted')
  } catch (e: any) {
    const detail = e?.detail
    if (detail && typeof detail === 'object' && detail.message) {
      feoDeleteError.value = detail.message
      feoDeleteLinkedIds.value = detail.feo_category_ids || []
    } else {
      feoDeleteError.value = typeof detail === 'string' ? detail : 'Ошибка удаления'
      feoDeleteLinkedIds.value = []
    }
  } finally {
    savingFeo.value = false
  }
}

defineExpose({ open })
</script>
