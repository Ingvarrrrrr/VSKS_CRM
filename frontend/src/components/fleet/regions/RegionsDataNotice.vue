<template>
  <div v-if="unspecifiedCount > 0" class="rv-notice">
    У <b>{{ unspecifiedCount }}</b> ед. техники не заполнено «Место нахождения» —
    они показаны отдельной группой «Место не указано» и не попадают на карту.
  </div>
</template>

<script setup lang="ts">
defineProps<{
  unspecifiedCount: number
}>()
</script>

<style scoped></style>
