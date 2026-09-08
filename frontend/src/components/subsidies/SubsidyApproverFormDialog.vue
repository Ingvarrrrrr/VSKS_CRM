<template>
  <!-- ── Approver Add/Edit Dialog ── -->
  <v-dialog v-model="showApproverFormDialog" max-width="480" :persistent="true" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon :icon="approverEditTarget ? 'mdi-pencil-outline' : 'mdi-plus'" color="teal" class="mr-2" />
        {{ approverEditTarget ? 'Редактировать' : 'Добавить' }} согласующего
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showApproverFormDialog = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-combobox
          v-model="approverForm.role_name"
          :items="ROLE_SUGGESTIONS"
          label="Роль / Должность *"
          variant="outlined"
          density="compact"
          class="mb-3"
          hide-details
          @update:model-value="onApproverRoleChange"
        />
        <v-alert
          v-if="approverForm.role_name === 'Ответственный исполнитель'"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-3"
          text="Для роли «Ответственный исполнитель» ФИО не указывается — исполнитель определяется для каждой закупки из её данных. Конкретного человека можно выбрать при скачивании листа согласования — поле «Ответственный исполнитель» в диалоге документа."
        />
        <v-autocomplete
          v-if="approverForm.role_name !== 'Ответственный исполнитель'"
          v-model="approverForm.selectedUser"
          :items="approverUsersList"
          item-title="full_name"
          item-value="id"
          label="Сотрудник *"
          variant="outlined"
          density="compact"
          class="mb-1"
          clearable
          return-object
          @update:model-value="onApproverUserSelect"
        />
        <v-alert
          v-if="approverEditTarget && !approverForm.selectedUser"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
          text="Старая запись без привязки к сотруднику. Выберите сотрудника для сохранения."
        />
        <div v-if="!approverEditTarget || approverForm.selectedUser" class="mb-3" />
        <v-checkbox
          v-model="approverForm.is_default"
          label="Выбирать по умолчанию при генерации документов"
          density="compact"
          hide-details
          class="mb-1"
        />
        <v-checkbox
          v-model="approverForm.can_initiate"
          label="Может быть инициатором служебной записки"
          density="compact"
          hide-details
          class="mb-1"
        />
        <v-checkbox
          v-model="approverForm.show_feo_path"
          label="Показывать путь категории ФЭО в примечании"
          density="compact"
          hide-details
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="showApproverFormDialog = false">Отмена</v-btn>
        <v-btn
          color="teal"
          :loading="savingApprover"
          :disabled="!approverForm.role_name || (approverForm.role_name !== 'Ответственный исполнитель' && !approverForm.selectedUser)"
          @click="saveApprover"
        >
          {{ approverEditTarget ? 'Сохранить' : 'Добавить' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { ROLE_SUGGESTIONS, useSubsidyApprovers } from '@/composables/subsidies/useSubsidyApprovers'

const { mobile } = useDisplay()

const {
  showApproverFormDialog, savingApprover, approverEditTarget, approverForm, approverUsersList,
  onApproverRoleChange, onApproverUserSelect, saveApprover,
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
