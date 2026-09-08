<template>
  <v-dialog v-model="show" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title>{{ editingDept ? 'Редактировать отдел' : 'Новый отдел' }}</v-card-title>
      <v-card-text>
        <!-- Step hints for new department -->
        <v-alert v-if="!editingDept" type="info" variant="tonal" density="compact" class="mb-4">
          <div class="text-body-2 font-weight-medium mb-1">Как заполнить:</div>
          <ol class="text-body-2 pl-4" style="line-height:1.6">
            <li>Введите название отдела (например, "Отдел закупок")</li>
            <li>Привяжите к субсидии, если отдел работает по конкретной субсидии</li>
            <li>Начальника и сотрудников добавите после создания отдела</li>
          </ol>
        </v-alert>

        <v-text-field v-model="deptForm.name" label="Название отдела *" variant="outlined" density="compact" class="mb-3"
          placeholder="Например: Отдел закупок, Бухгалтерия, Склад" />

        <v-select v-model="deptForm.subsidy_id" :items="subsidies" item-title="name" item-value="id"
          label="Субсидия" variant="outlined" density="compact" clearable class="mb-3"
          hint="Если отдел обслуживает конкретную субсидию. Оставьте пустым для общего отдела." persistent-hint />

        <template v-if="editingDept">
          <v-select v-model="deptForm.head_user_id" :items="deptMemberItems" item-title="text" item-value="value"
            label="Начальник отдела" variant="outlined" density="compact" clearable class="mb-3"
            :hint="deptMemberItems.length === 0 ? 'Сначала добавьте сотрудников в отдел (кнопка справа)' : 'Выберите из сотрудников этого отдела'"
            persistent-hint :disabled="deptMemberItems.length === 0" />

          <v-select v-model="deptForm.deputy_head_user_id" :items="deptMemberItems" item-title="text" item-value="value"
            label="Зам. начальника отдела" variant="outlined" density="compact" clearable class="mb-3"
            hint="Используется в восходящей цепочке согласования заявок (ниже начальника)" persistent-hint
            :disabled="deptMemberItems.length === 0" />

          <v-select v-model="deptForm.curator_user_id" :items="userDropdownItems" item-title="text" item-value="value"
            label="Куратор" variant="outlined" density="compact" clearable class="mb-3"
            hint="Любой человек, курирующий это подразделение (в цепочке согласования выше начальника). Не обязательно зам." persistent-hint />

          <v-select v-model="deptForm.parent_id" :items="otherDeptItems" item-title="text" item-value="value"
            label="Вышестоящее подразделение" variant="outlined" density="compact" clearable
            hint="Если это подотдел внутри другого (например, Сектор мониторинга внутри Отдела закупок)" persistent-hint />
        </template>

        <v-alert v-if="!editingDept" type="warning" variant="tonal" density="compact" class="mt-2">
          После создания отдела нажмите на него в дереве слева, чтобы добавить сотрудников и назначить начальника.
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" :disabled="!deptForm.name" @click="$emit('save')">{{ editingDept ? 'Сохранить' : 'Создать' }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  editingDept: any
  deptForm: { name: string; subsidy_id: number | null; head_user_id: number | null; deputy_head_user_id: number | null; curator_user_id: number | null; parent_id: number | null }
  subsidies: any[]
  deptMemberItems: { text: string; value: number }[]
  userDropdownItems: { text: string; value: number }[]
  otherDeptItems: { text: string; value: number }[]
  mobile: boolean
}>()
defineEmits<{ (e: 'save'): void }>()
const show = defineModel<boolean>('show', { required: true })
</script>
