<template>
  <!-- ── Диалог «Редактировать часть позиции» (владелец, 13.10.2026) ──
       Маленький диалог в стиле PlannedItemEditDialog.vue — только то, что
       относится к ОДНОЙ части объединённой позиции: кол-во, цена за
       единицу, сумма. Смонтирован ОДИН раз в FeoTreeTable.vue (singleton
       состояние, как и FeoRowDrillDialog.vue), открывает FeoLevel5Panel.vue. -->
  <v-dialog v-model="p.partEditDialog.value.show" max-width="420" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-pencil" color="blue" class="mr-2" />Редактировать часть позиции
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <div class="text-caption text-medium-emphasis mb-3">{{ p.partEditDialog.value.itemName }}</div>
        <v-row dense>
          <v-col cols="5">
            <v-text-field v-model="p.partEditDialog.value.quantity" label="Кол-во" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="7">
            <v-text-field v-model="p.partEditDialog.value.unit" label="Ед. изм." variant="outlined" density="compact" />
          </v-col>
        </v-row>
        <v-text-field
          v-model.number="p.partEditDialog.value.unitPrice"
          type="number"
          label="Цена за единицу, ₽ (необязательно)"
          variant="outlined"
          density="compact"
          class="mb-1"
        />
        <!-- Сумма: если заданы и кол-во, и цена — считается сервером при
             сохранении (та же формула/формулировка, что и у плановой позиции
             целиком, editPriceCaption в useFeoPlannedItemEditDialog.ts); можно
             ввести только сумму (задача владельца). -->
        <div class="d-flex align-start" style="gap:6px">
          <v-text-field
            v-model="p.partEditDialog.value.amount"
            label="Сумма части, ₽" type="number"
            variant="outlined" density="compact"
            :readonly="amountIsComputed"
            :bg-color="amountIsComputed ? 'grey-lighten-4' : undefined"
            :error="!!p.partEditDialog.value.error"
            class="flex-grow-1"
          />
          <!-- Ошибка превышения плана позиции — стрелка к полю «Сумма», не
               только текст (задача проекта/Lessons.md: «ошибка → стрелка к
               полю», тот же переиспользуемый PointerArrow.vue, что и у
               excess-drilldown FeoTreeRow.vue, Правило №6). -->
          <PointerArrow v-if="p.partEditDialog.value.error" direction="left" current title="Сумма превышает план позиции" />
        </div>
        <div v-if="p.partEditDialog.value.error" class="text-caption mt-1" style="color:#dc2626;line-height:1.3">
          <v-icon icon="mdi-alert-circle-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ p.partEditDialog.value.error }}
        </div>
        <div v-else class="text-caption text-medium-emphasis mt-1" style="line-height:1.35">
          <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />
          Кол-во и цена заданы оба — сумма посчитается сама. Σ сумм всех частей не может быть больше плана позиции.
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="p.partEditDialog.value.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="p.partEditDialog.value.saving" @click="p.saveEditPlannedItemPart">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplay } from 'vuetify'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useFeoPlannedItemPartEditDialog } from '@/composables/subsidies/useFeoPlannedItemPartEditDialog'
import PointerArrow from '@/components/common/PointerArrow.vue'

const { mobile } = useDisplay()
const p = useFeoPlannedItemPartEditDialog(useSubsidyDetailCtx())

// Та же формула «кол-во × цена → сумма недоступна для ручного ввода», что и
// у плановой позиции целиком (editAmountIsComputed, useFeoPlannedItemEditDialog.ts) —
// формулировка подсказки ниже специально близка к editPriceCaption там же.
const amountIsComputed = computed(() => {
  const d = p.partEditDialog.value
  return d.quantity !== '' && d.quantity != null && d.unitPrice !== '' && d.unitPrice != null
})
</script>
