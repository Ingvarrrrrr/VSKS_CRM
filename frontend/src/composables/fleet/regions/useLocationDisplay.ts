import { findCityInCatalog } from '@/components/fleet/russiaCitiesCatalog'

// Визуальные хелперы для отображения «места нахождения» — общие для
// топ-списка, карточек и пинов карты (ПРАВИЛО №6: одна функция форматирования
// на каждый показатель, не дублировать в каждом компоненте).
const BADGE_PALETTES = [
  { bg: 'rgba(106,166,255,.12)', color: '#6aa6ff' },
  { bg: 'rgba(246,179,74,.12)', color: '#f6b34a' },
  { bg: 'rgba(34,201,151,.12)', color: '#22c997' },
  { bg: 'rgba(139,92,246,.12)', color: '#8b5cf6' },
  { bg: 'rgba(93,208,255,.12)', color: '#5dd0ff' },
  { bg: 'rgba(255,91,106,.12)', color: '#ff5b6a' },
]

const CARD_COLORS = ['blue', 'amber', 'green', 'purple', 'cyan', 'red'] as const

// 2026-09: раньше абревиатура бралась из первых букв ВСЕХ слов подряд, включая
// региональные префиксы ("ДНР г. Донецк" → "ДГД") — бессмысленный набор букв.
// Теперь префиксы региона/административной единицы отбрасываются, а «Место не
// указано» получает нейтральный прочерк вместо абревиатуры-мусора «МНУ».
const ABBR_NOISE = new Set(['днр', 'лнр', 'г.', 'г', 'обл.', 'область', 'край', 'респ.', 'республика'])

export function useLocationDisplay() {
  function locationAbbr(name: string): string {
    const trimmed = name.trim()
    if (!trimmed || trimmed === 'Место не указано') return '—'
    const words = trimmed.split(/\s+/).filter(Boolean)
    const meaningful = words.filter(w => !ABBR_NOISE.has(w.toLowerCase()))
    const pick = meaningful.length ? meaningful : words
    const lettersOnly = (w: string) => w.replace(/[^\p{L}]/gu, '')
    if (pick.length === 1) {
      const clean = lettersOnly(pick[0]) || pick[0]
      return clean.slice(0, 3).toUpperCase()
    }
    return pick.slice(0, 3).map(w => (lettersOnly(w)[0] || w[0] || '')).join('').toUpperCase()
  }

  function locationBadgeBg(idx: number): string {
    return BADGE_PALETTES[idx % BADGE_PALETTES.length].bg
  }

  function locationBadgeColor(idx: number): string {
    return BADGE_PALETTES[idx % BADGE_PALETTES.length].color
  }

  function cardColorClassForLocation(idx: number): string {
    return `rv-card--${CARD_COLORS[idx % CARD_COLORS.length]}`
  }

  // 2026-09 (geo-fix #4, п.1): раньше подпись под названием места нахождения
  // («ФПГ ДНР» / «филиал ЦУ» и т.п.) бралась из geo_normalize.shtab_label_for_city
  // — жёстко зашитый источник приобретения/штаб по кучке ключевых слов, не
  // связанный с реальными данными парка. Владелец: на карте эта подпись лишняя
  // (это не место нахождения, а справочная категория). В списке/карточках та же
  // подпись настолько же неинформативна («группа не определена» почти всегда),
  // поэтому здесь она тоже убрана — вместо неё показываем субъект РФ (регион),
  // в котором находится место, если справочник городов (russiaCitiesCatalog.ts)
  // смог его определить. Пусто — subtitle не рендерится (см. v-if в шаблонах).
  function locationSubtitle(region: string): string {
    if (!region || region === 'Место не указано') return ''
    const hit = findCityInCatalog(region)
    return hit ? hit.region : ''
  }

  return {
    locationAbbr,
    locationBadgeBg,
    locationBadgeColor,
    cardColorClassForLocation,
    locationSubtitle,
  }
}
