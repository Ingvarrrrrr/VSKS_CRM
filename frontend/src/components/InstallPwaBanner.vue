<template>
  <div v-if="visible" class="pwa-install-banner">
    <div class="pwa-install-row">
      <v-icon icon="mdi-cellphone-arrow-down" class="pwa-install-icon" />
      <div class="pwa-install-text">
        <div class="pwa-install-title">Установить приложение</div>
        <div class="pwa-install-subtitle">{{ isIos ? 'Откроется как отдельное приложение' : 'Быстрый доступ с домашнего экрана' }}</div>
      </div>
      <v-btn size="small" color="primary" variant="flat" @click="onInstall">
        Установить
      </v-btn>
      <v-btn size="small" variant="text" icon="mdi-close" @click="dismiss" />
    </div>
  </div>

  <v-dialog v-model="iosDialog" max-width="420">
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon start>mdi-apple</v-icon>
        Установка на iPhone / iPad
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="iosDialog = false" />
      </v-card-title>
      <v-card-text>
        <ol class="pwa-ios-steps">
          <li>Нажмите кнопку <strong>«Поделиться»</strong> внизу Safari (квадрат со стрелкой вверх).</li>
          <li>Прокрутите меню и выберите <strong>«На экран „Домой"»</strong> (<v-icon size="18" icon="mdi-plus-box-outline" />).</li>
          <li>Подтвердите кнопкой <strong>«Добавить»</strong>.</li>
        </ol>
        <v-alert type="info" variant="tonal" density="compact" class="mt-3 text-caption">
          После добавления откройте приложение с домашнего экрана — оно будет работать как нативное.
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" variant="tonal" @click="iosDialog = false">Понятно</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'

const DISMISS_KEY = 'pwa_install_dismissed_at'
const DISMISS_DAYS = 7

const visible = ref(false)
const iosDialog = ref(false)
const isIos = ref(false)

let deferredPrompt: any = null

function isStandalone(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as any).standalone === true
}

function isMobile(): boolean {
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
    window.matchMedia('(max-width: 768px)').matches
}

function detectIos(): boolean {
  const ua = navigator.userAgent
  const ios = /iPhone|iPad|iPod/i.test(ua) ||
    (ua.includes('Macintosh') && 'ontouchend' in document)
  return ios && /Safari/i.test(ua) && !/CriOS|FxiOS/i.test(ua)
}

function recentlyDismissed(): boolean {
  const ts = Number(localStorage.getItem(DISMISS_KEY) || 0)
  if (!ts) return false
  return (Date.now() - ts) < DISMISS_DAYS * 24 * 60 * 60 * 1000
}

function onBeforeInstallPrompt(e: Event) {
  e.preventDefault()
  deferredPrompt = e
  if (!recentlyDismissed() && isMobile() && !isStandalone()) {
    visible.value = true
  }
}

async function onInstall() {
  if (isIos.value) {
    iosDialog.value = true
    return
  }
  if (!deferredPrompt) return
  const evt = deferredPrompt
  deferredPrompt = null
  visible.value = false
  try {
    evt.prompt()
    await evt.userChoice
  } catch { /* user dismissed native prompt */ }
}

function dismiss() {
  visible.value = false
  localStorage.setItem(DISMISS_KEY, String(Date.now()))
}

function onAppInstalled() {
  visible.value = false
  deferredPrompt = null
}

onMounted(() => {
  if (isStandalone()) return
  if (!isMobile()) return
  if (recentlyDismissed()) return

  window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
  window.addEventListener('appinstalled', onAppInstalled)

  // iOS Safari doesn't fire beforeinstallprompt — show banner with instructions
  if (detectIos()) {
    isIos.value = true
    visible.value = true
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
  window.removeEventListener('appinstalled', onAppInstalled)
})
</script>

<style scoped>
.pwa-install-banner {
  position: fixed;
  left: 12px;
  right: 12px;
  bottom: 12px;
  z-index: 1100;
  background: rgb(var(--v-theme-surface));
  border: 1px solid var(--crm-border-strong);
  border-radius: 12px;
  padding: 10px 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.18);
}
.pwa-install-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pwa-install-icon {
  font-size: 28px;
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}
.pwa-install-text {
  flex: 1;
  min-width: 0;
}
.pwa-install-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--crm-text);
}
.pwa-install-subtitle {
  font-size: 12px;
  color: var(--crm-text-muted);
}
.pwa-ios-steps {
  margin: 8px 0 0;
  padding-left: 22px;
  line-height: 1.7;
}
.pwa-ios-steps li {
  margin-bottom: 4px;
}
@media (min-width: 769px) {
  .pwa-install-banner { display: none; }
}
</style>
