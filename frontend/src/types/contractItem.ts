// Phase 27.1 — contract_items TypeScript types
// Mirrors backend ContractItemOut Pydantic schema

export interface ContractItem {
  id: number
  purchase_id: number
  source_item_id: number | null
  contract_id: number | null
  product_id: number | null
  name: string
  quantity: number | null
  unit: string | null
  unit_price: number | null
  total: number | null
  vat_rate?: string | null       // Fix 27.1.3: НДС ставка per-item
  // 2026-10-02 (НДС «в цене»/«сверху»): null = «как у закупки» (contract_vat_on_top
  // шапки), иначе построчный флаг в режиме per_item — см. useVatCalc.ts::effectiveVatOnTop.
  vat_on_top?: boolean | null
  match_confirmed: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface ContractItemDraft {
  source_item_id?: number | null
  contract_id?: number | null
  product_id?: number | null
  name: string
  quantity?: number | null
  unit?: string | null
  unit_price?: number | null
  total?: number | null
  // Владелец (02.10.2026): CreateOrderView::save() раньше НЕ слал vat_rate/
  // vat_on_top в drafts контракт-позиций вовсе — ставка/флаг НДС строки
  // «Договор» терялись при каждом PUT (replaceAllContractItems пересоздаёт
  // строки). Добавлены сюда и в маппинг drafts, иначе lineTotalWithVat на
  // бэке не от чего считать «сверху».
  vat_rate?: string | null
  vat_on_top?: boolean | null
  match_confirmed?: boolean
}
