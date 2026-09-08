import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { OdometerRow } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// История пробега для карточки ТС (виджет sparkline «История пробега»,
// Slice-2). Точки графика — последние 12 записей одометра, отсортированные
// по дате.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleOdometerHistory() {
  const odometerRows = ref<OdometerRow[]>([])

  async function loadOdometer(id: number) {
    try {
      const data = await apiFetch<OdometerRow[]>(`/vehicle-odometer/?vehicle_id=${id}`)
      odometerRows.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.warn('[useVehicleOdometerHistory] loadOdometer failed (silent):', e)
      odometerRows.value = []
    }
  }

  // Sparkline computed — last 12 odometer records sorted asc by date
  const sparkPoints = computed(() => {
    const rows = [...odometerRows.value]
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
      .slice(-12)
    return rows
  })

  // Build SVG polyline points for 600×96 viewBox
  const sparkPolyline = computed(() => {
    const pts = sparkPoints.value
    if (pts.length < 2) return ''
    const minKm = Math.min(...pts.map(p => p.odometer_km))
    const maxKm = Math.max(...pts.map(p => p.odometer_km))
    const range = maxKm - minKm || 1
    const W = 600, H = 96, PAD = 8
    return pts.map((p, i) => {
      const x = pts.length === 1 ? W / 2 : (i / (pts.length - 1)) * W
      const y = PAD + ((maxKm - p.odometer_km) / range) * (H - PAD * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
  })

  // Area path (filled) under sparkline
  const sparkAreaPath = computed(() => {
    const pts = sparkPoints.value
    if (pts.length < 2) return ''
    const minKm = Math.min(...pts.map(p => p.odometer_km))
    const maxKm = Math.max(...pts.map(p => p.odometer_km))
    const range = maxKm - minKm || 1
    const W = 600, H = 96, PAD = 8
    const coords = pts.map((p, i) => {
      const x = pts.length === 1 ? W / 2 : (i / (pts.length - 1)) * W
      const y = PAD + ((maxKm - p.odometer_km) / range) * (H - PAD * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    return `M${coords.join(' L')} L${W},${H} L0,${H} Z`
  })

  // Last spark point for the terminal dot
  const sparkLastPoint = computed(() => {
    const pts = sparkPoints.value
    if (pts.length < 2) return null
    const minKm = Math.min(...pts.map(p => p.odometer_km))
    const maxKm = Math.max(...pts.map(p => p.odometer_km))
    const range = maxKm - minKm || 1
    const W = 600, H = 96, PAD = 8
    const last = pts[pts.length - 1]
    const i = pts.length - 1
    const x = (i / (pts.length - 1)) * W
    const y = PAD + ((maxKm - last.odometer_km) / range) * (H - PAD * 2)
    return { x, y }
  })

  // Axis labels for sparkline (first, middle, last dates)
  const sparkAxisLabels = computed(() => {
    const pts = sparkPoints.value
    if (pts.length < 2) return []
    const fmt = (d: string) => {
      const dt = new Date(d)
      return `${String(dt.getMonth() + 1).padStart(2, '0')}.${String(dt.getFullYear()).slice(-2)}`
    }
    const indices = [0, Math.floor((pts.length - 1) / 2), pts.length - 1]
    return [...new Set(indices)].map(i => fmt(pts[i].date))
  })

  // Sparkline stats
  const sparkStats = computed(() => {
    const pts = sparkPoints.value
    if (pts.length < 2) return null
    const totalKm = pts[pts.length - 1].odometer_km - pts[0].odometer_km
    const months = Math.max(1, Math.round(
      (new Date(pts[pts.length - 1].date).getTime() - new Date(pts[0].date).getTime()) / (30 * 24 * 3600 * 1000)
    ))
    const avgPerMonth = Math.round(totalKm / months)
    const lastDelta = pts[pts.length - 1].delta_km ?? (pts.length >= 2 ? pts[pts.length - 1].odometer_km - pts[pts.length - 2].odometer_km : 0)
    return { totalKm, avgPerMonth, lastDelta }
  })

  return {
    odometerRows,
    loadOdometer,
    sparkPoints,
    sparkPolyline,
    sparkAreaPath,
    sparkLastPoint,
    sparkAxisLabels,
    sparkStats,
  }
}
