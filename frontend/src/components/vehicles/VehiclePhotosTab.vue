<template>
  <div class="vehicle-photos-tab pa-4">
    <!-- Upload zone -->
    <div class="mb-4">
      <FileDropZone
        multiple
        accept="image/jpeg,image/jpg,image/png,image/webp,image/heic"
        hint="JPG, PNG, WEBP, HEIC — до 25 МБ каждый"
        @files="onFilesSelected"
      >
        <template #default="{ dragging }">
          <div class="text-center pa-4">
            <v-icon size="32" :color="dragging ? 'primary' : 'grey-lighten-1'" class="mb-1">
              mdi-camera-plus-outline
            </v-icon>
            <div class="text-body-2 mb-1">+ Добавить фото</div>
            <div class="text-caption text-medium-emphasis">Перетащите или нажмите · JPG, PNG, WEBP · до 25 МБ</div>
          </div>
        </template>
      </FileDropZone>

      <!-- Upload progress -->
      <div v-if="uploading" class="mt-2">
        <v-progress-linear indeterminate color="primary" height="3" rounded />
        <div class="text-caption text-medium-emphasis mt-1">
          Загрузка {{ uploadProgress.done }} / {{ uploadProgress.total }}…
        </div>
      </div>

      <!-- Upload errors -->
      <v-alert
        v-for="err in uploadErrors"
        :key="err"
        type="error"
        variant="tonal"
        density="compact"
        closable
        class="mt-2"
        @click:close="uploadErrors = uploadErrors.filter(e => e !== err)"
      >
        {{ err }}
      </v-alert>
    </div>

    <!-- Loading skeleton -->
    <v-row v-if="loading" dense>
      <v-col v-for="n in 6" :key="n" cols="4" sm="3" md="2">
        <v-skeleton-loader type="image" height="120" />
      </v-col>
    </v-row>

    <!-- Empty state -->
    <div v-else-if="photos.length === 0" class="text-center py-10 text-medium-emphasis">
      <v-icon size="48" class="mb-2">mdi-image-off-outline</v-icon>
      <div class="text-body-1">Фотографии не загружены</div>
    </div>

    <!-- Photo grid -->
    <v-row v-else dense>
      <v-col
        v-for="photo in photos"
        :key="photo.id"
        cols="4"
        sm="3"
        md="2"
      >
        <div class="photo-card" @click="openLightbox(photo)">
          <!-- Thumbnail -->
          <v-img
            v-if="blobUrls[photo.id]"
            :src="blobUrls[photo.id]"
            :aspect-ratio="1"
            cover
            class="photo-thumb rounded"
          >
            <template #placeholder>
              <div class="d-flex align-center justify-center fill-height">
                <v-progress-circular indeterminate size="20" />
              </div>
            </template>
          </v-img>
          <div v-else class="photo-thumb-placeholder rounded d-flex align-center justify-center">
            <v-progress-circular indeterminate size="20" color="primary" />
          </div>

          <!-- Caption + delete -->
          <div class="photo-caption d-flex align-center pa-1">
            <span class="text-caption text-truncate flex-grow-1" :title="photo.name">{{ photo.name }}</span>
            <v-btn
              icon
              size="x-small"
              variant="text"
              color="error"
              class="flex-shrink-0"
              @click.stop="confirmDelete(photo)"
            >
              <v-icon size="14">mdi-delete-outline</v-icon>
            </v-btn>
          </div>
        </div>
      </v-col>
    </v-row>

    <!-- Lightbox dialog -->
    <v-dialog v-model="lightboxOpen" max-width="960" @keydown.esc="lightboxOpen = false">
      <v-card v-if="lightboxPhoto">
        <v-toolbar density="compact" color="surface">
          <v-toolbar-title class="text-body-2">{{ lightboxPhoto.name }}</v-toolbar-title>
          <template #append>
            <v-btn icon @click="lightboxOpen = false">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </template>
        </v-toolbar>

        <!-- Navigation -->
        <div class="lightbox-body d-flex align-center">
          <v-btn
            icon
            variant="text"
            :disabled="lightboxIndex <= 0"
            class="lightbox-nav"
            @click="lightboxIndex--"
          >
            <v-icon>mdi-chevron-left</v-icon>
          </v-btn>

          <v-img
            v-if="blobUrls[lightboxPhoto.id]"
            :src="blobUrls[lightboxPhoto.id]"
            max-height="70vh"
            contain
            class="flex-grow-1"
          />
          <div v-else class="flex-grow-1 d-flex align-center justify-center" style="min-height: 200px;">
            <v-progress-circular indeterminate color="primary" />
          </div>

          <v-btn
            icon
            variant="text"
            :disabled="lightboxIndex >= photos.length - 1"
            class="lightbox-nav"
            @click="lightboxIndex++"
          >
            <v-icon>mdi-chevron-right</v-icon>
          </v-btn>
        </div>

        <v-card-text class="text-center text-caption text-medium-emphasis pt-0 pb-2">
          {{ lightboxIndex + 1 }} / {{ photos.length }}
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Delete confirmation -->
    <v-dialog v-model="deleteDialog" max-width="380">
      <v-card>
        <v-card-title class="text-h6">Удалить фото?</v-card-title>
        <v-card-text v-if="deleteTarget">
          «{{ deleteTarget.name }}» будет удалено без возможности восстановления.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import FileDropZone from '@/components/FileDropZone.vue'

