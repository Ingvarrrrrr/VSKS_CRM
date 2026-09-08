<template>
  <v-dialog v-model="showApproversDialog" max-width="700" scrollable :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-account-multiple" color="teal" class="mr-2" />
        Согласующие: {{ approversSubsidy?.name }}
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showApproversDialog = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-0">
        <v-data-table
          v-resizable-columns="'subsidies-approvers'"
          :headers="approversHeaders"
          :items="approversList"
          :loading="loadingApprovers"
          density="compact"
          hide-default-footer
          :items-per-page="-1"
          no-data-text="Нет согласующих. Добавьте первого."
        >
          <template #item.is_default="{ item }">
            <v-chip v-if="item.is_default" color="success" size="x-small">По умолчанию</v-chip>
          </template>
          <template #item.can_initiate="{ item }">
            <v-chip v-if="item.can_initiate" color="blue" size="x-small">Инициатор</v-chip>
            <v-chip v-if="item.show_feo_path" color="orange" size="x-small" class="ml-1">ФЭО путь</v-chip>
          </template>
          <template #item.order_num="{ index }">
            <span class="text-caption text-medium-emphasis">{{ index + 1 }}</span>
          </template>
          <template #item.full_name="{ item }">
            <span v-if="item.role_name === 'Ответственный исполнитель'" class="text-medium-emphasis font-italic">
              — Исполнитель определяется для каждой закупки
            </span>
            <span v-else>{{ item.full_name }}</span>
          </template>
          <template #item.actions="{ item, index }">
            <v-btn icon="mdi-arrow-up" size="x-small" variant="text" :disabled="index === 0" @click="moveApprover(index, -1)" />
            <v-btn icon="mdi-arrow-down" size="x-small" variant="text" :disabled="index === approversList.length - 1" @click="moveApprover(index, 1)" />
            <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="startEditApprover(item)" />
            <v-btn icon="mdi-delete" size="x-small" variant="text" color="error" @click="deleteApprover(item)" />
          </template>
        </v-data-table>
      </v-card-text>
      <v-divider />
      <v-card-actions class="px-4 py-3">
        <v-btn variant="outlined" color="indigo" prepend-icon="mdi-content-copy"
               @click="openCopyApproversDialog">
          Скопировать из другой субсидии
        </v-btn>
        <v-spacer />
        <v-btn color="teal" variant="tonal" prepend-icon="mdi-plus" @click="startAddApprover">
          Добавить
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="showApproversDialog = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { approversHeaders, useSubsidyApprovers } from '@/composables/subsidies/useSubsidyApprovers'

const { mobile } = useDisplay()

const {
  showApproversDialog, loadingApprovers, approversSubsidy, approversList,
  openCopyApproversDialog, startAddApprover, startEditApprover,
  deleteApprover, moveApprover,
} = useSubsidyApprovers()
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
