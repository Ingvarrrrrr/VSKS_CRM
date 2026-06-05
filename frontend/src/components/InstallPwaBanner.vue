<template>
  <div v-if="visible" class="pwa-install-banner">
    <div class="pwa-install-row">
      <v-icon icon="mdi-cellphone-arrow-down" class="pwa-install-icon" />
      <div class="pwa-install-text">
        <div class="pwa-install-title">{{ iosNeedsSafari ? 'Откройте в Safari' : 'Установить приложение' }}</div>
        <div class="pwa-install-subtitle">{{ iosNeedsSafari ? 'На iPhone установка работает только из Safari' : (isIos ? 'Откроется как отдельное приложение' : 'Быстрый доступ с домашнего экрана') }}</div>
      </div>
      <v-btn size="small" color="primary" variant="flat" @click="onInstall">
        {{ iosNeedsSafari ? 'Как?' : 'Установить' }}
      </v-btn>
      <v-btn size="small" variant="text" icon="mdi-close" @click="dismiss" />
    </div>
  </div>

  <v-dialog v-model="iosDialog" max-width="420" persistent>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon start>mdi-apple</v-icon>
        Установка на iPhone
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="iosDialog = false" />
      </v-card-title>
      <v-card-text>
        <p class="text-body-2 mb-3">
          Нажмите «Установить профиль». Дальше iPhone сам проведёт через 3 шага в Настройках — просто нажимайте кнопки которые он предлагает.
        </p>
        <v-stepper v-model="iosStep" non-linear hide-actions>
          <v-stepper-header>
            <v-stepper-item :value="1" :complete="iosStep > 1" title="Скачать" />
            <v-divider />
            <v-stepper-item :value="2" :complete="iosStep > 2" title="Настройки" />
            <v-divider />
            <v-stepper-item :value="3" title="Готово" />
          </v-stepper-header>
        </v-stepper>
        <v-list density="compact" class="mt-3 text-body-2">
          <v-list-item :class="{ 'text-medium-emphasis': iosStep > 1 }">
            <template #prepend><v-icon size="20">mdi-numeric-1-circle</v-icon></template>
            Нажмите «Установить профиль» — Safari спросит: «Разрешить загрузку профиля?» → <strong>Разрешить</strong>
          </v-list-item>
          <v-list-item :class="{ 'text-medium-emphasis': iosStep > 2 }">
            <template #prepend><v-icon size="20">mdi-numeric-2-circle</v-icon></template>
            Откройте <strong>Настройки</strong> → вверху появится «Профиль загружен» → откройте → <strong>Установить</strong> (введите код-пароль)
          </v-list-item>
          <v-list-item>
            <template #prepend><v-icon size="20">mdi-numeric-3-circle</v-icon></template>
            Готово — на главном экране появится иконка <strong>GALA</strong>
          </v-list-item>
        </v-list>
        <v-alert v-if="iosStep === 1" type="warning" variant="tonal" density="compact" class="mt-3 text-caption">
          iOS покажет красную надпись «Не подписан» — это нормально, профиль безопасен.
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-btn v-if="iosStep === 1" color="primary" variant="flat" block size="large" @click="downloadProfile">
          <v-icon start>mdi-download</v-icon>Установить профиль
        </v-btn>
        <v-btn v-else color="primary" variant="tonal" block @click="iosDialog = false">
          Понятно
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="safariDialog" max-width="420">
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon start>mdi-apple-safari</v-icon>
        Установка только из Safari
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="safariDialog = false" />
      </v-card-title>
      <v-card-text>
        <p class="text-body-2 mb-2">
          На iPhone приложение устанавливается <strong>только через Safari</strong> — в Chrome кнопки установки нет и не появится.
        </p>
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Почему так: Apple разрешает добавлять приложения на домашний экран
          только своему браузеру Safari. Chrome и другие браузеры на iPhone
          работают на движке Apple и этой возможности лишены — это ограничение
          самой iOS, а не нашего приложения.
        </v-alert>
        <v-list density="compact" class="text-body-2">
          <v-list-item>
            <template #prepend><v-icon size="20">mdi-numeric-1-circle</v-icon></template>
            Скопируйте ссылку кнопкой ниже
          </v-list-item>
          <v-list-item>
            <template #prepend><v-icon size="20">mdi-numeric-2-circle</v-icon></template>
            Откройте <strong>Safari</strong> и вставьте ссылку
          </v-list-item>
          <v-list-item>
            <template #prepend><v-icon size="20">mdi-numeric-3-circle</v-icon></template>
            Внизу появится баннер <strong>«Установить приложение»</strong>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-btn color="primary" variant="flat" block size="large" @click="copyLink">
          <v-icon start>{{ linkCopied ? 'mdi-check' : 'mdi-content-copy' }}</v-icon>
          {{ linkCopied ? 'Ссылка скопирована' : 'Скопировать ссылку' }}
        </v-btn>
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
const iosStep = ref(1)
const isIos = ref(false)
const iosNeedsSafari = ref(false)  // iOS-устройство, но браузер не Safari (Chrome/Firefox)
const safariDialog = ref(false)
const linkCopied = ref(false)

function downloadProfile() {
  iosStep.value = 2
  // Trigger profile download — Safari opens the .mobileconfig install flow.
  // Передаём origin: за nginx бэкенд не видит публичный хост → иначе webclip
  // указывал бы на http://localhost:80/ и ярлык был бы мёртвый.
  const base = encodeURIComponent(window.location.origin)
  window.location.href = `/api/install.mobileconfig?base=${base}`
}

let deferredPrompt: any = null

function isStandalone(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as any).standalone === true
}

function isMobile(): boolean {
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
    window.matchMedia('(max-width: 768px)').matches
}

function detectIosDevice(): boolean {
  const ua = navigator.userAgent
  return /iPhone|iPad|iPod/i.test(ua) ||
    (ua.includes('Macintosh') && 'ontouchend' in document)
}

function detectIos(): boolean {
  const ua = navigator.userAgent
  return detectIosDevice() && /Safari/i.test(ua) && !/CriOS|FxiOS/i.test(ua)
}

async function copyLink() {
  try {
    await navigator.clipboard.writeText(window.location.origin + '/')
    linkCopied.value = true
    setTimeout(() => { linkCopied.value = false }, 2500)
  } catch { /* clipboard заблокирован — пользователь скопирует из адресной строки */ }
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
  if (iosNeedsSafari.value) {
    safariDialog.value = true
    return
  }
  if (isIos.value) {
    iosStep.value = 1
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
  } else if (detectIosDevice()) {
    // Chrome/Firefox на iOS: Apple запрещает установку PWA вне Safari и не шлёт
    // beforeinstallprompt → показываем подсказку «откройте в Safari».
    iosNeedsSafari.value = true
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
@media (min-width: 769px) {
  .pwa-install-banner { display: none; }
}
</style>
