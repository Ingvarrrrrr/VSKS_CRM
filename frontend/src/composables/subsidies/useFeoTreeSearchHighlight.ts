// Ожидание появления узла/плановой позиции в DOM после поиска по дереву ФЭО
// (владелец, 2026-10-13, правка к useFeoTreeSearch.ts::goToFeoSearchResult —
// см. докстринг там же). Вынесено в отдельный файл по Правилу №5: сама логика
// поиска (useFeoTreeSearch.ts) и логика ожидания+прокрутки — две разные
// ответственности, держать их в одном файле означало бы снова раздувать его.
//
// Раньше scrollAndHighlight ждал РОВНО 2 фиксированных nextTick после await
// refreshComparison и тихо завершался (return), если querySelector не находил
// элемент — пользователь не получал никакого сигнала, что поиск не сработал.
// На практике двух тиков не хватает: раскрытие предков (expandedIds) +
// подгрузка comparisonData + перерисовка глубоко вложенного дерева ФЭО —
// несколько последовательных реактивных обновлений, и готового элемента в DOM
// после второго nextTick может ещё не быть. Вместо фиксированного числа тиков —
// опрос querySelector до 5 секунд (owner: «подождать появления... опрос
// querySelector до 5 с, например каждые 100 мс»).
export async function waitForFeoSearchElement(
  root: HTMLElement,
  selector: string,
  timeoutMs = 5000,
  intervalMs = 100,
): Promise<HTMLElement | null> {
  const started = Date.now()
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const el = root.querySelector<HTMLElement>(selector)
    if (el) return el
    if (Date.now() - started >= timeoutMs) return null
    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }
}
