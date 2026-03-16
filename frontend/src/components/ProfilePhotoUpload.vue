<template>
  <v-dialog v-model="dialog" max-width="400" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between pt-4 px-5">
        <span class="text-subtitle-1 font-weight-bold">
          <v-icon icon="mdi-camera-account" size="18" class="mr-2" />Моя фотография
        </span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>

      <v-card-text class="px-5 pb-2">
        <!-- Photo preview -->
        <div class="d-flex justify-center mb-4">
          <v-avatar size="140" :color="!displayPhoto ? 'grey-lighten-2' : undefined" class="photo-circle">
            <img v-if="displayPhoto" :src="displayPhoto" alt="фото" class="photo-img" />
            <v-icon v-else icon="mdi-account" size="72" color="grey-lighten-1" />
          </v-avatar>
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
          JPG, PNG, WebP · автоматически обрезается до квадрата 300×300px
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

const dialog = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const savedPhoto = ref<string | null>(null)
const previewUrl = ref<string | null>(null)
const saving = ref(false)
const deleting = ref(false)

const displayPhoto = computed(() => previewUrl.value || savedPhoto.value)

const emit = defineEmits<{ 'saved': [photoUrl: string | null] }>()

async function loadPhoto() {
  try {
    const data = await apiFetch<{ photo_url: string | null }>('/users/me/photo')
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
    resizeImage(dataUrl, 300, 300).then(resized => {
      previewUrl.value = resized
    })
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

async function savePhoto() {
  if (!previewUrl.value) return
  saving.value = true
  try {
    await apiFetch('/users/me/photo', { method: 'PUT', body: { photo_url: previewUrl.value } })
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
    await apiFetch('/users/me/photo', { method: 'DELETE' })
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
</style>
