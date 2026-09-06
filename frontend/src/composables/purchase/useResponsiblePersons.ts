// Справочник «Ответственных лиц» субсидии (используется как список для выбора
// «Ответственный исполнитель» в диалоге листа согласования — AddResponsibleDialog.vue).
// Вынесено из CreateOrderView.vue без изменения поведения — те же apiFetch-пути.
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

export interface ResponsiblePerson { id: number; full_name: string; position?: string; display?: string }
interface OrgUserLike { full_name: string; position?: string | null }

export function useResponsiblePersons(
  form: Record<string, any>,
  orgUsersList: Ref<OrgUserLike[]>,
) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const responsiblePersonsList = ref<ResponsiblePerson[]>([])
  const pickerResponsibleName = ref<string>('')
  const addResponsibleDialog = ref(false)
  const newResponsibleName = ref('')
  const newResponsiblePosition = ref('')
  const savingResponsible = ref(false)

  async function loadResponsiblePersonsList() {
    if (!form.subsidy_id) { responsiblePersonsList.value = []; return }
    try {
      const list = await apiFetch<ResponsiblePerson[]>(`/subsidies/${form.subsidy_id}/responsible-persons`)
      responsiblePersonsList.value = list.map(p => ({
        ...p,
        display: p.position ? `${p.full_name} (${p.position})` : p.full_name,
      }))
    } catch { responsiblePersonsList.value = [] }
  }

  // Список для выбора «Ответственный исполнитель» в диалоге листа согласования:
  // сотрудники организации (orgUsersList) + справочник ответственных
  // (responsiblePersonsList), объединённые и дедуплицированные по ФИО.
  // При совпадении приоритет у записи справочника (там указана должность).
  // Плюс: текущее предзаполненное значение (pickerResponsibleName) добавляется
  // принудительно, если его нет ни в одном из наборов — иначе оно "исчезает"
  // из списка при открытии автокомплита (v-autocomplete показывает пусто для
  // значения, отсутствующего в items).
  const responsibleOptions = computed(() => {
    const norm = (s: string) => s.trim().toLowerCase()
    const byName = new Map<string, { full_name: string; position?: string | null; display: string; source: 'user' | 'directory' }>()

    for (const u of orgUsersList.value) {
      if (!u.full_name) continue
      byName.set(norm(u.full_name), {
        full_name: u.full_name,
        position: u.position,
        display: u.position ? `${u.full_name} (${u.position})` : u.full_name,
        source: 'user',
      })
    }
    // Справочник имеет приоритет — перезаписывает запись сотрудника с тем же ФИО.
    for (const p of responsiblePersonsList.value) {
      if (!p.full_name) continue
      byName.set(norm(p.full_name), {
        full_name: p.full_name,
        position: p.position,
        display: p.display || (p.position ? `${p.full_name} (${p.position})` : p.full_name),
        source: 'directory',
      })
    }
    const current = pickerResponsibleName.value?.trim()
    if (current && !byName.has(norm(current))) {
      byName.set(norm(current), { full_name: current, display: current, source: 'directory' })
    }
    return [...byName.values()].sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'))
  })

  async function saveNewResponsible() {
    if (!newResponsibleName.value.trim() || !form.subsidy_id) return
    savingResponsible.value = true
    try {
      const created = await apiFetch<ResponsiblePerson>(`/subsidies/${form.subsidy_id}/responsible-persons`, {
        method: 'POST',
        body: JSON.stringify({ full_name: newResponsibleName.value.trim(), position: newResponsiblePosition.value.trim() || null }),
      })
      const entry = { ...created, display: created.position ? `${created.full_name} (${created.position})` : created.full_name }
      responsiblePersonsList.value.push(entry)
      responsiblePersonsList.value.sort((a, b) => a.full_name.localeCompare(b.full_name))
      pickerResponsibleName.value = created.full_name
      addResponsibleDialog.value = false
      newResponsibleName.value = ''
      newResponsiblePosition.value = ''
    } catch { showSnack('Ошибка сохранения', 'error') }
    finally { savingResponsible.value = false }
  }

  return {
    responsiblePersonsList, pickerResponsibleName, addResponsibleDialog,
    newResponsibleName, newResponsiblePosition, savingResponsible,
    loadResponsiblePersonsList, responsibleOptions, saveNewResponsible,
  }
}
