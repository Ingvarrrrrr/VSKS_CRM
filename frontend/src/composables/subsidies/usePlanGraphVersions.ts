// Состояние и логика четырёх диалогов «Версии план-графика» (История/Экспорт
// редакций/Снимок версии/Сохранить редакцию) — вынесены из SubsidiesView.vue.
// Module-level singleton state, как useSubsidyApprovers.ts/useToast.ts в этом же
// проекте: и родитель (кнопки тулбара дерева ФЭО — openVersionHistory/
// openExportVersionsDialog/openSaveVersionDialog остаются вызываемыми под теми
// же именами), и каждый из четырёх диалогов, вызывая usePlanGraphVersions(),
// получают ОДНО и то же реактивное состояние.
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyDetailContext } from './useSubsidyDetail'

// ── Version history ──
const showVersionHistoryDialog = ref(false)
const versionHistoryList = ref<Array<{
  id: number
  version_number: number
  created_at: string
  created_by_name: string
  note: string
  total_planned: number
  total_used: number
  item_count: number
}>>([])
const versionHistoryLoading = ref(false)
const selectedVersionSnapshot = ref<any>(null)
const showVersionSnapshotDialog = ref(false)
// 12-05 F2: compare state
const compareSelected = ref<number[]>([])
const compareLoading = ref(false)

// ── Export versions dialog state ──
const showExportVersionsDialog = ref(false)
const exportVersionsLoading = ref(false)      // loading the list
const exportVersionsList = ref<any[]>([])
const exportSelectedIds = ref<number[]>([])
const exportIncludeCurrent = ref(true)        // current live FEO preselected
const exportRunning = ref(false)              // during download

// ── Save version state ──
const showSaveVersionDialog = ref(false)
const saveVersionEffectiveDate = ref('') // YYYY-MM-DD
const saveVersionNote = ref('')
const saveVersionLoading = ref(false)

