<template>
  <!-- ── Templates Dialog (multi-type) ── -->
  <v-dialog v-model="showTemplateDialog" max-width="1100" scrollable :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-file-document-multiple-outline" color="indigo" class="mr-2" />
        Шаблоны документов
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showTemplateDialog = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-3">
        <div class="text-caption text-medium-emphasis mb-3">{{ templateSubsidy?.name }}</div>
        <v-alert type="info" variant="tonal" density="compact" class="mb-4" text="Скачайте текущий шаблон (в нём уже расставлены переменные), отредактируйте в Word и загрузите обратно — он будет использоваться для этой субсидии вместо глобального. Список переменных с примерами — ниже, полное руководство — кнопка внизу." />

        <v-list density="compact">
          <v-list-item v-for="t in subsidyTemplatesList" :key="t.doc_type" class="px-0 mb-2">
            <template #prepend>
              <v-icon :color="t.has_custom ? 'green' : 'grey'" class="mr-2">
                {{ t.has_custom ? 'mdi-check-circle' : 'mdi-circle-outline' }}
              </v-icon>
            </template>
            <template #title>
              <span class="text-body-2 font-weight-medium">{{ t.label }}</span>
              <v-chip v-if="t.has_custom" size="x-small" color="green" variant="tonal" class="ml-2">свой</v-chip>
              <v-chip v-else-if="t.has_global" size="x-small" color="grey" variant="tonal" class="ml-2">глобальный</v-chip>
              <v-chip v-else size="x-small" color="warning" variant="tonal" class="ml-2">нет шаблона</v-chip>
              <v-tooltip v-if="t.has_custom && t.render_ok === false" location="top"
                text="Шаблон содержит синтаксическую ошибку docxtpl. Загрузите исправленную версию.">
                <template #activator="{ props: tipProps }">
                  <v-chip v-bind="tipProps" size="x-small" variant="flat" prepend-icon="mdi-alert"
                    class="ml-2" style="background-color:#fb923c; color:white; cursor:default">
                    Шаблон не работает
                  </v-chip>
                </template>
              </v-tooltip>
            </template>
            <template #append>
              <div class="d-flex gap-1">
                <v-btn
                  v-if="t.has_custom || t.has_global"
                  icon="mdi-download" variant="text" size="small" color="indigo"
                  title="Скачать текущий шаблон"
                  @click="downloadSubsidyTemplate(t.doc_type)"
                />
                <v-btn
                  icon="mdi-upload" variant="text" size="small" color="primary"
                  title="Загрузить свой шаблон"
                  @click="triggerTemplateUpload(t.doc_type)"
                />
                <v-btn
                  v-if="t.has_custom"
                  icon="mdi-delete-outline" variant="text" size="small" color="error"
                  title="Удалить — вернётся к глобальному"
                  @click="deleteSubsidyTemplate(t.doc_type)"
                />
              </div>
            </template>
          </v-list-item>
        </v-list>

        <!-- Template variables reference panel -->
        <v-expansion-panels variant="accordion" class="mt-3">
          <v-expansion-panel title="Доступные переменные шаблона">
            <template #text>
              <v-text-field
                v-model="varsSearch"
                prepend-inner-icon="mdi-magnify"
                label="Поиск по переменной или описанию..."
                density="compact"
                hide-details
                clearable
                class="mb-2"
              />
              <v-data-table
                v-resizable-columns="'subsidies-template-vars'"
                :headers="[
                  { title: 'Переменная', key: 'var', width: '280px', minWidth: '280px' },
                  { title: 'Описание', key: 'description' },
                  { title: 'Пример записи в шаблоне', key: 'example_template', width: '22%' },
                  { title: 'Что получится', key: 'example_result', width: '20%' },
                ]"
                :items="filteredVars"
                density="compact"
                :items-per-page="-1"
                hide-default-footer
                class="text-caption"
              >
                <template #item.var="{ item }">
                  <div class="d-flex align-center gap-1" style="white-space: nowrap; min-width: 260px;">
                    <v-tooltip :text="item.var" location="top">
                      <template #activator="{ props: tProps }">
                        <code class="text-caption text-truncate" style="max-width: 210px; display: inline-block;" v-bind="tProps">{{ item.var }}</code>
                      </template>
                    </v-tooltip>
                    <v-btn
                      icon size="x-small" variant="text"
                      :title="'Копировать ' + item.var"
                      @click="copyVar(item.var)"
                    >
                      <v-icon size="x-small">mdi-content-copy</v-icon>
                    </v-btn>
                  </div>
                </template>
                <template #item.example_template="{ item }">
                  <code class="text-caption">{{ item.example_template }}</code>
                </template>
              </v-data-table>
            </template>
          </v-expansion-panel>
        </v-expansion-panels>

        <!-- Hidden file input for template upload -->
        <input ref="templateFileInputRef" type="file" accept=".docx" style="display:none"
          @change="onTemplateFileSelected" />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-btn variant="outlined" prepend-icon="mdi-book-open-variant" color="indigo" @click="downloadMarkupGuide">
          Руководство по переменным
        </v-btn>
        <v-spacer />
        <v-btn variant="outlined" color="indigo" prepend-icon="mdi-content-copy"
               @click="openCopyTemplatesDialog">
          Скопировать из другой субсидии
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="showTemplateDialog = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { useSubsidyTemplates } from '@/composables/subsidies/useSubsidyTemplates'

const { mobile } = useDisplay()

const {
  showTemplateDialog, templateSubsidy, subsidyTemplatesList, templateFileInputRef,
  varsSearch, filteredVars, downloadSubsidyTemplate, triggerTemplateUpload,
  deleteSubsidyTemplate, onTemplateFileSelected, copyVar, downloadMarkupGuide,
  openCopyTemplatesDialog,
} = useSubsidyTemplates()
// templateFileInputRef используется только через шаблонный ref="templateFileInputRef"
// ниже (composable дёргает .click() из triggerTemplateUpload) — noUnusedLocals не видит
// такое использование в статическом ref-атрибуте, поэтому оставляем явную отметку.
void templateFileInputRef
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
