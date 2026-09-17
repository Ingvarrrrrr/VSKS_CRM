<template>
  <!-- 5. Закрывающие документы (admin+) -->
  <v-card variant="outlined" class="mb-4">
    <!-- Мобильный фикс (владелец, 2026-09-04, «прокручиваемых вбок таблиц быть не должно»):
         заголовок + кнопка без flex-wrap уезжали за правый край на узком экране, кнопка
         «Добавить закрывающий документ» обрезалась. flex-wrap ga-2 — тот же приём, что уже
         применён у заголовков «Загрузите чеки»/«Чеки» выше в этом файле: на десктопе места
         хватает и перенос не срабатывает, на мобильном кнопка уходит на вторую строку. -->
    <v-card-title class="d-flex flex-wrap align-center ga-2 text-subtitle-1 font-weight-bold px-4 pt-4">
      Закрывающие документы
      <v-spacer />
      <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-plus" @click="addAcceptanceDoc">Добавить закрывающий документ</v-btn>
    </v-card-title>
    <v-card-text>
      <!-- Phase 26-ppp: кнопки «Загрузить» для типов документов (Договор/Акт/УПД/...)
           перенесены в секцию «Документы к закупке» (один блок upload вместо
           двух мест). Здесь оставляем ТОЛЬКО реквизиты (тип/№/дата/сумма) —
           связь с файлом по-прежнему есть через doc.file_id paperclip-кнопку. -->

      <!-- Реквизиты закрывающих документов -->
      <div v-for="(doc, idx) in acceptanceDocs" :key="idx" class="mb-3">
        <div class="d-flex align-center gap-2 mb-1">
          <span class="text-caption font-weight-medium">Документ {{ idx + 1 }}</span>
          <v-spacer />
          <v-btn
            v-if="doc.file_id"
            icon="mdi-paperclip"
            variant="text"
            size="x-small"
            color="primary"
            title="Скачать прикреплённый файл (чек)"
            @click="downloadAcceptanceFile(doc.file_id!)"
          />
          <v-btn icon="mdi-close" variant="text" size="x-small" color="error" @click="acceptanceDocs.splice(idx, 1)" />
        </div>
        <v-row dense>
          <v-col cols="12" md="5">
            <v-combobox
              v-model="doc.name"
              :items="acceptanceDocTypes"
              label="Тип документа"
              variant="outlined"
              density="compact"
              hide-details="auto"
              @update:model-value="onAcceptanceDocTypeAdd($event)"
            >
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps" :title="item.raw">
                  <template #append>
                    <v-btn
                      v-if="!builtinAcceptanceDocTypes.includes(item.raw)"
                      icon="mdi-close"
                      size="x-small"
                      variant="text"
                      color="error"
                      @click.stop="deleteCustomDocType(item.raw)"
                    />
                  </template>
                </v-list-item>
              </template>
            </v-combobox>
          </v-col>
          <v-col cols="12" md="2">
            <v-text-field v-model="doc.number" label="Номер" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="2">
            <v-text-field v-model="doc.date" label="Дата" variant="outlined" density="compact" type="date" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model.number="doc.amount" label="Сумма" variant="outlined" density="compact" type="number" suffix="₽" hide-details />
          </v-col>
        </v-row>
        <v-divider v-if="idx < acceptanceDocs.length - 1" class="mt-3" />
      </div>

      <!-- Кнопка загрузки чека для авансового отчёта -->
      <div v-if="isEdit && purchaseId && (formMode === 'advance_report' || form.purchase_method === 'advance')" class="mt-3 mb-1">
        <v-btn size="small" variant="tonal" color="#fb923c" prepend-icon="mdi-receipt-text" @click="onJsonBtnClick">
          Загрузить чек
        </v-btn>
      </div>

      <!-- Владелец (п.7, 2026-09-17): «поле "Перетащите закрывающий документ"
           некорректно, туда перетаскиваешь и ничего не происходит». Проверено
           по коду: зона технически рабочая (FileDropZone → onAcceptanceDocFilesDropped
           → uploadFilesForType(files,'other') → POST .../files, снэк «Файл
           загружен») — сбивало с толку то, что результат появляется НЕ здесь,
           а в отдельной карточке «Документы к закупке» (PurchaseDocumentsCard,
           дальше по странице), тогда как сюда, в «Закрывающие документы»,
           ничего не добавляется — ни строки, ни превью. Владелец просит на
           это место крупную кнопку «Добавить закрывающий документ» — тот же
           addAcceptanceDoc, что и мелкая кнопка в заголовке (ПРАВИЛО №6, один
           источник действия, не второй механизм), просто заметнее. -->
      <v-btn
        v-if="isEdit && purchaseId"
        block
        size="x-large"
        variant="tonal"
        color="teal"
        prepend-icon="mdi-plus"
        class="mt-3"
        @click="addAcceptanceDoc"
      >
        Добавить закрывающий документ
      </v-btn>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Блок «Закрывающие документы». Вынесено из CreateOrderView.vue (рефакторинг
// без изменения поведения, часть 3). acceptanceDocs — тот же reactive-массив
// родителя (передан пропом без v-model, мутируется напрямую splice/push —
// тот же приём, что и form/items в других вынесенных секциях); остальные
// функции/справочники (addAcceptanceDoc/downloadAcceptanceFile/onJsonBtnClick/...)
// остаются в родителе и приходят колбэками, т.к. используются там же в
// save()/loadPurchase()/DocPickerDialogs.
defineProps<{
  form: any
  isEdit: boolean
  purchaseId: number | null
  formMode: string
  acceptanceDocs: Array<{ name: string; number: string; date: string; amount: number | null; file_id?: number | null }>
  acceptanceDocTypes: string[]
  builtinAcceptanceDocTypes: string[]
  addAcceptanceDoc: () => void
  downloadAcceptanceFile: (fileId: number) => void
  onAcceptanceDocTypeAdd: (val: string | null) => void
  deleteCustomDocType: (val: string) => void
  onJsonBtnClick: () => void
  onAcceptanceDocFilesDropped: (files: File[]) => void
}>()
</script>
