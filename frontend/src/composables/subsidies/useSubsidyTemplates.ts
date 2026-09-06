// Состояние и CRUD шаблонов документов субсидии, общее для SubsidyTemplatesDialog
// и SubsidyCopyTemplatesDialog — вынесено из SubsidiesView.vue. Module-level
// singleton (как useSubsidyApprovers.ts/useApprovalsBadge.ts), т.к. оба диалога
// и сам SubsidiesView.vue (иконка «есть свои шаблоны» в списке субсидий, кнопка
// строки — открывает диалог) должны видеть одно и то же состояние.
//
// contractTemplates — ЕДИНСТВЕННЫЙ источник признака «у субсидии есть свои
// шаблоны», раньше жил как локальный ref в SubsidiesView.vue и писался только
// отсюда (openTemplateDialog) — вынесен сюда целиком, а не скопирован, чтобы
// не завести вторую копию одного признака (Правило №6).
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { SubsidyRow } from './types'

export interface TemplateVar { var: string; description: string; example_template: string; example_result: string }

export const DOC_TYPE_RU: Record<string, string> = {
  service_note_delivery: 'Служебная_записка_выдача',
  service_note_payment: 'Служебная_записка_оплата',
  service_note_procurement: 'Служебная_записка_закупка',
  service_note_advance: 'Служебная_записка_аванс',
  contract_tz: 'Договор_с_ТЗ',
  tech_spec: 'Техническое_задание',
  tech_spec_request: 'ТЗ_запрос_цен',
  tech_spec_contract: 'ТЗ_к_договору',
  contract: 'Договор',
  approval_sheet: 'Лист_согласования',
  order_purchase: 'Приказ_о_закупке',
  contract_services: 'Договор_услуг',
  // Алиасы — сохранены на бэке для старых закупок, оставлены и здесь на всякий случай
  contract_services_large: 'Договор_услуги_крупный',
  contract_services_small: 'Договор_услуги_малый',
  contract_services_food: 'Договор_услуги_питание',
  methodology_large: 'Методические_рекомендации_большие',
  methodology_small: 'Методические_рекомендации_малые',
  contract_goods_single: 'Договор_поставка_единственный',
  contract_gph_individual: 'Договор_ГПХ_физлицо',
  contract_gph_individual_rid: 'Договор_ГПХ_физлицо_РИД',
  contract_repair_vehicle: 'Договор_ремонт_ТС',
  contract_repair_framework: 'Договор_ремонт_рамочный',
  fabrikant_instruction: 'Фабрикант_инструкция',
  fabrikant_application_form: 'Фабрикант_форма_заявки',
  fabrikant_documentation: 'Фабрикант_документация',
  fabrikant_contract_project: 'Фабрикант_проект_договора',
}

// Template management state
const showTemplateDialog  = ref(false)
const templateSubsidy     = ref<SubsidyRow | null>(null)
const contractTemplates   = ref<Record<number, boolean>>({})
const subsidyTemplatesList = ref<Array<{ doc_type: string; label: string; has_custom: boolean; has_global: boolean; render_ok?: boolean | null }>>([])
const templateFileInputRef = ref<HTMLInputElement | null>(null)
const uploadingDocType     = ref<string | null>(null)

// Template variables panel state
const templateVars = ref<TemplateVar[]>([])
const varsSearch = ref('')

// ── Copy Templates state ──
const showCopyTemplatesDialog = ref(false)
const copyTemplates = ref<{ sourceId: number | null; replace: boolean; loading: boolean; error: string }>({
  sourceId: null, replace: false, loading: false, error: '',
})

