import type { Options } from 'html2canvas'

let tinyCanvas: HTMLCanvasElement | null = null
let activeGuards = 0
let origCreatePattern: typeof CanvasRenderingContext2D.prototype.createPattern | null = null
let origDrawImage: typeof CanvasRenderingContext2D.prototype.drawImage | null = null

function getTinyCanvas(): HTMLCanvasElement {
  if (!tinyCanvas) {
    tinyCanvas = document.createElement('canvas')
    tinyCanvas.width = 1
    tinyCanvas.height = 1
  }
  return tinyCanvas
}

function isZeroSizedDrawable(source: unknown): boolean {
  if (!source || typeof source !== 'object') return false
  const candidate = source as { width?: unknown; height?: unknown }
  const w = typeof candidate.width === 'number' ? candidate.width : null
  const h = typeof candidate.height === 'number' ? candidate.height : null
  if (w !== null && w <= 0) return true
  if (h !== null && h <= 0) return true
  return false
}

export function installZeroCanvasGuards(): () => void {
  if (typeof CanvasRenderingContext2D === 'undefined') {
    return () => {}
  }
  const proto = CanvasRenderingContext2D.prototype
  if (activeGuards === 0) {
    origCreatePattern = proto.createPattern
    origDrawImage = proto.drawImage

    proto.createPattern = function safeCreatePattern(
      this: CanvasRenderingContext2D,
      image: CanvasImageSource,
      repetition: string | null,
    ): CanvasPattern | null {
      const safeImage = isZeroSizedDrawable(image) ? getTinyCanvas() : image
      return origCreatePattern!.call(this, safeImage, repetition)
    }

    proto.drawImage = function safeDrawImage(
      this: CanvasRenderingContext2D,
      image: CanvasImageSource,
      ...args: number[]
    ): void {
      if (isZeroSizedDrawable(image)) return
      return (origDrawImage as (...a: unknown[]) => void).call(this, image, ...args)
    } as typeof CanvasRenderingContext2D.prototype.drawImage
  }
  activeGuards += 1

  let released = false
  return () => {
    if (released) return
    released = true
    activeGuards = Math.max(0, activeGuards - 1)
    if (activeGuards === 0) {
      if (origCreatePattern) proto.createPattern = origCreatePattern
      if (origDrawImage) proto.drawImage = origDrawImage
      origCreatePattern = null
      origDrawImage = null
    }
  }
}

function sanitizeClonedDom(clonedDoc: Document, clonedRoot: HTMLElement): void {
  clonedDoc.querySelectorAll('canvas').forEach((c) => {
    if (c.width <= 0 || c.height <= 0) {
      c.style.display = 'none'
    }
  })

  const view = clonedDoc.defaultView
  const targets = clonedRoot.querySelectorAll<HTMLElement>(
    '.v-progress-linear__determinate, .v-progress-linear__indeterminate, .v-skeleton-loader, [style*="gradient"], .feo-stage-row',
  )
  targets.forEach((node) => {
    const inlineW = node.style.width
    const inlineH = node.style.height
    const cs = view?.getComputedStyle(node)
    const zeroSize =
      inlineW === '0%' ||
      inlineW === '0px' ||
      inlineH === '0%' ||
      inlineH === '0px' ||
      cs?.width === '0px' ||
      cs?.height === '0px' ||
      cs?.display === 'none'
    if (zeroSize) {
      node.style.setProperty('background-image', 'none', 'important')
      node.style.setProperty('border-image', 'none', 'important')
    }
  })
}

export async function safeHtml2Canvas(
  el: HTMLElement,
  options: Partial<Options> = {},
): Promise<HTMLCanvasElement> {
  const rect = el.getBoundingClientRect()
  if (rect.width < 1 || rect.height < 1) {
    throw new Error('Таблица скрыта или пуста — невозможно сформировать PDF с экрана')
  }

  const { default: html2canvas } = await import('html2canvas')
  const userIgnore = options.ignoreElements
  const userOnClone = options.onclone

  const releaseGuards = installZeroCanvasGuards()
  try {
    return await html2canvas(el, {
      ...options,
      ignoreElements: (node) => {
        if (node instanceof HTMLCanvasElement && (node.width <= 0 || node.height <= 0)) {
          return true
        }
        if (node instanceof HTMLElement) {
          if (node.hasAttribute('data-html2canvas-ignore')) return true
          if (node.classList.contains('v-overlay-container')) return true
        }
        return userIgnore ? userIgnore(node) : false
      },
      onclone: (clonedDoc, clonedEl) => {
        sanitizeClonedDom(clonedDoc, clonedEl)
        userOnClone?.(clonedDoc, clonedEl)
      },
    })
  } finally {
    releaseGuards()
  }
}
