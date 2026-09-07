<template>
  <div class="d-flex align-center justify-space-between mb-6">
    <div>
      <h1 class="text-h5 font-weight-bold" v-if="!isEdit || purchaseLoaded">
        {{ pageTitle }}
      </h1>
      <div v-else class="text-h5 font-weight-bold text-medium-emphasis">…</div>
      <div class="d-flex align-center gap-2 mt-1">
        <v-chip v-if="isEdit && form.status" :color="statusColor[form.status]" size="small" variant="tonal">
          {{ statusLabel[form.status] }}
        </v-chip>
        <!-- Владелец (2026-09-02, закупка РЕЕ-2026-00904): «раньше суперадмин мог
             двигать закупки по статусам самостоятельно, куда делось это поле» —
             в карточке закупки такого управления не было вообще (было только в
             списке, OrdersView.vue). Минует workflow-проверки, доступно только
             SaaS-роли. -->
        <v-menu v-if="isSaas && isEdit && purchaseId">
          <template #activator="{ props: menuProps }">
            <v-btn v-bind="menuProps" icon="mdi-shield-crown" size="x-small" variant="text" color="red-darken-2"
              :loading="forcingOrderStatus" title="Принудительно сменить статус (SaaS-admin)" />
          </template>
          <v-list density="compact">
            <v-list-item v-for="s in statusOrder" :key="s" :disabled="s === form.status" @click="forceOrderStatus(s)">
              <template #prepend><v-icon :color="statusColor[s]" icon="mdi-circle-medium" /></template>
              <v-list-item-title>{{ statusLabel[s] }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
        <v-chip v-if="form.substatus" size="x-small" variant="outlined" color="teal">
          {{ substatusOptions.find(o => o.value === form.substatus)?.title || form.substatus }}
        </v-chip>
        <v-icon v-if="form.is_monthly_payment" size="small" color="blue" title="Ежемесячный платёж">mdi-calendar-sync</v-icon>
        <span v-if="isEdit && form.registry_number" class="text-caption text-medium-emphasis">
          Реестр: {{ form.registry_number }}
        </span>
        <v-fade-transition>
          <span v-if="draftSaved" class="text-caption text-success">
            <v-icon size="12" icon="mdi-cloud-check" /> Черновик сохранён
          </span>
        </v-fade-transition>
        <v-btn v-if="!isEdit && hasDraft" size="x-small" variant="outlined" color="warning"
          prepend-icon="mdi-delete-sweep" @click="clearDraft(); showSnack('Черновик удалён')">
          Очистить черновик
        </v-btn>
      </div>
    </div>
    <v-btn variant="outlined" prepend-icon="mdi-arrow-left" :to="backRoute">К списку</v-btn>
  </div>

  <!-- Задача владельца (сессия 2026-08-21): плашка превышения ФЭО + строка «Создана
       из заявки №N». См. computed-и purchaseExcess*/purchaseData выше — оба блока
       тихо не рендерятся, пока backend-агент не досчитал соответствующие поля в
       GET /api/purchases/{id} (v-if по наличию полей, не заглушки). -->
  <div v-if="isEdit && purchaseData?.feo_excess" class="feo-excess-culprit mb-3">
    <v-icon size="16" icon="mdi-alert-decagram" class="mr-1" />
    <span>{{ purchaseExcessText }}</span>
    <v-chip size="x-small" :color="purchaseExcessStateColor" variant="flat" class="ml-1">
      {{ purchaseExcessStateText }}
    </v-chip>
  </div>

  <!-- Владелец (2026-09-02): «уведомление глобально, если позиция категории
       ФЭО вверху и в каждом товаре не соответствует друг другу — об этом
       должен быть алярм прям стоять». По образцу .purchase-stopped-banner
       (OrdersView.vue) — крупная рамка на всю ширину, держится, пока
       расхождение есть (не таймаут-снэкбар). Красный занят остановкой
       закупки — здесь предупреждающий (амбер) цвет. См. GET /api/purchases/{id}
       → feo_mismatch/feo_mismatch_items (app.routers.purchases._compute_purchase_feo_mismatch). -->
  <div v-if="isEdit && purchaseData?.feo_mismatch" class="feo-mismatch-banner mb-3">
    <div class="feo-mismatch-banner__head">
      <v-icon icon="mdi-alert" size="18" class="mr-1" />
      <span class="feo-mismatch-banner__title">РАСХОЖДЕНИЕ КАТЕГОРИИ ФЭО</span>
    </div>
    <div class="feo-mismatch-banner__hint">
      Категория ФЭО у закупки и у товаров не совпадает. Выберите плановую позицию
      из нужной категории либо исправьте категорию — иначе лист согласования и
      план ФЭО разъедутся.
    </div>
    <ul class="feo-mismatch-banner__list">
      <li v-for="mi in (purchaseData?.feo_mismatch_items || [])" :key="mi.item_id">
        {{ mi.message }}
      </li>
    </ul>
    <!-- Владелец (2026-09-02): чинит ровно то, что описывает reason='header'/'both' —
         видна только пока «разные категории для каждого товара» выключены и есть
         хоть одна позиция со своей (протухшей) категорией. См. fixFeoMismatchOwnCategories. -->
    <v-btn v-if="feoMismatchFixableItems.length" size="small" variant="tonal" color="warning"
      prepend-icon="mdi-broom" :loading="fixingFeoMismatch" class="mt-2"
      @click="fixFeoMismatchOwnCategories">
      Убрать свои категории у позиций ({{ feoMismatchFixableItems.length }})
    </v-btn>
  </div>
  <div v-if="isEdit && purchaseData?.wish_id" class="text-caption text-medium-emphasis mb-3 d-flex align-center ga-1 flex-wrap">
    <v-icon size="14" icon="mdi-file-document-outline" />
    <span>Создана из заявки №{{ purchaseData.wish_id }}{{ purchaseData.wish_title ? ` «${purchaseData.wish_title}»` : '' }}</span>
    <v-btn size="x-small" variant="text" color="primary"
      @click="goToWish(purchaseData.wish_id)">
      Открыть заявку
    </v-btn>
  </div>
  <!-- Владелец (2026-08-21, дефект «отцеплённая закупка»): status='wishes' —
       закупка скрыта из реестра (см. backend list_purchases). Чип «Желания
       сотрудников» сам по себе ничего не объясняет — прямо говорим, что
       происходит: ждёт одобрения заявки (ещё не в плане) или отцеплена
       обратно в черновик (force_wish_status/принудительный откат). -->
  <v-alert v-if="isEdit && purchaseData?.status === 'wishes' && purchaseData?.wish_id"
    type="warning" variant="tonal" density="compact" class="mb-3">
    {{ wishWithdrawnBannerText }}
  </v-alert>
</template>

<script setup lang="ts">
// Шапка формы закупки (заголовок/статус-чип/SaaS force-status/индикатор
// черновика) + баннеры превышения ФЭО и «создано из заявки». Вынесено из
// CreateOrderView.vue (рефакторинг без изменения поведения, часть 3) —
// form/purchaseData остаются в родителе, сюда приходят пропом; действия,
// требующие вызова родительских функций (forceOrderStatus/clearDraft/
// showSnack/fixFeoMismatchOwnCategories/переход к заявке) — тоже пропами-колбэками.
interface Props {
  form: any
  isEdit: boolean
  purchaseLoaded: boolean
  pageTitle: string
  isSaas: boolean
  purchaseId: number | null
  statusOrder: string[]
  statusLabel: Record<string, string>
  statusColor: Record<string, string>
  forcingOrderStatus: boolean
  substatusOptions: Array<{ value: string; title: string }>
  hasDraft: boolean
  draftSaved: boolean
  backRoute: string
  purchaseData: any
  purchaseExcessText: string
  purchaseExcessStateColor: string
  purchaseExcessStateText: string
  feoMismatchFixableItems: any[]
  fixingFeoMismatch: boolean
  wishWithdrawnBannerText: string
  forceOrderStatus: (s: string) => void
  clearDraft: () => void
  showSnack: (msg: string, type?: any, opts?: any) => void
  fixFeoMismatchOwnCategories: () => void
  goToWish: (wishId: number) => void
}
defineProps<Props>()
</script>

<style scoped>
/* «Заметный сигнал превышения» — по образцу .feo-excess-culprit в SubsidiesView.vue
   (сознательно крупнее и контрастнее .feo-plan-note — задача владельца, сессия
   2026-08-21: «в карточке закупки видно превышение»). Scoped-стиль, дублируется
   как и остальные per-view карточки в этом проекте (не вынесен в общий CSS, т.к.
   применяется только к заголовку карточки закупки). */
.feo-excess-culprit {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  font-size: 13px; font-weight: 700; line-height: 1.4; white-space: normal;
  color: #7f1d1d; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 6px; padding: 6px 10px; max-width: 100%;
}

/* Владелец (2026-09-02): «алярм» расхождения категории ФЭО шапка/товар/план —
   по образцу .purchase-stopped-banner (OrdersView.vue), но предупреждающий
   (амбер), т.к. красный там занят остановкой закупки. Держится, пока
   purchaseData.feo_mismatch=true — не самозакрывающийся снэкбар. */
.feo-mismatch-banner {
  width: 100%;
  border: 2px solid #b45309;
  background: #fffbeb;
  color: #7c2d12;
  border-radius: 6px;
  padding: 10px 14px;
}
.feo-mismatch-banner__head {
  display: flex;
  align-items: center;
}
.feo-mismatch-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
}
.feo-mismatch-banner__hint {
  font-size: 0.8rem;
  font-weight: 500;
  margin-top: 2px;
  opacity: 0.92;
}
.feo-mismatch-banner__list {
  margin: 6px 0 0;
  padding-left: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.feo-mismatch-banner__list li {
  margin-bottom: 2px;
}
</style>