// ctx — опциональный: см. комментарий у useSubsidyApprovers() в
// useSubsidyApprovers.ts — inject() не резолвит provide() того же компонента,
// поэтому SubsidiesView.vue (родитель, провайдер) зовёт useSubsidyTemplates()
// без аргумента, а SubsidyCopyTemplatesDialog.vue (настоящий потомок) —
// useSubsidyTemplates(useSubsidyDetailCtx()).
export function useSubsidyTemplates(ctx?: SubsidyDetailContext) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
    toast.addToast(text, color, opts)
  }

  const filteredVars = computed(() => {
    if (!varsSearch.value) return templateVars.value
    const q = varsSearch.value.toLowerCase()
    return templateVars.value.filter(v =>
      v.var.toLowerCase().includes(q) ||
      v.description.toLowerCase().includes(q) ||
      v.example_template.toLowerCase().includes(q)
    )
  })

  async function loadTemplateVars() {
    try {
      templateVars.value = await apiFetch<TemplateVar[]>('/documents/template-vars')
    } catch (e) { console.error('loadTemplateVars:', e) }
  }

  async function copyVar(text: string) {
    // phase26-mm: на HTTP-only проде navigator.clipboard undefined.
    // Fallback на document.execCommand('copy') через временный textarea.
    let ok = false
    try {
      if (window.isSecureContext && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
        ok = true
      } else {
        const ta = document.createElement('textarea')
        ta.value = text
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        ta.style.top = '0'
        ta.style.left = '0'
        document.body.appendChild(ta)
        ta.focus()
        ta.select()
        try { ok = document.execCommand('copy') } catch { ok = false }
        document.body.removeChild(ta)
      }
    } catch { ok = false }
    if (ok) showSnack(`Скопировано: ${text}`, 'success', { duration: 2500 })
    else showSnack(`Не удалось скопировать. Выделите и нажмите Ctrl+C: ${text}`, 'error')
  }

  const copySourceSubsidiesForTemplates = computed(() =>
    (ctx?.allSubsidies.value || []).filter((s: SubsidyRow) => s.id !== templateSubsidy.value?.id)
  )

  function openCopyTemplatesDialog() {
    copyTemplates.value = { sourceId: null, replace: false, loading: false, error: '' }
    showCopyTemplatesDialog.value = true
  }

  async function openTemplateDialog(s: SubsidyRow) {
    templateSubsidy.value = s
    showTemplateDialog.value = true
    subsidyTemplatesList.value = []
    try {
      const list = await apiFetch<Array<{ doc_type: string; label: string; has_custom: boolean; has_global: boolean; render_ok?: boolean | null }>>(
        `/subsidies/${s.id}/templates`
      )
      subsidyTemplatesList.value = list
      contractTemplates.value[s.id] = list.some((t: { has_custom: boolean }) => t.has_custom)
    } catch {
      subsidyTemplatesList.value = []
    }
  }

  async function confirmCopyTemplates() {
    if (!templateSubsidy.value?.id || !copyTemplates.value.sourceId) return
    copyTemplates.value.loading = true
    copyTemplates.value.error = ''
    try {
      const result = await apiFetch<{ copied: string[]; skipped: string[]; reason?: string }>(
        `/subsidies/${templateSubsidy.value.id}/templates/copy-from/${copyTemplates.value.sourceId}?replace=${copyTemplates.value.replace}`,
        { method: 'POST' }
      )
      showCopyTemplatesDialog.value = false
      if (result.reason) {
        showSnack(result.reason, 'error')
      } else {
        const skippedNote = result.skipped.length ? `, пропущено: ${result.skipped.length}` : ''
        showSnack(`Скопировано шаблонов: ${result.copied.length}${skippedNote}`, 'success')
      }
      await openTemplateDialog(templateSubsidy.value)
    } catch (e: any) {
      copyTemplates.value.error = e?.payload?.message || e?.message || 'Ошибка копирования'
    } finally {
      copyTemplates.value.loading = false
    }
  }

  function triggerTemplateUpload(docType: string) {
    uploadingDocType.value = docType
    templateFileInputRef.value?.click()
  }

  async function onTemplateFileSelected(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file || !templateSubsidy.value || !uploadingDocType.value) return
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await fetch(`/api/subsidies/${templateSubsidy.value.id}/templates/${uploadingDocType.value}`, {
        method: 'PUT',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        const detail = err.detail || `Ошибка загрузки (HTTP ${res.status})`
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
      }
      showSnack('Шаблон загружен')
      await openTemplateDialog(templateSubsidy.value)
    } catch (e: any) {
      showSnack(e.message || 'Ошибка загрузки шаблона', 'error')
    } finally {
      uploadingDocType.value = null
      ;(event.target as HTMLInputElement).value = ''
    }
  }

  async function downloadSubsidyTemplate(docType: string) {
    if (!templateSubsidy.value) return
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/subsidies/${templateSubsidy.value.id}/templates/${docType}/download?t=${Date.now()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) { showSnack('Ошибка скачивания', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ruName = DOC_TYPE_RU[docType] || docType
    a.download = `Шаблон_${ruName}_субсидия_${templateSubsidy.value.id}.docx`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function deleteSubsidyTemplate(docType: string) {
    if (!templateSubsidy.value) return
    try {
      await apiFetch(`/subsidies/${templateSubsidy.value.id}/templates/${docType}`, { method: 'DELETE' })
      showSnack('Шаблон удалён', 'warning')
      await openTemplateDialog(templateSubsidy.value)
    } catch {
      showSnack('Ошибка удаления шаблона', 'error')
    }
  }

  async function downloadMarkupGuide() {
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/documents/template-guide', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) { showSnack('Ошибка скачивания руководства', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'Инструкция_по_шаблонам.docx'
    a.click()
    URL.revokeObjectURL(url)
  }

  return {
    showTemplateDialog, templateSubsidy, contractTemplates, subsidyTemplatesList,
    templateFileInputRef, uploadingDocType, templateVars, varsSearch, filteredVars,
    showCopyTemplatesDialog, copyTemplates, copySourceSubsidiesForTemplates,
    loadTemplateVars, copyVar, openCopyTemplatesDialog, openTemplateDialog, confirmCopyTemplates,
    triggerTemplateUpload, onTemplateFileSelected, downloadSubsidyTemplate, deleteSubsidyTemplate,
    downloadMarkupGuide,
  }
}
