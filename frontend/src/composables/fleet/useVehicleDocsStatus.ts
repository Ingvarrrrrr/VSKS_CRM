import { computed, type Ref } from 'vue'
import type { Vehicle } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Статус документов/сроков карточки ТС (алерты, quick-stats плитка
// «Документы», карточка «Документы и сроки», статус-пилюля hero-плашки).
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleDocsStatus(vehicle: Ref<Vehicle | null>) {
  const isInsuranceExpiringSoon = computed(() => {
    if (!vehicle.value?.insurance_until) return false
    const diff = new Date(vehicle.value.insurance_until).getTime() - Date.now()
    return diff < 30 * 24 * 3600 * 1000
  })

  const isToSoon = computed(() => {
    if (vehicle.value?.next_to_km == null || vehicle.value?.current_odometer_km == null) return false
    return (vehicle.value.next_to_km - vehicle.value.current_odometer_km) < 1000
  })

  /** Returns how many days remain until a date string. Negative = expired. */
  function daysLeftNum(dateStr: string | null | undefined): number | null {
    if (!dateStr) return null
    const diff = new Date(dateStr).getTime() - Date.now()
    return Math.round(diff / (24 * 3600 * 1000))
  }

  /** Human-readable days-left label */
  function daysLeft(dateStr: string | null | undefined): string {
    const n = daysLeftNum(dateStr)
    if (n === null) return '—'
    if (n < 0) return `просрочен ${Math.abs(n)} дн.`
    if (n === 0) return 'сегодня'
    return `${n} дн.`
  }

  /** CSS class for document dot indicator */
  function docDotClass(dateStr: string | null | undefined): string {
    if (!dateStr) return 'vp-dot--alert'
    const n = daysLeftNum(dateStr) ?? 0
    if (n < 0) return 'vp-dot--alert'
    if (n < 30) return 'vp-dot--warn'
    return 'vp-dot--ok'
  }

  /** Initials from org name for avatar */
  const respInitials = computed(() => {
    const name = vehicle.value?.assigned_org_name || vehicle.value?.owner_org_name || ''
    if (!name) return '?'
    const words = name.trim().split(/\s+/)
    if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
    return name.slice(0, 2).toUpperCase()
  })

  /** Document status summary for quick-stats tile */
  const docsStatus = computed(() => {
    const v = vehicle.value
    if (!v) return { filled: 0, hasProblems: false, problemText: 'нет данных' }

    const now = Date.now()
    const problems: string[] = []
    let filled = 0

    // ОСАГО
    if (v.insurance_until) {
      const ok = new Date(v.insurance_until).getTime() > now
      if (ok) filled++
      else problems.push('ОСАГО истёк')
    } else {
      problems.push('нет ОСАГО')
    }

    // Техосмотр
    if (v.tech_inspection_until) {
      const ok = new Date(v.tech_inspection_until).getTime() > now
      if (ok) filled++
      else problems.push('техосмотр истёк')
    } else {
      problems.push('нет техосмотра')
    }

    // ПТС
    if (v.pts_number) filled++
    else problems.push('нет ПТС')

    // СТС
    if (v.sts_number) filled++
    else problems.push('нет СТС')

    const hasProblems = problems.length > 0
    const problemText: string = hasProblems ? problems[0]! : 'все документы OK'

    return { filled, hasProblems, problemText }
  })

  return {
    isInsuranceExpiringSoon,
    isToSoon,
    daysLeftNum,
    daysLeft,
    docDotClass,
    respInitials,
    docsStatus,
  }
}
