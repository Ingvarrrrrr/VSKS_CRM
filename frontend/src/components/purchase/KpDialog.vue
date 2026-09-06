<template>
  <v-dialog v-model="kpDialog" max-width="780" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
        <v-icon color="cyan-darken-2">mdi-email-multiple-outline</v-icon>
        Запрос коммерческих предложений
        <v-progress-circular v-if="kpItemsLoading" size="18" indeterminate color="cyan-darken-2" class="ml-2" />
      </v-card-title>
      <v-card-text class="px-6 pb-2">

        <!-- Intro text + delivery date -->
        <v-row dense class="mb-1">
          <v-col cols="8">
            <div class="text-subtitle-2 mb-1">Вводный текст письма</div>
            <v-textarea
              v-model="kpIntroText"
              variant="outlined" density="compact" rows="3" auto-grow hide-details
              placeholder="Уважаемые коллеги, просим предоставить коммерческое предложение..."
            />
          </v-col>
          <v-col cols="4">
            <div class="text-subtitle-2 mb-1">Срок поставки</div>
            <v-text-field
              v-model="kpDeliveryDate"
              variant="outlined" density="compact" hide-details
              placeholder="до 31.12.2026"
            />
          </v-col>
        </v-row>

        <!-- Contractor selector -->
        <div class="text-subtitle-2 mb-1 mt-3">Получатели</div>
        <div class="d-flex align-center gap-2 mb-2">
          <v-autocomplete
            v-model="kpSelected"
            :items="kpContractorOptions"
            item-title="label"
            item-value="id"
            label="Найти контрагента"
            variant="outlined" density="compact"
            multiple hide-selected hide-details
            class="flex-grow-1"
            no-data-text="Не найдено"
          />
        </div>

        <!-- Selected contractors list -->
        <div v-if="kpSelected.length" class="mb-3">
          <div
            v-for="cid in kpSelected" :key="cid"
            class="d-flex align-center gap-2 pa-2 rounded mb-1"
            style="border: 1px solid rgba(0,0,0,0.12);"
          >
            <v-icon icon="mdi-domain" size="small" color="cyan-darken-2" />
            <span class="text-body-2 font-weight-medium" style="min-width:140px">
              {{ kpContractorList.find(c=>c.id===cid)?.name }}
            </span>

            <template v-if="kpEditEmailId !== cid">
              <span v-if="kpContractorList.find(c=>c.id===cid)?.email" class="text-body-2 text-medium-emphasis flex-grow-1">
                {{ kpContractorList.find(c=>c.id===cid)?.email }}
              </span>
              <v-chip v-else color="warning" size="x-small" variant="tonal" class="flex-grow-1">
                <v-icon start icon="mdi-alert-circle-outline" />
                нет email
              </v-chip>
              <v-btn
                :icon="kpContractorList.find(c=>c.id===cid)?.email ? 'mdi-pencil-outline' : 'mdi-email-plus-outline'"
                size="x-small" variant="text"
                :color="kpContractorList.find(c=>c.id===cid)?.email ? 'grey' : 'warning'"
                title="Добавить/изменить email контрагента"
                @click="kpStartEditEmail(cid)"
              />
            </template>
            <template v-else>
              <v-text-field
                v-model="kpEditEmailValue"
                label="Email"
                type="email"
                variant="outlined" density="compact" hide-details
                class="flex-grow-1"
                autofocus
                @keyup.enter="kpSaveEmail(cid)"
                @keyup.esc="kpEditEmailId = null"
              />
              <v-btn icon="mdi-check" size="x-small" variant="tonal" color="success"
                :loading="kpSavingEmail" @click="kpSaveEmail(cid)" />
              <v-btn icon="mdi-close" size="x-small" variant="text" @click="kpEditEmailId = null" />
            </template>

            <v-btn
              icon="mdi-close" size="x-small" variant="text" color="error"
              title="Убрать из списка"
              @click="kpSelected = kpSelected.filter(id => id !== cid)"
            />
          </div>
        </div>

        <!-- Free email recipients -->
        <div v-if="kpFreeRecipients.length" class="mb-2">
          <div v-for="(fr, i) in kpFreeRecipients" :key="i"
            class="d-flex align-center gap-2 pa-2 rounded mb-1"
            style="border: 1px solid rgba(0,0,0,0.12);"
          >
            <v-icon icon="mdi-email-outline" size="small" color="cyan-darken-2" />
            <v-text-field
              v-model="fr.name"
              label="Название / имя"
              variant="outlined" density="compact" hide-details
              style="max-width:170px"
            />
            <v-text-field
              v-model="fr.email"
              label="Email *"
              type="email"
              variant="outlined" density="compact" hide-details
              class="flex-grow-1"
            />
            <v-btn
              icon="mdi-email-outline" size="x-small" variant="tonal" color="cyan-darken-2"
              :disabled="!fr.email"
              title="Открыть в почтовом клиенте"
              @click="openMailtoFree(fr)"
            />
            <v-btn
              icon="mdi-content-copy" size="x-small" variant="text"
              title="Скопировать текст письма"
              @click="copyFreeEmail(fr)"
            />
            <v-btn icon="mdi-close" size="x-small" variant="text" color="error"
              @click="kpFreeRecipients.splice(i, 1)" />
          </div>
        </div>
        <v-btn
          prepend-icon="mdi-email-plus-outline" size="small" variant="text" color="cyan-darken-2"
          class="mb-3"
          @click="kpFreeRecipients.push({ name: '', email: '' })"
        >
          Добавить email вручную
        </v-btn>

        <!-- Per-contractor preview -->
        <template v-if="kpSelected.length > 0">
          <v-divider class="mb-3" />
          <div class="text-subtitle-2 mb-2">Индивидуальные запросы ({{ kpSelected.length }} конт.):</div>
          <v-expansion-panels variant="accordion" class="mb-2">
            <v-expansion-panel
              v-for="cid in kpSelected"
              :key="cid"
            >
              <v-expansion-panel-title>
                <div class="d-flex align-center gap-2 w-100">
                  <v-icon size="16" :color="kpContractorList.find(c=>c.id===cid)?.email ? 'success' : 'warning'">
                    {{ kpContractorList.find(c=>c.id===cid)?.email ? 'mdi-email-check' : 'mdi-email-off' }}
                  </v-icon>
                  <span class="font-weight-medium">{{ kpContractorList.find(c=>c.id===cid)?.name }}</span>
                  <v-chip size="x-small" color="teal" variant="tonal" class="ml-1">
                    {{ kpItemsForContractor(cid).length }} тов.
                  </v-chip>
                  <v-chip
                    v-for="cat in kpContractorList.find(c=>c.id===cid)?.product_categories?.slice(0,2) ?? []"
                    :key="cat" size="x-small" color="grey" variant="tonal" class="ml-1"
                  >{{ cat }}</v-chip>
                  <v-spacer />
                  <v-btn
                    size="x-small" color="cyan-darken-2" variant="tonal"
                    prepend-icon="mdi-email-outline"
                    :disabled="!kpContractorList.find(c=>c.id===cid)?.email"
                    @click.stop="openMailtoForContractor(cid)"
                  >В почту</v-btn>
                  <v-btn size="x-small" variant="text" class="ml-1" @click.stop="copyContractorEmail(cid)">
                    Копировать
                  </v-btn>
                </div>
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <div v-if="kpItemsForContractor(cid).length === 0" class="text-caption text-medium-emphasis py-2">
                  Нет товаров с подходящими категориями — будут отправлены все позиции
                </div>
                <v-table v-else density="compact">
                  <thead>
                    <tr>
                      <th>Наименование</th>
                      <th>Категория</th>
                      <th class="text-right">Кол-во</th>
                      <th class="text-right">Ед.</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in kpItemsForContractor(cid)" :key="item.id">
                      <td class="text-sm">{{ item.item_name }}</td>
                      <td><v-chip size="x-small" color="teal" variant="tonal">{{ item.category || '—' }}</v-chip></td>
                      <td class="text-right text-sm">{{ item.quantity }}</td>
                      <td class="text-right text-caption">{{ item.unit }}</td>
                    </tr>
                  </tbody>
                </v-table>
                <!-- Email preview -->
                <v-textarea
                  :model-value="buildContractorEmail(cid)"
                  variant="outlined" density="compact" rows="6" readonly
                  class="mt-3" hide-details
                  label="Предпросмотр письма"
                />
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </template>
      </v-card-text>
      <v-card-actions class="px-6 pb-4 gap-2">
        <v-btn variant="text" @click="kpDialog = false">Закрыть</v-btn>
        <v-spacer />
        <v-btn
          variant="outlined"
          prepend-icon="mdi-file-excel-outline"
          color="green-darken-1"
          size="small"
          :disabled="!purchaseId"
          @click="downloadKpXlsx"
        >
          Скачать xlsx
        </v-btn>
        <v-btn
          color="teal" variant="flat"
          prepend-icon="mdi-send-outline"
          :loading="kpSendingAll"
          :disabled="kpAllEmails.length === 0"
          @click="sendAllKpViaApi"
        >
          Отправить письма ({{ kpAllEmails.length }})
        </v-btn>
        <v-btn
          variant="text" size="small"
          prepend-icon="mdi-email-multiple-outline"
          :disabled="kpAllEmails.length === 0"
          @click="sendAllKp"
        >
          Открыть в почтовом клиенте
        </v-btn>
        <v-btn
          color="primary" variant="flat"
          prepend-icon="mdi-content-save-outline"
          :loading="kpSaving"
          :disabled="kpAllEmails.length === 0"
          @click="saveKpRequest"
        >
          Сохранить запрос
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDisplay } from 'vuetify'
import { usePurchaseKp, type KpFormSlice } from '@/composables/purchase/usePurchaseKp'

const props = defineProps<{
  purchaseId: number | null
  form: KpFormSlice
}>()

const { mobile } = useDisplay()
const purchaseIdRef = computed(() => props.purchaseId)

const {
  kpDialog, kpSelected, kpIntroText, kpDeliveryDate, kpItemsLoading, kpFreeRecipients,
  kpEditEmailId, kpEditEmailValue, kpSavingEmail, kpSaving, kpSendingAll,
  kpContractorList, kpAllEmails, kpContractorOptions,
  kpItemsForContractor, buildContractorEmail, kpStartEditEmail, kpSaveEmail,
  openMailtoFree, copyFreeEmail, openKpDialog, openMailtoForContractor,
  copyContractorEmail, sendAllKp, sendAllKpViaApi, saveKpRequest, downloadKpXlsx,
} = usePurchaseKp(purchaseIdRef, props.form)

defineExpose({ openKpDialog })
</script>
