import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { VitePWA } from 'vite-plugin-pwa'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false,
      includeAssets: ['favicon.svg', 'apple-touch-icon.png', 'pwa-192x192.png', 'pwa-512x512.png'],
      manifest: {
        name: 'GALA',
        short_name: 'GALA',
        description: 'Управление закупками и бюджетным контролем',
        theme_color: '#fb923c',
        background_color: '#0f0e0c',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // index.html НЕ precache'ится (не в globPatterns) — раньше старый index.html
        // отдавался из SW-кэша → ссылки на старые JS/CSS → пользователь не получал
        // свежие коммиты без Ctrl+F5. Assets (JS/CSS) precache'ятся как обычно —
        // у них immutable hash, cleanupOutdatedCaches чистит старые версии сам.
        globPatterns: ['**/*.{js,css,ico,png,svg,woff,woff2,ttf}'],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024, // 5 MiB
        importScripts: ['/custom-sw.js'],
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        // 2026-09-16, разбор бага «после деплоя пусто, только логотип»: по умолчанию
        // vite-plugin-pwa САМ добавляет navigateFallback:'index.html' (см.
        // node_modules/vite-plugin-pwa defaultWorkbox), если явно не выключить. Он
        // регистрирует свой NavigationRoute ПЕРЕД любым нашим runtimeCaching-правилом
        // для navigate — то есть предыдущая попытка (Phase 26-FFF, NetworkFirst
        // 'html-cache' ниже в истории файла) НИКОГДА реально не выполнялась, весь
        // navigate трафик уходил в скрытый дефолтный роут. А тот роут в паре с
        // createHandlerBoundToURL('index.html') требует index.html В precache —
        // которого там нет (см. комментарий выше) — то есть весь навигационный
        // роутинг SW был в непредсказуемом, не задокументированном состоянии.
        // Явно выключаем дефолт и берём navigate ПОЛНОСТЬЮ под свой контроль —
        // см. custom-sw.js (fetch-хендлер для request.mode==='navigate').
        // Альтернатива «NetworkFirst с версионным маркером» отклонена: потребовала
        // бы встраивать метку сборки в index.html и синхронизировать её с SW на
        // каждый деплой — лишняя движущаяся часть ради выигрыша, которого NetworkOnly
        // даёт бесплатно (протухший HTML физически не может появиться, если он
        // никогда не сохраняется в CacheStorage).
        navigateFallback: undefined,
        runtimeCaching: [
          {
            // PDF/DOCX/XLSX export — крупный traffic, не кэшируем.
            urlPattern: /^\/api\/.+\/(documents|export)\//,
            handler: 'NetworkOnly',
          },
          {
            // CRM-данные и права ВСЕГДА живые: никакого SW-кэша на /api/.
            // Раньше NetworkFirst с api-cache (до 12ч) отдавал stale GET-ответы —
            // пользователь видел старые субсидии/права после отзыва доступа.
            // NetworkOnly = всегда сеть, кэш по API физически не создаётся.
            urlPattern: /^\/api\//,
            handler: 'NetworkOnly',
          },
          // navigate (request.mode==='navigate') НЕ описан здесь намеренно: generateSW
          // умеет отдавать только строковые стратегии (NetworkFirst/NetworkOnly/...),
          // а нам нужен NetworkOnly + собственный офлайн-фолбэк без обращения к
          // CacheStorage — это гибче сделать напрямую в custom-sw.js одним
          // fetch-листенером, зарегистрированным ДО генерируемого workbox-роутинга
          // (importScripts исполняется первым). См. custom-sw.js.
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3002,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:80',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
