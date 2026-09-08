<template>
  <v-dialog v-model="show" max-width="460" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-help-circle" color="primary" class="mr-2" />
        Как пользоваться
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-list density="compact">
          <v-list-item prepend-icon="mdi-plus-circle-outline">
            <v-list-item-title class="text-body-2">Нажми <strong>+</strong> в заголовке отдела — добавить сотрудника в отдел</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-drag">
            <v-list-item-title class="text-body-2">Перетащи сотрудника <strong>внутри</strong> отдела — изменить порядок</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-drag">
            <v-list-item-title class="text-body-2">Перетащи сотрудника <strong>за пределы</strong> отдела — он выйдет из отдела</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-drag">
            <v-list-item-title class="text-body-2">Перетащи свободного сотрудника <strong>на отдел</strong> — он вступит в отдел</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-arrow-right-circle">
            <v-list-item-title class="text-body-2">Тяни от <strong>→</strong> (зелёная точка) сотрудника к другому — создаётся связь подчинённости</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-domain">
            <v-list-item-title class="text-body-2">Тяни от сотрудника к <strong>организации</strong> — он станет руководителем всей организации (фиолетовая стрелка)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-arrow-right-circle">
            <v-list-item-title class="text-body-2">Тяни от точки-выхода <strong>отдела</strong> к другому отделу — тот станет подчинённым (синяя стрелка)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-arrow-right-circle">
            <v-list-item-title class="text-body-2">Тяни от точки-выхода <strong>организации</strong> к другой организации — та станет подчинённой (фиолетовая стрелка)</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-crown">
            <v-list-item-title class="text-body-2">Корона — начальник отдела. При добавлении в отдел с начальником связь создаётся автоматически</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-close-circle-outline">
            <v-list-item-title class="text-body-2">Нажми <strong>×</strong> на стрелке — удалить связь</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-auto-fix">
            <v-list-item-title class="text-body-2">"Авторасстановка" — автоматически расставить по рангу (начальник → зам → специалист)</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn color="primary" variant="flat" @click="show = false">Понятно</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
</script>
