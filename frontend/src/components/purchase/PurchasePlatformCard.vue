<template>
  <!-- 10. Публикация на площадках (can_publish permission) -->
  <v-card variant="outlined" class="mb-4" style="border-color:#7C3AED">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
      <span class="d-flex align-center gap-2">
        <v-icon icon="mdi-broadcast" color="deep-purple" size="20" />
        Публикация на площадках
      </span>
      <div class="d-flex gap-2">
        <v-btn color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-folder-zip"
          :loading="docLoading === 'fabrikant_package'"
          @click="downloadFabrikantPackage">
          Скачать пакет (ZIP)
        </v-btn>
        <v-btn color="deep-purple" variant="tonal" size="small" prepend-icon="mdi-upload-network"
          @click="openPublishDialog">
          Опубликовать
        </v-btn>
      </div>
    </v-card-title>
    <v-card-text class="px-4 pb-3">
      <div v-if="!publications.length" class="text-medium-emphasis text-caption">
        Закупка ещё не публиковалась ни на одной площадке
      </div>
      <v-table v-else density="compact">
        <thead>
          <tr>
            <th class="text-caption text-medium-emphasis" style="width:140px">Площадка</th>
            <th class="text-caption text-medium-emphasis" style="width:130px">Статус</th>
            <th class="text-caption text-medium-emphasis" style="width:160px">Номер закупки</th>
            <th class="text-caption text-medium-emphasis">Ссылка на закупку</th>
            <th class="text-caption text-medium-emphasis"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="pub in publications" :key="pub.id">
            <td class="font-weight-medium text-caption">{{ PLATFORM_LABELS[pub.platform] || pub.platform }}</td>
            <td>
              <v-chip size="x-small" :color="PUB_STATUS_COLOR[pub.status]" variant="tonal">
                {{ PUB_STATUS_LABEL[pub.status] || pub.status }}
              </v-chip>
            </td>
            <td class="text-caption">
              <template v-if="pub.status === 'draft'">
                <span v-if="pub.platform_number" class="font-weight-medium">{{ pub.platform_number }}</span>
                <span v-else-if="pub.external_id" class="text-medium-emphasis">{{ pub.external_id }}</span>
                <span v-else class="text-medium-emphasis">—</span>
              </template>
              <span v-else-if="pub.status === 'error'" class="text-error" style="white-space: normal; word-break: break-word">{{ pub.error_text || 'Ошибка публикации' }}</span>
              <span v-else-if="pub.external_id">{{ pub.external_id }}</span>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td class="text-caption">
              <!-- Черновик: ссылка недоступна до размещения — показываем пояснение -->
              <template v-if="pub.status === 'draft'">
                <span class="text-orange-darken-2">
                  Черновик №{{ pub.platform_number || '—' }} создан на Фабриканте.
                  Разместите его в личном кабинете площадки — до размещения ссылка недоступна.
                </span>
              </template>
              <template v-else>
                <a v-if="pub.external_url" :href="pub.external_url" target="_blank"
                  class="text-blue-darken-2 text-decoration-none">
                  {{ pub.external_url }}
                  <v-icon size="11">mdi-open-in-new</v-icon>
                </a>
                <span v-else class="text-medium-emphasis">—</span>
              </template>
            </td>
            <td style="width:72px" class="text-right">
              <!-- Обновить статус: для черновика и опубликованного (состояние может меняться) -->
              <v-btn
                v-if="pub.platform === 'fabrikant' && (pub.status === 'draft' || pub.status === 'published')"
                icon="mdi-refresh"
                size="x-small"
                variant="text"
                color="orange-darken-2"
                :loading="refreshingPubId === pub.id"
                title="Обновить статус с площадки"
                @click="refreshPubStatus(pub)"
              />
              <!-- Ретрай при ошибке -->
              <v-btn v-if="pub.status === 'error'" icon="mdi-send" size="x-small" variant="text"
                color="deep-purple" @click="pub.platform === 'fabrikant' ? openFabrikantRetry(pub.platform) : retryPublish(pub.platform)" />
            </td>
          </tr>
        </tbody>
      </v-table>

      <!-- Документы пакета Фабрикант -->
      <v-divider class="my-3" />
      <div class="text-caption font-weight-medium text-deep-purple mb-2">Документы пакета Фабрикант</div>
      <v-list density="compact" class="pa-0">
        <v-list-item v-for="doc in FABRIKANT_PKG_DOCS" :key="doc.ft" class="px-0 py-1" min-height="36">
          <template #prepend>
            <span class="text-caption" style="min-width:160px">{{ doc.label }}</span>
          </template>
          <template #default>
            <v-chip v-if="fabrikantOverride(doc.ft)" size="x-small" color="deep-purple" variant="tonal" class="mr-1">
              своя версия
            </v-chip>
            <v-chip v-else size="x-small" color="grey" variant="tonal" class="mr-1">авто</v-chip>
            <span v-if="fabrikantOverride(doc.ft)" class="text-caption text-medium-emphasis mr-2">
              {{ fabrikantOverride(doc.ft)!.filename }}
            </span>
          </template>
          <template #append>
            <v-btn icon="mdi-upload" size="x-small" variant="text" density="compact"
              @click="triggerFabrikantUpload(doc.ft)" title="Загрузить свою версию" />
            <template v-if="fabrikantOverride(doc.ft)">
              <v-btn icon="mdi-download" size="x-small" variant="text" density="compact"
                @click="downloadFile(fabrikantOverride(doc.ft)!.id, fabrikantOverride(doc.ft)!.filename)" />
              <v-btn icon="mdi-delete-outline" size="x-small" variant="text" density="compact" color="error"
                @click="deleteFabrikantOverride(fabrikantOverride(doc.ft)!.id)" />
            </template>
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Карточка «Публикация на площадках». Вынесено из CreateOrderView.vue
// (рефакторинг без изменения поведения, часть 3). Все данные/функции — из
// composables/purchase/usePurchasePublications.ts и useFabrikantPackage.ts,
// вызываемых в родителе (downloadFabrikantPackage/docLoading используются
// ещё и в секции «Документы» ниже) — приходят пропами. Скрытый
// <input ref="fabrikantFileInputEl"> НЕ перенесён сюда — тот же случай
// ref-автосвязывания, что и в PurchaseDocumentsCard.vue, остаётся в родителе.
// openPublishDialog — тонкая обёртка в родителе над тем же inline-выражением,
// что раньше стояло прямо в @click (publishErrors/publishDialog/pendingPlatform/
// fabrikantNoNmcd мутируются идентично, просто вызовом функции, а не инлайном,
// т.к. дочерний компонент не может писать в чужие refs напрямую).
defineProps<{
  docLoading: string | null
  downloadFabrikantPackage: () => void
  openPublishDialog: () => void
  publications: any[]
  PLATFORM_LABELS: Record<string, string>
  PUB_STATUS_COLOR: Record<string, string>
  PUB_STATUS_LABEL: Record<string, string>
  refreshingPubId: number | null
  refreshPubStatus: (pub: any) => void
  openFabrikantRetry: (platform: string) => void
  retryPublish: (platform: string) => void
  FABRIKANT_PKG_DOCS: ReadonlyArray<{ readonly ft: string; readonly label: string }>
  fabrikantOverride: (ft: string) => any
  downloadFile: (id: number, filename: string) => void
  deleteFabrikantOverride: (id: number) => void
  triggerFabrikantUpload: (ft: string) => void
}>()
</script>
