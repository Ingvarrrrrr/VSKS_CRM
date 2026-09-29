<template>
  <v-dialog v-model="show" max-width="480">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">Удалить товары?</v-card-title>
      <v-card-text class="px-6">
        <template v-if="blocked.length === 0">
          Будет удалено <strong>{{ count }}</strong> товаров из каталога.
        </template>
        <template v-else>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
            {{ blocked.length }} из {{ count }} не удалены — используются в других документах:
          </v-alert>
          <div class="obj-list">
            <div v-for="b in blocked" :key="b.id" class="obj-row">
              <strong>{{ b.name }}</strong>
              <div class="text-caption text-medium-emphasis">{{ b.message }}</div>
            </div>
          </div>
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">{{ blocked.length > 0 ? 'Закрыть' : 'Отмена' }}</v-btn>
        <v-btn v-if="blocked.length === 0" color="error" :loading="deleting" @click="$emit('confirm')">Удалить {{ count }} товаров</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  count: number
  deleting: boolean
  blocked?: { id: number; name: string; message: string }[]
}>(), { blocked: () => [] })
defineEmits<{ (e: 'confirm'): void }>()

const show = defineModel<boolean>('modelValue', { required: true })
</script>

<style scoped>
.obj-list { max-height: 260px; overflow-y: auto; }
.obj-row { padding: 6px 0; border-bottom: 1px solid rgba(0,0,0,0.06); }
</style>
