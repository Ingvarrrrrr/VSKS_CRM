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
  match_confirmed?: boolean
}
