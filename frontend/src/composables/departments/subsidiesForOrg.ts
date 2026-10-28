// ПРАВИЛО №6: единственная формула «субсидии этой организации» — читают
// отсюда и диалог создания отдела (useDeptCreate), и диалог редактирования
// (StaffDeptDialog через StaffView.vue), а не копируют фильтр каждый раз.
export function filterSubsidiesByOrg(subsidies: any[] | null | undefined, orgId: number | null | undefined): any[] {
  if (!orgId) return []
  return (subsidies || []).filter((s: any) => s.org_id === orgId)
}
