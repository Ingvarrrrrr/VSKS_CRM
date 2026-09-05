/**
 * «2 минуты назад» / «нет данных 40 минут» — единая формулировка для всех мест,
 * где показывается свежесть точки местоположения (индикатор кнопки смены,
 * карта диспетчера, карточка сотрудника, свой трек). 2026-09.
 */
export function formatRelativeTime(iso: string | Date | null | undefined): string {
  if (!iso) return 'нет данных'
  const date = typeof iso === 'string' ? new Date(iso) : iso
  const diffMs = Date.now() - date.getTime()
  if (isNaN(diffMs)) return 'нет данных'
  if (diffMs < 0) return 'только что'

  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return 'только что'

  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} ${pluralMinutes(diffMin)} назад`

  const diffHours = Math.floor(diffMin / 60)
  if (diffHours < 24) return `${diffHours} ${pluralHours(diffHours)} назад`

  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays} ${pluralDays(diffDays)} назад`
}

/** Тот же расчёт, но с явным акцентом на «нет данных N времени» — используется
 * там, где важно подчеркнуть устаревание (метка на карте), а не просто время. */
export function formatStaleness(iso: string | Date | null | undefined): string {
  if (!iso) return 'нет данных'
  return formatRelativeTime(iso)
}

function pluralMinutes(n: number): string {
  return pluralRu(n, 'минуту', 'минуты', 'минут')
}
function pluralHours(n: number): string {
  return pluralRu(n, 'час', 'часа', 'часов')
}
function pluralDays(n: number): string {
  return pluralRu(n, 'день', 'дня', 'дней')
}

function pluralRu(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

/** Порог «данные свежие» / «устаревшие» / «давно нет данных» — используется для
 * цвета метки на карте диспетчера (зелёный/жёлтый/серый). */
export function stalenessLevel(iso: string | Date | null | undefined): 'fresh' | 'stale' | 'old' | 'none' {
  if (!iso) return 'none'
  const date = typeof iso === 'string' ? new Date(iso) : iso
  const diffMin = (Date.now() - date.getTime()) / 60000
  if (isNaN(diffMin)) return 'none'
  if (diffMin < 5) return 'fresh'
  if (diffMin < 30) return 'stale'
  return 'old'
}
