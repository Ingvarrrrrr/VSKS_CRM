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
