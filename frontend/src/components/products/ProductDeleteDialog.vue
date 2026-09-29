<template>
  <v-dialog v-model="show" max-width="520">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Удалить товар?</v-card-title>
      <v-card-text class="px-6">
        <template v-if="blockMessage">
          <v-alert type="error" variant="tonal" density="compact" class="mb-3" style="white-space:pre-line">
            {{ blockMessage }}
          </v-alert>
          <div v-for="g in blockingGroups" :key="g.key" class="mb-3">
            <div class="text-body-2 font-weight-medium mb-1">{{ g.label }} ({{ g.group.count }})</div>
            <div class="obj-list">
              <div v-for="it in g.group.items" :key="it.id" class="obj-row">
                <router-link :to="it.route" target="_blank" class="obj-link">
                  {{ g.linkText(it) }}
                </router-link>
                <span v-if="it.item_count > 1" class="text-caption text-medium-emphasis">
                  ({{ it.item_count }} поз.)
                </span>
              </div>
              <div v-if="g.group.count > g.group.items.length" class="text-caption text-medium-emphasis mt-1">
                и ещё {{ g.group.count - g.group.items.length }}
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <strong>{{ target?.name }}</strong> будет удалён из каталога.
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">{{ blockMessage ? 'Закрыть' : 'Отмена' }}</v-btn>
        <v-btn v-if="!blockMessage" color="error" :loading="deleting" @click="$emit('confirm')">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Product, ProductDeleteImpact, ProductDeleteImpactItem } from '@/composables/products/productsTypes'

const props = defineProps<{
  target: Product | null
  deleting: boolean
  // 409 «есть связанные записи» — от backend/app/services/product_delete_impact.py
  // (Правило №6: фронт не выдумывает свой текст, только раскладывает готовые
  // данные ответа по строкам со ссылками на карточки).
  blockMessage?: string
  blockImpact?: ProductDeleteImpact | null
}>()
defineEmits<{ (e: 'confirm'): void }>()

const show = defineModel<boolean>('modelValue', { required: true })

const GROUP_META: Record<string, { label: string; linkText: (it: ProductDeleteImpactItem) => string }> = {
  purchases: { label: 'Закупки', linkText: it => `Закупка ${it.number ?? ('№' + it.id)} — ${it.name || '—'}` },
  wishes: { label: 'Заявки', linkText: it => `Заявка №${it.id} — ${it.name || '—'}` },
  contracts: { label: 'Договоры', linkText: it => `Договор №${it.number ?? it.id} — ${it.name || '—'}` },
  commercial_requests: { label: 'Коммерческие предложения', linkText: it => `КП №${it.id} — ${it.name || '—'}` },
}

const blockingGroups = computed(() => {
  const impact = props.blockImpact
  if (!impact) return []
  return (['purchases', 'wishes', 'contracts', 'commercial_requests'] as const)
    .filter(key => (impact[key]?.count ?? 0) > 0)
    .map(key => ({ key, ...GROUP_META[key], group: impact[key] }))
})
</script>

<style scoped>
.obj-list { max-height: 220px; overflow-y: auto; }
.obj-row {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 0; font-size: 13px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.obj-link { color: rgb(var(--v-theme-primary)); text-decoration: none; }
.obj-link:hover { text-decoration: underline; }
</style>
