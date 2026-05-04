<template>
  <v-dialog v-model="dialog" max-width="400" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between pt-4 px-5">
        <span class="text-subtitle-1 font-weight-bold">
          <v-icon icon="mdi-camera-account" size="18" class="mr-2" />{{ props.userId ? 'Фото сотрудника' : 'Моя фотография' }}
        </span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>

      <v-card-text class="px-5 pb-2">
        <!-- Photo preview -->
        <div class="d-flex justify-center mb-4">
          <template v-if="props.format === 'rectangle'">
            <div class="photo-rect">
              <img v-if="displayPhoto" :src="displayPhoto" alt="фото" />
              <v-icon v-else icon="mdi-account" size="72" color="grey-lighten-1" />
            </div>
          </template>
          <template v-else>
            <v-avatar size="140" :color="!displayPhoto ? 'grey-lighten-2' : undefined" class="photo-circle">
              <img v-if="displayPhoto" :src="displayPhoto" alt="фото" class="photo-img" />
              <v-icon v-else icon="mdi-account" size="72" color="grey-lighten-1" />
            </v-avatar>
          </template>
        </div>

        <!-- Hidden file input -->
        <input
          ref="fileInputRef"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          style="display:none"
          @change="onFileSelected"
        />

        <div class="d-flex justify-center ga-2">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-upload" @click="fileInputRef?.click()">
            {{ savedPhoto ? 'Изменить' : 'Загрузить фото' }}
          </v-btn>
          <v-btn v-if="savedPhoto" color="error" variant="text" prepend-icon="mdi-delete"
            :loading="deleting" @click="deletePhoto">
            Удалить
          </v-btn>
        </div>

        <div class="text-caption text-center text-medium-emphasis mt-3">
          JPG, PNG, WebP · {{ props.format === 'rectangle' ? 'обрезается 4:5 (240×300px)' : 'автоматически обрезается до квадрата 300×300px' }}
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="close">Закрыть</v-btn>
        <v-btn v-if="previewUrl" color="primary" variant="flat" :loading="saving" @click="savePhoto">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

const props = withDefaults(defineProps<{
  format?: 'circle' | 'rectangle'
  userId?: number
}>(), {
  format: 'circle',
  userId: undefined,
})

const dialog = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const savedPhoto = ref<string | null>(null)
const previewUrl = ref<string | null>(null)
const saving = ref(false)
const deleting = ref(false)

const displayPhoto = computed(() => previewUrl.value || savedPhoto.value)

const emit = defineEmits<{ 'saved': [photoUrl: string | null] }>()

function photoApiPath() {
  return props.userId ? `/users/${props.userId}/photo` : '/users/me/photo'
}

async function loadPhoto() {
  try {
    const data = await apiFetch<{ photo_url: string | null }>(photoApiPath())
    savedPhoto.value = data.photo_url || null
  } catch { savedPhoto.value = null }
}

function open() {
  dialog.value = true
  previewUrl.value = null
  loadPhoto()
}

function close() {
  dialog.value = false
  previewUrl.value = null
}

function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    const dataUrl = ev.target?.result as string
    if (props.format === 'rectangle') {
      resizeImageRect(dataUrl, 240, 300).then(resized => {
        previewUrl.value = resized
      })
    } else {
      resizeImage(dataUrl, 300, 300).then(resized => {
        previewUrl.value = resized
      })
    }
  }
  reader.readAsDataURL(file)
  // Reset input so same file can be selected again
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function resizeImage(dataUrl: string, maxW: number, maxH: number): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const size = Math.min(img.width, img.height)
      const canvas = document.createElement('canvas')
      canvas.width = maxW
      canvas.height = maxH
      const ctx = canvas.getContext('2d')!
      // Crop center square then draw scaled
      const sx = (img.width - size) / 2
      const sy = (img.height - size) / 2
      ctx.drawImage(img, sx, sy, size, size, 0, 0, maxW, maxH)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.src = dataUrl
  })
}

function resizeImageRect(dataUrl: string, targetW: number, targetH: number): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      // Cover crop: 4:5 ratio centered
      const ratio = targetW / targetH
      let srcW = img.width
      let srcH = img.height
      let sx = 0
      let sy = 0
      if (srcW / srcH > ratio) {
        // wider than target ratio — crop sides
        const newW = srcH * ratio
        sx = (srcW - newW) / 2
        srcW = newW
      } else {
        // taller than target ratio — crop top/bottom
        const newH = srcW / ratio
        sy = (srcH - newH) / 2
        srcH = newH
      }
      const canvas = document.createElement('canvas')
      canvas.width = targetW
      canvas.height = targetH
      const ctx = canvas.getContext('2d')!
      ctx.drawImage(img, sx, sy, srcW, srcH, 0, 0, targetW, targetH)
      resolve(canvas.toDataURL('image/jpeg', 0.85))
    }
    img.src = dataUrl
  })
}

async function savePhoto() {
  if (!previewUrl.value) return
  saving.value = true
  try {
    await apiFetch(photoApiPath(), { method: 'PUT', body: { photo_url: previewUrl.value } })
    savedPhoto.value = previewUrl.value
    previewUrl.value = null
    emit('saved', savedPhoto.value)
  } catch (e: any) {
    console.error('Photo save error:', e)
  } finally { saving.value = false }
}

async function deletePhoto() {
  deleting.value = true
  try {
    await apiFetch(photoApiPath(), { method: 'DELETE' })
    savedPhoto.value = null
    previewUrl.value = null
    emit('saved', null)
  } catch { /* ignore */ } finally { deleting.value = false }
}

defineExpose({ open })
</script>

<style scoped>
.photo-circle {
  border: 3px solid rgba(0,0,0,0.08);
}
.photo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}
.photo-rect {
  width: 200px;
  height: 250px;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.04);
  border: 2px solid rgba(0,0,0,0.08);
}
.photo-rect img { width: 100%; height: 100%; object-fit: cover; }
</style>
