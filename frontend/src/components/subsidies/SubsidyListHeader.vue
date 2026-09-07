<template>
  <div class="page-header">
    <div class="page-header-left">
      <v-icon icon="mdi-cash-multiple" size="32" color="#3B82F6" class="mr-3" />
      <div>
        <div class="page-title">Субсидии</div>
        <div class="page-subtitle">Управление субсидиями и распределение бюджета · {{ selectedYear }}</div>
      </div>
    </div>
    <div class="page-header-right">
      <v-chip-group v-if="availableYears.length" v-model="selectedYear" mandatory class="year-chips mr-3">
        <v-chip
          v-for="year in availableYears" :key="year" :value="year"
          filter variant="elevated" color="primary" size="small"
        >{{ year }}</v-chip>
      </v-chip-group>
      <v-btn-toggle v-if="!mobile" v-model="viewMode" mandatory density="comfortable" variant="outlined" divided class="mr-2">
        <v-btn value="table" size="small" icon="mdi-table" title="Таблица" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" title="Карточки" />
      </v-btn-toggle>
      <RegistryExportButton
        title="Реестр субсидий"
        :get-columns="getSubsidyExportColumns"
        :get-rows="getSubsidyExportRows"
        :get-capture-el="() => registryArea"
        class="mr-2"
        @error="(m: string) => showSnack(m, 'error')"
      />
      <v-btn
        v-if="canEditFeo"
        variant="outlined" prepend-icon="mdi-download-outline" class="mr-2"
        title="Шаблон импорта направлений ФЭО (без выбранной субсидии — общий, с нейтральными примерами)"
        @click="ctx.downloadFeoTemplate()"
      >
        Шаблон ФЭО
      </v-btn>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="addOpen = true">
        Добавить
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useSubsidyList } from '@/composables/subsidies/useSubsidyList'

// registryArea — элемент, который скриншотит RegistryExportButton (сама таблица/
// карточки списка субсидий — в SubsidyListTable.vue/SubsidyCardsGrid.vue,
// рендерятся ПОСЛЕ этого компонента внутри одного div-обёртки в SubsidiesView.vue).
// Ref на сам div остаётся в SubsidiesView.vue (там же `<div ref="registryArea">`);
// сюда передаётся read-only пропом — в отличие от остального состояния списка,
// DOM-элемент не нужен нигде, кроме этой кнопки, заводить его в useSubsidyList()
// незачем.
const props = defineProps<{ registryArea: HTMLElement | null }>()
const registryArea = computed(() => props.registryArea)

const addOpen = defineModel<boolean>('addOpen', { default: false })

const ctx = useSubsidyDetailCtx()
const { selectedYear, availableYears, mobile, viewMode, getSubsidyExportColumns, getSubsidyExportRows } = useSubsidyList(ctx)

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const authStore = useAuthStore()
const canEditFeo = computed(() => authStore.hasAction('feo_category.edit'))
</script>
