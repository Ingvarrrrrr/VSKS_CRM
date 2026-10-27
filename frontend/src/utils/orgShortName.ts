// orgShortName.ts — короткое имя организации для показа человеку (владелец,
// 27.10.2026, приёмка диалога «Похожие товары», п.3): ЕГРЮЛ/справочник
// магазинов хранит полное наименование («ОБЩЕСТВО С ОГРАНИЧЕННОЙ
// ОТВЕТСТВЕННОСТЬЮ "ТОРГОВАЯ СЕТЬ "МАГАЗИН 01""), в колонке «Магазин» нужно
// «ООО «Торговая сеть «Магазин 01»»». В проекте такого хелпера не было (grep
// по frontend/src на 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ'/shortName/abbreviate —
// пусто) — заводим один здесь, используется ТОЛЬКО в SimilarProductsDialog.vue.
// Список организационно-правовых форм намеренно короткий — расширять по
// мере необходимости, незнакомую форму не угадываем (возвращаем как есть).

// \b в JS не распознаёт кириллицу словесным символом (\w — только
// [A-Za-z0-9_]), поэтому граница формы задаётся явным lookahead на
// пробел/конец строки, а не \b.
const LEGAL_FORMS: [RegExp, string][] = [
  [/^публичное акционерное общество(?=[\s.]|$)\.?/i, 'ПАО'],
  [/^непубличное акционерное общество(?=[\s.]|$)\.?/i, 'АО'],
  [/^акционерное общество(?=[\s.]|$)\.?/i, 'АО'],
  [/^общество с ограниченной ответственностью(?=[\s.]|$)\.?/i, 'ООО'],
  [/^индивидуальный предприниматель(?=[\s.]|$)\.?/i, 'ИП'],
]

// lower-case всё, затем первая буква — заглавная ("ТОРГОВАЯ СЕТЬ " → "Торговая сеть ").
function sentenceCase(s: string): string {
  const lower = s.toLowerCase()
  const m = lower.match(/[a-zа-я0-9]/i)
  if (!m || m.index == null) return lower
  return lower.slice(0, m.index) + lower.charAt(m.index).toUpperCase() + lower.slice(m.index + 1)
}

// Sentence-case только вне уже готовых «...» сегментов (не трогаем то, что
// уже обработано нижним уровнем вложенных кавычек).
function sentenceCaseOutsideGuillemets(s: string): string {
  return s.split(/(«[^»]*»)/).map(part => (part.startsWith('«') ? part : sentenceCase(part))).join('')
}

/**
 * Полное юридическое наименование → короткое для интерфейса:
 * `ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТОРГОВАЯ СЕТЬ "МАГАЗИН 01""`
 * → `ООО «Торговая сеть «Магазин 01»»`.
 * Форма не распознана (не из LEGAL_FORMS) или нет текста — возвращает
 * исходную строку без изменений (не угадываем).
 */
export function orgShortName(fullName: string | null | undefined): string {
  const raw = (fullName || '').trim()
  if (!raw) return raw

  let abbr: string | null = null
  let rest = raw
  for (const [re, short] of LEGAL_FORMS) {
    if (re.test(rest)) {
      abbr = short
      rest = rest.replace(re, '').trim()
      break
    }
  }
  if (!abbr) return raw

  // Название может быть в кавычках (любой стиль — ", «») или без них.
  const quoteChars = ['"', '«']
  const hasQuotes = quoteChars.some(q => rest.includes(q))
  if (!hasQuotes) {
    return `${abbr} ${sentenceCase(rest)}`.trim()
  }

  // Нормализуем все кавычки (", «, ») к одному виду " для единообразного
  // парсинга вложенности, берём всё МЕЖДУ первой и последней кавычкой как
  // имя (между ними могут быть ещё одна пара кавычек — вложенное имя).
  const normalized = rest.replace(/[«»]/g, '"')
  const first = normalized.indexOf('"')
  const last = normalized.lastIndexOf('"')
  if (first === -1 || last === -1 || last <= first) {
    return `${abbr} ${sentenceCase(rest)}`.trim()
  }
  let inner = normalized.slice(first + 1, last)
  // Единственная оставшаяся пара кавычек внутри (вложенное имя) → «...»,
  // sentence-case только внутри неё.
  inner = inner.replace(/"([^"]*)"/g, (_m, g1: string) => `«${sentenceCase(g1)}»`)
  const outer = sentenceCaseOutsideGuillemets(inner).trim()
  return `${abbr} «${outer}»`
}
