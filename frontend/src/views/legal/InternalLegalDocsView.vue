<template>
  <v-container fluid class="pa-4 internal-legal-docs">
    <v-card elevation="2">
      <v-card-title class="text-h6">
        Правовые документы — внутренние
      </v-card-title>
      <v-card-subtitle class="pb-2">
        Документы по 152-ФЗ, которые не публикуются на сайте (модель угроз,
        акт уровня защищённости, уведомление в РКН, приказы и т. п.) —
        доступны только администратору. Публичные документы открыты всем
        без входа: раздел «Правовые документы» в подвале сайта.
      </v-card-subtitle>

      <v-divider />

      <v-card-text v-if="loading" class="d-flex justify-center align-center py-8">
        <v-progress-circular indeterminate color="primary" />
        <span class="ml-4 text-body-2">Загрузка списка документов…</span>
      </v-card-text>

      <v-alert v-else-if="loadError" type="error" variant="tonal" class="ma-4">
        {{ loadError }}
        <template #append>
          <v-btn size="small" variant="text" @click="loadList">Повторить</v-btn>
        </template>
      </v-alert>

      <v-row v-else no-gutters class="internal-legal-docs-body">
        <v-col cols="12" md="4" class="internal-legal-docs-list">
          <v-list density="compact" nav>
            <v-list-item
              v-for="d in docs"
              :key="d.slug"
              :active="d.slug === selectedSlug"
              :title="d.title"
              :subtitle="`Редакция ${d.version}${d.effective_date ? ', от ' + d.effective_date : ''}`"
              @click="openDoc(d.slug)"
            />
            <v-list-item v-if="docs.length === 0" title="Документов нет" />
          </v-list>
        </v-col>

        <v-col cols="12" md="8" class="internal-legal-docs-content">
          <div v-if="docLoading" class="d-flex justify-center align-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-alert v-else-if="docError" type="error" variant="tonal" class="ma-4">
            {{ docError }}
          </v-alert>
          <template v-else-if="selectedDoc">
            <div class="internal-legal-docs-toolbar">
              <div>
                <div class="text-subtitle-1 font-weight-bold">{{ selectedDoc.title }}</div>
                <div class="text-caption text-medium-emphasis">
                  Редакция {{ selectedDoc.version }}<span v-if="selectedDoc.effective_date">, действует с {{ selectedDoc.effective_date }}</span>
                </div>
              </div>
              <v-btn
                size="small"
                variant="tonal"
                prepend-icon="mdi-printer-outline"
                @click="printDoc"
              >
                Печать
              </v-btn>
            </div>
            <v-divider class="mb-4" />
            <!-- eslint-disable-next-line vue/no-v-html -- html собран legal/build.py из markdown, скрипты не генерируются -->
            <div class="internal-legal-doc-html" v-html="selectedDoc.html" />
          </template>
          <div v-else class="text-body-2 text-medium-emphasis pa-4">
            Выберите документ из списка слева.
          </div>
        </v-col>
      </v-row>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiFetch } from '@/api'

interface InternalLegalDocSummary {
  slug: string
  title: string
  version: string
  effective_date: string
}

interface InternalLegalDoc extends InternalLegalDocSummary {
  html: string
}

const docs = ref<InternalLegalDocSummary[]>([])
const loading = ref(true)
const loadError = ref('')

const selectedSlug = ref('')
const selectedDoc = ref<InternalLegalDoc | null>(null)
const docLoading = ref(false)
const docError = ref('')

async function loadList() {
  loading.value = true
  loadError.value = ''
  try {
    docs.value = await apiFetch<InternalLegalDocSummary[]>('/admin/legal-docs')
  } catch (e: any) {
    loadError.value = e?.message || 'Не удалось загрузить список документов'
  } finally {
    loading.value = false
  }
}

async function openDoc(slug: string) {
  selectedSlug.value = slug
  docLoading.value = true
  docError.value = ''
  selectedDoc.value = null
  try {
    selectedDoc.value = await apiFetch<InternalLegalDoc>(`/admin/legal-docs/${encodeURIComponent(slug)}`)
  } catch (e: any) {
    docError.value = e?.message || 'Не удалось загрузить документ'
  } finally {
    docLoading.value = false
  }
}

function printDoc() {
  window.print()
}

onMounted(loadList)
</script>

<style scoped>
.internal-legal-docs-body {
  min-height: 60vh;
}
.internal-legal-docs-list {
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.internal-legal-docs-content {
  padding: 16px 24px;
}
.internal-legal-docs-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.internal-legal-doc-html :deep(h1),
.internal-legal-doc-html :deep(h2),
.internal-legal-doc-html :deep(h3) {
  margin: 1.2em 0 0.5em;
}
.internal-legal-doc-html :deep(h1:first-child),
.internal-legal-doc-html :deep(h2:first-child),
.internal-legal-doc-html :deep(h3:first-child) {
  margin-top: 0;
}
.internal-legal-doc-html :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1.2em;
}
.internal-legal-doc-html :deep(th),
.internal-legal-doc-html :deep(td) {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}

@media print {
  .internal-legal-docs-list,
  .internal-legal-docs-toolbar {
    display: none !important;
  }
}
</style>
