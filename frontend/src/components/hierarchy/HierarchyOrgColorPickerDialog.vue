<template>
  <Teleport to="body">
    <v-dialog v-model="show" max-width="360" :z-index="9999">
      <v-card>
        <v-card-title class="pa-4 text-body-1">
          <v-icon icon="mdi-palette" class="mr-2" />Цвет организации
        </v-card-title>
        <v-card-text class="pa-4 pt-0 d-flex flex-wrap gap-2 justify-center">
          <div
            v-for="c in colors"
            :key="c"
            :style="{ background: c, width: '32px', height: '32px', borderRadius: '50%', cursor: 'pointer', border: '2px solid #fff', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }"
            @click="emit('pick', c)"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="show = false">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{ colors: string[] }>()
const emit = defineEmits<{ pick: [color: string] }>()
const show = defineModel<boolean>({ default: false })
</script>
