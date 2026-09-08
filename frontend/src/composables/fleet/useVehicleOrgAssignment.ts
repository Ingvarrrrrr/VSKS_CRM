import { computed, type Ref } from 'vue'
import { useOrgContractorAutofill } from '@/composables/useOrgContractorAutofill'
import { useContractorsStore } from '@/stores/contractors'
import { useToast, type ToastType } from '@/composables/useToast'
import type { OrgItem, Vehicle, VehicleForm } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Владелец / Эксплуатант карточки ТС: списки организаций (с подмешиванием
// текущей, если её нет в /auth/my-orgs), автодополнение из контрагентов
// (useOrgContractorAutofill) и живой предпросмотр ИНН. Вынесено из
// VehicleDetailView.vue без изменения поведения.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleOrgAssignment(
  form: VehicleForm,
  orgsList: Ref<OrgItem[]>,
  vehicle: Ref<Vehicle | null>,
) {
  const contractorsStore = useContractorsStore()
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  // 2026-09 (дефект «Владелец показывает id вместо названия»): даже после
  // перехода loadOrgs() на /auth/my-orgs список может не содержать организацию
  // текущего ТС (например, она деактивирована или доступ пользователя её не
  // покрывает) — тогда v-autocomplete без соответствующего id в :items выводит
  // сырое числовое значение. Подмешиваем текущую организацию по имени из самой
  // машины (vehicle.owner_org_name / assigned_org_name, уже приходит в
  // GET /api/vehicles/{id}), чтобы поле ВСЕГДА показывало название, а не id.
  const ownerOrgItems = computed<OrgItem[]>(() => {
    const items = orgsList.value
    const id = form.owner_org_id
    const name = vehicle.value?.owner_org_name
    if (id != null && name && !items.some(o => o.id === id)) {
      return [...items, { id, name }]
    }
    return items
  })
  const assignedOrgItems = computed<OrgItem[]>(() => {
    const items = orgsList.value
    const id = form.assigned_org_id
    const name = vehicle.value?.assigned_org_name
    if (id != null && name && !items.some(o => o.id === id)) {
      return [...items, { id, name }]
    }
    return items
  })
  // Полное название — для v-tooltip над клампнутым в 2 строки полем.
  const ownerOrgFullName = computed(() =>
    ownerOrgItems.value.find(o => o.id === form.owner_org_id)?.name || vehicle.value?.owner_org_name || ''
  )
  const assignedOrgFullName = computed(() =>
    assignedOrgItems.value.find(o => o.id === form.assigned_org_id)?.name || vehicle.value?.assigned_org_name || ''
  )

  // ─────────────── Владелец/Эксплуатант — автозаполнение из контрагентов ───────────────
  // Жалоба владельца (2026-09-03): поиск по «Владельцу»/«Эксплуатанту» шёл только
  // среди ~27 внутренних организаций аккаунта, ИНН не подставлялся ни в одну
  // сторону. См. composables/useOrgContractorAutofill.ts — там же решение по
  // случаю «выбран контрагент без внутренней организации».
  const ownerAutofill = useOrgContractorAutofill(orgsList)
  const assignedAutofill = useOrgContractorAutofill(orgsList)

  const ownerOrgUid = computed<string | null>(() => form.owner_org_id != null ? `org-${form.owner_org_id}` : null)
  const assignedOrgUid = computed<string | null>(() => form.assigned_org_id != null ? `org-${form.assigned_org_id}` : null)

  const ownerOrgOptions = computed(() => ownerAutofill.buildOptions(form.owner_org_id, vehicle.value?.owner_org_name))
  const assignedOrgOptions = computed(() => assignedAutofill.buildOptions(form.assigned_org_id, vehicle.value?.assigned_org_name))

  // Живой предпросмотр ИНН — сразу после выбора, без сохранения/перезагрузки
  // карточки (в отличие от vehicle.owner_inn/operator_inn — those придут только
  // после PATCH и повторного GET).
  const ownerInnDisplay = computed(() => {
    const org = orgsList.value.find(o => o.id === form.owner_org_id)
    return (org?.inn ?? null) || vehicle.value?.owner_inn || null
  })
  const operatorInnDisplay = computed(() => {
    if (!form.assigned_org_id) return null
    const org = orgsList.value.find(o => o.id === form.assigned_org_id)
    return (org?.inn ?? null) || vehicle.value?.operator_inn || null
  })

  async function onOwnerOrgSelect(uid: string | null) {
    if (!uid) { form.owner_org_id = null; return }
    const res = await ownerAutofill.resolveSelection(uid)
    if (res.error) { showSnack(res.error, 'error'); return }
    if (res.orgId == null) return
    form.owner_org_id = res.orgId
    if (res.createdOrg && !orgsList.value.some(o => o.id === res.createdOrg!.id)) {
      orgsList.value = [...orgsList.value, res.createdOrg]
    }
    if (res.message) showSnack(res.message)
  }

  async function onAssignedOrgSelect(uid: string | null) {
    if (!uid) { form.assigned_org_id = null; return }
    const res = await assignedAutofill.resolveSelection(uid)
    if (res.error) { showSnack(res.error, 'error'); return }
    if (res.orgId == null) return
    form.assigned_org_id = res.orgId
    if (res.createdOrg && !orgsList.value.some(o => o.id === res.createdOrg!.id)) {
      orgsList.value = [...orgsList.value, res.createdOrg]
    }
    if (res.message) showSnack(res.message)
  }

  return {
    contractorsStore,
    ownerOrgItems,
    assignedOrgItems,
    ownerOrgFullName,
    assignedOrgFullName,
    ownerAutofill,
    assignedAutofill,
    ownerOrgUid,
    assignedOrgUid,
    ownerOrgOptions,
    assignedOrgOptions,
    ownerInnDisplay,
    operatorInnDisplay,
    onOwnerOrgSelect,
    onAssignedOrgSelect,
  }
}
