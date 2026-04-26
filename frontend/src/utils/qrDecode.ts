import jsQR from 'jsqr'

async function loadBitmap(file: File): Promise<{ bitmap: ImageBitmap | HTMLImageElement, width: number, height: number }> {
  if ('createImageBitmap' in window) {
    try {
      const bm = await createImageBitmap(file, { imageOrientation: 'from-image' as any })
      return { bitmap: bm, width: bm.width, height: bm.height }
    } catch { /* fallback */ }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.src = url
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej })
    return { bitmap: img, width: img.naturalWidth || img.width, height: img.naturalHeight || img.height }
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

function decodeFromBitmap(bm: ImageBitmap | HTMLImageElement, w: number, h: number, rotate: 0 | 90 | 180 | 270 = 0): string | null {
  const MAX = 1600
  const scale = Math.min(1, MAX / Math.max(w, h))
  const dw = Math.max(1, Math.round(w * scale))
  const dh = Math.max(1, Math.round(h * scale))
  const c = document.createElement('canvas')
  if (rotate === 90 || rotate === 270) { c.width = dh; c.height = dw } else { c.width = dw; c.height = dh }
  const ctx = c.getContext('2d', { willReadFrequently: true })!
  ctx.translate(c.width / 2, c.height / 2)
  ctx.rotate((rotate * Math.PI) / 180)
  ctx.drawImage(bm as any, -dw / 2, -dh / 2, dw, dh)
  const data = ctx.getImageData(0, 0, c.width, c.height)
  const code = jsQR(data.data, data.width, data.height, { inversionAttempts: 'attemptBoth' })
  return code?.data || null
}

export async function decodeQrFromImageFile(file: File): Promise<string | null> {
  const { bitmap, width, height } = await loadBitmap(file)
  for (const r of [0, 90, 180, 270] as const) {
    const code = decodeFromBitmap(bitmap, width, height, r)
    if (code) return code
  }
  return null
}
