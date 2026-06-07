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
}

export interface PriceLink {
  url: string
  price: number | null
}

// Mutable form object for the full product create/edit dialog. The parent owns
// the reactive instance and passes it down; the child v-models its fields.
export interface FullProductForm {
  name: string
  category: string
  product_type: string
  item_kind: string
  price: number | null
  description: string
  photo_url: string
  photo_link: string
  is_active: boolean
  priceLinks: PriceLink[]
}
