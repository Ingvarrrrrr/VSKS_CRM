// alignBudgetAllPreview.ts — чистая формула подтверждения «Приравнять ФЭО к
// плану по всем статьям» (AlignBudgetAllDialog.vue), вынесена в отдельный
// файл (ПРАВИЛО №5), чтобы считать её юнит-тестом на синтетическом дереве
// без монтирования компонента/мока ctx-синглтона.
//
// НАЙДЕНО владельцем 27.10.2026 (ДНР_актуальная): «у 41 статьи на сумму
// 99 215 853,86 ₽» при плане 62 973 630,53 ₽ — старая формула суммировала
// newBudget КАЖДОГО изменённого узла дерева подряд (группы И их дети вместе).
// node.plan/node.over УЖЕ кумулятивны по поддереву (compute_feo_plan_tree на
// backend, та же величина здесь из ctx.planTreeByCat) — сумма группы уже
// включает сумму детей, повторное сложение через сами дети задваивало деньги.
//
// Три отдельные величины теперь:
//   count        — сколько ЛИСТОВЫХ категорий (!hasChildren) реально меняются.
//                  Решение: ГРУППА — не «статья» сама по себе (её own-сумма
//                  целиком состоит из листьев, считать её отдельной «статьёй»
//                  задвоило бы листья) — «статья» в терминах владельца — это
//                  конечная строка ФЭО, не агрегат направления/подкатегории.
//   budgetAfter  — Σ ТОЛЬКО по КОРНЕВЫМ узлам (parent_id===null) нового
//                  бюджета (plan+over), если корень меняется, иначе старого —
//                  та же техника, что уже не даёт задвоения у calculated_
//                  budget/feo_budget_total на backend (Σ по корням, не по
//                  всем узлам дерева), см. app.services.feo_tree_write.
//                  align_budget_to_plan_all — ОДНА формула на фронте и бэке.
//   budgetBefore — читается вызывающим кодом напрямую из ctx.selectedBudget
//                  (тот же источник, что карточка «Бюджет (ФЭО)»), сюда не
//                  передаётся — эта функция считает только то, что меняется.

export interface AlignPreviewCategory {
  id: number
  parent_id: number | null
  hasChildren: boolean
  budget: number | string | null | undefined
}

export interface AlignPreviewPlanEntry {
  plan?: number
  over?: number
}

const EPS = 0.005

/** newBudget узла — ТА ЖЕ целевая формула, что align_budget_to_plan на backend. */
export function alignTargetBudget(entry: AlignPreviewPlanEntry | undefined): number {
  return Number(entry?.plan || 0) + Number(entry?.over || 0)
}

export interface AlignBudgetAllPreview {
  count: number
  budgetAfter: number
}

export function computeAlignBudgetAllPreview(
  categories: AlignPreviewCategory[],
  planTreeByCat: Record<number, AlignPreviewPlanEntry | undefined>,
): AlignBudgetAllPreview {
  let count = 0
  for (const cat of categories) {
    if (cat.hasChildren) continue  // группа — не «статья», см. докстринг выше
    const newBudget = alignTargetBudget(planTreeByCat[cat.id])
    const oldBudget = Number(cat.budget || 0)
    if (Math.abs(newBudget - oldBudget) > EPS) count += 1
  }

  let budgetAfter = 0
  for (const cat of categories) {
    if (cat.parent_id != null) continue  // только корни — Σ по ним без задвоения
    const newBudget = alignTargetBudget(planTreeByCat[cat.id])
    const oldBudget = Number(cat.budget || 0)
    budgetAfter += Math.abs(newBudget - oldBudget) > EPS ? newBudget : oldBudget
  }

  return { count, budgetAfter: Math.round(budgetAfter * 100) / 100 }
}
