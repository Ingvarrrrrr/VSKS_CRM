<!-- Фотогалерея (Slice 2) — превью-плитка + переход на вкладку «Фото». -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-camera-outline" size="small" class="mr-2" />
      Фотогалерея
      <span v-if="photoCount !== null" class="vp-box-sub ml-auto">{{ photoCount }} фото</span>
    </v-card-title>
    <v-card-text>
      <div class="vp-photos-grid">
        <div
          v-for="n in 4"
          :key="n"
          class="vp-photo-cell"
        >
          <v-icon icon="mdi-image-outline" size="20" class="vp-photo-icon" />
        </div>
      </div>
      <v-btn
        class="mt-3"
        variant="tonal"
        color="primary"
        block
        prepend-icon="mdi-image-multiple-outline"
        @click="$emit('open-photos')"
      >
        {{ photoCount !== null ? `Все фото (${photoCount})` : 'Открыть фото' }}
      </v-btn>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
defineProps<{
  photoCount: number | null
}>()

defineEmits<{
  (e: 'open-photos'): void
}>()
</script>
