<template>
  <!-- ── REJECT DIALOG ── -->
  <v-dialog v-model="rejectDialog" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 pb-2">Отклонить заявку</v-card-title>
      <v-card-text class="pa-4">
        <v-textarea
          v-model="rejectionReason"
          label="Причина отклонения *"
          variant="outlined"
          density="compact"
          rows="4"
          :rules="[v => !!v || 'Укажите причину']"
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="rejectDialog = false">Отмена</v-btn>
        <v-btn variant="flat" color="error" :loading="rejectingWish" :disabled="!(rejectionReason || '').trim()" @click="$emit('reject-confirm')">
          Отклонить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── ПРИНУДИТЕЛЬНАЯ СМЕНА СТАТУСА ИЗ СПИСКА (владелец, 2026-09-02, SaaS-admin) ── -->
  <v-dialog :model-value="!!rowForceStatusWish" max-width="440" :fullscreen="mobile" @update:model-value="(v: boolean) => { if (!v) rowForceStatusWish = null }">
    <v-card v-if="rowForceStatusWish">
      <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
        <v-icon color="red-darken-2">mdi-shield-crown</v-icon>
        Сменить статус заявки №{{ rowForceStatusWish.id }}
      </v-card-title>
      <v-card-text class="pa-4 pt-2">
        <v-select
          v-model="forceStatusValue"
          :items="WISH_FORCE_STATUS_OPTIONS"
          label="Новый статус"
          variant="outlined"
          density="compact"
          hide-details
        />
        <div class="text-body-2 text-medium-emphasis mt-2">
          Минуя все workflow-проверки. Доступно только SaaS-роли.
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="rowForceStatusWish = null">Отмена</v-btn>
        <v-btn color="red-darken-2" variant="flat" prepend-icon="mdi-flash" :loading="forcingStatus" @click="$emit('apply-row-force-status')">
          Применить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── FEO PER-ITEM DISABLE CONFIRM (владелец, 2026-08-19, тумблер вернули) ── -->
  <v-dialog v-model="feoPerItemDisableDialog" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 pb-2">Одна категория ФЭО на всю заявку?</v-card-title>
      <v-card-text class="pa-4">
        У позиций заявки разные категории ФЭО (разных категорий: {{ feoPerItemDisableCount }}) —
        при переключении в режим «одна на всех» построчный выбор будет очищен, и всем позициям
        достанется ОДНА категория, которую нужно будет выбрать в открывшемся блоке над таблицей.
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="$emit('cancel-feo-per-item-disable')">Отмена</v-btn>
        <v-btn variant="flat" color="warning" @click="$emit('confirm-feo-per-item-disable')">Переключить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── STOP DIALOG (владелец, 2026-08-13) ── -->
  <v-dialog v-model="stopDialog" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
        <v-icon color="error">mdi-alert-octagon</v-icon>
        Остановить заявку
      </v-card-title>
      <v-card-text class="pa-4">
        <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
          Заявка и её закупки, не дошедшие до договора, будут остановлены и уйдут из плана закупок.
          Данные не удаляются. Чтобы изменить количество, создайте новую заявку (можно скопировать эту).
        </v-alert>
        <v-textarea
          v-model="stopReason"
          label="Причина остановки (необязательно)"
          variant="outlined"
          density="compact"
          rows="3"
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="stopDialog = false">Отмена</v-btn>
        <v-btn variant="flat" color="error" :loading="stoppingWish" @click="$emit('stop-confirm')">
          Остановить заявку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── CONVERT TO ADVANCE REPORT DIALOG (владелец, 2026-09-04) ── -->
  <v-dialog v-model="convertToAdvanceDialog" max-width="560" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
        <v-icon color="orange-darken-2">mdi-cash-refund</v-icon>
        Оформить как авансовый отчёт
      </v-card-title>
      <v-card-text class="pa-4">
        <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
          Заявка «{{ convertingToAdvanceWish?.title }}» перестанет быть заявкой на закупку и
          станет авансовым отчётом — появится в реестре «Авансовые отчёты» с теми же позициями,
          суммами, субсидией и категорией ФЭО. Если по заявке уже есть закупка в плане закупок
          (ещё не на этапе договора) — она будет отменена, новая закупка станет авансовой.
          Действие необратимо через интерфейс — вернуть обратно в обычную заявку нельзя.
        </v-alert>
        <div class="text-body-2">
          Позиций: {{ (convertingToAdvanceWish?.items || []).length }},
          сумма: {{ ctx.formatPrice(convertingToAdvanceWish?.total_amount ?? convertingToAdvanceWish?.estimated_price ?? 0) }}
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="convertToAdvanceDialog = false">Отмена</v-btn>
        <v-btn variant="flat" color="orange-darken-2" :loading="convertingToAdvanceLoading" @click="$emit('convert-to-advance-confirm')">
          Оформить как авансовый отчёт
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── CONVERT DIALOG ── -->
  <v-dialog v-model="convertDialog" max-width="540" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 pb-2">Создать закупку из заявки</v-card-title>
      <v-card-text class="pa-4">
        <div class="mb-4 pa-3 bg-grey-lighten-4 rounded">
          <div class="text-subtitle-2 font-weight-bold mb-1">Исходная заявка</div>
          <div class="text-body-2">{{ convertingWish?.title }}</div>
          <div class="text-caption text-medium-emphasis mt-1">
            <span v-if="convertingWish?.total_amount">НМЦК: {{ ctx.formatPrice(convertingWish.total_amount) }}</span>
          </div>
        </div>
        <v-row dense class="mb-3">
          <v-col cols="6">
            <v-text-field
              v-model.number="convertForm.approved_quantity"
              label="Утверждённое количество"
              type="number"
              variant="outlined"
              density="compact"
              min="0"
            />
          </v-col>
          <v-col cols="6">
            <!-- Владелец: при наличии позиций сумма закупки = сумма позиций
                 (ПРАВИЛО №6 — один источник истины), поле не редактируется —
                 меняется только через позиции заявки. -->
            <v-text-field
              v-if="convertingWishItemsCount === 0"
              v-model.number="convertForm.approved_price"
              label="Утверждённая цена (₽)"
              type="number"
              variant="outlined"
              density="compact"
              min="0"
            />
            <div v-else class="text-caption text-medium-emphasis">
              Сумма закупки = сумма позиций ({{ convertingWishItemsCount }} поз., {{ ctx.formatPrice(convertingWishItemsSum) }}).
              Чтобы изменить — отредактируйте позиции заявки.
            </div>
          </v-col>
        </v-row>
        <v-select
          v-model="convertForm.subsidy_id"
          :items="ctx.subsidies.value"
          item-title="name"
          item-value="id"
          label="Субсидия (опционально)"
          variant="outlined"
          density="compact"
          clearable
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="convertDialog = false">Отмена</v-btn>
        <v-btn variant="flat" color="primary" :loading="convertingWishLoading" @click="$emit('convert-confirm')">
          Создать закупку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// WishActionDialogs.vue — вспомогательные диалоги над одной заявкой: отклонение,
