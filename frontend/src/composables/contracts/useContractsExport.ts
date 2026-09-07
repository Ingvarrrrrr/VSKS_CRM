// useContractsExport.ts — экспорт реестра договоров в .xlsx + .zip с
// прикреплёнными файлами (закрывающие/платёжные/прочие документы).
// Дословный перенос из ContractsView.vue (doExport).
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { contractTypeLabel, purchaseMethodLabel, fmtDate } from './contractsLabels'
import type { Contract, Purchase } from './contractsTypes'

interface CatFiles { closing: { name: string; path: string }[]; payment: { name: string; path: string }[]; other: { name: string; path: string }[] }
const CLOSING_TYPES = new Set(['act', 'upd'])
const PAYMENT_TYPES = new Set(['invoice'])

export function useContractsExport(options: {
  filtered: { value: Contract[] }
  purchasesByContract: { value: Record<number, Purchase[]> }
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { filtered, purchasesByContract, showSnack } = options

  const exportDialog = ref(false)
  const exportColumns = reactive([
    { key: 'number', title: '№ договора', selected: true },
    { key: 'date', title: 'Дата договора', selected: true },
    { key: 'contract_type', title: 'Тип договора', selected: true },
    { key: 'purchase_method', title: 'Способ закупки', selected: true },
    { key: 'contractor_name', title: 'Контрагент', selected: true },
    { key: 'contractor_inn', title: 'ИНН контрагента', selected: true },
    { key: 'subject', title: 'Предмет договора', selected: true },
    { key: 'subsidy_name', title: 'Субсидия', selected: true },
    { key: 'max_amount', title: 'Макс. сумма', selected: true },
    { key: 'total_ordered', title: 'Заказано', selected: true },
    { key: 'total_delivered', title: 'Поставлено', selected: true },
    { key: 'total_paid', title: 'Оплачено', selected: true },
    { key: 'remaining_ordered', title: 'Ост. (заказ)', selected: true },
    { key: 'remaining_delivered', title: 'Не поставлено', selected: true },
    { key: 'remaining_paid', title: 'Не оплачено', selected: true },
    { key: 'start_date', title: 'Дата начала', selected: true },
    { key: 'end_date', title: 'Дата окончания', selected: true },
    { key: 'etp_url', title: 'Ссылка ЭТП', selected: false },
    { key: 'notes', title: 'Примечания', selected: false },
    { key: 'closing_docs', title: 'Закрывающие документы', selected: true },
    { key: 'payment_docs', title: 'Платёжные документы', selected: true },
    { key: 'other_docs', title: 'Прочие документы', selected: true },
  ])

  const exportLoading = ref(false)

  async function doExport() {
    exportLoading.value = true
    try {
      const XLSX = await import('xlsx')
      const JSZip = (await import('jszip')).default
      const zip = new JSZip()
      const docsFolder = zip.folder('Документы')!
      const selected = exportColumns.filter(c => c.selected)
      const docKeys = new Set(['closing_docs', 'payment_docs', 'other_docs'])
      const hasDocCols = selected.some(c => docKeys.has(c.key))

      const header = selected.map(c => c.title)
      const rows: any[][] = [header]
      // Parallel array: for each data row, store {colKey -> zipPath} for link generation
      const rowLinks: Map<string, string>[] = []

      const contractFiles = new Map<number, CatFiles>()
      const token = localStorage.getItem('auth_token')
      const baseUrl = window.location.origin

      // Collect and download all files, categorized
      if (hasDocCols) {
        for (const contract of filtered.value) {
          const cats: CatFiles = { closing: [], payment: [], other: [] }
          const safeNum = (contract.number || contract.id).toString().replace(/[\\/:*?"<>|]/g, '_')
          const folderName = `${safeNum}_${contract.contractor_name || 'без_контрагента'}`.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
          const contractFolder = docsFolder.folder(folderName)!

          // Load purchases if not yet loaded
          if (!purchasesByContract.value[contract.id]) {
            try {
              const items = await apiFetch<Purchase[]>(`/purchases/by-contract/${contract.id}`)
              purchasesByContract.value = { ...purchasesByContract.value, [contract.id]: items }
            } catch { /* skip */ }
          }

          const purchasesForContract = purchasesByContract.value[contract.id] || []
          const seenHashes = new Set<string>()

          for (const p of purchasesForContract) {
            try {
              const filesResp = await apiFetch<any[]>(`/purchases/${p.id}/files`)
              if (!Array.isArray(filesResp)) continue
              for (const f of filesResp) {
                // Skip duplicates by content_hash within same contract export
                if (f.content_hash && seenHashes.has(f.content_hash)) continue
                if (f.content_hash) seenHashes.add(f.content_hash)

                try {
                  const resp = await fetch(`${baseUrl}/api/purchases/${p.id}/files/${f.id}/download`, {
                    headers: { Authorization: `Bearer ${token}` }
                  })
                  if (!resp.ok) continue
                  const blob = await resp.blob()
                  const fileName = f.filename || `file_${f.id}`
                  contractFolder.file(fileName, blob)
                  const entry = { name: fileName, path: `Документы/${folderName}/${fileName}` }

                  const ft = f.file_type || 'other'
                  if (CLOSING_TYPES.has(ft)) cats.closing.push(entry)
                  else if (PAYMENT_TYPES.has(ft)) cats.payment.push(entry)
                  else cats.other.push(entry)
                } catch { /* skip */ }
              }
            } catch { /* skip */ }
          }
          contractFiles.set(contract.id, cats)
        }
      }

      // Build data rows — one row per file (or at least one row per contract)
      const merges: { s: { r: number; c: number }; e: { r: number; c: number } }[] = []

      // Collect etp_urls per contract from loaded purchases
      const etpUrlsByContract = new Map<number, string>()
      for (const contract of filtered.value) {
        const ps = purchasesByContract.value[contract.id] || []
        const urls = [...new Set(ps.filter((p: Purchase) => p.purchase_method !== 'advance').map((p: Purchase) => p.etp_url).filter(Boolean))]
        etpUrlsByContract.set(contract.id, urls.join('\n'))
      }

      for (const contract of filtered.value) {
        const cats = contractFiles.get(contract.id) || { closing: [], payment: [], other: [] }
        const maxFiles = Math.max(1, cats.closing.length, cats.payment.length, cats.other.length)
        const startRow = rows.length

        for (let fi = 0; fi < maxFiles; fi++) {
          const row: any[] = []
          const links: Map<string, string> = new Map()
          for (const col of selected) {
            if (col.key === 'closing_docs') {
              row.push(cats.closing[fi]?.name || '')
              if (cats.closing[fi]) links.set(col.key, cats.closing[fi].path)
            } else if (col.key === 'payment_docs') {
              row.push(cats.payment[fi]?.name || '')
              if (cats.payment[fi]) links.set(col.key, cats.payment[fi].path)
            } else if (col.key === 'other_docs') {
              row.push(cats.other[fi]?.name || '')
              if (cats.other[fi]) links.set(col.key, cats.other[fi].path)
            } else if (fi === 0) {
              // Contract data only on first row
              if (col.key === 'contract_type') row.push(contractTypeLabel(contract.contract_type))
              else if (col.key === 'purchase_method') row.push(purchaseMethodLabel(contract.purchase_method))
              else if (col.key === 'etp_url') row.push(etpUrlsByContract.get(contract.id) || '')
              else if (['max_amount', 'total_ordered', 'total_delivered', 'total_paid', 'remaining_ordered', 'remaining_delivered', 'remaining_paid'].includes(col.key)) {
                const v = (contract as any)[col.key]; row.push(v != null ? Number(v) : '')
              } else if (['date', 'start_date', 'end_date'].includes(col.key)) row.push(fmtDate((contract as any)[col.key]))
              else row.push((contract as any)[col.key] ?? '')
            } else {
              row.push('') // empty for subsequent file rows
            }
          }
          rows.push(row)
          rowLinks.push(links)
        }

        // Merge contract data cells if multiple file rows
        if (maxFiles > 1) {
          for (let ci = 0; ci < selected.length; ci++) {
            if (!docKeys.has(selected[ci].key)) {
              merges.push({ s: { r: startRow, c: ci }, e: { r: startRow + maxFiles - 1, c: ci } })
            }
          }
        }
      }

      const ws = XLSX.utils.aoa_to_sheet(rows)
      ws['!merges'] = merges

      // Add clickable links to document cells
      for (let r = 1; r < rows.length; r++) {
        const links = rowLinks[r - 1]
        if (!links) continue
        for (const [colKey, zipPath] of links) {
          const ci = selected.findIndex(c => c.key === colKey)
          if (ci < 0) continue
          const cellRef = XLSX.utils.encode_cell({ r, c: ci })
          const cell = ws[cellRef]
          if (cell && cell.v) {
            cell.l = { Target: zipPath, Tooltip: 'Открыть документ' }
          }
        }
      }

      // Auto-width
      const colWidths = header.map((h: string, i: number) => {
        let max = h.length
        for (let r = 1; r < rows.length; r++) { max = Math.max(max, String(rows[r][i] ?? '').length) }
        return { wch: Math.min(max + 2, 50) }
      })
      ws['!cols'] = colWidths

      const wb = XLSX.utils.book_new()
      XLSX.utils.book_append_sheet(wb, ws, 'Реестр договоров')
      const xlsxData = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
      const dateSuffix = new Date().toISOString().slice(0, 10)
      zip.file(`Реестр_договоров_${dateSuffix}.xlsx`, xlsxData)

      const zipBlob = await zip.generateAsync({ type: 'blob' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(zipBlob)
      a.download = `Реестр_договоров_${dateSuffix}.zip`
      a.click()
      URL.revokeObjectURL(a.href)

      exportDialog.value = false
      showSnack('Реестр скачан')
    } catch (e: any) {
      showSnack(`Ошибка экспорта: ${e.message || e}`, 'error')
    } finally {
      exportLoading.value = false
    }
  }

  return { exportDialog, exportColumns, exportLoading, doExport }
}
