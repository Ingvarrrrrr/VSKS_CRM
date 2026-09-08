<template>
  <Teleport to="body">
    <v-dialog v-model="show" max-width="520" :z-index="9999" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 text-body-1">
          <v-icon icon="mdi-account-details" class="mr-2" />{{ userName }}
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <div v-if="!orgs.length" class="text-medium-emphasis">Нет данных об организациях</div>
          <div v-for="o in orgs" :key="o.org_id" class="mb-3 pa-3 rounded" style="background:rgba(0,0,0,0.03)">
            <div class="d-flex align-center gap-2 mb-2">
              <v-chip v-if="o.org_name" size="small" :color="o.is_primary ? 'primary' : 'grey'" variant="tonal">{{ o.org_name }}</v-chip>
              <v-chip v-if="o.is_primary" size="x-small" color="blue" variant="flat">основная</v-chip>
            </div>
            <v-row dense>
              <v-col cols="12" md="4">
                <v-text-field v-model="o.position" label="Должность" variant="outlined" density="compact" hide-details @blur="emit('save-org', o.org_id)" />
              </v-col>
              <v-col cols="6" md="4">
                <v-text-field v-model.number="o.salary_amount" label="Оклад, ₽" variant="outlined" density="compact" type="number" hide-details @blur="emit('save-org', o.org_id)" />
              </v-col>
              <v-col cols="6" md="4">
                <v-text-field v-model.number="o.employment_percent" label="% ставки" variant="outlined" density="compact" type="number" hide-details @blur="emit('save-org', o.org_id)" />
              </v-col>
            </v-row>
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn variant="text" color="primary" prepend-icon="mdi-pencil" @click="show = false; emit('edit')">Редактировать</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="show = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  userName: string
  orgs: any[]
}>()
const emit = defineEmits<{ edit: []; 'save-org': [orgId: number] }>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
</script>
