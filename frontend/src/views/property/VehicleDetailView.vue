<template>
  <v-container>
    <h2>Карточка ТС #{{ route.params.id }}</h2>
    <p class="text-medium-emphasis">Stub — реализация в плане 29-17</p>
  </v-container>
</template>
<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>
