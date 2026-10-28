<template>
  <v-dialog v-model="show" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title>Редактировать отдел</v-card-title>
      <v-card-text>
        <v-text-field v-model="deptForm.name" label="Название отдела *" variant="outlined" density="compact" class="mb-3"
          placeholder="Например: Отдел закупок, Бухгалтерия, Склад" />

        <!-- Организация отдела — не редактируется здесь (см. useDeptCreate для
             создания); субсидия ниже фильтруется по этой организации, тот же
             источник orgName/subsidies, что передаёт StaffView.vue. -->
        <v-text-field :model-value="orgName" label="Организация" variant="outlined" density="compact" class="mb-3" readonly disabled />

        <v-select v-model="deptForm.subsidy_id" :items="subsidies" item-title="name" item-value="id"
          label="Субсидия" variant="outlined" density="compact" clearable class="mb-3"
          hint="Только субсидии этой организации. Оставьте пустым для общего отдела." persistent-hint />

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
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" :disabled="!deptForm.name" @click="$emit('save')">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  editingDept: any
  deptForm: { name: string; subsidy_id: number | null; head_user_id: number | null; deputy_head_user_id: number | null; curator_user_id: number | null; parent_id: number | null }
  orgName?: string
  subsidies: any[]
  deptMemberItems: { text: string; value: number }[]
  userDropdownItems: { text: string; value: number }[]
  otherDeptItems: { text: string; value: number }[]
  mobile: boolean
}>()
defineEmits<{ (e: 'save'): void }>()
const show = defineModel<boolean>('show', { required: true })
</script>
