// Отдельный конфиг vitest — НЕ трогает vite.config.ts (там PWA-плагин, лишний риск).
// Тесты — чистая логика (frontend/src/constants), DOM не нужен, окружение 'node'.
import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.spec.ts', 'src/**/*.test.ts'],
  },
})
