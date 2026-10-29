<template>
  <Transition name="duck-fade">
    <button
      v-if="showButton"
      type="button"
      class="duck-play-btn"
      @click="openGame"
    >
      ▶ Поиграть, пока грузится
    </button>
  </Transition>
  <DuckShootWindow v-model:open="gameOpen" @close="gameOpen = false" />
</template>

<script setup lang="ts">
// Кнопка-триггер мини-игры «Утиная охота» — показывается только когда
// загрузка идёт уже долго (isLongWait из useLongWait.ts, единственный
// источник этого признака, ПРАВИЛО №6) и только внутри приложения
// (не на публичных страницах входа/регистрации/лендинге — тот же список
// PUBLIC_ROUTES, что уже использует App.vue для AppBar/showAppBar).
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ensureLongWaitListener, isLongWait } from '../../composables/useLongWait'
import DuckShootWindow from './DuckShootWindow.vue'

const PUBLIC_ROUTES = ['/', '/login', '/register', '/verify-email', '/reset-password', '/consent-required']

const route = useRoute()
const gameOpen = ref(false)

const showButton = computed(() =>
  isLongWait.value && !gameOpen.value && !PUBLIC_ROUTES.includes(route.path)
)

function openGame() {
  gameOpen.value = true
}

onMounted(() => {
  ensureLongWaitListener()
})
</script>

<style scoped>
.duck-play-btn {
  position: fixed;
  right: 24px;
  bottom: calc(24px + env(safe-area-inset-bottom, 0px));
  z-index: 2400;
  background: #fff;
  color: #111;
  border: 1px solid #111;
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 13px;
  padding: 10px 14px;
  cursor: pointer;
}
.duck-play-btn:hover {
  background: #111;
  color: #fff;
}

.duck-fade-enter-active,
.duck-fade-leave-active {
  transition: opacity 0.2s ease;
}
.duck-fade-enter-from,
.duck-fade-leave-to {
  opacity: 0;
}
</style>
