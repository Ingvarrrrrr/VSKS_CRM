<template>
  <v-table density="comfortable" class="tz-table">
    <thead>
      <tr class="tz-table-header">
        <th style="width:36px;text-align:center">№</th>
        <th style="width:72px;text-align:center">Фото</th>
        <th>Наименование и описание</th>
        <th style="width:90px;text-align:center">Кол-во</th>
        <th style="width:72px;text-align:center">Ед.</th>
      </tr>
    </thead>
    <tbody>
      <tr v-if="!items.length">
        <td colspan="5" class="text-center py-4 text-medium-emphasis">Нет позиций</td>
      </tr>
      <tr v-for="(item, idx) in items" :key="item.id ?? item._uid ?? idx" style="vertical-align:top">
        <td class="text-center text-medium-emphasis pt-3">{{ idx + 1 }}</td>
        <td class="text-center py-2">
          <v-avatar v-if="item._photo_url" size="56" rounded="sm" style="overflow:hidden">
            <img :src="item._photo_url" style="width:56px;height:56px;object-fit:cover;display:block" />
          </v-avatar>
          <v-icon v-else size="40" color="grey-lighten-2">mdi-image-off-outline</v-icon>
        </td>
        <td class="py-2">
          <div class="font-weight-medium mb-1" style="font-size:13px">{{ item.item_name }}</div>
          <WishTzItemRow :item="item" :mode="mode" hide-name-caption @propose="$emit('propose', item)" />
        </td>
        <td class="text-center pt-3">{{ item.quantity ?? '—' }}</td>
        <td class="text-center pt-3">{{ item.unit || '—' }}</td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
// WishTzLocalTable — лист-таблица ТЗ заявки (№, фото+название, описание,
// кол-во, ед. изм.), источник данных — ТОЛЬКО локальные позиции формы
// (props.items, те же объекты, что держит wishForm.items). Владелец,
// 26.10.2026: «до этого показывалось прямо как лист с ТЗ... почему
// переделалось?» — коммит b966b1db заменил такой лист на отдельные крупные
// текстовые блоки (WishTzItemRow.vue) НАД таблицей; эта таблица возвращает
// прежний вид, переиспользуя WishTzItemRow как содержимое ячейки описания
// (hide-name-caption — там же, ПРАВИЛО №6: рендер текста/правки ТЗ не
// дублируется вторым механизмом).
//
// Работает ДО сохранения заявки (wishId ещё нет — строки берём из формы) И
// после (строки те же локальные items, уже имеют id с сервера). Проверка
// дублей ТЗ — отдельно, только после сохранения, через TzRowsSection.vue
// (баннер) в WishTzSection.vue — эта таблица к ней не относится (вынесена
// ради модульности, ПРАВИЛО №5).
import WishTzItemRow from '@/components/wishes/WishTzItemRow.vue'

type EditorItem = any

defineProps<{
  items: EditorItem[]
  mode: 'exact' | '44fz'
}>()

defineEmits<{ propose: [item: EditorItem] }>()
</script>

<style scoped>
/* --crm-table-header — общая theme-aware переменная (App.vue, Правило №6),
   тот же вид, что у TzRowsSection.vue (закупка). */
.tz-table :deep(th) {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.6);
}
.tz-table-header {
  background: var(--crm-table-header);
}
</style>
