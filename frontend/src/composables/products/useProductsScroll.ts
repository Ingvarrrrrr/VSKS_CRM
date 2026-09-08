// useProductsScroll.ts — зеркальная горизонтальная полоса прокрутки над
// таблицей товаров. Дословный перенос из ProductsView.vue.
import { ref } from 'vue'

export function useProductsScroll() {
  const mirrorScrollRef = ref<HTMLElement | null>(null)
  const tableScrollWidth = ref(0)

  function initMirrorScroll() {
    const wrapper = document.querySelector('.products-table .v-table__wrapper') as HTMLElement
    const mirror  = mirrorScrollRef.value
    if (!wrapper || !mirror) return

    const update = () => { tableScrollWidth.value = wrapper.scrollWidth }
    update()

    let syncing = false
    mirror.addEventListener('scroll', () => {
      if (syncing) return; syncing = true
      wrapper.scrollLeft = mirror.scrollLeft
      syncing = false
    })
    wrapper.addEventListener('scroll', () => {
      if (syncing) return; syncing = true
      mirror.scrollLeft = wrapper.scrollLeft
      syncing = false
    })

    new ResizeObserver(update).observe(wrapper)
  }

  return { mirrorScrollRef, tableScrollWidth, initMirrorScroll }
}
