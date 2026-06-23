import { ref, nextTick } from 'vue'
import { useTheme } from 'vuetify'

export interface ExportColumn {
  key: string
  title: string
  align?: 'start' | 'center' | 'end'
}

export interface ExportTableOptions {
  title: string
  columns: ExportColumn[]
  rows: Array<Record<string, any>>
  format: 'xlsx' | 'pdf'
  filename?: string
}

export interface ExportZipOptions {
  title: string
  columns: ExportColumn[]
  rows: Array<Record<string, any>>
  kind: 'tasks' | 'purchases'
  filename?: string
}

export interface KanbanColumn {
  status_title: string
  cards: Array<{
    title: string
    subtitle?: string
    fields?: Array<{ label: string; value: string }>
  }>
}

export interface ExportKanbanOptions {
  title: string
  columns: KanbanColumn[]
  filename?: string
}

async function _downloadBlob(res: Response, fallbackName: string): Promise<void> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const j = await res.json(); if (j?.message) msg = j.message } catch {}
    throw new Error(msg)
  }
  const blob = await res.blob()
  let downloadName = fallbackName
  const cd = res.headers.get('Content-Disposition') ?? ''
  const match = cd.match(/filename[^;=\n]*=(?:(['"])(.+?)\1|([^;\n]+))/i)
  if (match) downloadName = (match[2] ?? match[3] ?? downloadName).trim()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = downloadName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function _authHeaders(): Record<string, string> {
  const token = localStorage.getItem('auth_token')
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

function _sanitizeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]+/g, '_').trim() || 'export'
}

/** Возвращает непрозрачный светлый цвет: прозрачный/полупрозрачный/тёмный → белый. */
function _opaqueLightBg(raw: string | null | undefined): string {
  if (!raw) return '#ffffff'
  const m = raw.match(/rgba?\(([^)]+)\)/i)
  if (!m) return raw === 'transparent' ? '#ffffff' : raw
  const parts = m[1].split(',').map((s) => parseFloat(s.trim()))
  const [r, g, b, a = 1] = parts
  if (a < 0.95) return '#ffffff'
  // Тёмный фон (тёмная тема) → светлый лист
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b
  if (luminance < 130) return '#ffffff'
  return `rgb(${r}, ${g}, ${b})`
}

export interface ScreenshotPdfOptions {
  /** CSS-селекторы элементов, которые надо скрыть в PDF (напр. нефункциональная колонка «Действия»). */
  hideSelectors?: string[]
  /** Доп. CSS, инжектируемый в клон документа перед снимком (только для рендера PDF). */
  extraCss?: string
}

/**
 * WYSIWYG-PDF: снимок реального DOM-элемента (текущий вид — таблица/карточки,
 * цвета, бейджи статусов) через html2canvas → постранично в jsPDF.
 */
async function _exportScreenshotPdf(
  el: HTMLElement,
  title: string,
  filename?: string,
  opts?: ScreenshotPdfOptions,
): Promise<void> {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import('html2canvas'),
    import('jspdf'),
  ])

  // Фон PDF всегда непрозрачный светлый: прозрачный/rgba(0,0,0,0) фон (VueFlow-канва,
  // элементы без своего фона) html2canvas → jsPDF превращает в ЧЁРНЫЙ. Принудительно белый.
  const bg = _opaqueLightBg(getComputedStyle(document.body).backgroundColor)

  // Подготовка к снимку через реальный DOM (html2canvas-onclone с sticky-колонками
  // ненадёжен). Прячем нефункциональные элементы и вливаем PDF-CSS, потом откатываем.
  const hidden: HTMLElement[] = []
  if (opts?.hideSelectors?.length) {
    el.querySelectorAll<HTMLElement>(opts.hideSelectors.join(',')).forEach((n) => {
      n.dataset._pdfDisplay = n.style.display
      n.style.display = 'none'
      hidden.push(n)
    })
  }
  let styleEl: HTMLStyleElement | null = null
  if (opts?.extraCss) {
    styleEl = document.createElement('style')
    styleEl.textContent = opts.extraCss
    document.head.appendChild(styleEl)
  }
  await new Promise<void>((r) => requestAnimationFrame(() => r()))

  let canvas: HTMLCanvasElement
  try {
    canvas = await html2canvas(el, {
      scale: Math.min(2, window.devicePixelRatio || 1.5),
      backgroundColor: bg,
      useCORS: true,
      logging: false,
      windowWidth: el.scrollWidth,
      windowHeight: el.scrollHeight,
    })
  } finally {
    for (const n of hidden) {
      n.style.display = n.dataset._pdfDisplay ?? ''
      delete n.dataset._pdfDisplay
    }
    if (styleEl) styleEl.remove()
  }

  const orientation = canvas.width >= canvas.height ? 'landscape' : 'portrait'
  const pdf = new jsPDF({ orientation, unit: 'pt', format: 'a4' })
  const pageW = pdf.internal.pageSize.getWidth()
  const pageH = pdf.internal.pageSize.getHeight()
  const margin = 24

  const imgW = pageW - margin * 2
  const imgH = (canvas.height * imgW) / canvas.width
  const img = canvas.toDataURL('image/png')

  if (imgH <= pageH - margin * 2) {
    pdf.addImage(img, 'PNG', margin, margin, imgW, imgH)
  } else {
    // Высокий контент — режем canvas по страницам
    const pxPerPage = Math.floor((canvas.width * (pageH - margin * 2)) / imgW)
    let renderedPx = 0
    let first = true
    while (renderedPx < canvas.height) {
      const sliceH = Math.min(pxPerPage, canvas.height - renderedPx)
      const slice = document.createElement('canvas')
      slice.width = canvas.width
      slice.height = sliceH
      const ctx = slice.getContext('2d')!
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, slice.width, slice.height)
      ctx.drawImage(canvas, 0, renderedPx, canvas.width, sliceH, 0, 0, canvas.width, sliceH)
      const sliceImg = slice.toDataURL('image/png')
      const sliceImgH = (sliceH * imgW) / canvas.width
      if (!first) pdf.addPage()
      pdf.addImage(sliceImg, 'PNG', margin, margin, imgW, sliceImgH)
      renderedPx += sliceH
      first = false
    }
  }

  const name = filename ?? `${_sanitizeFilename(title)}_${new Date().toISOString().slice(0, 10)}.pdf`
  pdf.save(name)
}

