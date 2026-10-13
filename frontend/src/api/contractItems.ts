// Phase 27.1 — contract_items API client
// Uses the same apiFetch pattern as the rest of the frontend (frontend/src/api.ts)
import { apiFetch } from '@/api'
import type { ContractItem, ContractItemDraft } from '@/types/contractItem'

export async function listContractItems(purchaseId: number): Promise<ContractItem[]> {
  return apiFetch<ContractItem[]>(`/purchases/${purchaseId}/contract-items`)
}

export async function copyFromPurchase(purchaseId: number): Promise<ContractItem[]> {
  return apiFetch<ContractItem[]>(`/purchases/${purchaseId}/contract-items/copy-from-purchase`, {
    method: 'POST',
  })
}

// Волна 4 п.22 «Подставить названия из ТЗ» — меняет ТОЛЬКО name у уже
// существующих договорных позиций, сопоставленных со своей позицией ТЗ через
// source_item_id; количество/цена/сумма/товар не трогает (в отличие от
// copyFromPurchase выше, которая полностью перезаписывает состав). Ответ —
// не голый список (в отличие от copyFromPurchase): бэк обязан явно сказать,
// сколько позиций не сопоставилось и разошёлся ли состав ТЗ/договора (см.
// backend/app/routers/contract_items.py::copy_names_from_purchase_items) —
// молча портить/пропускать нельзя.
export interface CopyNamesFromPurchaseResult {
  items: ContractItem[]
  updated_count: number
  unmatched_count: number
  unmatched: { id: number; name: string }[]
  purchase_items_total: number
  contract_items_total: number
  composition_mismatch: boolean
}

export async function copyNamesFromPurchase(purchaseId: number): Promise<CopyNamesFromPurchaseResult> {
  return apiFetch<CopyNamesFromPurchaseResult>(
    `/purchases/${purchaseId}/contract-items/copy-names-from-purchase`,
    { method: 'POST' },
  )
}

// Пункт 22 чек-листа (владелец, 2026-10-13) «Перенести все позиции из
// договора в поставку» — та же пара, что copyFromPurchase выше, один шаг
// дальше (ТЗ → Договор → Поставка). Перезаписывает accepted_* ВСЕХ позиций
// (см. backend/app/routers/contract_items.py::copy_contract_items_to_delivery).
export interface CopyToDeliveryResult {
  updated_count: number
  items: { id: number; accepted_name: string | null; accepted_quantity: number | null; accepted_unit: string | null }[]
}

export async function copyContractToDelivery(purchaseId: number): Promise<CopyToDeliveryResult> {
  return apiFetch<CopyToDeliveryResult>(
    `/purchases/${purchaseId}/contract-items/copy-to-delivery`,
    { method: 'POST' },
  )
}

export async function replaceAllContractItems(
  purchaseId: number,
  items: ContractItemDraft[],
): Promise<ContractItem[]> {
  return apiFetch<ContractItem[]>(`/purchases/${purchaseId}/contract-items`, {
    method: 'PUT',
    body: items as any,
  })
}

export async function createContractItem(
  purchaseId: number,
  item: ContractItemDraft,
): Promise<ContractItem> {
  return apiFetch<ContractItem>(`/purchases/${purchaseId}/contract-items`, {
    method: 'POST',
    body: item as any,
  })
}

export async function patchContractItem(
  purchaseId: number,
  itemId: number,
  patch: Partial<ContractItemDraft>,
): Promise<ContractItem> {
  return apiFetch<ContractItem>(`/purchases/${purchaseId}/contract-items/${itemId}`, {
    method: 'PATCH',
    body: patch as any,
  })
}

export async function deleteContractItem(purchaseId: number, itemId: number): Promise<void> {
  await apiFetch<void>(`/purchases/${purchaseId}/contract-items/${itemId}`, {
    method: 'DELETE',
  })
}
