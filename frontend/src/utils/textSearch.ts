// textSearch.ts — общий текстовый поиск «слова в любом порядке, без учёта
// регистра и ё/е» (Правило №6: один алгоритм на весь проект, не копия цикла
// в каждом месте). Выделено из трёх мест, где эта логика уже жила отдельно:
//  - useFeoTreeSearch.ts (searchWords/matchesAllWords — поиск по дереву ФЭО,
//    владелец 2026-09-15: «ОУ-2 огнетушитель» находит «Огнетушитель ОУ-2»);
//  - FeoPlanTreePicker.vue (normalize/queryWords/nameMatches — тот же приём,
//    плюс ё→е и снятие пунктуации);
//  - ordersSearch.ts (itemsMatchQuery/purchaseMatchesSearch — раньше было
//    подстрокой по ЦЕЛОЙ строке запроса, здесь переведено на то же словное
//    сравнение, что и остальные два места).
// Задача владельца (15.10.2026): «поле динамического поиска» во всплывающих
// окнах субсидии — использует эти же функции (useDrillSearch.ts), второй
// движок сравнения строк не заводим.

/** Нормализация текста: нижний регистр, ё→е, всё не-буквенно-цифровое — в
 *  пробел, схлопнуть повторные пробелы, обрезать края. */
export function normalizeSearchText(s: string | null | undefined): string {
  return (s ?? '')
    .toString()
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

/** Запрос → список непустых нормализованных слов для поиска. Vuetify
 *  clearable (кнопка «×») отдаёт null, а не '' — нормализация обрабатывает
 *  null сама. */
export function searchWords(query: string | null | undefined): string[] {
  const n = normalizeSearchText(query)
  return n ? n.split(' ') : []
}

/** Все слова запроса встречаются в тексте подстрокой, в любом порядке —
 *  никакого fuzzy (см. feedback_dedup_exact_only.md — тот же принцип). */
export function matchesAllWords(text: string | null | undefined, words: string[]): boolean {
  if (!words.length) return true
  const t = normalizeSearchText(text)
  return words.every(w => t.includes(w))
}
