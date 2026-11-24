<template>
  <!-- Режим «по закупкам»: папки по purchase_id без слияния -->
  <template v-for="f in ctx.purchaseFoldersFor(owner)" :key="`pf-${owner.id}-${f.purchase_id}`">
    <tr
      class="feo-tr feo-req-row"
      :class="[ctx.kpiFolderClass(f), feoMarks.feoRowAttrs('purchase', f.purchase_id).class]"
      :style="feoMarks.mergeRowStyle({ background: 'rgba(20,184,166,0.10)' }, 'purchase', f.purchase_id)"
      @contextmenu.prevent="onFolderContextMenu($event, f)"
    >
      <td
        class="feo-td feo-td-name"
        :style="feoMarks.mergeCellStyle({ paddingLeft: ((owner.depth + 1) * 20 + 8) + 'px' }, 'purchase', f.purchase_id, 'name')"
        :class="feoMarks.feoCellAttrs('purchase', f.purchase_id, 'name').class"
        @click="onFolderCellClick($event, f, 'name')"
        @contextmenu.prevent="onFolderContextMenu($event, f, 'name')"
      >
        <div class="feo-name-inner">
          <span class="feo-tree-chevron" style="cursor:pointer" @click.stop="ctx.togglePurchaseFolder(f.purchase_id)">
            <v-icon size="16">{{ ctx.expandedPurchases.value.has(f.purchase_id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
          </span>
          <v-icon size="15" color="#0D9488" class="mr-1">{{ ctx.expandedPurchases.value.has(f.purchase_id) ? 'mdi-folder-open-outline' : 'mdi-folder-outline' }}</v-icon>
          <span>{{ ctx.purchaseFolderTitle(f) }}</span>
          <v-chip size="x-small" variant="tonal" color="blue" class="ml-2" :prepend-icon="purchaseStatusIcon(f.purchase_status)">{{ purchaseStatusLabel(f.purchase_status) }}</v-chip>
          <span v-if="f.purchase_substatus" class="text-caption text-teal-darken-2 font-weight-medium ms-1">({{ purchaseSubstatusLabel(f.purchase_substatus) || f.purchase_substatus }})</span>
          <span class="feo-code ml-2">{{ f.items.length }} поз.</span>
          <a v-if="f.wish_id" href="javascript:void(0)" class="feo-purchase-link ml-2"
            title="Перейти к заявкам"
            @click.stop="ctx.router.push('/wishes')"
          >
            <v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ f.wish_id }}
          </a>
          <!-- Владелец, 2026-08-13: остановка закупки (сейчас всегда скрыт — backend
               ещё не отдаёт stopped_at в этой выборке, см. FeoPurchaseFolder.stopped_at) -->
          <span v-if="f.stopped_at" class="feo-stopped-marker ml-2">
            <v-icon icon="mdi-alert-octagon" size="13" class="mr-1" />ЗАКУПКА ОСТАНОВЛЕНА · {{ ctx.feoStoppedLine(f) }}
          </span>
        </div>
      </td>
      <td
        class="feo-td feo-td-num"
        @click="onFolderCellClick($event, f, 'budget')"
        @contextmenu.prevent="onFolderContextMenu($event, f, 'budget')"
      ><span class="feo-amount-empty">—</span></td>
      <td
        class="feo-td feo-td-num"
        :style="feoMarks.mergeCellStyle({}, 'purchase', f.purchase_id, 'quantity')"
        :class="feoMarks.feoCellAttrs('purchase', f.purchase_id, 'quantity').class"
        @click="onFolderCellClick($event, f, 'quantity')"
        @contextmenu.prevent="onFolderContextMenu($event, f, 'quantity')"
      >
        <span class="feo-amount" style="font-size:12px">{{ f.qty }}{{ f.unit ? ` ${f.unit}` : '' }}</span>
      </td>
      <td
        class="feo-td feo-td-num"
        :style="feoMarks.mergeCellStyle({}, 'purchase', f.purchase_id, 'amount')"
        :class="feoMarks.feoCellAttrs('purchase', f.purchase_id, 'amount').class"
        @click="onFolderCellClick($event, f, 'amount')"
        @contextmenu.prevent="onFolderContextMenu($event, f, 'amount')"
      >
        <span class="feo-amount" style="font-size:12px">{{ formatCurrency(f.total) }}</span>
      </td>
      <td
        class="feo-td feo-td-num"
        @click="onFolderCellClick($event, f, 'spent')"
        @contextmenu.prevent="onFolderContextMenu($event, f, 'spent')"
      ><span class="feo-amount-empty">—</span></td>
      <td
        class="feo-td feo-td-num"
        @click="onFolderCellClick($event, f, 'residual')"
        @contextmenu.prevent="onFolderContextMenu($event, f, 'residual')"
      ><span class="feo-amount-empty">—</span></td>
      <td
        class="feo-td feo-td-actions"
        @contextmenu.prevent="onFolderContextMenu($event, f)"
      >
        <div class="d-flex align-center justify-end">
          <v-btn icon="mdi-cart-outline" variant="text" size="x-small" color="blue"
            title="Открыть закупку"
            @click.stop="ctx.router.push(`/orders/${f.purchase_id}`)" />
        </div>
      </td>
    </tr>
    <template v-if="ctx.expandedPurchases.value.has(f.purchase_id)">
      <tr
        v-for="it in f.items"
        :key="`pfi-${owner.id}-${it.id}`"
        class="feo-tr feo-req-row"
        :class="[ctx.kpiItemRowClass(it), feoMarks.feoRowAttrs(it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id).class]"
        :data-item-id="it.id"
        data-item-group="owner-purchase-folder"
        :style="feoMarks.mergeRowStyle({ background: 'rgba(20,184,166,0.04)' }, it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id)"
        @contextmenu.prevent="onItemContextMenu($event, it, f)"
      >
        <td
          class="feo-td feo-td-name"
          :style="feoMarks.mergeCellStyle({ paddingLeft: ((owner.depth + 2) * 20 + 8) + 'px' }, it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id, 'name')"
          :class="feoMarks.feoCellAttrs(it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id, 'name').class"
          @click="onItemCellClick($event, it, f, 'name')"
          @contextmenu.prevent="onItemContextMenu($event, it, f, 'name')"
        >
          <div class="feo-name-inner">
            <span style="width:16px;display:inline-block" />
            <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-file-document-outline" color="#22C55E" />
            <v-avatar v-if="it.product_photo" size="28" rounded class="mr-1 flex-shrink-0" style="cursor:pointer"
              @click.stop="ctx.photoPreview.value = { src: it.product_photo!, title: it.item_name }">
              <v-img :src="it.product_photo" cover />
            </v-avatar>
            <v-icon :icon="purchaseStatusIcon(it.purchase_status)" :color="purchaseStatusColor(it.purchase_status)" size="14" class="mr-1" :title="it.purchase_substatus ? `${purchaseStatusLabel(it.purchase_status)} (${purchaseSubstatusLabel(it.purchase_substatus)})` : purchaseStatusLabel(it.purchase_status)" />
            <span class="feo-name feo-name--l3">{{ it.item_name }}</span>
            <span v-if="it.purchase_substatus" class="text-caption text-teal-darken-2 font-weight-medium ms-1">({{ purchaseSubstatusLabel(it.purchase_substatus) || it.purchase_substatus }})</span>
          </div>
        </td>
        <td
          class="feo-td feo-td-num"
          @click="onItemCellClick($event, it, f, 'budget')"
          @contextmenu.prevent="onItemContextMenu($event, it, f, 'budget')"
        ><span class="feo-amount-empty">—</span></td>
        <td
          class="feo-td feo-td-num"
          :style="feoMarks.mergeCellStyle({}, it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id, 'quantity')"
          :class="feoMarks.feoCellAttrs(it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id, 'quantity').class"
          @click="onItemCellClick($event, it, f, 'quantity')"
          @contextmenu.prevent="onItemContextMenu($event, it, f, 'quantity')"
        >
          <span class="feo-amount" style="font-size:12px">{{ it.quantity }}{{ it.unit ? ` ${it.unit}` : '' }}</span>
        </td>
        <td
          class="feo-td feo-td-num"
          :style="feoMarks.mergeCellStyle({}, it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id, 'amount')"
          :class="feoMarks.feoCellAttrs(it.wish_id ? 'wish' : 'purchase', it.wish_id || f.purchase_id || it.id, 'amount').class"
          @click="onItemCellClick($event, it, f, 'amount')"
          @contextmenu.prevent="onItemContextMenu($event, it, f, 'amount')"
        >
          <span class="feo-amount" style="font-size:12px">{{ formatCurrency(it.total_price) }}</span>
          <div v-if="it.unit_price" class="feo-plan-note text-medium-emphasis">{{ formatCurrency(it.unit_price) }}/ед.</div>
        </td>
        <td
          class="feo-td feo-td-num"
          @click="onItemCellClick($event, it, f, 'spent')"
          @contextmenu.prevent="onItemContextMenu($event, it, f, 'spent')"
        ><span class="feo-amount-empty">—</span></td>
        <td
          class="feo-td feo-td-num"
          @click="onItemCellClick($event, it, f, 'residual')"
          @contextmenu.prevent="onItemContextMenu($event, it, f, 'residual')"
        ><span class="feo-amount-empty">—</span></td>
        <td
          class="feo-td feo-td-actions"
          @contextmenu.prevent="onItemContextMenu($event, it, f)"
        >
          <div class="d-flex align-center justify-end">
            <a v-if="it.wish_id" href="javascript:void(0)" class="feo-purchase-link"
              title="Изменить можно только в заявке"
              @click.stop="ctx.router.push({ path: '/wishes', query: { open: String(it.wish_id) } })"
            ><v-icon icon="mdi-hand-heart-outline" size="11" class="mr-1" />заявка #{{ it.wish_id }}</a>
            <v-btn v-if="it.wish_id" icon="mdi-swap-horizontal" size="x-small" variant="text" color="teal"
              title="Сменить категорию ФЭО позиции"
              @click.stop="ctx.openWishItemFeoEdit(owner, it)" />
            <template v-if="!it.wish_id">
              <v-btn icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
                title="Редактировать позицию закупки"
                @click="ctx.openReqItemEdit(owner, it)" />
              <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                title="Удалить позицию из закупки"
                @click="ctx.confirmReqItemDelete(owner, it)" />
            </template>
          </div>
        </td>
      </tr>
    </template>
  </template>
</template>

<script setup lang="ts">
// Позиции «из заявок» в режиме «по закупкам» — папки по purchase_id без
// слияния по имени. Вынесены из SubsidiesView.vue (волна 5c); соседний
// компонент FeoReqItemsRows.vue — режим слияния/группировки. Формулы —
// composables/subsidies/useFeoReqItems.ts (Правило №6).
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import { purchaseStatusIcon, purchaseStatusColor, purchaseStatusLabel, purchaseSubstatusLabel } from '@/constants/purchaseStatus'
import type { FeoNode } from '@/composables/subsidies/types'
import { useFeoMarksContext } from '@/composables/subsidies/useFeoMarksContext'

const props = defineProps<{ owner: FeoNode }>()
const owner = props.owner

const ctx = useSubsidyDetailCtx()
const feoMarks = useFeoMarksContext()

function onFolderContextMenu(e: MouseEvent, f: any, fieldName = '*') {
  feoMarks.onFeoCellContextMenu(e, {
    entityType: 'purchase',
    entityId: f.purchase_id,
    fieldName,
    fieldLabel: fieldName === 'amount' ? 'Сумма' : (fieldName === 'quantity' ? 'Количество' : 'Закупка'),
    cellValue: fieldName === 'amount' ? formatCurrency(f.total) : (fieldName === 'quantity' ? f.qty : ctx.purchaseFolderTitle(f)),
    rawNumber: fieldName === 'amount' ? f.total : (fieldName === 'quantity' ? f.qty : undefined),
    subsidyId: ctx.selectedId.value,
    extraItems: [
      {
        key: 'open_order',
        label: `🛒 Открыть закупку #${f.purchase_id}`,
        icon: 'mdi-cart',
        onClick: () => {
          ctx.router.push(`/orders/${f.purchase_id}`)
        },
      },
    ],
  })
}

function onFolderCellClick(e: MouseEvent, f: any, fieldName: string) {
  feoMarks.onFeoCellClick(e, {
    entityType: 'purchase',
    entityId: f.purchase_id,
    fieldName,
    subsidyId: ctx.selectedId.value,
  })
}

function onItemContextMenu(e: MouseEvent, it: any, f: any, fieldName = '*') {
  const isWish = !!it.wish_id
  const entityType = isWish ? 'wish' : 'purchase'
  const entityId = isWish ? it.wish_id : (f.purchase_id || it.id)

  feoMarks.onFeoCellContextMenu(e, {
    entityType,
    entityId,
    fieldName,
    fieldLabel: fieldName === 'amount' ? 'Сумма' : (fieldName === 'quantity' ? 'Количество' : it.item_name),
    cellValue: fieldName === 'amount' ? formatCurrency(it.total_price) : (fieldName === 'quantity' ? it.quantity : it.item_name),
    rawNumber: fieldName === 'amount' ? it.total_price : (fieldName === 'quantity' ? it.quantity : undefined),
    subsidyId: ctx.selectedId.value,
    extraItems: [
      {
        key: 'open_order',
        label: `🛒 Открыть закупку #${f.purchase_id}`,
        icon: 'mdi-cart',
        onClick: () => {
          ctx.router.push(`/orders/${f.purchase_id}`)
        },
      },
      ...(it.wish_id
        ? [
            {
              key: 'open_wish',
              label: `📋 Открыть заявку #${it.wish_id}`,
              icon: 'mdi-hand-heart-outline',
              onClick: () => {
                ctx.router.push({ path: '/wishes', query: { open: String(it.wish_id) } })
              },
            },
          ]
        : []),
    ],
  })
}

function onItemCellClick(e: MouseEvent, it: any, f: any, fieldName: string) {
  const isWish = !!it.wish_id
  const entityType = isWish ? 'wish' : 'purchase'
  const entityId = isWish ? it.wish_id : (f.purchase_id || it.id)

  feoMarks.onFeoCellClick(e, {
    entityType,
    entityId,
    fieldName,
    subsidyId: ctx.selectedId.value,
  })
}
</script>
