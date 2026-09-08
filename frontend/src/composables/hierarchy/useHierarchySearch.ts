// Поиск по графу: сотрудники / отделы / организации.
// Подсвечивает совпавшие узлы, гасит остальные, цепляет «вьющуюся» стрелку-указатель
// (data.matched → рендерится анимированный pointer в каждом узле) и центрирует вид.
// Вынесено из HierarchyView.vue без изменения логики.
import { ref, type Ref } from 'vue'
import type { Node } from '@vue-flow/core'

export function useHierarchySearch(nodes: Ref<Node[]>, fitView: (opts?: any) => void) {
  const searchQuery = ref('')
  const searchMatchCount = ref(0)

  function applySearch() {
    const q = (searchQuery.value || '').trim().toLowerCase()
    const matchedIds: string[] = []
    for (const n of nodes.value) {
      const d: any = n.data || {}
      let hit = false
      if (q) {
        const hay: string[] = [String(d.label ?? '')]
        if (n.type === 'user') {
          if (d.position) hay.push(String(d.position))
          if (d.deptOrgName) hay.push(String(d.deptOrgName))
          for (const o of (d.userOrgs || [])) {
            if (o.org) hay.push(String(o.org))
            if (o.pos) hay.push(String(o.pos))
            if (o.dept) hay.push(String(o.dept))
          }
        } else if (n.type === 'org') {
          if (d.inn) hay.push(String(d.inn))
        } else if (n.type === 'dept') {
          if (d.orgName) hay.push(String(d.orgName))
        }
        hit = hay.some(s => s.toLowerCase().includes(q))
      }
      d.matched = hit
      n.data = d
      n.class = q ? (hit ? 'hv-node-match' : 'hv-node-dim') : ''
      if (hit) matchedIds.push(n.id)
    }
    searchMatchCount.value = matchedIds.length
    if (matchedIds.length) {
      fitView({ nodes: matchedIds, padding: 0.45, duration: 500, maxZoom: 1.3 })
    }
  }

  return { searchQuery, searchMatchCount, applySearch }
}
