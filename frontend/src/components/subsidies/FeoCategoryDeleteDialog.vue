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
        <!-- Жалоба владельца (п.6 волны 2, 2026-09-13): диалог предупреждал только
             про дочерние категории и молчал про плановые позиции — при удалении
             категории «Канцелярские и бытовые расходы...» каскадом снесло все
             позиции поддерева («Стенды», «Ростов»), хотя владелец хотел удалить
             только одну («Москва») — но тем же значком корзины удалялась КАТЕГОРИЯ,
             не позиция. Число — с бэкенда (GET /feo-categories/{id}/subtree,
             planned_items_count), не пересчитывается на фронте вторым способом. -->
        <v-alert v-if="feoDeletePlannedItemsCount > 0" type="warning" density="compact" variant="tonal" class="mb-3">
          Вместе с категорией будет удалено {{ feoDeletePlannedItemsCount }}
          {{ plannedItemsCountWord(feoDeletePlannedItemsCount) }} — восстановить их будет нельзя.
        </v-alert>
        <!-- Стек отмены дерева плана (Ctrl+Z/Ctrl+Y, доп. волна 2026-09-14) НЕ
             умеет отменять удаление категории — каскад (подкатегории + плановые
             позиции + отвязка ранних закупок/товаров, _purge_feo_categories в
             app/routers/feo_categories.py) необратим и по составу теряет больше,
             чем «создать заново» способно вернуть: новая категория получила бы
             ДРУГОЙ id и пустое содержимое, а человек решил бы, что всё вернулось.
             Честное предупреждение вместо тихой полу-отмены (правило координатора:
             «молчаливой полуотмены быть не должно») — показывается ВСЕГДА, даже
             для пустой категории без детей/позиций. -->
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          <v-icon icon="mdi-undo-variant" size="14" class="mr-1" style="opacity:.6" />
          Это действие нельзя отменить кнопкой «Отменить»/Ctrl+Z — удаление направления необратимо.
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
import { deleteCategoryRaw } from '@/composables/subsidies/useFeoTreeDnd'
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
// Сколько плановых позиций (feo_planned_items) каскадом удалится вместе с
// категорией — жалоба владельца (п.6 волны 2, 2026-09-13): значок корзины у
// категории сносит ВСЕ плановые позиции её поддерева (_purge_feo_categories в
// feo_categories.py), а этот диалог предупреждал только про дочерние категории.
// Число — с бэкенда (GET /feo-categories/{id}/subtree.planned_items_count,
// расширенный этой же волной), не второй пересчёт на фронте (Правило №6).
const feoDeletePlannedItemsCount = ref(0)

const feoDeleteChildrenCount = computed(() => {
  if (!feoDeleteTarget.value) return 0
  return collectSubtreeIds(ctx.feoCategories.value, feoDeleteTarget.value.id).length - 1
})

// Простое русское склонение количества («1 позиция» / «2 позиции» / «5 позиций») —
// тот же mod10/mod100-приём, что и в @/utils/relativeTime.ts::pluralRu, локальная
// копия не экспортируется оттуда, дублировать импортом нельзя.
function plannedItemsCountWord(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'плановая позиция'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'плановые позиции'
  return 'плановых позиций'
}

async function open(node: FeoCategory) {
  feoDeleteTarget.value = node
  feoDeleteError.value = ''
  feoDeletePlannedItemsCount.value = 0
  visible.value = true
  try {
    const res = await apiFetch<{ planned_items_count?: number }>(`/feo-categories/${node.id}/subtree`)
    feoDeletePlannedItemsCount.value = res.planned_items_count || 0
  } catch {
    // Не удалось получить число — диалог остаётся рабочим без этого предупреждения,
    // не блокируем удаление молчаливым отказом (см. feoDeleteError — это отдельная,
    // блокирующая ошибка про связанные закупки).
  }
}

async function deleteFeoCategory() {
  if (!feoDeleteTarget.value) return
  savingFeo.value = true
  feoDeleteError.value = ''
  try {
    // deleteCategoryRaw — то же место, что зовёт и стек отмены (undo создания
    // категории в FeoCategoryDialog.vue, только когда категория ещё пуста) —
    // второй DELETE-запрос не заводим (Правило №6). Само это удаление в стек
    // НЕ кладётся (см. предупреждение в шаблоне выше) — необратимый каскад.
    const res = await deleteCategoryRaw(feoDeleteTarget.value.id)
    if (!res.ok) {
      const detail = res.detail
      if (detail && typeof detail === 'object' && detail.message) {
        feoDeleteError.value = detail.message
        feoDeleteLinkedIds.value = detail.feo_category_ids || []
      } else {
        feoDeleteError.value = res.error
        feoDeleteLinkedIds.value = []
      }
      return
    }
    visible.value = false
    showSnack('Направление удалено', 'warning')
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
    ctx.syncFeoFilled()
    emit('deleted')
  } finally {
    savingFeo.value = false
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
</style>
