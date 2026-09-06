<template>
  <!-- Purchase broadcast dialog -->
  <v-dialog v-model="open" max-width="480" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center gap-2 pt-4">
        <v-icon color="orange">mdi-bullhorn</v-icon>
        Рассылка из закупки
      </v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-3">
          Сообщение будет отправлено каждому сотруднику индивидуально в Telegram
        </div>
        <v-radio-group v-model="scope" class="mb-3">
          <v-radio value="department" label="Отдел" />
          <v-radio value="organization" label="Организация" />
          <v-radio v-if="orgs.length > 1" value="all" label="Все организации" />
        </v-radio-group>
        <v-select v-if="scope === 'department'" v-model="scopeId"
          :items="depts" item-title="name" item-value="id"
          label="Выберите отдел" variant="outlined" density="compact" class="mb-3" />
        <v-select v-if="scope === 'organization'" v-model="scopeId"
          :items="orgs" item-title="name" item-value="id"
          label="Выберите организацию" variant="outlined" density="compact" class="mb-3" />
        <v-textarea v-model="text" label="Текст сообщения" variant="outlined"
          density="compact" rows="3" autofocus />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn color="orange" variant="tonal" :loading="sending"
          :disabled="!text.trim() || (scope !== 'all' && !scopeId)"
          @click="$emit('send')">
          Отправить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const open = defineModel<boolean>({ default: false })
const scope = defineModel<string>('scope', { default: 'organization' })
const scopeId = defineModel<number | null>('scopeId', { default: null })
const text = defineModel<string>('text', { default: '' })

defineProps<{
  sending: boolean
  orgs: { id: number; name: string }[]
  depts: { id: number; name: string }[]
}>()

defineEmits<{ (e: 'send'): void }>()

const { mobile } = useDisplay()
</script>
