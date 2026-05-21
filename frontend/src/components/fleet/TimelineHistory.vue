<template>
  <div class="timeline">
    <div
      v-for="event in events"
      :key="event.id"
      class="tl-item"
    >
      <!-- Left: dot + vertical line -->
      <div class="tl-item__left">
        <div class="tl-item__dot" :class="`tl-item__dot--${event.status}`" />
        <div class="tl-item__line" />
      </div>

      <!-- Content -->
      <div class="tl-item__content">
        <div class="tl-item__title">{{ event.title }}</div>
        <div v-if="event.description" class="tl-item__desc">{{ event.description }}</div>
        <div v-if="event.user || event.timestamp" class="tl-item__meta">
          <span v-if="event.user" class="tl-item__user">{{ event.user }}</span>
          <span v-if="event.timestamp" class="tl-item__time">{{ formatTs(event.timestamp) }}</span>
        </div>
      </div>
    </div>

    <div v-if="!events.length" class="tl-empty">История событий пуста</div>
  </div>
</template>

<script setup lang="ts">
export interface TimelineEvent {
  id: number | string
  status: 'done' | 'active' | 'pending'
  title: string
  description?: string
  timestamp?: string
  user?: string
}

defineProps<{
  events: TimelineEvent[]
}>()

function formatTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}
</script>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.tl-item {
  display: grid;
  grid-template-columns: 20px 1fr;
  gap: 10px;
  position: relative;
}

.tl-item__left {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.tl-item__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
  border: 2px solid transparent;
  transition: background 0.2s;
}

.tl-item__dot--done {
  background: var(--ok, #22c997);
  border-color: var(--ok, #22c997);
}

.tl-item__dot--active {
  background: var(--accent, #6aa6ff);
  border-color: var(--accent, #6aa6ff);
  box-shadow: 0 0 0 3px rgba(106, 166, 255, 0.2);
}

.tl-item__dot--pending {
  background: transparent;
  border-color: var(--muted, #8a93a8);
}

.tl-item__line {
  width: 2px;
  flex: 1;
  background: var(--line, #222838);
  margin-top: 4px;
  min-height: 12px;
}

.tl-item:last-child .tl-item__line {
  display: none;
}

.tl-item__content {
  padding-bottom: 12px;
  padding-top: 2px;
}

.tl-item__title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text, #e9edf5);
}

.tl-item__desc {
  font-size: 11.5px;
  color: var(--muted, #8a93a8);
  margin-top: 2px;
}

.tl-item__meta {
  display: flex;
  gap: 8px;
  margin-top: 3px;
  flex-wrap: wrap;
}

.tl-item__user {
  font-size: 11px;
  color: var(--accent, #6aa6ff);
  font-weight: 600;
}

.tl-item__time {
  font-size: 11px;
  color: var(--muted, #8a93a8);
  font-weight: 600;
}

.tl-empty {
  font-size: 12px;
  color: var(--muted, #8a93a8);
  font-style: italic;
  padding: 8px 0;
}
</style>
