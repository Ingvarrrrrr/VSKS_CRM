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
        // Phase 26-FFF: убрали 'html' из globPatterns — index.html больше не precached.
        // Раньше старый index.html отдавался из SW-кэша → ссылки на старые JS/CSS →
        // пользователь не получал свежие коммиты без Ctrl+F5. Теперь NetworkFirst через
        // runtimeCaching ниже: сначала пробуем сеть (timeout 3s), fallback на кэш только
        // если оффлайн. Assets (JS/CSS) precache'ятся как обычно — у них immutable hash.
        globPatterns: ['**/*.{js,css,ico,png,svg,woff,woff2,ttf}'],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024, // 5 MiB
        importScripts: ['/custom-sw.js'],
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        navigateFallbackDenylist: [/^\/api\//, /^\/deploy\//],
        runtimeCaching: [
          {
            // PDF/DOCX/XLSX export — крупный traffic, не кэшируем.
            urlPattern: /^\/api\/.+\/(documents|export)\//,
            handler: 'NetworkOnly',
          },
          {
            // Phase 26-FFF: index.html / любой navigate → NetworkFirst. Свежий HTML
            // → свежие asset-ссылки → новый bundle подхватывается без жёсткой перезагрузки.
            urlPattern: ({ request }) => request.mode === 'navigate',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'html-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 5, maxAgeSeconds: 60 * 60 * 24 },
            },
          },
          {
            // CRM-данные и права ВСЕГДА живые: никакого SW-кэша на /api/.
            // Раньше NetworkFirst с api-cache (до 12ч) отдавал stale GET-ответы —
            // пользователь видел старые субсидии/права после отзыва доступа.
            // NetworkOnly = всегда сеть, кэш по API физически не создаётся.
            urlPattern: /^\/api\//,
            handler: 'NetworkOnly',
          },
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
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
