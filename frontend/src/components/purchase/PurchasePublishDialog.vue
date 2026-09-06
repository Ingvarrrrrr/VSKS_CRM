<template>
  <!-- Publish dialog -->
  <v-dialog v-model="open" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
        <v-icon color="deep-purple">mdi-broadcast</v-icon>
        Опубликовать закупку
      </v-card-title>
      <v-card-text class="px-6">

        <!-- Ошибки валидации -->
        <v-alert v-if="publishErrors.length" type="error" variant="tonal" density="compact" class="mb-4">
          <div class="text-subtitle-2 mb-1">Заполните обязательные поля:</div>
          <ul class="pl-4 mb-0">
            <li v-for="e in publishErrors" :key="e.target" class="text-body-2"
              style="cursor:pointer" @click="revealField(e.target)">
              <v-icon size="14" class="mr-1">mdi-arrow-right-circle</v-icon>{{ e.text }}
            </li>
          </ul>
        </v-alert>

          <p class="text-body-2 text-medium-emphasis mb-4">
            Выберите площадку. Данные закупки будут отправлены автоматически.
          </p>
          <v-list density="compact" class="border rounded">
            <v-list-item
              v-for="pl in AVAILABLE_PLATFORMS" :key="pl.value"
              :title="pl.title"
              :subtitle="pl.subtitle"
              class="py-3"
            >
              <template #prepend>
                <v-avatar :color="pl.color" size="36" class="mr-3">
                  <v-icon size="18" color="white">{{ pl.icon }}</v-icon>
                </v-avatar>
              </template>
              <template #append>
                <v-btn
                  color="deep-purple" variant="tonal" size="small"
                  :loading="publishingPlatform === pl.value"
                  :disabled="isPlatformPublished(pl.value)"
                  @click="pendingPlatform = pl.value; if (pl.value === 'fabrikant') { initFabrikantDates(); fabrikantNoNmcd = !(publishNmck > 0) }"
                >
                  {{ publications.some(p => p.platform === pl.value && p.status === 'draft') ? 'Черновик на ЭТП' : isPlatformPublished(pl.value) ? 'Опубликовано' : 'Опубликовать' }}
                </v-btn>
              </template>
            </v-list-item>
          </v-list>

          <!-- Настройки Фабрикант: даты -->
          <v-expand-transition>
            <div v-if="pendingPlatform === 'fabrikant'" class="mt-3 px-1">
              <v-divider class="mb-3" />
              <div class="text-subtitle-2 mb-3">Параметры публикации на Фабрикант</div>
              <v-alert v-if="!currentSubsidyOrgInn" type="warning" variant="tonal" density="compact" class="mb-3 text-caption">
                Не заполнен ИНН организации-заказчика. Перейдите в раздел <strong>Организации</strong> → нажмите карандаш → укажите ИНН.
              </v-alert>

              <!-- Тип процедуры -->
              <v-select
                v-model="fabrikantProcedureType"
                :items="FABRIKANT_PROCEDURE_TYPES"
                item-title="title"
                item-value="value"
                label="Тип процедуры"
                variant="outlined"
                density="compact"
                hide-details
                class="mb-3"
              />

              <!-- Подсказка для Мониторинга цен -->
              <v-alert v-if="fabrikantProcedureType === 'price_monitoring'" type="info" variant="tonal" density="compact" class="mb-3 text-caption">
                Сбор ценовых предложений без объявления цены и позиций. НМЦД не требуется.
              </v-alert>

              <div id="pub-target-okpd2" style="position:relative">
                <v-autocomplete
                  v-model="fabrikantOkpd2"
                  :items="okpd2Items"
                  :item-value="(i: {code: string}) => i.code"
                  :item-title="(i: {code: string; name: string}) => okpd2ItemTitle(i)"
                  :no-filter="true"
                  :loading="okpd2Loading"
                  clearable
                  label="Код ОКПД2 (обязательно)"
                  variant="outlined"
                  density="compact"
                  class="mb-3"
                  :error="okpd2Pointer && !fabrikantOkpd2"
                  @update:search="searchOkpd2"
                  @update:model-value="okpd2Pointer = false; clearGuideArrow()"
                >
                  <template #no-data>
                    <v-list-item>
                      <v-list-item-title class="text-caption" :class="okpd2Error ? 'text-error' : 'text-medium-emphasis'">
                        {{ okpd2Error || 'Ничего не найдено' }}
                      </v-list-item-title>
                    </v-list-item>
                  </template>
                </v-autocomplete>
                <div v-if="okpd2Pointer" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
              </div>

              <!-- НМЦД — скрыт для Мониторинга цен -->
              <div v-if="fabrikantProcedureType !== 'price_monitoring'" class="mb-3">
                <div v-if="publishNmck > 0" class="text-body-2 mb-1">
                  НМЦД: <strong>{{ formatMoney(publishNmck) }}</strong>
                </div>
                <v-checkbox
                  v-model="fabrikantNoNmcd"
                  label="Опубликовать без НМЦД"
                  density="compact"
                  hide-details
                  color="orange-darken-2"
                />
                <div v-if="publishNmck === 0" class="text-caption text-medium-emphasis mt-1">
                  НМЦД не найдена в закупке — будет опубликовано без НМЦД. Чтобы указать цену, заполните НМЦД в карточке.
                  <v-btn variant="text" size="x-small" class="ml-1" @click="revealField('nmck')">Показать поле НМЦД</v-btn>
                </div>
              </div>

              <v-row dense>
                <v-col cols="12" sm="6">
                  <v-text-field
                    v-model="fabrikantDates.proposal_start"
                    type="datetime-local"
                    label="Начало приёма предложений"
                    variant="outlined" density="compact"
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    v-model="fabrikantDates.proposal_end"
                    type="datetime-local"
                    label="Конец приёма предложений"
                    variant="outlined" density="compact"
                  />
                </v-col>
                <!-- Определение победителя — только для ЗП -->
                <v-col v-if="fabrikantProcedureType === 'zp'" cols="12" sm="6">
                  <v-text-field
                    v-model="fabrikantDates.determination_date"
                    type="datetime-local"
                    label="Определение победителя"
                    variant="outlined" density="compact"
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    v-model="fabrikantDates.summing_up_date"
                    type="datetime-local"
                    label="Подведение итогов"
                    variant="outlined" density="compact"
                  />
                </v-col>
              </v-row>

              <!-- Поля редукциона -->
              <template v-if="fabrikantProcedureType === 'reduction'">
                <v-divider class="my-2" />
                <div class="text-caption text-medium-emphasis mb-2">Параметры редукциона</div>
                <v-row dense>
                  <v-col cols="12">
                    <div id="pub-target-auction-date" style="position:relative">
                      <div v-if="auctionPointerTarget === 'auction-date'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                      <div :class="auctionPointerTarget === 'auction-date' ? 'pub-glow' : ''">
                        <v-text-field
                          v-model="fabrikantAuctionDateStart"
                          type="datetime-local"
                          label="Дата и время начала редукциона *"
                          variant="outlined" density="compact"
                          :error="!fabrikantAuctionDateStart"
                          @update:model-value="auctionPointerTarget = null; clearGuideArrow()"
                        />
                      </div>
                    </div>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <div id="pub-target-auction-bet" style="position:relative">
                      <div v-if="auctionPointerTarget === 'auction-bet'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
                      <div :class="auctionPointerTarget === 'auction-bet' ? 'pub-glow' : ''">
                        <v-text-field
                          v-model.number="fabrikantAuctionBetFrom"
                          type="number"
                          label="Граница ставки от *"
                          variant="outlined" density="compact"
                          :error="numOrNull(fabrikantAuctionBetFrom) === null"
                          @update:model-value="auctionPointerTarget = null; clearGuideArrow()"
                        />
                      </div>
                    </div>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-text-field
                      v-model.number="fabrikantAuctionBetTo"
                      type="number"
                      label="Граница ставки до *"
                      variant="outlined" density="compact"
                      :error="numOrNull(fabrikantAuctionBetTo) === null"
                      @update:model-value="auctionPointerTarget = null"
                    />
                  </v-col>
                </v-row>
              </template>

              <v-checkbox
                v-model="fabrikantAttachDocs"
                label="Прикрепить пакет документов (5 файлов)"
                density="compact"
                hide-details
                color="orange-darken-2"
                class="mb-2"
              />
              <div class="d-flex gap-2 mt-1">
                <v-btn variant="text" @click="pendingPlatform = null">Назад</v-btn>
                <v-btn color="orange-darken-2"
                  :loading="publishingPlatform === 'fabrikant'"
                  :disabled="!fabrikantOkpd2 || !fabrikantDates.proposal_start || !fabrikantDates.proposal_end || !currentSubsidyOrgInn"
                  @click="() => { publishErrors = checkPublishReady(); if (!publishErrors.length) doPublish('fabrikant'); else revealField(publishErrors[0]!.target) }"
                >Опубликовать на Фабрикант</v-btn>
              </div>
            </div>
          </v-expand-transition>

          <!-- Выбор типа процедуры для Росэлторг -->
          <v-expand-transition>
            <div v-if="pendingPlatform === 'roseltorg_rb'" class="mt-3 px-1">
              <v-divider class="mb-3" />
              <div class="text-subtitle-2 mb-2">Тип процедуры Росэлторг.Бизнес</div>
              <v-select
                v-model="roseltorgProcedureType"
                :items="ROSELTORG_PROCEDURE_TYPES"
                item-title="title"
                item-value="value"
                label="Выберите тип процедуры"
                variant="outlined"
                density="compact"
                hide-details
              />
              <div class="d-flex gap-2 mt-3">
                <v-btn variant="text" @click="pendingPlatform = null; roseltorgProcedureType = null">Назад</v-btn>
                <v-btn
                  color="deep-purple"
                  :disabled="!roseltorgProcedureType"
                  :loading="publishingPlatform === 'roseltorg_rb'"
                  @click="doPublish('roseltorg_rb', roseltorgProcedureType)"
                >Опубликовать на Росэлторг</v-btn>
              </div>
            </div>
          </v-expand-transition>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false; pendingPlatform = null; roseltorgProcedureType = null; publishErrors = []">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { numOrNull } from '@/utils/numberFormat'
