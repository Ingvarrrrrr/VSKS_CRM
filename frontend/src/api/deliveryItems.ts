import { apiFetch } from '@/api'

export interface DeliveryItem {
  id: number
  purchase_id: number
  contract_item_id?: number | null
  purchase_item_id?: number | null
  product_id?: number | null
  name: string
  unit?: string | null
  qty: number
  unit_price: number
  total: number
  delivery_date?: string | null
  doc_number?: string | null
  status: 'pending' | 'partial' | 'delivered'
  notes?: string | null
  created_at?: string
}

export interface DeliverySummary {
  contract_total: number
  delivered_total: number
  delivered_qty_pct: number
  delivered_amount_pct: number
  status_counts: Record<string, number>
}

export interface DeliveryItemsResponse {
  items: DeliveryItem[]
  summary: DeliverySummary
}

export interface WaybillParsedItem {
  raw_name: string
  qty: number
  unit_price: number
  total: number
  unit?: string | null
  doc_number?: string | null
  delivery_date?: string | null
  suggested_contract_item_id?: number | null
  suggested_purchase_item_id?: number | null
  confidence: number
}

export interface WaybillParseResponse {
  doc_number?: string | null
  delivery_date?: string | null
  items: WaybillParsedItem[]
  warnings: string[]
}

export interface WaybillApplyItem {
  name: string
  qty: number
  unit_price: number
  unit?: string | null
  delivery_date?: string | null
  doc_number?: string | null
  contract_item_id?: number | null
  purchase_item_id?: number | null
  product_id?: number | null
  status?: string
  notes?: string | null
}

export async function listDeliveryItems(purchaseId: number): Promise<DeliveryItemsResponse> {
  return apiFetch<DeliveryItemsResponse>(`/purchases/${purchaseId}/delivery-items`)
}

export async function createDeliveryItem(purchaseId: number, data: Partial<DeliveryItem>): Promise<DeliveryItem> {
  return apiFetch<DeliveryItem>(`/purchases/${purchaseId}/delivery-items`, {
    method: 'POST',
    body: data as any,
  })
}

export async function patchDeliveryItem(
  purchaseId: number,
  itemId: number,
  patch: Partial<DeliveryItem>,
): Promise<DeliveryItem> {
  return apiFetch<DeliveryItem>(`/purchases/${purchaseId}/delivery-items/${itemId}`, {
    method: 'PATCH',
    body: patch as any,
  })
}

export async function deleteDeliveryItem(purchaseId: number, itemId: number): Promise<void> {
  await apiFetch<void>(`/purchases/${purchaseId}/delivery-items/${itemId}`, {
    method: 'DELETE',
  })
}

export async function createDeliveryItemsFromContract(purchaseId: number): Promise<DeliveryItem[]> {
  return apiFetch<DeliveryItem[]>(`/purchases/${purchaseId}/delivery-items/from-contract`, {
    method: 'POST',
  })
}

export async function parseWaybill(purchaseId: number, file: File): Promise<WaybillParseResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<WaybillParseResponse>(`/purchases/${purchaseId}/delivery-items/parse-waybill`, {
    method: 'POST',
    body: formData,
  })
}

export async function applyWaybill(
  purchaseId: number,
  data: { items: WaybillApplyItem[]; doc_number?: string; delivery_date?: string },
): Promise<DeliveryItem[]> {
  return apiFetch<DeliveryItem[]>(`/purchases/${purchaseId}/delivery-items/apply-waybill`, {
    method: 'POST',
    body: data as any,
  })
}
