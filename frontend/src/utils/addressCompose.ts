// Сборка/разбор адреса по частям — зеркало backend/app/services/address_compose.py
// (ПРАВИЛО №6: один и тот же алгоритм, продублирован сюда только из-за границы
// Python/TS — другого способа делить код между FastAPI и Vue в проекте нет).
// Не писать второй регэксп на «г./г.о.» где-то ещё на фронте — звать
// extractSettlementName()/parseAddress() отсюда.
//
// Баг владельца (28.10.2026): «г.о. Бердянск» разбиралось как «о.Бердянск» —
// регэксп на префикс «г.» не отличал его от сокращения «г.о.» (городской
// округ). Фикс — тот же, что и в backend/app/services/address_compose.py.

export interface AddressParts {
  postal_code: string
  region: string
  district: string
  settlement_type: string
  settlement: string
  street: string
  house: string
  building: string
  office: string
}

export const ADDRESS_PART_KEYS: (keyof AddressParts)[] = [
  'postal_code', 'region', 'district', 'settlement_type', 'settlement',
  'street', 'house', 'building', 'office',
]

export function emptyAddressParts(): AddressParts {
  return {
    postal_code: '', region: '', district: '', settlement_type: '', settlement: '',
    street: '', house: '', building: '', office: '',
  }
}

export function hasAnyAddressPart(parts: Partial<AddressParts> | null | undefined): boolean {
  if (!parts) return false
  return ADDRESS_PART_KEYS.some(k => !!(parts[k] || '').toString().trim())
}

// --- Населённый пункт -------------------------------------------------
const G_PREFIX_RE = /(?:^|,)\s*г(?:\.\s*|\s+)(?!о\.)([^,]+?)\s*(?:,|$)/i
const CITY_WORD_RE = /(?:^|,)\s*город\s+([^,]+?)\s*(?:,|$)/i
const FEDERAL_CITIES = ['Москва', 'Санкт-Петербург', 'Севастополь']
const OKRUG_RE = /(?:^|,)\s*г\.?\s*о\.?\s*([^,]+?)\s*(?:,|$)|(?:^|,)\s*городск\w*\s+округ\w*\s+([^,]+?)\s*(?:,|$)|(?:^|,)\s*муниципальн\w*\s+округ\w*\s+([^,]+?)\s*(?:,|$)/i
const RAION_RE = /(?:^|,)\s*([^,]*?\bрайон[^,]*?)\s*(?:,|$)/i
const STREET_RE = /(?:^|,)\s*((?:ул\.|улица|пр-т|проспект|пер\.|переулок|ш\.|шоссе|б-р|бульвар|наб\.|набережная|пл\.|площадь)\s*[^,]*?)\s*(?:,|$)/i
const HOUSE_RE = /(?:^|,)\s*(?:д\.|дом)\s*([^,]+?)\s*(?:,|$)/i
const BUILDING_RE = /(?:^|,)\s*(?:корп\.?|корпус|стр\.?|строение)\s*([^,]+?)\s*(?:,|$)/i
const OFFICE_RE = /(?:^|,)\s*(?:оф\.?|офис|кв\.?|квартира|пом\.?|помещение)\s*([^,]+?)\s*(?:,|$)/i
const POSTAL_RE = /(?<!\d)(\d{6})(?!\d)/

export function extractSettlementName(address: string | null | undefined): string {
  if (!address || !address.trim()) return ''
  let m = G_PREFIX_RE.exec(address)
  if (m) return m[1].trim()
  m = CITY_WORD_RE.exec(address)
  if (m) return m[1].trim()
  for (const fed of FEDERAL_CITIES) {
    const re = new RegExp('(?:^|[,\\s])' + fed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?:[,\\s]|$)')
    if (re.test(address)) return fed
  }
  m = OKRUG_RE.exec(address)
  if (m) {
    const name = m[1] || m[2] || m[3] || ''
    return name.trim()
  }
  return ''
}

function settlementTypeFor(address: string, settlement: string): string {
  if (!settlement) return ''
  if (G_PREFIX_RE.test(address)) return 'г.'
  if (CITY_WORD_RE.test(address)) return 'г.'
  if (FEDERAL_CITIES.includes(settlement)) return ''
  if (OKRUG_RE.test(address)) return 'г.о.'
  return ''
}

function extractDistrictName(address: string, settlement: string): string {
  if (!address) return ''
  let m = RAION_RE.exec(address)
  if (m) {
    const name = m[1].trim()
    if (name && name.toLowerCase() !== (settlement || '').toLowerCase()) return name
  }
  m = OKRUG_RE.exec(address)
  if (m) {
    const name = (m[1] || m[2] || m[3] || '').trim()
    if (name && G_PREFIX_RE.test(address) && name.toLowerCase() !== (settlement || '').toLowerCase()) {
      return name
    }
  }
  return ''
}

function extractSegment(address: string, re: RegExp): string {
  if (!address) return ''
  const m = re.exec(address)
  return m ? m[1].trim() : ''
}

/** Строка адреса → части. Best-effort, никогда не бросает. Зеркало
 * backend/app/services/address_compose.py::parse_address. */
export function parseAddress(address: string | null | undefined): AddressParts {
  const result = emptyAddressParts()
  if (!address || !address.trim()) return result
  const text = address.trim()

  const postal = POSTAL_RE.exec(text)
  if (postal) result.postal_code = postal[1]

  const settlement = extractSettlementName(text)
  if (settlement) {
    result.settlement = settlement
    result.settlement_type = settlementTypeFor(text, settlement)
  }

  const district = extractDistrictName(text, settlement)
  if (district) result.district = district

  result.street = extractSegment(text, STREET_RE)
  result.house = extractSegment(text, HOUSE_RE)
  result.building = extractSegment(text, BUILDING_RE)
  result.office = extractSegment(text, OFFICE_RE)
  return result
}

/** Части → строка адреса. Зеркало address_compose.py::compose_address.
 * Регион (`region`) сюда НЕ передаётся с фронта — распознавание субъекта РФ
 * по тексту (region_from_text.py) живёт только на backend; на фронте
 * предпросмотр строится из region, введённого/разобранного так же. */
export function composeAddress(parts: Partial<AddressParts> | null | undefined): string {
  const p = { ...emptyAddressParts(), ...(parts || {}) }
  const segments: string[] = []
  if (p.postal_code.trim()) segments.push(p.postal_code.trim())
  if (p.region.trim()) segments.push(p.region.trim())
  if (p.district.trim()) segments.push(p.district.trim())
  if (p.settlement.trim()) {
    const stype = p.settlement_type.trim()
    segments.push(stype ? `${stype} ${p.settlement.trim()}` : p.settlement.trim())
  }
  if (p.street.trim()) segments.push(p.street.trim())
  if (p.house.trim()) segments.push(`д. ${p.house.trim()}`)
  if (p.building.trim()) segments.push(`корп. ${p.building.trim()}`)
  if (p.office.trim()) segments.push(`оф. ${p.office.trim()}`)
  return segments.filter(Boolean).join(', ')
}