// ctx — опциональный по тому же принципу, что и в useSubsidyApprovers.ts. Нужен
// только selectedId (см. тело функций ниже) — Pick вместо полного
// SubsidyDetailContext, чтобы SubsidiesView.vue мог передать сюда просто свой
// локальный ref selectedId, не собирая по месту весь объект контекста (он
// строится один раз, в самом низу файла, через provideSubsidyDetail). Диалоги
// (настоящие потомки) вызывают usePlanGraphVersions(useSubsidyDetailCtx()) —
// полный ctx структурно совместим с Pick.
export function usePlanGraphVersions(ctx?: Pick<SubsidyDetailContext, 'selectedId'>) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
    toast.addToast(text, color, opts)
  }

  async function loadVersionHistory() {
    if (!ctx?.selectedId.value) return
    versionHistoryLoading.value = true
    try {
      versionHistoryList.value = await apiFetch<any[]>(`/subsidies/${ctx.selectedId.value}/plan-graph/versions`)
    } finally {
      versionHistoryLoading.value = false
    }
  }

  async function openVersionHistory() {
    compareSelected.value = []
    await loadVersionHistory()
    showVersionHistoryDialog.value = true
  }

  async function viewVersionSnapshot(verId: number) {
    if (!ctx?.selectedId.value) return
    selectedVersionSnapshot.value = await apiFetch<any>(`/subsidies/${ctx.selectedId.value}/plan-graph/versions/${verId}?with_reconciliation=true`)
    showVersionSnapshotDialog.value = true
  }

  async function downloadVersionExcel(vid: number) {
    if (!ctx?.selectedId.value) return
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/subsidies/${ctx.selectedId.value}/plan-graph/versions/${vid}/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error('Ошибка экспорта')
      const blob = await res.blob()
      const cd = res.headers.get('content-disposition') || ''
      const m = cd.match(/filename="?([^"]+)"?/)
      const filename = m?.[1] ?? `version-${vid}.xlsx`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка экспорта', 'error')
    }
  }

  function formatEditionDate(iso: string | null): string {
    if (!iso) return '—'
    const d = new Date(iso)
    if (isNaN(d.getTime())) return '—'
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  async function openExportVersionsDialog() {
    if (!ctx?.selectedId.value) return
    exportVersionsLoading.value = true
    showExportVersionsDialog.value = true
    exportSelectedIds.value = []
    exportIncludeCurrent.value = true
    try {
      exportVersionsList.value = await apiFetch<any[]>(`/subsidies/${ctx.selectedId.value}/plan-graph/versions`)
    } finally {
      exportVersionsLoading.value = false
    }
  }

  function toggleExportId(id: number) {
    const idx = exportSelectedIds.value.indexOf(id)
    if (idx === -1) exportSelectedIds.value.push(id)
    else exportSelectedIds.value.splice(idx, 1)
  }

  // Выгружает текущую (живую) ФЭО — тот же эндпоинт, что и кнопка «Экспорт» дерева
  // ФЭО (backend не дублируется), используется runVersionsExport ниже как частный
  // случай «выбрана только текущая, без сохранённых редакций».
  async function exportFeoToExcel() {
    if (!ctx?.selectedId.value) return
    const token = localStorage.getItem('auth_token')
    const res = await fetch(`/api/feo-categories/export?subsidy_id=${ctx.selectedId.value}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) { showSnack('Ошибка экспорта', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const cd = res.headers.get('Content-Disposition') || ''
    // Парсим RFC 5987: предпочитаем filename*=UTF-8'' (кириллица), иначе filename="...".
    // Голый /filename=([^;]+)/ захватывал кавычки → браузер превращал их в «_» → битый «.xlsx_».
    let name = 'feo_export.xlsx'
    const star = cd.match(/filename\*\s*=\s*UTF-8''([^;\n]+)/i)
    const plain = cd.match(/filename\s*=\s*(?:"([^"]+)"|([^;\n]+))/i)
    if (star) name = decodeURIComponent(star[1]!.trim())
    else if (plain) name = (plain[1] ?? plain[2] ?? name).trim()
    a.href = url; a.download = name; a.click()
    URL.revokeObjectURL(url)
  }

  async function runVersionsExport() {
    if (!ctx?.selectedId.value) return
    const sel = exportSelectedIds.value
    const inc = exportIncludeCurrent.value
    if (sel.length === 0 && !inc) {
      showSnack('Выберите хотя бы одну редакцию', 'warning')
      return
    }
    if (sel.length === 0 && inc) {
      await exportFeoToExcel()
      showExportVersionsDialog.value = false
      return
    }
    if (sel.length === 1 && !inc) {
      await downloadVersionExcel(sel[0]!)
      showExportVersionsDialog.value = false
      return
    }
    // multi: several selected, or selected+current
    exportRunning.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const url = `/api/subsidies/${ctx.selectedId.value}/plan-graph/versions/export-multi.xlsx?ids=${sel.join(',')}&include_current=${inc}`
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        let errMsg = 'Ошибка выгрузки'
        try { const j = await res.json(); errMsg = j.message || j.detail || errMsg } catch { /* ignore */ }
        throw new Error(errMsg)
      }
      const blob = await res.blob()
      const cd = res.headers.get('Content-Disposition') || ''
      let name = 'feo_editions.xlsx'
      const star = cd.match(/filename\*\s*=\s*UTF-8''([^;\n]+)/i)
      const plain = cd.match(/filename\s*=\s*(?:"([^"]+)"|([^;\n]+))/i)
      if (star) name = decodeURIComponent(star[1]!.trim())
      else if (plain) name = (plain[1] ?? plain[2] ?? name).trim()
      const objUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl; a.download = name; a.click()
      URL.revokeObjectURL(objUrl)
      showExportVersionsDialog.value = false
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка выгрузки', 'error')
    } finally {
      exportRunning.value = false
    }
  }

  async function downloadCompareExcel() {
    if (!ctx?.selectedId.value || compareSelected.value.length !== 2) return
    compareLoading.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const [v1, v2] = [...compareSelected.value].sort((a, b) => a - b)
      const res = await fetch(`/api/subsidies/${ctx.selectedId.value}/plan-graph/versions/compare.xlsx?v1=${v1}&v2=${v2}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        let errMsg = 'Ошибка сравнения'
        try {
          const err = await res.json()
          errMsg = err?.message || err?.detail?.message || err?.detail || errMsg
        } catch {}
        throw new Error(errMsg)
      }
      const blob = await res.blob()
      const cd = res.headers.get('content-disposition') || ''
      const m = cd.match(/filename="?([^"]+)"?/)
      const filename = m?.[1] ?? `compare-v${v1}-v${v2}.xlsx`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка сравнения', 'error')
    } finally {
      compareLoading.value = false
    }
  }

  // 12-05 F3: reconciliation helpers for snapshot tree view
  const flattenedSnapshotTree = computed(() => {
    const tree = selectedVersionSnapshot.value?.snapshot?.tree || []
    const out: any[] = []
    function walk(nodes: any[], depth = 1) {
      for (const n of nodes) {
        out.push({ ...n, level: depth, _key: `${n.id}_${depth}` })
        if (n.children?.length) walk(n.children, depth + 1)
      }
    }
    walk(tree)
    return out
  })

  function getReconStatus(node: any): 'matched' | 'moved' | 'orphan' {
    const rec = selectedVersionSnapshot.value?.reconciliation?.[node.id]
    if (!rec || !rec.matched_current_id) return 'orphan'
    if (rec.match_type === 'fallback') return 'moved'
    return 'matched'
  }
  function getActualUsed(nodeId: number): number {
    return selectedVersionSnapshot.value?.reconciliation?.[nodeId]?.actual_used || 0
  }
  function getActualResidual(node: any): number {
    const used = getActualUsed(node.id)
    return (node.budget || 0) - used
  }
  const snapshotTotalActual = computed(() => {
    const tree = selectedVersionSnapshot.value?.snapshot?.tree || []
    let total = 0
    // только level-1 чтобы не дублировать (children агрегированы)
    for (const n of tree) total += getActualUsed(n.id)
    return total
  })

  // 12-05: Save version
  function openSaveVersionDialog() {
    if (!ctx?.selectedId.value) return
    const today = new Date().toISOString().slice(0, 10)
    saveVersionEffectiveDate.value = today
    saveVersionNote.value = ''
    showSaveVersionDialog.value = true
  }

  async function saveVersion() {
    if (!ctx?.selectedId.value || !saveVersionEffectiveDate.value) return
    saveVersionLoading.value = true
    try {
      await apiFetch(`/subsidies/${ctx.selectedId.value}/plan-graph/versions`, {
        method: 'POST',
        body: JSON.stringify({
          effective_date: saveVersionEffectiveDate.value,
          note: saveVersionNote.value || null,
        }),
      })
      showSaveVersionDialog.value = false
      // re-load history if dialog open
      if (showVersionHistoryDialog.value) {
        await loadVersionHistory()
      }
      showSnack('Редакция ФЭО сохранена')
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка сохранения редакции', 'error')
    } finally {
      saveVersionLoading.value = false
    }
  }

  return {
    showVersionHistoryDialog, versionHistoryList, versionHistoryLoading,
    selectedVersionSnapshot, showVersionSnapshotDialog, compareSelected, compareLoading,
    showExportVersionsDialog, exportVersionsLoading, exportVersionsList, exportSelectedIds,
    exportIncludeCurrent, exportRunning,
    showSaveVersionDialog, saveVersionEffectiveDate, saveVersionNote, saveVersionLoading,
    loadVersionHistory, openVersionHistory, viewVersionSnapshot, downloadVersionExcel,
    formatEditionDate, openExportVersionsDialog, toggleExportId, exportFeoToExcel,
    runVersionsExport, downloadCompareExcel,
    flattenedSnapshotTree, getReconStatus, getActualUsed, getActualResidual, snapshotTotalActual,
    openSaveVersionDialog, saveVersion,
  }
}