import { AVAILABLE_PLATFORMS, FABRIKANT_PROCEDURE_TYPES, ROSELTORG_PROCEDURE_TYPES, type Publication, type PublishTarget } from '@/composables/purchase/usePurchasePublications'

const open = defineModel<boolean>('open', { default: false })
const pendingPlatform = defineModel<string | null>('pendingPlatform', { default: null })
const roseltorgProcedureType = defineModel<string | null>('roseltorgProcedureType', { default: null })
const fabrikantProcedureType = defineModel<'zp' | 'reduction' | 'price_monitoring'>('fabrikantProcedureType', { default: 'zp' })
const fabrikantOkpd2 = defineModel<string>('fabrikantOkpd2', { default: '' })
const fabrikantNoNmcd = defineModel<boolean>('fabrikantNoNmcd', { default: false })
const fabrikantAttachDocs = defineModel<boolean>('fabrikantAttachDocs', { default: true })
const fabrikantAuctionDateStart = defineModel<string>('fabrikantAuctionDateStart', { default: '' })
const fabrikantAuctionBetFrom = defineModel<number | null>('fabrikantAuctionBetFrom', { default: null })
const fabrikantAuctionBetTo = defineModel<number | null>('fabrikantAuctionBetTo', { default: null })
const publishErrors = defineModel<{ text: string; target: PublishTarget }[]>('publishErrors', { default: () => [] })
const okpd2Pointer = defineModel<boolean>('okpd2Pointer', { default: false })
const auctionPointerTarget = defineModel<string | null>('auctionPointerTarget', { default: null })

defineProps<{
  publishingPlatform: string | null
  publications: Publication[]
  currentSubsidyOrgInn: string | null
  publishNmck: number
  okpd2Items: { code: string; name: string; section: string | null }[]
  okpd2Loading: boolean
  okpd2Error: string
  fabrikantDates: { proposal_start: string; proposal_end: string; determination_date: string; summing_up_date: string }
  formatMoney: (v: number) => string
  isPlatformPublished: (platform: string) => boolean
  checkPublishReady: () => { text: string; target: PublishTarget }[]
  okpd2ItemTitle: (item: { code: string; name: string }) => string
  searchOkpd2: (q: string | undefined) => void
  doPublish: (platform: string, procedureType?: string | null) => Promise<void>
  revealField: (target: string) => void
  clearGuideArrow: () => void
  initFabrikantDates: () => void
}>()

const { mobile } = useDisplay()
</script>
