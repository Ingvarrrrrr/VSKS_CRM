<template>
  <v-table density="compact" class="permission-matrix">
    <thead>
      <tr>
        <th class="key-col">Право</th>
        <th v-for="role in roles" :key="role" class="role-col">
          {{ roleLabel(role) }}
        </th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="col in columns" :key="colKey(col)">
        <td class="key-col">{{ colTitle(col) }}</td>
        <td v-for="role in roles" :key="role" class="role-col">
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
  roles: string[]
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
.permission-matrix :deep(th.role-col),
.permission-matrix :deep(td.role-col) {
  min-width: 130px;
  text-align: center;
  vertical-align: middle;
  padding: 2px !important;
}
.permission-matrix :deep(th.role-col) {
  font-size: 0.78rem;
  white-space: normal;
  word-break: break-word;
  vertical-align: bottom;
  padding-bottom: 6px !important;
}
.permission-matrix :deep(th.key-col),
.permission-matrix :deep(td.key-col) {
  min-width: 280px;
  text-align: left;
  font-weight: 500;
  position: sticky;
  left: 0;
  z-index: 1;
  background: rgb(var(--v-theme-surface));
}
.permission-matrix :deep(th.key-col) {
  z-index: 2;
}
</style>
