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
      injectRegister: 'auto',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png', 'pwa-192x192.png', 'pwa-512x512.png'],
      manifest: {
        name: 'VSKS CRM',
        short_name: 'VSKS',
        description: 'Система управления субсидиями',
        theme_color: '#1976D2',
        background_color: '#0F172A',
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
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024, // 5 MiB
        importScripts: ['/custom-sw.js'],
        // Новый SW сразу заменяет старый и берёт под контроль все открытые вкладки.
        // После каждого deploy клиенты получают свежий bundle без ручных действий.
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        // SPA-fallback: любой navigation попадает на index.html (precache),
        // но ТОЛЬКО не для /api/* (они проксируются NetworkOnly ниже).
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/deploy\//],
        runtimeCaching: [
          {
            // ВСЕ API-запросы — NetworkOnly. PUT/POST/DELETE летят в backend
            // напрямую, GET всегда возвращает свежие данные.
            // Раньше /api/* был NetworkFirst → workbox кэшировал ответы и
            // отдавал stale при медленной сети → save в БД проходил, но UI
            // показывал старые значения после reopen диалога.
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
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
