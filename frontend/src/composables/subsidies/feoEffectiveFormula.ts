// ПРАВИЛО №6 — один показатель, один источник: АГРЕГАЦИЯ «расчётной оценки
// ФЭО узла» (есть свой budget — он и есть ответ; нет — лист отдаёт свой
// прямой вклад, группа отдаёт Σ детей ПЛЮС свой собственный прямой вклад)
// была продублирована в ДВУХ местах: useFeoTreeAmounts.ts::feoEffectiveFor
// (дерево ФЭО на странице субсидии, SubsidiesView.vue) и
// FeoCategoriesView.vue::feoEffectiveFor (отдельная страница «Категории
// ФЭО»). Расхождение (находка владельца 22.10.2026, ДНР_2026 id 105): группа
// без своего budget считала оценку ТОЛЬКО как Σ детей — собственный прямой
// вклад группы (свои плановые позиции/свои закупки, заведённые прямо на
// направлении, а не в его подкатегориях) терялся МОЛЧА в обоих местах.
//
// Сами «прямые вклады» узла в двух местах РАЗНЫЕ по смыслу — на странице
// субсидии есть понятие плана (FeoPlannedItem/plan_manual с бэкенда), у
// «Категорий ФЭО» этого вовсе нет (страница не грузит plan-tree/плановые
// позиции — только бюджет узла и факт закупок). Поэтому полностью
// переиспользовать useFeoTreeAmounts.ts на той странице без переписывания её
// data-слоя (загрузка plan-tree и т.д.) нельзя — это другой контекст данных.
// Переносимая, общая часть — ТОЛЬКО форма рекурсии (budget узла первичен;
// иначе лист = свой прямой вклад; группа = Σ вклада детей + СВОЙ прямой
// вклад) — она и вынесена сюда ОДНОЙ функцией. «Прямой вклад» каждая сторона
// передаёт своим callback'ом (ownContributionFor) — единственное, что у них
// по-настоящему отличается.
export interface FeoEffectiveNode {
  budget?: number | string | null
  hasChildren: boolean
}

// ПРАВИЛО №6 (QA-находка, 22.10.2026): «нет своего ФЭО» — ОДНО правило на оба
// места (0 и null — оба «не задано», см. feedback владельца про budget=0 в
// useFeoTreeAmounts.ts), раньше FeoCategoriesView.vue держала свою копию
// (`node.hasChildren && node.budget == null` — лист без ФЭО никогда не попадал
// в «авто»-ветку, хотя его расчёт всё равно входит в ИТОГО через
// computeFeoEffective). feoBudgetIsSet — чистая проверка значения;
// isEstimatedNode — её применение к узлу БЕЗ ограничения hasChildren (лист и
// группа без своего budget одинаково «расчётные»).
export function feoBudgetIsSet(budget: number | string | null | undefined): boolean {
  return budget != null && Number(budget) !== 0
}

export function isEstimatedNode(node: FeoEffectiveNode): boolean {
  return !feoBudgetIsSet(node.budget)
}

/**
 * Расчётная оценка узла дерева ФЭО (та же формула, что раньше дублировалась
 * в useFeoTreeAmounts.ts и FeoCategoriesView.vue):
 *   - budgetIsSet(node) → Number(node.budget);
 *   - лист (!hasChildren) → ownContributionFor(node);
 *   - группа → Σ computeFeoEffective(child) по children + ownContributionFor(node)
 *     (собственный прямой вклад группы — закупки/план, заведённые прямо на
 *     направлении, не в его подкатегориях).
 *
 * budgetIsSet по умолчанию — feoBudgetIsSet выше (0 и null — «не задано»,
 * единое правило для обеих страниц, QA-правка 22.10.2026); передать свой
 * предикат можно, но по умолчанию второй копии правила больше нет.
 */
export function computeFeoEffective<T extends FeoEffectiveNode & { children: T[] }>(
  node: T,
  ownContributionFor: (node: T) => number,
  budgetIsSet: (node: T) => boolean = (n) => feoBudgetIsSet(n.budget),
): number {
  if (budgetIsSet(node)) return Number(node.budget)
  if (!node.hasChildren) return ownContributionFor(node)
  return node.children.reduce((acc, c) => acc + computeFeoEffective(c, ownContributionFor, budgetIsSet), 0)
    + ownContributionFor(node)
}