interface PhotoMeta {
  id: number
  vehicle_id: number
  kind: string
  name: string
  mime: string | null
  size: number | null
}

const props = defineProps<{
  vehicleId: number
}>()

// ── State ──────────────────────────────────────────────────────────────────────
const photos = ref<PhotoMeta[]>([])
const loading = ref(false)
const blobUrls = ref<Record<number, string>>({})

const uploading = ref(false)
const uploadProgress = ref({ done: 0, total: 0 })
const uploadErrors = ref<string[]>([])

const lightboxOpen = ref(false)
const lightboxIndex = ref(0)
const lightboxPhoto = computed<PhotoMeta | null>(
  () => photos.value[lightboxIndex.value] ?? null
)

const deleteDialog = ref(false)
const deleteTarget = ref<PhotoMeta | null>(null)
const deleting = ref(false)

// ── API helpers ────────────────────────────────────────────────────────────────
async function fetchPhotos() {
  loading.value = true
  try {
    const res = await fetch(
      `/api/vehicle-attachments?vehicle_id=${props.vehicleId}`,
      { credentials: 'include' }
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const all: PhotoMeta[] = await res.json()
    photos.value = all.filter(a => a.kind === 'photo')
    // Load blob URLs for new photos
    for (const p of photos.value) {
      if (!blobUrls.value[p.id]) {
        loadBlobUrl(p)
      }
    }
  } catch (e) {
    console.error('fetchPhotos error', e)
  } finally {
    loading.value = false
  }
}

async function loadBlobUrl(photo: PhotoMeta) {
  try {
    const res = await fetch(`/api/vehicle-attachments/${photo.id}/download`, {
      credentials: 'include',
    })
    if (!res.ok) return
    const blob = await res.blob()
    blobUrls.value = { ...blobUrls.value, [photo.id]: URL.createObjectURL(blob) }
  } catch {
    // silently skip — thumbnail stays empty
  }
}

// ── Upload ─────────────────────────────────────────────────────────────────────
async function onFilesSelected(files: File[]) {
  if (!files.length) return
  uploadErrors.value = []
  uploading.value = true
  uploadProgress.value = { done: 0, total: files.length }

  for (const file of files) {
    try {
      const fd = new FormData()
      fd.append('vehicle_id', String(props.vehicleId))
      fd.append('kind', 'photo')
      fd.append('name', file.name)
      fd.append('file', file)

      const res = await fetch('/api/vehicle-attachments/upload', {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const msg = body?.detail?.message ?? body?.detail ?? `Ошибка HTTP ${res.status}`
        uploadErrors.value = [...uploadErrors.value, `${file.name}: ${msg}`]
      } else {
        const created: PhotoMeta = await res.json()
        photos.value = [...photos.value, created]
        loadBlobUrl(created)
      }
    } catch {
      uploadErrors.value = [...uploadErrors.value, `${file.name}: сетевая ошибка`]
    }
    uploadProgress.value.done++
  }

  uploading.value = false
}

// ── Lightbox ───────────────────────────────────────────────────────────────────
function openLightbox(photo: PhotoMeta) {
  const idx = photos.value.findIndex(p => p.id === photo.id)
  lightboxIndex.value = idx >= 0 ? idx : 0
  lightboxOpen.value = true
}

// ── Delete ─────────────────────────────────────────────────────────────────────
function confirmDelete(photo: PhotoMeta) {
  deleteTarget.value = photo
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const res = await fetch(`/api/vehicle-attachments/${deleteTarget.value.id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const msg = body?.detail?.message ?? `HTTP ${res.status}`
      uploadErrors.value = [...uploadErrors.value, `Удаление: ${msg}`]
      return
    }
    // Revoke blob URL
    const url = blobUrls.value[deleteTarget.value.id]
    if (url) URL.revokeObjectURL(url)
    const newUrls = { ...blobUrls.value }
    delete newUrls[deleteTarget.value.id]
    blobUrls.value = newUrls

    photos.value = photos.value.filter(p => p.id !== deleteTarget.value!.id)

    // Close lightbox if deleted photo was open
    if (lightboxOpen.value) {
      if (photos.value.length === 0) {
        lightboxOpen.value = false
      } else {
        lightboxIndex.value = Math.min(lightboxIndex.value, photos.value.length - 1)
      }
    }
    deleteDialog.value = false
    deleteTarget.value = null
  } finally {
    deleting.value = false
  }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────────
watch(() => props.vehicleId, fetchPhotos, { immediate: true })

onBeforeUnmount(() => {
  for (const url of Object.values(blobUrls.value)) {
    URL.revokeObjectURL(url)
  }
})
</script>

<style scoped>
.photo-card {
  cursor: pointer;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.2);
  transition: box-shadow 0.15s;
}
.photo-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
}
.photo-thumb {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
}
.photo-thumb-placeholder {
  width: 100%;
  aspect-ratio: 1;
  background: rgba(var(--v-theme-surface-variant), 0.5);
  min-height: 80px;
}
.photo-caption {
  min-height: 28px;
  max-width: 100%;
  overflow: hidden;
}
.lightbox-body {
  min-height: 280px;
}
.lightbox-nav {
  flex-shrink: 0;
}
</style>
