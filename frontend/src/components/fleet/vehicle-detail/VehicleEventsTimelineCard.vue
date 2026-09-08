<!-- Лента событий (Slice 2) — объединённая история пробега/чек-листа/полей/передач. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-timeline-text-outline" size="small" class="mr-2" />
      Лента событий
      <span class="vp-box-sub ml-auto">последние 8</span>
    </v-card-title>
    <v-card-text>
      <div v-if="events.length === 0" class="text-medium-emphasis text-body-2 py-2">
        Событий пока нет
      </div>
      <div v-else class="vp-tl">
        <div
          v-for="(ev, i) in events"
          :key="i"
          class="vp-tl-item"
          :class="`vp-tl-item--${ev.dotClass}`"
        >
          <div class="vp-tl-dot" :class="`vp-tl-dot--${ev.dotClass}`"></div>
          <div class="vp-tl-content">
            <div class="vp-tl-title">{{ ev.title }}</div>
            <div v-if="ev.body" class="vp-tl-body">{{ ev.body }}</div>
            <time class="vp-tl-time">{{ formatDate(ev.date) }}</time>
          </div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import type { TimelineEvent } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  events: TimelineEvent[]
  formatDate: (d?: string | null) => string
}>()
</script>
