<template>
  <div
    class="gala-swarm-preview-wrap"
    :class="{ 'gala-swarm-preview-wrap--dark': isDark }"
    @pointerdown.stop
    @mousedown.stop
  >
    <button
      v-if="!expanded"
      type="button"
      class="gala-swarm-preview-toggle"
      title="Панель проверки Swarm Rebuild (Alt+Shift+S)"
      @click="expanded = true"
    >
      🛠 Swarm Демо
    </button>

    <div v-else class="gala-swarm-preview-bar">
      <span class="gala-swarm-preview-label">SWARM:</span>
      <button
        type="button"
        class="gala-swarm-preview-btn gala-swarm-preview-btn--accent"
        title="Сделать снимок открытой страницы и пересобрать её курсорами (Alt+Shift+S)"
        @click="rebuildLiveScreen"
      >
        ✨ Собрать живой экран (Alt+Shift+S)
      </button>
      <button
        type="button"
        class="gala-swarm-preview-btn"
        :class="{ 'gala-swarm-preview-btn--active': swarmSimEnabled }"
        title="Искусственно замедлить переходы до 2.6с на localhost, чтобы видеть сборку на реальных вкладках"
        @click="toggleSim"
      >
        🐢 Переходы 2.6с: {{ swarmSimEnabled ? 'ВКЛ' : 'ВЫКЛ' }}
      </button>
      <span class="gala-swarm-preview-sep" />
      <button
        v-for="item in SECTIONS"
        :key="item.key"
        type="button"
        class="gala-swarm-preview-btn"
        :class="{ 'gala-swarm-preview-btn--active': activeKey === item.key }"
        @click="selectSection(item)"
      >
        {{ item.label }}
      </button>
      <span class="gala-swarm-preview-sep" />
      <button type="button" class="gala-swarm-preview-btn" @click="finish">⚡ Завершить</button>
      <button type="button" class="gala-swarm-preview-btn" @click="triggerLongWait">🎮 Игра (&gt;2с)</button>
      <button type="button" class="gala-swarm-preview-btn" @click="toggleTheme">{{ isDark ? '☀' : '🌙' }}</button>
      <button type="button" class="gala-swarm-preview-btn" title="Свернуть панель" @click="expanded = false">✕</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import {
  completeSwarmPreview,
  setSwarmSimEnabled,
  startSwarmPreview,
  swarmSimEnabled,
} from '../../composables/useLongWait'

interface SectionPreset {
  key: string
  label: string
  path: string
  booting?: boolean
}

const props = defineProps<{ autoOpen?: boolean }>()

const SECTIONS: SectionPreset[] = [
  { key: 'subsidies', label: 'Субсидии', path: '/subsidies' },
  { key: 'orders', label: 'Закупки', path: '/orders' },
  { key: 'form', label: 'Карточка', path: '/orders/4884/edit' },
  { key: 'dashboard', label: 'Дашборд', path: '/dashboard' },
]

const route = useRoute()
const router = useRouter()
const theme = useTheme()
const expanded = ref(!!props.autoOpen)
const activeKey = ref('subsidies')
const isDark = computed(() => theme.global.name.value === 'dark')

function currentPreset(): SectionPreset {
  return SECTIONS.find((s) => s.key === activeKey.value) || SECTIONS[0]
}

function selectSection(item: SectionPreset) {
  activeKey.value = item.key
  if (!item.booting && route.path !== item.path) {
    router.push(item.path).catch(() => {})
  }
  startSwarmPreview(item.path, { booting: !!item.booting })
}

function rebuildLiveScreen() {
  startSwarmPreview(route.path, { liveDom: true })
}

function toggleSim() {
  setSwarmSimEnabled(!swarmSimEnabled.value)
}

function finish() {
  completeSwarmPreview()
}

function triggerLongWait() {
  const item = currentPreset()
  startSwarmPreview(item.path, { booting: !!item.booting, longWait: true })
}

function toggleTheme() {
  const next = isDark.value ? 'light' : 'dark'
  theme.global.name.value = next
  try {
    localStorage.setItem('theme', next)
  } catch {}
}

onMounted(() => {
  if (props.autoOpen) startSwarmPreview('/subsidies')
})
</script>

<style scoped>
.gala-swarm-preview-wrap {
  position: fixed;
  top: 54px;
  right: 16px;
  z-index: 10050;
  font-family: var(--font-ui, 'Inter Tight', sans-serif);
  color: #1c1916;
}

.gala-swarm-preview-wrap--dark { color: #f1f5f9; }

.gala-swarm-preview-toggle {
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid rgba(194, 98, 10, 0.45);
  background: rgba(255, 255, 255, 0.92);
  color: #c2620a;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 3px 12px rgba(28, 25, 22, 0.12);
}

.gala-swarm-preview-wrap--dark .gala-swarm-preview-toggle {
  background: rgba(28, 25, 22, 0.92);
  border-color: rgba(251, 146, 60, 0.45);
  color: #fb923c;
}

.gala-swarm-preview-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  max-width: calc(100vw - 32px);
  padding: 6px 10px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(90, 84, 72, 0.24);
  box-shadow: 0 6px 24px rgba(28, 25, 22, 0.14);
  backdrop-filter: blur(8px);
}

.gala-swarm-preview-wrap--dark .gala-swarm-preview-bar {
  background: rgba(28, 25, 22, 0.95);
  border-color: rgba(240, 236, 228, 0.18);
}

.gala-swarm-preview-label {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  font-weight: 700;
  opacity: 0.7;
}

.gala-swarm-preview-sep {
  width: 1px;
  height: 18px;
  background: rgba(90, 84, 72, 0.24);
  margin: 0 2px;
}

.gala-swarm-preview-btn {
  border: 1px solid rgba(90, 84, 72, 0.22);
  background: transparent;
  color: inherit;
  font-size: 11.5px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 8px;
  cursor: pointer;
}

.gala-swarm-preview-btn:hover { background: rgba(194, 98, 10, 0.12); }

.gala-swarm-preview-btn--active {
  background: #c2620a;
  border-color: #c2620a;
  color: #ffffff;
}

.gala-swarm-preview-wrap--dark .gala-swarm-preview-btn--active {
  background: #fb923c;
  border-color: #fb923c;
  color: #0f0e0c;
}

.gala-swarm-preview-btn--accent {
  border-color: rgba(194, 98, 10, 0.45);
  color: #c2620a;
}

.gala-swarm-preview-wrap--dark .gala-swarm-preview-btn--accent {
  border-color: rgba(251, 146, 60, 0.45);
  color: #fb923c;
}
</style>
