<template>
  <div v-if="needsChoice" class="cookie-banner" role="dialog" aria-label="Выбор cookie и аналогичных технологий хранения данных браузера">
    <div class="cookie-banner-row">
      <span class="cookie-banner-text">
        Мы используем файлы cookie и аналогичные технологии хранения в браузере. Необходимые —
        для входа и настроек интерфейса — работают всегда. Дополнительных (аналитика, реклама)
        сейчас нет; если появятся, они включатся только после «Принять».
        <router-link to="/legal/cookies" target="_blank" class="cookie-banner-link">Подробнее</router-link>
      </span>
      <div class="cookie-banner-actions">
        <v-btn size="small" color="primary" variant="tonal" class="cookie-banner-btn" @click="acceptAll">Принять</v-btn>
        <v-btn size="small" color="primary" variant="tonal" class="cookie-banner-btn" @click="acceptNecessary">Отклонить</v-btn>
      </div>
    </div>
  </div>
  <v-snackbar v-model="savedNoticeVisible" :timeout="4000" location="bottom">
    Выбор сохранён. Изменить можно в «Настройки cookie» внизу страницы.
  </v-snackbar>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useCookieConsent } from '@/composables/useCookieConsent'

const { needsChoice, choose } = useCookieConsent()

const savedNoticeVisible = ref(false)

function acceptAll() {
  choose('all')
  savedNoticeVisible.value = true
}

function acceptNecessary() {
  choose('necessary')
  savedNoticeVisible.value = true
}
</script>

<style scoped>
.cookie-banner {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1050;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid var(--crm-border-strong, rgba(0, 0, 0, 0.12));
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.12);
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  /* Баннер лежит в потоке своего фиксированного слоя, но не перехватывает
     касания вне собственного прямоугольника — только его содержимое кликабельно. */
  pointer-events: auto;
}
/* Смонтирован глобально (App.vue) — на mobile внутри приложения снизу
   экрана уже стоит фиксированный bottom-nav (AppBar.vue .mobile-bottom-nav,
   высота 60px + safe-area, z-index 2000). Поднимаем баннер над ним, иначе
   он перекрывает кнопки таб-баром. На публичных страницах
   (лендинг/логин/регистрация) bottom-nav нет — здесь просто небольшой
   отступ от низа экрана, не баг. */
@media (max-width: 959.98px) {
  .cookie-banner {
    bottom: calc(60px + env(safe-area-inset-bottom));
  }
}
.cookie-banner-row {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.cookie-banner-text {
  flex: 1;
  min-width: 200px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--crm-text-secondary, rgba(var(--v-theme-on-surface), 0.8));
}
.cookie-banner-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  margin-left: 4px;
  white-space: nowrap;
}
.cookie-banner-link:hover {
  text-decoration: none;
}
.cookie-banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cookie-banner-btn {
  min-width: 112px;
}

/* Известное ограничение: на мобильных первым посещением InstallPwaBanner
   (App.vue, вне участка этой задачи) может показаться одновременно и
   визуально перекрыть этот баннер снизу — координации между компонентами
   нет. Cookie-баннер держит меньший z-index (1050 < 1100 у install-баннера),
   поэтому install-баннер в этом случае оказывается сверху и остаётся
   кликабельным; после закрытия/установки cookie-баннер занимает своё место. */
</style>
