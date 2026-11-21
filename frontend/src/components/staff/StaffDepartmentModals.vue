<template>
  <div>
    <StaffDeptDialog
      :model-value="deptDialog"
      @update:model-value="$emit('update:deptDialog', $event)"
      :editing-dept="editingDept"
      :dept-form="deptForm"
      :org-name="editingDeptOrgName"
      :subsidies="editingDeptSubsidyOptions"
      :dept-member-items="deptMemberItems"
      :user-dropdown-items="userDropdownItems"
      :other-dept-items="otherDeptItems"
      :mobile="mobile"
      @save="$emit('save-dept')"
    />

    <DeptCreateDialog
      :model-value="deptCreateShow"
      @update:model-value="$emit('update:deptCreateShow', $event)"
      :form="deptCreateForm"
      :orgs="deptCreateOrgs"
      :subsidy-options="deptCreateSubsidyOptions"
      :saving="deptCreateSaving"
      :loading-lists="deptCreateLoadingLists"
      @create="$emit('create-dept')"
    />

    <StaffAddMemberDialog
      :model-value="addMemberDialog"
      @update:model-value="$emit('update:addMemberDialog', $event)"
      :add-member-mode="addMemberMode"
      @update:add-member-mode="$emit('update:addMemberMode', $event)"
      :selected-dept="selectedDept"
      :member-form="memberForm"
      :new-member-form="newMemberForm"
      :user-dropdown-items="userDropdownItems"
      :role-items="createRoleItems"
      :organizations="organizations"
      :get-positions-for-org="getPositionsForOrg"
      :new-member-saving="newMemberSaving"
      :mobile="mobile"
      @add="$emit('add-member')"
      @create-and-add="$emit('create-and-add-member')"
    />

    <StaffEditMemberDialog
      :model-value="editMemberDialog"
      @update:model-value="$emit('update:editMemberDialog', $event)"
      :edit-member-target="editMemberTarget"
      :edit-member-form="editMemberForm"
      @save="$emit('save-edit-member')"
    />

    <StaffDelegateDialog
      :model-value="delegateDialog"
      @update:model-value="$emit('update:delegateDialog', $event)"
      :delegate-form="delegateForm"
      :user-dropdown-items="userDropdownItems"
      @add="$emit('add-delegate')"
    />

    <StaffDeptImportDialog
      :model-value="deptImportDialog"
      @update:model-value="$emit('update:deptImportDialog', $event)"
      :dept-import-file="deptImportFile"
      @update:dept-import-file="$emit('update:deptImportFile', $event)"
      :dept-import-result="deptImportResult"
      :dept-importing="deptImporting"
      @download-template="$emit('download-dept-template')"
      @import="$emit('do-dept-import')"
    />
  </div>
</template>

<script setup lang="ts">
import StaffDeptDialog from '@/components/staff/StaffDeptDialog.vue'
import DeptCreateDialog from '@/components/departments/DeptCreateDialog.vue'
import StaffAddMemberDialog from '@/components/staff/StaffAddMemberDialog.vue'
import StaffEditMemberDialog from '@/components/staff/StaffEditMemberDialog.vue'
import StaffDelegateDialog from '@/components/staff/StaffDelegateDialog.vue'
import StaffDeptImportDialog from '@/components/staff/StaffDeptImportDialog.vue'

defineProps<{
  deptDialog: boolean
  editingDept: any
  deptForm: any
  editingDeptOrgName: string
  editingDeptSubsidyOptions: any[]
  deptMemberItems: any[]
  userDropdownItems: any[]
  otherDeptItems: any[]
  mobile: boolean
  deptCreateShow: boolean
  deptCreateForm: any
  deptCreateOrgs: any[]
  deptCreateSubsidyOptions: any[]
  deptCreateSaving: boolean
  deptCreateLoadingLists: boolean
  addMemberDialog: boolean
  addMemberMode: string
  selectedDept: any
  memberForm: any
  newMemberForm: any
  createRoleItems: any[]
  organizations: any[]
  getPositionsForOrg: (orgId?: number) => string[]
  newMemberSaving: boolean
  editMemberDialog: boolean
  editMemberTarget: any
  editMemberForm: any
  delegateDialog: boolean
  delegateForm: any
  deptImportDialog: boolean
  deptImportFile: any
  deptImportResult: any
  deptImporting: boolean
}>()

defineEmits<{
  'update:deptDialog': [val: boolean]
  'save-dept': []
  'update:deptCreateShow': [val: boolean]
  'create-dept': []
  'update:addMemberDialog': [val: boolean]
  'update:addMemberMode': [val: string]
  'add-member': []
  'create-and-add-member': []
  'update:editMemberDialog': [val: boolean]
  'save-edit-member': []
  'update:delegateDialog': [val: boolean]
  'add-delegate': []
  'update:deptImportDialog': [val: boolean]
  'update:deptImportFile': [val: any]
  'download-dept-template': []
  'do-dept-import': []
}>()
</script>
