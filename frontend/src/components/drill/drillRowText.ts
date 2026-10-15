// drillRowText.ts — «текст строки» для поиска в каждом из окон-расшифровок
// (Правило №5 — вынесено из самих диалогов, StageFeoDrillDialog.vue и
// FeoCardDrillDialog.vue уже за 500 строк, новая логика сюда, а не в них;
// Правило №6 — одна функция textOf на вид строки, не копия в каждом
// диалоге). Используется через useDrillSearch.ts (frontend/src/composables/
// useDrillSearch.ts) и DrillSearchField.vue.
//
// Сумма кладётся в текст ДВАЖДЫ — с запятой и с точкой (владелец, 15.10.2026:
// совпадение по сумме «как строка цифр с запятой и без пробелов, например
// «11870,60» и «11870.60»»).
function amountText(n: number | null | undefined): string {
  if (n == null || typeof n !== 'number' || Number.isNaN(n)) return ''
  const abs = Math.abs(n)
  return `${abs.toFixed(2).replace('.', ',')} ${abs.toFixed(2)}`
}

function join(...parts: (string | number | null | undefined)[]): string {
  return parts.filter(p => p != null && p !== '').map(String).join(' ')
}

// ── StageFeoDrillDialog.vue ──────────────────────────────────────────────
export function textOfStageCurrentRow(r: any): string {
  return join(r.name, amountText(r.amount))
}
export function textOfStageLeafPurchase(p: any): string {
  return join(
    p.purchase_number, p.id, p.subject, p.item_name, p.contractor_name, p.contract_number,
    amountText(typeof p.amount === 'number' ? p.amount : undefined),
  )
}
export function textOfStageTypeDrillRow(r: any): string {
  return join(
    r.purchase_number, r.subject, r.subsidy_name, r.feo_category_name, r.item_name, r.item_type,
    amountText(r.stage_amount), r.items_text,
  )
}

// ── RedistributableDrillDialog.vue ───────────────────────────────────────
export function textOfRedistributableRow(r: any): string {
  return join(
    r.name, r.category_path, r.subsidy_name,
    amountText(r.contribution), amountText(r.committed), amountText(r.raw),
  )
}

// ── ContractsDrillDialog.vue ─────────────────────────────────────────────
export function textOfContractRow(r: any): string {
  return join(
    r.number, r.subject, r.contractor_name, r.contract_type_label, r.subsidy_name,
    amountText(r.contract_amount), amountText(r.ordered_amount), amountText(r.remaining),
  )
}

// ── PaidOverDeliveredDrillDialog.vue ──────────────────────────────────────
export function textOfPaidOverDeliveredRow(r: any): string {
  return join(
    r.registry_number, r.purchase_number, r.subject, r.status_label, r.reason,
    amountText(r.delivered), amountText(r.paid), amountText(r.excess),
  )
}

// ── OrderSubstitutionDialog.vue ───────────────────────────────────────────
export function textOfOrderSubstitutionRow(r: any): string {
  return join(
    r.category_path, r.name,
    amountText(r.plan_from_file), amountText(r.contract_amount), amountText(r.diff),
    ...(r.purchases || []).map((p: any) => join(p.registry_number, p.purchase_number)),
  )
}

// ── FeoCardDrillDialog.vue ────────────────────────────────────────────────
export function textOfFeoPlannedRow(r: any): string {
  return join(r.name, r.category_path, r.kind_label, r.item_type, amountText(r.amount), r.quantity)
}
function textOfFeoItem(it: any): string {
  return join(it.name, it.category_path, it.subject, it.purchase_number, it.item_type, amountText(it.amount), amountText(it.over_amount))
}
export function textOfFeoCategoryOrDirectionRow(r: any): string {
  return join(
    r.category_path, r.kind_label,
    amountText(r.amount), amountText(r.budget_amount), amountText(r.planned_amount),
    ...((r.items || []) as any[]).map(textOfFeoItem),
  )
}

// ── MetricDrillDialog.vue (план abstract-noodling-pelican.md, п.8) ─────────
export function textOfMetricDrillRow(r: any): string {
  return join(
    r.purchase_number, r.subject, r.supplier, r.status, r.subsidy_name, r.category_path, r.name,
    r.contract_number, r.contractor, r.parent_subject,
    amountText(r.amount), amountText(r.contribution), amountText(r.committed),
    r.items_text,
  )
}

// ── MonthlyFutureTreeDialog.vue (план abstract-noodling-pelican.md, п.8) ───
// Узел-договор (корень дерева) и узел-месяц (лист) — оба текста собираются в
// одну функцию matchesNode (дерево фильтруется filterTree.ts с одной textOf
// на тип узла; contract-узел и month-узел различаются по наличию поля month).
export function textOfMonthlyFutureNode(n: any): string {
  if (n.month) {
    return join(n.month, n.order_number, amountText(n.amount))
  }
  return join(n.contract_number, n.contractor, n.parent_subject, amountText(n.amount))
}