// принудительная смена статуса из списка, подтверждение отключения «Разные категории
// ФЭО для каждого товара», остановка, «оформить как авансовый отчёт», создание закупки
// (convert). Дословный перенос шаблона (2258-2442) из WishesView.vue — состояние и
// подтверждающие действия остаются в useWishForm.ts/useWishActions.ts (родитель
// WishFormDialog.vue передаёт их через v-model, минимальные props/emits).
import { useWishesContext } from '@/composables/wishes/useWishesContext'
import type { Wish } from '@/composables/wishes/wishTypes'

defineProps<{
  mobile: boolean
  rejectingWish: boolean
  WISH_FORCE_STATUS_OPTIONS: { value: string; title: string }[]
  forcingStatus: boolean
  feoPerItemDisableCount: number
  stoppingWish: boolean
  convertingToAdvanceWish: Wish | null
  convertingToAdvanceLoading: boolean
  convertingWish: Wish | null
  convertingWishLoading: boolean
  convertingWishItemsCount: number
  convertingWishItemsSum: number
}>()

defineEmits<{
  (e: 'reject-confirm'): void
  (e: 'apply-row-force-status'): void
  (e: 'confirm-feo-per-item-disable'): void
  (e: 'cancel-feo-per-item-disable'): void
  (e: 'stop-confirm'): void
  (e: 'convert-to-advance-confirm'): void
  (e: 'convert-confirm'): void
}>()

const rejectDialog = defineModel<boolean>('rejectDialog', { required: true })
const rejectionReason = defineModel<string>('rejectionReason', { required: true })
const rowForceStatusWish = defineModel<Wish | null>('rowForceStatusWish', { required: true })
const forceStatusValue = defineModel<string>('forceStatusValue', { required: true })
const feoPerItemDisableDialog = defineModel<boolean>('feoPerItemDisableDialog', { required: true })
const stopDialog = defineModel<boolean>('stopDialog', { required: true })
const stopReason = defineModel<string>('stopReason', { required: true })
const convertToAdvanceDialog = defineModel<boolean>('convertToAdvanceDialog', { required: true })
const convertDialog = defineModel<boolean>('convertDialog', { required: true })
const convertForm = defineModel<{ approved_quantity: number | null; approved_price: number | null; subsidy_id: number | null }>('convertForm', { required: true })

const ctx = useWishesContext()
</script>
