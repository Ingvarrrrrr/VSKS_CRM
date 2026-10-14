// Shared types for the PurchaseItemsEditor family of presentational components.
// These mirror the local interfaces the parent (PurchaseItemsEditor.vue) owns;
// kept here so extracted children can type their props/emits without duplicating
// the definitions. The parent re-imports these so there is a single source.

export interface Contractor {
  id: number
  name: string
  inn?: string | null
  kpp?: string | null
  address?: string | null
}

export interface ProductLike {
  id: number
  name: string
  description?: string
  product_type?: string
  category?: string
  price?: number | null
  avg_price?: number | null
  photo_url?: string | null
  photo_link?: string | null
  has_photo?: boolean
  contract_price?: number | null
  description_44fz?: string
  // Ед. изм. + упаковка (владелец, 14.10) — подсказка в подборе товара
  // (ProductPickerDialog.vue), formatUnitWithPack: «упак. (10 шт.)».
  unit?: string | null
  pack_quantity?: number | string | null
  pack_unit?: string | null
}

export interface PriceLink {
  url: string
  price: number | null
}

// Grouping/filtering of positions by product category/type. The parent computes
// the ordered row list; children render it. A row is either a group header
// (header != null) or a data row pointing at the ORIGINAL index in items[] so
// all idx-based emits keep working regardless of sort/filter.
export interface ItemsDisplayRow {
  idx?: number
  header?: string
  level?: 1 | 2   // 1 = category, 2 = type inside category
  count?: number
  sum?: number
}