export function useRegistryExport() {
  const exporting = ref(false)
  const theme = useTheme()

  async function exportScreenshotPdf(
    el: HTMLElement,
    title: string,
    filename?: string,
    opts?: ScreenshotPdfOptions,
  ): Promise<void> {
    exporting.value = true
    // PDF всегда в светлой теме — тёмный фон/белый текст нечитаемы на бумаге.
    const prevTheme = theme.global.name.value
    const wasDark = theme.global.current.value.dark
    try {
      if (wasDark) {
        theme.global.name.value = 'light'
        await nextTick()
        await new Promise<void>((r) => requestAnimationFrame(() => r()))
      }
      await _exportScreenshotPdf(el, title, filename, opts)
    } finally {
      if (wasDark) theme.global.name.value = prevTheme
      exporting.value = false
    }
  }

  async function exportTable(opts: ExportTableOptions): Promise<void> {
    exporting.value = true
    try {
      const { format, filename, ...body } = opts
      const res = await fetch(`/api/exports/table.${format}`, {
        method: 'POST',
        headers: _authHeaders(),
        body: JSON.stringify({ ...body, filename }),
      })
      await _downloadBlob(res, filename ?? `${opts.title}.${format}`)
    } finally {
      exporting.value = false
    }
  }

  async function exportZip(opts: ExportZipOptions): Promise<void> {
    exporting.value = true
    try {
      const res = await fetch('/api/exports/tasks.zip', {
        method: 'POST',
        headers: _authHeaders(),
        body: JSON.stringify({
          title: opts.title,
          columns: opts.columns,
          rows: opts.rows,
          kind: opts.kind,
          filename: opts.filename,
        }),
      })
      await _downloadBlob(res, opts.filename ?? `${opts.title}.zip`)
    } finally {
      exporting.value = false
    }
  }

  async function exportKanban(opts: ExportKanbanOptions): Promise<void> {
    exporting.value = true
    try {
      const res = await fetch('/api/exports/kanban.pdf', {
        method: 'POST',
        headers: _authHeaders(),
        body: JSON.stringify({
          title: opts.title,
          columns: opts.columns,
          filename: opts.filename,
        }),
      })
      await _downloadBlob(res, opts.filename ?? `${opts.title}.pdf`)
    } finally {
      exporting.value = false
    }
  }

  return { exportTable, exportZip, exportKanban, exportScreenshotPdf, exporting }
}
