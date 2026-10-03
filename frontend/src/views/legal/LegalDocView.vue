<template>
  <div class="legal-page">
    <div class="legal-page-inner">

      <!-- Document found -->
      <template v-if="doc">
        <div class="legal-topbar">
          <button class="legal-back" type="button" @click="goBack">
            <v-icon icon="mdi-arrow-left" size="18" />
            Вернуться
          </button>
        </div>

        <v-alert
          v-if="!OPERATOR.filled"
          type="warning"
          variant="tonal"
          density="compact"
          class="legal-draft-alert"
        >
          Документ опубликован в редакции с незаполненными реквизитами
        </v-alert>

        <header class="legal-header">
          <h1 class="legal-title">{{ doc.title }}</h1>
          <p class="legal-meta">Редакция {{ doc.version }}, действует с {{ doc.effectiveDate }}</p>
        </header>

        <!-- eslint-disable-next-line vue/no-v-html -- html приходит из legal/build.py, скрипты вырезаны на сборке -->
        <div class="legal-content" v-html="doc.html" />

        <nav v-if="otherDocs.length" class="legal-other-docs">
          <div class="legal-other-docs-title">Другие правовые документы</div>
          <ul class="legal-other-docs-list">
            <li v-for="d in otherDocs" :key="d.slug">
              <router-link :to="d.route">{{ d.title }}</router-link>
            </li>
          </ul>
        </nav>
      </template>

      <!-- Unknown slug -->
      <template v-else>
        <div class="legal-topbar">
          <button class="legal-back" type="button" @click="goBack">
            <v-icon icon="mdi-arrow-left" size="18" />
            Вернуться
          </button>
        </div>

        <div class="legal-not-found">
          <v-icon icon="mdi-file-question-outline" size="56" class="mb-3" color="warning" />
          <h1 class="legal-title">Документ не найден</h1>
          <p class="legal-meta">Такого правового документа не существует. Возможно, ссылка устарела.</p>

          <ul class="legal-other-docs-list mt-6">
            <li v-for="d in allDocs" :key="d.slug">
              <router-link :to="d.route">{{ d.title }}</router-link>
            </li>
          </ul>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LEGAL_DOCS, LEGAL_DOC_LIST, OPERATOR } from '@/legal/documents.generated'

const route = useRoute()
const router = useRouter()

const slug = computed(() => String(route.params.slug || ''))
const doc = computed(() => LEGAL_DOCS[slug.value])

const allDocs = computed(() => LEGAL_DOC_LIST)
const otherDocs = computed(() => LEGAL_DOC_LIST.filter(d => d.slug !== slug.value))

function goBack() {
  // Открыт напрямую (новая вкладка из ConsentCheckbox, прямой заход по ссылке) —
  // истории для router.back() нет, возвращаемся на лендинг, а не в пустоту.
  const historyState = window.history.state as { back?: string | null } | null
  if (historyState && historyState.back) {
    router.back()
  } else {
    router.push('/')
  }
}
</script>

<style scoped>
.legal-page {
  min-height: 100vh;
  background: var(--crm-bg, rgb(var(--v-theme-background)));
  padding: 24px 16px 64px;
}
.legal-page-inner {
  max-width: 760px;
  margin: 0 auto;
}

.legal-topbar {
  margin-bottom: 20px;
}
.legal-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: var(--crm-text-muted, rgba(var(--v-theme-on-surface), 0.6));
  padding: 4px 0;
}
.legal-back:hover {
  color: rgb(var(--v-theme-primary));
}

.legal-draft-alert {
  margin-bottom: 20px;
}

.legal-header {
  margin-bottom: 28px;
  border-bottom: 1px solid var(--crm-border, rgba(0, 0, 0, 0.08));
  padding-bottom: 20px;
}
.legal-title {
  font-size: 1.6rem;
  font-weight: 700;
  line-height: 1.3;
  color: var(--crm-text, rgb(var(--v-theme-on-surface)));
  margin: 0 0 8px;
}
.legal-meta {
  font-size: 13px;
  color: var(--crm-text-muted, rgba(var(--v-theme-on-surface), 0.6));
  margin: 0;
}

.legal-not-found {
  text-align: center;
  padding: 48px 16px;
}
.legal-not-found .legal-title { margin-bottom: 8px; }
.legal-not-found .legal-meta { margin-bottom: 8px; }

/* ══════ Типографика документа ══════
   Колонка ограничена по ширине ~70 символов (ch — ширина символа "0" текущего
   шрифта), не по пикселям, чтобы читаемость не «плыла» при смене гарнитуры. */
.legal-content {
  max-width: 70ch;
  margin: 0 auto;
  color: var(--crm-text-secondary, rgba(var(--v-theme-on-surface), 0.87));
  font-size: 15px;
  line-height: 1.7;
}
.legal-content :deep(h1),
.legal-content :deep(h2),
.legal-content :deep(h3),
.legal-content :deep(h4) {
  color: var(--crm-text, rgb(var(--v-theme-on-surface)));
  font-weight: 700;
  line-height: 1.35;
  margin: 1.6em 0 0.6em;
}
.legal-content :deep(h1) { font-size: 1.35rem; }
.legal-content :deep(h2) { font-size: 1.2rem; }
.legal-content :deep(h3) { font-size: 1.05rem; }
.legal-content :deep(h1:first-child),
.legal-content :deep(h2:first-child),
.legal-content :deep(h3:first-child) {
  margin-top: 0;
}
.legal-content :deep(p) {
  margin: 0 0 1em;
}
.legal-content :deep(ul),
.legal-content :deep(ol) {
  margin: 0 0 1.2em;
  padding-left: 1.4em;
}
.legal-content :deep(li) {
  margin-bottom: 0.4em;
}
.legal-content :deep(a) {
  color: rgb(var(--v-theme-primary));
}
.legal-content :deep(strong) { color: var(--crm-text, rgb(var(--v-theme-on-surface))); }
.legal-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 1.4em;
  font-size: 14px;
}
.legal-content :deep(th),
.legal-content :deep(td) {
  border: 1px solid var(--crm-border, rgba(0, 0, 0, 0.12));
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}
.legal-content :deep(th) {
  background: var(--crm-table-header, rgba(0, 0, 0, 0.03));
}
.legal-content :deep(blockquote) {
  margin: 0 0 1.2em;
  padding: 4px 16px;
  border-left: 3px solid var(--crm-border-strong, rgba(0, 0, 0, 0.15));
  color: var(--crm-text-muted, rgba(var(--v-theme-on-surface), 0.6));
}
.legal-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--crm-border, rgba(0, 0, 0, 0.08));
  margin: 2em 0;
}

.legal-other-docs {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--crm-border, rgba(0, 0, 0, 0.08));
}
.legal-other-docs-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--crm-text-muted, rgba(var(--v-theme-on-surface), 0.6));
  margin-bottom: 10px;
}
.legal-other-docs-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.legal-other-docs-list a {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  font-size: 14px;
}
.legal-other-docs-list a:hover {
  text-decoration: underline;
}
</style>
