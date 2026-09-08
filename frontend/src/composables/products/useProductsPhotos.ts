// useProductsPhotos.ts — массовое скачивание фото по внешним ссылкам.
// Дословный перенос из ProductsView.vue.
import { reactive } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

export function useProductsPhotos(options: {
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { load, showSnack } = options

  const dlPhotoDialog = reactive({
    show: false,
    loading: false,
    result: null as { updated: number; skipped: number; errors: { id: number; name: string; error: string }[] } | null,
  })

  function openDownloadPhotosDialog() {
    dlPhotoDialog.result = null
    dlPhotoDialog.show = true
  }

  async function doDownloadAllPhotos() {
    dlPhotoDialog.loading = true
    try {
      dlPhotoDialog.result = await apiFetch<typeof dlPhotoDialog.result>('/products/download-photos', { method: 'POST' })
      if (dlPhotoDialog.result?.updated) await load()
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка скачивания фото', 'error')
    } finally {
      dlPhotoDialog.loading = false
    }
  }

  return { dlPhotoDialog, openDownloadPhotosDialog, doDownloadAllPhotos }
}
