<template>
  <!-- Превышение бюджета субсидии -->
  <v-dialog v-model="budgetOverrideOpen" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 d-flex align-center ga-2">
        <v-icon color="warning">mdi-alert</v-icon>
        Превышение бюджета субсидии
      </v-card-title>
      <v-card-text>
        <v-alert type="warning" variant="tonal" class="mb-3">
          Сумма закупки превышает остаток бюджета субсидии на
          <strong>{{ budgetInfo ? formatMoney(budgetInfo.over) : '' }}</strong>.
        </v-alert>
        Как администратор вы можете сохранить закупку с превышением бюджета.
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="outlined" @click="budgetOverrideOpen = false">Отмена</v-btn>
        <v-btn color="warning" variant="flat" :loading="saving" @click="$emit('save-with-override')">
          Сохранить с превышением
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Отключение разных ФЭО по позициям -->
  <v-dialog v-model="feoPerItemDisableOpen" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 d-flex align-center ga-2">
        <v-icon color="warning">mdi-alert</v-icon>
        Отключить разные ФЭО по позициям?
      </v-card-title>
      <v-card-text>
        У {{ feoPerItemDisableCount }} {{ feoPerItemDisableCount === 1 ? 'позиции' : 'позиций' }} указана своя категория ФЭО — при отключении режима она будет очищена.
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="outlined" @click="$emit('cancel-feo-disable')">Отмена</v-btn>
        <v-btn color="warning" variant="flat" @click="$emit('confirm-feo-disable')">Отключить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Возможный повтор закупки -->
  <v-dialog v-model="duplicateOpen" max-width="560" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-warning">Возможный повтор закупки</v-card-title>
      <v-card-text>
        <div class="mb-3">Уже есть разовые закупки с этим контрагентом и совпадающей суммой (НМЦК, цена договора или платёж). Возможно, это повтор:</div>
        <v-list density="compact">
          <v-list-item v-for="m in duplicateMatches" :key="m.id"
            @click="$router.push(`/orders/${m.id}/edit`)" style="cursor:pointer;">
            <v-list-item-title>№{{ m.purchase_number ?? m.id }} — {{ m.name || 'без названия' }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ m.total_nmck != null ? Number(m.total_nmck).toLocaleString('ru-RU') + ' ₽' : '' }}
              <span v-if="(m as any).match_reason"> · совпало по: {{ (m as any).match_reason }}</span>
              <span v-if="m.contract_date"> · {{ m.contract_date }}</span>
              · {{ m.status }}
            </v-list-item-subtitle>
            <template #append><v-icon size="small">mdi-open-in-new</v-icon></template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer/>
        <v-btn variant="text" @click="duplicateOpen = false">Отмена</v-btn>
        <v-btn color="warning" variant="flat" @click="$emit('confirm-duplicate-save')">Всё равно сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Владелец (2026-08-21, дефект «Цена договора пустая»): переход в «Договор»
       молча подставлял сумму позиций (backend Phase 27.1 D-07) без единого
       подтверждения — предлагаем проверить цену и перечень позиций (обычно
       переносятся из ТЗ) перед заключением договора. -->
  <v-dialog v-model="contractedConfirmOpen" max-width="560" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center ga-2">
        <v-icon color="indigo">mdi-file-sign</v-icon>
        Проверьте перед переходом в «Договор»
      </v-card-title>
      <v-card-text>
        <div class="mb-3">
          Цена договора = сумма позиций
          <strong>{{ formatMoney(displayNmck) }}</strong>.
          Проверьте перед заключением договора — при необходимости измените ниже.
        </div>
        <v-text-field
          v-model.number="contractPrice"
          label="Цена договора" type="number" variant="outlined" density="compact"
          suffix="₽" hide-details class="mb-3"
          @update:model-value="$emit('contract-price-edited')"
        />
        <div class="text-caption text-medium-emphasis mb-1">
          В договор уйдут позиции ниже. Названия обычно переносятся из ТЗ — если что-то
          нужно поправить, откройте редактор позиций.
        </div>
        <v-list density="compact" class="mb-2" style="max-height:260px;overflow-y:auto">
          <v-list-item v-for="(it, idx) in contractedConfirmItems" :key="idx">
            <v-list-item-title>{{ it.name }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ it.qty ?? '—' }} {{ it.unit || '' }} × {{ it.price != null ? formatMoney(it.price) : '—' }}
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="!contractedConfirmItems.length">
            <v-list-item-title class="text-medium-emphasis">Позиции не заполнены</v-list-item-title>
          </v-list-item>
        </v-list>
        <v-btn size="small" variant="text" color="primary" prepend-icon="mdi-pencil"
          @click="$emit('edit-items-before-contract')">
          Изменить позиции
        </v-btn>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="contractedConfirmOpen = false">Отмена</v-btn>
        <v-btn color="indigo" variant="flat" :loading="transitioning" @click="$emit('confirm-contracted-transition')">
          Всё верно, перейти в «Договор»
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const budgetOverrideOpen = defineModel<boolean>('budgetOverrideOpen', { default: false })
const feoPerItemDisableOpen = defineModel<boolean>('feoPerItemDisableOpen', { default: false })
const duplicateOpen = defineModel<boolean>('duplicateOpen', { default: false })
const contractedConfirmOpen = defineModel<boolean>('contractedConfirmOpen', { default: false })
const contractPrice = defineModel<number | null>('contractPrice', { default: null })

defineProps<{
  budgetInfo: { over: number } | null
  saving: boolean
  feoPerItemDisableCount: number
  duplicateMatches: any[]
  contractedConfirmItems: { name: string; qty: number | null; unit?: string; price: number | null }[]
  transitioning: boolean
  displayNmck: number
  formatMoney: (v: number) => string
}>()

defineEmits<{
  (e: 'save-with-override'): void
  (e: 'cancel-feo-disable'): void
  (e: 'confirm-feo-disable'): void
  (e: 'confirm-duplicate-save'): void
  (e: 'edit-items-before-contract'): void
  (e: 'confirm-contracted-transition'): void
  (e: 'contract-price-edited'): void
}>()

const { mobile } = useDisplay()
</script>
