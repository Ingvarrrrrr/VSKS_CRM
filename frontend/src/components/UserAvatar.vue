<template>
  <v-avatar :size="size" :color="!photoUrl ? iconCfg.color : undefined" style="flex-shrink:0">
    <img v-if="photoUrl" :src="photoUrl" alt="фото" class="avatar-photo" />
    <v-icon v-else :icon="iconCfg.icon" :size="iconSize" color="white" />
  </v-avatar>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const AVATARS = [
  { id: 'man',     icon: 'mdi-face-man',              color: '#4CAF50' },
  { id: 'woman',   icon: 'mdi-face-woman',            color: '#E91E63' },
  { id: 'cowboy',  icon: 'mdi-account-cowboy-hat',    color: '#FF9800' },
  { id: 'ninja',   icon: 'mdi-ninja',                 color: '#607D8B' },
  { id: 'robot',   icon: 'mdi-robot',                 color: '#2196F3' },
  { id: 'cool',    icon: 'mdi-emoticon-cool-outline',  color: '#9C27B0' },
  { id: 'alien',   icon: 'mdi-alien',                 color: '#00BCD4' },
  { id: 'pirate',  icon: 'mdi-pirate',                color: '#795548' },
]

const props = withDefaults(defineProps<{
  photoUrl?: string | null
  avatar?: string | null
  size?: number | string
}>(), { size: 32 })

const iconCfg = computed(() =>
  AVATARS.find(a => a.id === props.avatar) || { icon: 'mdi-account', color: '#9E9E9E' }
)
const iconSize = computed(() => {
  const s = typeof props.size === 'number' ? props.size : parseInt(String(props.size))
  return Math.round(s * 0.6)
})
</script>

<style scoped>
.avatar-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}
</style>
