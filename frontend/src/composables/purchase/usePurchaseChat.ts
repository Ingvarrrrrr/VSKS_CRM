// Обсуждение закупки — учёт вводимого комментария и упоминаний (@mention).
// Историческая реализация до перехода на общий ChatEmbed.vue («Обсуждение» в
// карточке закупки использует ChatEmbed) — сам список/textarea этой реализации
// в шаблоне сейчас не подключены, но loadPurchaseComments()/pCommentText всё ещё
// используются: loadPurchase() дозагружает purchaseComments, а рассылка
// (usePurchaseBroadcast) предзаполняется и очищает то же поле ввода. Вынесено
// без изменения поведения — те же apiFetch-пути.
import { ref, computed, nextTick, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

export function usePurchaseChat(
  purchaseId: ComputedRef<number | null>,
  allUsers: Ref<{ value: number; text: string }[]>,
  loadAllUsers: () => Promise<void>,
) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const purchaseChatContainer = ref<HTMLElement | null>(null)
  const purchaseCommentInput = ref<any>(null)
  const purchaseComments = ref<any[]>([])
  const pCommentText = ref('')
  const pCommentSaving = ref(false)
  const pEnterToSend = ref(localStorage.getItem('pchat_enter_to_send') !== 'false')
  const pMentionOpen = ref(false)
  const pMentionQuery = ref('')

  const pFilteredMentionUsers = computed(() => {
    const q = pMentionQuery.value.toLowerCase()
    if (!q) return allUsers.value.slice(0, 8)
    return allUsers.value.filter(u => u.text.toLowerCase().includes(q)).slice(0, 6)
  })

  async function loadPurchaseComments() {
    if (!purchaseId.value) return
    try {
      purchaseComments.value = await apiFetch<any[]>(`/purchases/${purchaseId.value}/comments`)
      nextTick(() => {
        if (purchaseChatContainer.value) purchaseChatContainer.value.scrollTop = purchaseChatContainer.value.scrollHeight
      })
    } catch { purchaseComments.value = [] }
  }

  async function addPurchaseComment() {
    if (!purchaseId.value || !pCommentText.value.trim()) return
    pCommentSaving.value = true
    pMentionOpen.value = false
    try {
      await apiFetch(`/purchases/${purchaseId.value}/comments`, {
        method: 'POST', body: JSON.stringify({ text: pCommentText.value.trim() }),
      })
      pCommentText.value = ''
      await loadPurchaseComments()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка', 'error')
    } finally { pCommentSaving.value = false }
  }

  async function deletePurchaseComment(commentId: number) {
    if (!purchaseId.value) return
    try {
      await apiFetch(`/purchases/${purchaseId.value}/comments/${commentId}`, { method: 'DELETE' })
      await loadPurchaseComments()
    } catch {}
  }

  function onPurchaseCommentInput() {
    const text = pCommentText.value
    const atIdx = text.lastIndexOf('@')
    if (atIdx >= 0) {
      const afterAt = text.slice(atIdx + 1)
      if (!afterAt.includes('\n') && afterAt.length <= 30) {
        pMentionQuery.value = afterAt
        pMentionOpen.value = true
        return
      }
    }
    pMentionOpen.value = false
  }

  function pInsertMention(user: { text: string; value: number }) {
    const text = pCommentText.value
    const atIdx = text.lastIndexOf('@')
    if (atIdx >= 0) pCommentText.value = text.slice(0, atIdx) + `@${user.text} `
    pMentionOpen.value = false
    nextTick(() => {
      const el = (purchaseCommentInput.value as any)?.$el?.querySelector('textarea')
      if (el) el.focus()
    })
  }

  function onPurchaseCommentKeydown(e: KeyboardEvent) {
    if (pMentionOpen.value) {
      if (e.key === 'Escape') { pMentionOpen.value = false; e.preventDefault(); return }
      if ((e.key === 'Tab' || e.key === 'Enter') && pFilteredMentionUsers.value.length > 0) {
        e.preventDefault(); pInsertMention(pFilteredMentionUsers.value[0]!); return
      }
    }
    if (e.key === 'Enter') {
      const ctrl = e.ctrlKey || e.metaKey
      if (pEnterToSend.value) {
        if (ctrl) {
          e.preventDefault()
          const ta = (purchaseCommentInput.value as any)?.$el?.querySelector('textarea')
          if (ta) { const s = ta.selectionStart; pCommentText.value = pCommentText.value.slice(0, s) + '\n' + pCommentText.value.slice(ta.selectionEnd); nextTick(() => { ta.selectionStart = ta.selectionEnd = s + 1 }) }
          return
        }
        if (!e.shiftKey) { e.preventDefault(); addPurchaseComment() }
      } else {
        if (ctrl) { e.preventDefault(); addPurchaseComment() }
      }
    }
  }

  function pOpenMentionPicker() {
    pMentionQuery.value = ''
    const text = pCommentText.value
    if (!text.endsWith('@')) pCommentText.value = text + (text && !text.endsWith(' ') ? ' @' : '@')
    pMentionOpen.value = true
    loadAllUsers()
  }

  function renderPurchaseMentions(text: string): string {
    if (!text) return ''
    const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return escaped.replace(/@([A-Za-zА-Яа-яёЁ\s]+?)(\s|$)/g, '<span style="color:#1976d2;font-weight:500">@$1</span>$2')
  }

  return {
    purchaseChatContainer, purchaseCommentInput, purchaseComments, pCommentText, pCommentSaving,
    pEnterToSend, pMentionOpen, pMentionQuery, pFilteredMentionUsers,
    loadPurchaseComments, addPurchaseComment, deletePurchaseComment,
    onPurchaseCommentInput, onPurchaseCommentKeydown, pOpenMentionPicker, pInsertMention,
    renderPurchaseMentions,
  }
}
