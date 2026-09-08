// StaffDeptTreeNode.ts — рекурсивный узел дерева отделов (render-function
// компонент). Дословный перенос DeptNode из StaffView.vue: без изменений
// логики, только вынесен в отдельный файл и параметризован цветовыми
// хелперами организации (были closures на orgColor/orgCssColor).
import { defineComponent, h, ref, resolveComponent } from 'vue'

export function createStaffDeptTreeNode(
  orgColor: (orgId: number | null | undefined) => string,
  orgCssColor: (orgId: number | null | undefined, alpha?: number) => string,
) {
  const StaffDeptTreeNode: any = defineComponent({
    name: 'StaffDeptTreeNode',
    props: { node: Object, depth: { type: Number, default: 0 }, multiOrg: { type: Boolean, default: false } },
    emits: ['select', 'edit', 'delete', 'add-member', 'edit-member', 'remove-member'],
    setup(props: any, { emit }: any) {
      const expanded = ref(true)
      return () => {
        const n = props.node
        const indent = props.depth * 24
        const VIcon = resolveComponent('v-icon') as any
        const VBtn = resolveComponent('v-btn') as any
        const VChip = resolveComponent('v-chip') as any
        const VSpacer = resolveComponent('v-spacer') as any
        const color = orgColor(n.org_id)
        const borderL = orgCssColor(n.org_id)
        const borderEdge = orgCssColor(n.org_id, 0.25)

        const items = [
          h('div', {
            class: 'dept-tree-row', style: { paddingLeft: indent + 'px', borderLeftColor: borderL, borderColor: borderEdge },
            onClick: () => emit('select', n),
          }, [
            n.children?.length
              ? h(VIcon, {
                  icon: expanded.value ? 'mdi-chevron-down' : 'mdi-chevron-right',
                  size: 18, class: 'mr-1 dept-chevron',
                  onClick: (e: Event) => { e.stopPropagation(); expanded.value = !expanded.value },
                })
              : h('span', { style: 'width:22px;display:inline-block' }),
            h(VIcon, { icon: 'mdi-folder-account', size: 18, color, class: 'mr-2' }),
            h('span', { class: 'font-weight-medium text-body-2' }, n.name),
            props.multiOrg && n.org_name
              ? h(VChip, { size: 'x-small', variant: 'tonal', color, class: 'ml-2' }, () => n.org_name)
              : null,
            n.head_user_name
              ? h(VChip, { size: 'x-small', variant: 'tonal', color: 'teal', class: 'ml-2' }, () => n.head_user_name)
              : null,
            h(VChip, { size: 'x-small', variant: 'outlined', class: 'ml-1' }, () => `${n.members?.length || 0} чел.`),
            h(VSpacer),
            h(VBtn, { icon: 'mdi-account-plus', size: 'x-small', variant: 'text', color: 'success', title: 'Добавить сотрудника', onClick: (e: Event) => { e.stopPropagation(); emit('add-member', n) } }),
            h(VBtn, { icon: 'mdi-pencil', size: 'x-small', variant: 'text', color: 'grey', title: 'Редактировать отдел', onClick: (e: Event) => { e.stopPropagation(); emit('edit', n) } }),
            h(VBtn, { icon: 'mdi-delete', size: 'x-small', variant: 'text', color: 'error', title: 'Удалить отдел', onClick: (e: Event) => { e.stopPropagation(); emit('delete', n) } }),
            h(VIcon, { icon: 'mdi-chevron-right', size: 20, class: 'ml-1 dept-row-arrow', color: 'primary' }),
          ]),
          // Members inline with edit/remove buttons
          ...(expanded.value ? (n.members || []).map((m: any) =>
            h('div', { class: 'dept-member-row', style: { paddingLeft: (indent + 28) + 'px' } }, [
              h(VIcon, { icon: m.user_id === n.head_user_id ? 'mdi-crown' : 'mdi-account', size: 14, color: m.user_id === n.head_user_id ? 'teal' : 'grey', class: 'mr-2' }),
              h('span', { class: 'text-body-2' }, m.name),
              m.position
                ? h('span', { class: 'text-caption text-medium-emphasis ml-2' }, `(${m.position})`)
                : h('span', { class: 'text-caption text-medium-emphasis ml-2', style: 'cursor:pointer;text-decoration:underline dotted;opacity:0.5', onClick: (e: Event) => { e.stopPropagation(); emit('edit-member', { dept: n, member: m }) } }, '+ должность'),
              h(VSpacer),
              h(VBtn, { icon: 'mdi-pencil', size: 'x-small', variant: 'text', color: 'primary', class: 'dept-member-action', title: 'Редактировать сотрудника', onClick: (e: Event) => { e.stopPropagation(); emit('edit-member', { dept: n, member: m, fullEdit: true }) } }),
              h(VBtn, { icon: 'mdi-close', size: 'x-small', variant: 'text', color: 'error', class: 'dept-member-action', title: 'Убрать из отдела', onClick: (e: Event) => { e.stopPropagation(); emit('remove-member', { deptId: n.id, userId: m.user_id }) } }),
            ])
          ) : []),
          // Children
          ...(expanded.value ? (n.children || []).map((child: any) =>
            h(StaffDeptTreeNode, {
              node: child, depth: props.depth + 1, multiOrg: props.multiOrg,
              onSelect: (v: any) => emit('select', v),
              onEdit: (v: any) => emit('edit', v),
              onDelete: (v: any) => emit('delete', v),
              onAddMember: (v: any) => emit('add-member', v),
              onEditMember: (v: any) => emit('edit-member', v),
              onRemoveMember: (v: any) => emit('remove-member', v),
            })
          ) : []),
        ]
        return h('div', items)
      }
    },
  })
  return StaffDeptTreeNode
}
