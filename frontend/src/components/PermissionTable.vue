<template>
  <v-table density="compact" class="permission-matrix">
    <thead>
      <tr>
        <th class="role-col">Роль</th>
        <th v-for="col in columns" :key="colKey(col)" class="perm-col">
          {{ colTitle(col) }}
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="role in rows" :key="role">
        <td class="role-col">{{ roleLabel(role) }}</td>
        <td v-for="col in columns" :key="colKey(col)">
          <v-tooltip
            :text="isLocked(role, colKey(col)) ? 'Нельзя снять с себя доступ к Ролям/Персоналу' : ''"
            location="top"
            :disabled="!isLocked(role, colKey(col))"
          >
            <template #activator="{ props: tipProps }">
              <div v-bind="tipProps" class="d-flex justify-center">
                <v-checkbox
                  :model-value="granted[role]?.has(colKey(col))"
                  :disabled="isLocked(role, colKey(col))"
                  hide-details
                  density="compact"
                  @update:model-value="(v) => $emit('change', role, colKey(col), !!v)"
                />
              </div>
            </template>
          </v-tooltip>
        </td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
const props = defineProps<{
  rows: string[]
  columns: any[]
  granted: Record<string, Set<string>>
  currentRole: string
  protectedKeys: string[]
}>()

defineEmits<{ (e: 'change', role: string, key: string, granted: boolean): void }>()

function colKey(col: any): string {
  return col.tab_key ?? col.action_key ?? ''
}

function colTitle(col: any): string {
  return col.title ?? col.description ?? colKey(col)
}

function isLocked(role: string, key: string): boolean {
  return role === props.currentRole && props.protectedKeys.includes(key)
}

function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    account_owner: 'Владелец аккаунта',
    admin: 'Администратор',
    org_admin: 'Админ организации',
    manager: 'Менеджер',
    employee: 'Сотрудник',
  }
  return labels[role] ?? role
}
</script>

<style scoped>
.permission-matrix :deep(th.perm-col) {
  min-width: 110px;
  text-align: center;
  font-size: 0.72rem;
  white-space: normal;
  word-break: break-word;
  vertical-align: bottom;
  padding-bottom: 6px;
}
.permission-matrix :deep(td) {
  text-align: center;
  padding: 2px !important;
  vertical-align: middle;
}
.permission-matrix :deep(.role-col) {
  min-width: 160px;
  text-align: left;
  font-weight: 500;
}
</style>
