<template>
  <div>
    <StaffDeleteUserDialog :dialog="deleteDialog" @confirm="$emit('delete')" />
    <StaffBulkDeleteUsersDialog :model-value="bulkDeleteUsersDialog" @update:model-value="$emit('update:bulkDeleteUsersDialog', $event)" :count="selectedCount" :loading="bulkDeleteUsersLoading" @confirm="$emit('bulk-delete')" />
    <StaffHierarchyDialog :dialog="hierarchyDialog" :all-subs-not-direct="allSubsNotDirect" :mobile="mobile" @add-subordinate="$emit('add-subordinate', $event)" @remove-subordinate="$emit('remove-subordinate', $event)" />
    <StaffUserImportDialog :dialog="userImportDialog" :mobile="mobile" @download-template="$emit('download-template')" @import="$emit('import', $event)" />
    <StaffInnDupDialog :model-value="innDupDialog" @update:model-value="$emit('update:innDupDialog', $event)" :duplicate-inn-groups="duplicateInnGroups" :mobile="mobile" @edit-user="$emit('edit-user', $event)" @merged="$emit('merged')" />
  </div>
</template>

<script setup lang="ts">
import StaffDeleteUserDialog from '@/components/staff/StaffDeleteUserDialog.vue'
import StaffBulkDeleteUsersDialog from '@/components/staff/StaffBulkDeleteUsersDialog.vue'
import StaffHierarchyDialog from '@/components/staff/StaffHierarchyDialog.vue'
import StaffUserImportDialog from '@/components/staff/StaffUserImportDialog.vue'
import StaffInnDupDialog from '@/components/staff/StaffInnDupDialog.vue'

defineProps<{
  deleteDialog: any
  bulkDeleteUsersDialog: boolean
  selectedCount: number
  bulkDeleteUsersLoading: boolean
  hierarchyDialog: any
  allSubsNotDirect: any[]
  mobile: boolean
  userImportDialog: any
  innDupDialog: boolean
  duplicateInnGroups: any[]
}>()

defineEmits<{
  'delete': []
  'update:bulkDeleteUsersDialog': [val: boolean]
  'bulk-delete': []
  'add-subordinate': [id: number]
  'remove-subordinate': [id: number]
  'download-template': []
  'import': [file: File]
  'update:innDupDialog': [val: boolean]
  'edit-user': [user: any]
  'merged': []
}>()
</script>
