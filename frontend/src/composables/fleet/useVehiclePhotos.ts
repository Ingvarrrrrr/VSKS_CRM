import { ref, onBeforeUnmount } from 'vue'
import { apiFetch } from '@/api'

// ─────────────────────────────────────────────────────────────────────────
// Превью фото ТС для hero-плашки и счётчик фотографий (карточка
// «Фотогалерея» на вкладке «Общее»). loadHeroPhoto скачивает бинарник через
// fetch() напрямую (не apiFetch — тот не отдаёт Blob), как было в исходном
// VehicleDetailView.vue.
// ─────────────────────────────────────────────────────────────────────────

export function useVehiclePhotos() {
  const photoCount = ref<number | null>(null)
  // Hero banner: превью самого свежего загруженного фото (kind='photo'), если оно есть.
  const heroPhotoUrl = ref<string | null>(null)

  async function loadHeroPhoto(attId: number) {
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/vehicle-attachments/${attId}/download`, {
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) return
      const blob = await res.blob()
      if (heroPhotoUrl.value) URL.revokeObjectURL(heroPhotoUrl.value)
      heroPhotoUrl.value = URL.createObjectURL(blob)
    } catch {
      // тихо — плашка откатится на силуэт/заглушку по приоритету в шаблоне
    }
  }

  async function loadPhotoCount(id: number) {
    try {
      const data = await apiFetch<Array<{ id: number; kind?: string }>>(`/vehicle-attachments/?vehicle_id=${id}`)
      const list = Array.isArray(data) ? data : []
      photoCount.value = list.length
      // Список приходит уже отсортированным backend'ом: kind asc, uploaded_at desc —
      // тот же порядок, что использует вкладка «Фото» (VehiclePhotosTab.vue) после
      // клиентской фильтрации по kind==='photo'. Первый элемент после фильтра — самое
      // свежее загруженное фото.
      const firstPhoto = list.find((a) => a.kind === 'photo') ?? null
      if (firstPhoto) {
        loadHeroPhoto(firstPhoto.id)
      } else {
        if (heroPhotoUrl.value) URL.revokeObjectURL(heroPhotoUrl.value)
        heroPhotoUrl.value = null
      }
    } catch {
      photoCount.value = null
    }
  }

  onBeforeUnmount(() => {
    if (heroPhotoUrl.value) URL.revokeObjectURL(heroPhotoUrl.value)
  })

  return { photoCount, heroPhotoUrl, loadPhotoCount, loadHeroPhoto }
}
