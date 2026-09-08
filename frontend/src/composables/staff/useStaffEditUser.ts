// useStaffEditUser.ts — диалог редактирования сотрудника: сам editDialog,
// членства в организациях/отделах (allOrgEntries), оклад, водительские данные,
// фото, синхронизация с контрагентом. Дословный перенос из StaffView.vue.
import { ref, reactive, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import { unformatPhone } from '@/utils/phoneFormat'
import type { ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import type { UserItem, OrgEntry } from './staffTypes'

export function useStaffEditUser(options: {
  users: { value: UserItem[] }
  organizations: { value: any[] }
  deptTree: { value: any[] }
  flatDepts: (nodes: any[]) => any[]
  showSnack: (text: string, color?: ToastType) => void
  loadDeptTree: () => Promise<void>
  loadHierarchyTree: () => Promise<void>
  refreshHierarchy: () => void
  loadDicts: (orgId?: number | null) => Promise<void>
}) {
  const { users, organizations, deptTree, flatDepts, showSnack, loadDeptTree, loadHierarchyTree, refreshHierarchy, loadDicts } = options

  const canChangePassword = computed(() => ['superadmin', 'account_owner'].includes(localStorage.getItem('user_role') || ''))

  const editDialog = reactive({
    show: false, userId: 0, username: '', full_name: '', last_name: '', first_name: '', middle_name: '', role: 'employee', city: '',
    department: '', position: '', phone: '', work_phone: '', email: '', password: '', avatar: '', saving: false, inn: '',
    telegram_id: '', max_chat_id: '',
    profile_photo: '',
    exclude_from_directory: false,
    all_orgs_access: false,
    superior_user_id: null as number | null,
    org_id: null as number | null,
    extraOrgIds: [] as number[],
    extraOrgsLoaded: false,
    extraOrgsLoading: false,
    orgPositions: {} as Record<number, string>,  // position per extra org
    orgSalary: {} as Record<number, number | null>,
    orgPercent: {} as Record<number, number | null>,
    orgDepts: {} as Record<number, string>,
    // Dept handled via ID (not text) — single source of truth via DepartmentMember table
    deptId: null as number | null,
    origDeptId: null as number | null,
    origPosition: '',
    // Diagnostic: departments where this user is head (head_user_id)
    headedDepts: [] as { id: number; name: string; org_name?: string }[],
    // 29-15: водительские данные
    can_drive: false,
    license_series: '',
    license_number: '',
    license_categories: '',
    license_issued_at: null as string | null,
    license_expires_at: null as string | null,
    medical_cert_expires_at: null as string | null,
    // 29.3: доп. документы водителя
    tachograph_card_expires_at: null as string | null,
    periodic_medical_expires_at: null as string | null,
    psych_cert_expires_at: null as string | null,
    // 30.3: скан ВУ
    license_scan: '',
  }) as any

  // All org entries from salary API (one per dept membership)
  const allOrgEntries = ref<OrgEntry[]>([])
  // Pre-load dicts whenever allOrgEntries changes (new orgs may appear in editDialog)
  watch(
    () => allOrgEntries.value.map(e => e.org_id),
    (orgIds) => { for (const id of orgIds) if (id) loadDicts(id) },
    { deep: true },
  )

  // Фикс: дедуп по org_id — при multi-dept (напр. Цыганов с 4 отделами в ВСКС) не дублируем орг в селекте Доступа
  // Используем Number() чтобы избежать несовпадения number vs string при Map.has()
  // Фикс-2: записи с id===null — несохранённые членства (optimistic push из watch extraOrgIds).
  // Их НЕ включаем в список для секции допусков: PUT overrides вернёт 404 до реального сохранения.
  // Владелец, 2026-09-01: имя резолвим по общему каталогу организаций (`organizations`,
  // GET /organizations/ — полный список, не урезанный assignable-скоуп редактора), а не
  // доверяем e.org_name «как есть» (мог не прийти из salary-эндпоинта). Если имени нет
  // НИГДЕ (организация недоступна) — пункт пропускаем, а не рисуем номер.
  function dedupOrgAccess(entries: typeof allOrgEntries.value) {
    const map = new Map<number, { org_id: number; org_name: string; role: string }>()
    for (const e of entries) {
      if (e.id === null) continue  // несохранённая org — допуски настраивать рано
      const key = Number(e.org_id)
      if (map.has(key)) continue
      const name = organizations.value.find((o: any) => o.id === key)?.name || e.org_name || ''
      if (!name) continue  // организация без резолвимого имени — не показываем
      map.set(key, { org_id: key, org_name: name, role: editDialog.role })
    }
    return Array.from(map.values())
  }

  // Группировка allOrgEntries по org_id — для отображения нескольких отделов одной организации.
  // «Дата трудоустройства» — общая на организацию (владелец, 2026-09-01): берём её один раз из
  // первой строки группы, а не показываем/редактируем на каждой dept-строке отдельно.
  const groupedOrgEntries = computed(() => {
    const groups: Record<number, typeof allOrgEntries.value> = {}
    for (const e of allOrgEntries.value) {
      const key = Number(e.org_id)
      if (!groups[key]) groups[key] = []
      groups[key].push(e)
    }
    return Object.entries(groups).map(([org_id, entries]) => ({
      org_id: Number(org_id),
      org_name: entries[0]?.org_name || '',
      hired_at: entries.find(e => e.hired_at)?.hired_at || null,
      entries,
    }))
  })

  // Правка общей на организацию «Даты трудоустройства» — уходит на ВСЕ строки этой организации
  // (бэкенд PATCH /users/{uid}/org-memberships/{id} тоже распространяет hired_at на всю пару
  // (user, org), это дублирующее локальное обновление — чтобы поле в UI сразу показывало новое
  // значение на всех dept-строках без перезагрузки).
  function setOrgHiredAt(org_id: number, value: string | null) {
    for (const e of allOrgEntries.value) {
      if (Number(e.org_id) === Number(org_id)) e.hired_at = value || null
    }
  }

  // Список отделов для данной org (из deptTree, уже загруженного)
  function deptsForOrg(org_id: number) {
    return flatDepts(deptTree.value)
      .filter((d: any) => d.org_id === org_id)
      .map((d: any) => ({ title: d.name, value: d.id }))
  }

  // Кнопка «+ ещё отдел в этой организации»: добавляет новую строку is_new=true
  function addDeptToOrg(org_id: number) {
    const org_name = allOrgEntries.value.find(e => e.org_id === org_id)?.org_name || ''
    const sharedHiredAt = allOrgEntries.value.find(e => e.org_id === org_id && e.hired_at)?.hired_at || null
    allOrgEntries.value.push({
      id: null,
      dept_id: null,
      org_id,
      org_name,
      dept_name: '',
      position: '',
      salary_amount: null,
      employment_percent: 100,
      hired_at: sharedHiredAt,
      dept_assigned_at: null,
      position_assigned_at: null,
      _idx: allOrgEntries.value.length,
      is_new: true,
    } as any)
  }

  // Фикс: при добавлении новой org через extraOrgIds — optimistic-push в allOrgEntries
  // чтобы UserPermissionsSection сразу видела её (до сохранения и reload)
  watch(
    () => editDialog.extraOrgIds,
    (newIds: number[], oldIds: number[]) => {
      if (!editDialog.userId) return
      const added = (newIds || []).filter(id => !(oldIds || []).includes(id))
      for (const orgId of added) {
        if (!allOrgEntries.value.some(e => e.org_id === orgId)) {
          const org = organizations.value.find((o: any) => o.id === orgId)
          allOrgEntries.value.push({
            id: null,
            dept_id: null,
            org_id: orgId,
            org_name: org?.name || '',
            dept_name: '',
            position: '',
            salary_amount: null,
            employment_percent: 100,
            hired_at: null,
            dept_assigned_at: null,
            position_assigned_at: null,
            _idx: allOrgEntries.value.length,
          })
        }
      }
    },
    { deep: false },
  )

  // Фото профиля и скан ВУ — чисто UI-состояние диалога (input[type=file],
  // компонент ProfilePhotoUpload); их ref/обработчики живут в самом
  // StaffEditUserDialog.vue и мутируют editDialog напрямую (та же ссылка).

  async function syncToContractor(userId: number) {
    try {
      const result = await apiFetch<{ ok: boolean; action: string; contractor_id: number }>(
        `/users/${userId}/sync-contractor`, { method: 'POST' }
      )
      showSnack(result.action === 'created' ? 'Контрагент создан' : 'Контрагент обновлён')
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка синхронизации', 'error')
    }
  }

  async function openEditUser(item: UserItem) {
    editDialog.userId = item.id
    editDialog.org_id = item.org_id ?? null
    editDialog.username = item.username
    editDialog.full_name = item.full_name || ''
    editDialog.last_name = item.last_name || ''
    editDialog.first_name = item.first_name || ''
    editDialog.middle_name = item.middle_name || ''
    editDialog.role = item.role
    editDialog.city = item.city || ''
    editDialog.department = item.department || ''
    editDialog.position = item.position || ''
    editDialog.origPosition = item.position || ''
    editDialog.email = item.email || ''
    editDialog.password = ''
    editDialog.avatar = item.avatar || ''
    editDialog.inn = item.inn || ''
    editDialog.phone = (item as any).phone || ''
    editDialog.work_phone = (item as any).work_phone || ''
    editDialog.telegram_id = (item as any).telegram_id || ''
    editDialog.max_chat_id = (item as any).max_chat_id || ''
    editDialog.exclude_from_directory = !!(item as any).exclude_from_directory
    editDialog.all_orgs_access = !!(item as any).all_orgs_access
    editDialog.superior_user_id = (item as any).superior_user_id ?? null
    // 29-15: водительские данные
    editDialog.can_drive = !!(item as any).can_drive
    editDialog.license_series = (item as any).license_series || ''
    editDialog.license_number = (item as any).license_number || ''
    editDialog.license_categories = (item as any).license_categories || ''
    editDialog.license_issued_at = (item as any).license_issued_at || null
    editDialog.license_expires_at = (item as any).license_expires_at || null
    editDialog.medical_cert_expires_at = (item as any).medical_cert_expires_at || null
    editDialog.tachograph_card_expires_at = (item as any).tachograph_card_expires_at || null
    editDialog.periodic_medical_expires_at = (item as any).periodic_medical_expires_at || null
    editDialog.psych_cert_expires_at = (item as any).psych_cert_expires_at || null
    editDialog.extraOrgIds = []
    editDialog.extraOrgsLoaded = false
    // Resolve dept ID from deptTree by matching name
    const allDepts = flatDepts(deptTree.value)
    const foundDept = allDepts.find((d: any) => d.name === item.department)
    editDialog.deptId = foundDept?.id ?? null
    editDialog.origDeptId = editDialog.deptId
    editDialog.show = true

    // Load extra orgs & all orgs lazily
    if (organizations.value.length === 0) {
      apiFetch<any[]>('/organizations/').then(r => { organizations.value = r }).catch(() => {})
    }
    editDialog.extraOrgsLoading = true
    editDialog.orgPositions = {}
    editDialog.orgSalary = {}
    editDialog.orgPercent = {}
    try {
      const [orgRes, salaryRes] = await Promise.all([
        apiFetch<{ primary: any; extra: any[] }>(`/users/${item.id}/organizations`),
        apiFetch<any[]>(`/users/${item.id}/salary`).catch(() => []),
      ])
      // Dedupe: одна организация = один chip, даже если юзер в нескольких отделах
      // одной org (фидбек Филиппов 01.06 — раньше показывался АНО ЦЕНТРПОИСК × 2).
      editDialog.extraOrgIds = [...new Set([
        ...(orgRes.primary?.id ? [orgRes.primary.id] : []),
        ...orgRes.extra.map((e: any) => e.id),
      ])]
      editDialog.extraOrgsLoaded = true
      const pos: Record<number, string> = {}
      for (const e of orgRes.extra) {
        if (e.position) pos[e.id] = e.position
      }
      editDialog.orgPositions = pos
      // Fill salary
      const sal: Record<number, number | null> = {}
      const pct: Record<number, number | null> = {}
      for (const s of (salaryRes || [])) {
        sal[s.org_id] = s.salary_amount
        pct[s.org_id] = s.employment_percent
      }
      editDialog.orgSalary = sal
      editDialog.orgPercent = pct
      // Fill all org entries — one row per dept membership (multi-dept fully visible)
      allOrgEntries.value = (salaryRes || []).map((s: any, i: number) => ({
        id: s.id ?? null, dept_id: s.dept_id ?? null,
        org_id: Number(s.org_id), org_name: s.org_name || '', dept_name: s.dept_name || '',
        position: s.position || '', salary_amount: s.salary_amount, employment_percent: s.employment_percent, hired_at: s.hired_at ? String(s.hired_at).slice(0, 10) : null,
        dept_assigned_at: s.dept_assigned_at ? String(s.dept_assigned_at).slice(0, 10) : null,
        position_assigned_at: s.position_assigned_at ? String(s.position_assigned_at).slice(0, 10) : null, _idx: i,
      }))
      editDialog.orgDepts = {}
      for (const s of (salaryRes || [])) {
        if (s.dept_name) editDialog.orgDepts[s.org_id] = s.dept_name
      }
    } catch { /* ignore */ } finally {
      editDialog.extraOrgsLoading = false
    }

    // Load photo best-effort
    editDialog.profile_photo = ''
    try {
      const photoRes = await apiFetch<{ photo_url: string | null }>(`/users/${item.id}/photo`)
      editDialog.profile_photo = photoRes.photo_url || ''
    } catch { /* ignore */ }

    // Phase 30.3: Load license scan best-effort (if driver)
    editDialog.license_scan = ''
    if (editDialog.can_drive) {
      try {
        const lic = await apiFetch<{ license_scan: string | null }>(`/users/${item.id}/license-scan`)
        editDialog.license_scan = lic.license_scan || ''
      } catch { /* ignore */ }
    }

    // Diagnostic: departments this user heads (head_user_id), for visibility audit.
    // Also loads managed-orgs from hierarchy endpoint if available.
    editDialog.headedDepts = []
    editDialog.headedOrgs = []
    try {
      const allDepts = flatDepts(deptTree.value)
      editDialog.headedDepts = allDepts
        .filter((d: any) => d.head_user_id === item.id)
        .map((d: any) => ({
          id: d.id,
          name: d.name,
          org_name: (organizations.value.find((o: any) => o.id === d.org_id) as any)?.name,
        }))
    } catch { /* ignore */ }
  }

  async function openEditUserById(userId: number) {
    let user = users.value.find(u => u.id === userId)
    if (!user) {
      try { user = await apiFetch<UserItem>(`/users/${userId}`) } catch { return }
    }
    openEditUser(user)
  }

  async function confirmDeleteOrgEntry(entry: any) {
    if (!editDialog.userId || !entry.id) return
    if (!confirm(`Удалить «${entry.org_name}${entry.dept_name ? ' · ' + entry.dept_name : ''}» из карточки?\nКарточка пропадёт из этого отдела на канвасе иерархии.`)) return
    try {
      await apiFetch(`/users/${editDialog.userId}/org-memberships/${entry.id}`, { method: 'DELETE' })
      showSnack('Запись удалена')
      // Reload allOrgEntries (все dept-строки без дедупа)
      const salaryRes = await apiFetch<any[]>(`/users/${editDialog.userId}/salary`).catch(() => [])
      allOrgEntries.value = (salaryRes || []).map((s: any, i: number) => ({
        id: s.id ?? null, dept_id: s.dept_id ?? null,
        org_id: Number(s.org_id), org_name: s.org_name || '', dept_name: s.dept_name || '',
        position: s.position || '', salary_amount: s.salary_amount, employment_percent: s.employment_percent, hired_at: s.hired_at ? String(s.hired_at).slice(0, 10) : null,
        dept_assigned_at: s.dept_assigned_at ? String(s.dept_assigned_at).slice(0, 10) : null,
        position_assigned_at: s.position_assigned_at ? String(s.position_assigned_at).slice(0, 10) : null, _idx: i,
      }))
      // Also update extraOrgIds list to drop this org if no entries left
      if (!allOrgEntries.value.some(e => e.org_id === entry.org_id)) {
        editDialog.extraOrgIds = (editDialog.extraOrgIds || []).filter((id: number) => id !== entry.org_id)
      }
    } catch (e: any) {
      showSnack('Не удалось удалить: ' + (e?.payload?.detail || e?.payload?.message || e?.message || ''), 'error')
    }
  }

  async function saveEditUser() {
    editDialog.saving = true
    try {
      // Sync User.position (primary field) with per-org position of primary org before PATCH
      const primaryEntryForBody = allOrgEntries.value.find(e => e.org_id === editDialog.org_id)
      if (primaryEntryForBody && primaryEntryForBody.position !== undefined) {
        editDialog.position = primaryEntryForBody.position || ''
      }

      // PATCH user fields (NOT department text — managed via DepartmentMember API below)
      const body: any = {
        last_name: editDialog.last_name || null,
        first_name: editDialog.first_name || null,
        middle_name: editDialog.middle_name || null,
        role: editDialog.role,
        city: editDialog.city || null,
        position: editDialog.position || null,
        email: editDialog.email || null,
        avatar: editDialog.avatar || null,
        inn: editDialog.inn || null,
        phone: unformatPhone(editDialog.phone) || null,
        work_phone: unformatPhone(editDialog.work_phone) || null,
        telegram_id: editDialog.telegram_id || null,
        max_chat_id: editDialog.max_chat_id || null,
        exclude_from_directory: editDialog.exclude_from_directory,
        all_orgs_access: editDialog.all_orgs_access,
        superior_user_id: editDialog.superior_user_id,
        // 29-15: водительские данные
        can_drive: editDialog.can_drive,
        license_series: editDialog.can_drive ? (editDialog.license_series || null) : null,
        license_number: editDialog.can_drive ? (editDialog.license_number || null) : null,
        license_categories: editDialog.can_drive ? (editDialog.license_categories || null) : null,
        license_issued_at: editDialog.can_drive ? (editDialog.license_issued_at || null) : null,
        license_expires_at: editDialog.can_drive ? (editDialog.license_expires_at || null) : null,
        medical_cert_expires_at: editDialog.can_drive ? (editDialog.medical_cert_expires_at || null) : null,
        tachograph_card_expires_at: editDialog.can_drive ? (editDialog.tachograph_card_expires_at || null) : null,
        periodic_medical_expires_at: editDialog.can_drive ? (editDialog.periodic_medical_expires_at || null) : null,
        psych_cert_expires_at: editDialog.can_drive ? (editDialog.psych_cert_expires_at || null) : null,
      }
      if (editDialog.password) body.password = editDialog.password
      const updated = await apiFetch<UserItem>(`/users/${editDialog.userId}`, {
        method: 'PATCH', body: JSON.stringify(body),
      })

      // Phase 30.3: separate save/delete for license_scan (Text blob, не в основном PATCH)
      if (editDialog.can_drive && editDialog.license_scan && editDialog.license_scan.startsWith('data:image/')) {
        try {
          await apiFetch(`/users/${editDialog.userId}/license-scan`, {
            method: 'PUT', body: JSON.stringify({ license_scan: editDialog.license_scan }),
          })
        } catch (e) { console.warn('[staff] license-scan save failed', e) }
      } else if (!editDialog.license_scan || !editDialog.can_drive) {
        try {
          await apiFetch(`/users/${editDialog.userId}/license-scan`, { method: 'DELETE' })
        } catch { /* ignore */ }
      }

      // Sync department membership (single source of truth — DepartmentMember table)
      const deptChanged = editDialog.deptId !== editDialog.origDeptId
      if (deptChanged) {
        if (editDialog.deptId) {
          // Add to new dept — backend auto-removes from old depts (exclusive)
          await apiFetch(`/departments/${editDialog.deptId}/members`, {
            method: 'POST',
            body: { user_id: editDialog.userId, position: editDialog.position || undefined },
          })
        } else if (editDialog.origDeptId) {
          // Cleared dept — remove from old dept
          await apiFetch(`/departments/${editDialog.origDeptId}/members/${editDialog.userId}`, {
            method: 'DELETE',
          })
        }
      }
      // Note: if only position changed (same dept), PATCH /users above already syncs
      // DepartmentMember.position via _sync_user_department — no extra call needed.

      // Save new dept entries added via «+ ещё отдел в этой организации» button
      // POST /departments/{dept_id}/members creates both DepartmentMember and UserOrganization row
      for (const entry of allOrgEntries.value) {
        if ((entry as any).is_new && entry.dept_id) {
          try {
            await apiFetch(`/departments/${entry.dept_id}/members`, {
              method: 'POST',
              body: {
                user_id: editDialog.userId,
                position: entry.position || undefined,
                dept_assigned_at: entry.dept_assigned_at || undefined,
              },
            })
            // Salary/percent on the new UO row will be synced by the org-membership PATCH loop below
          } catch (e: any) {
            showSnack(`Не удалось добавить отдел: ${e?.payload?.detail || e?.payload?.message || e?.message || ''}`, 'error')
          }
        }
      }

      // 7a: Sync per-row (per dept) position/salary/percent — NOT bulk-by-org
      // Each allOrgEntries row has its own id (user_organizations PK), save individually.
      // hired_at распространяется бэкендом на ВСЕ строки пары (user, org) — достаточно
      // отправлять его с любой строкой этой org, отправляем с каждой (идемпотентно).
      for (const entry of allOrgEntries.value) {
        if ((entry as any).is_new) continue // new rows already handled above
        if (entry.id) {
          try {
            // dept_assigned_at/position_assigned_at отправляем ТОЛЬКО если поле
            // реально заполнено (руками поправлено или подтянуто с бэка). Пустое
            // поле не шлём явным null — иначе бэкенд теряет возможность сам
            // проставить дату при смене должности (owner: «по умолчанию пусть
            // меняется... а не перебивать каждый раз руками»); см.
            // patch_user_org_membership_row / org_assignment_dates.py.
            // salary_amount/employment_percent — v-model.number; `?? null` не ловит ''
            // после очистки поля. Роутер пишет body[key] напрямую в Numeric/Integer-колонку
            // без Pydantic-типизации (body: dict) — '' там не 422, а падение на commit.
            // numOrNull — единый хелпер (2026-09-04).
            const patchBody: Record<string, unknown> = {
              position: entry.position || null,
              salary_amount: numOrNull(entry.salary_amount),
              employment_percent: numOrNull(entry.employment_percent),
              hired_at: entry.hired_at || null,
            }
            if (entry.dept_assigned_at) patchBody.dept_assigned_at = entry.dept_assigned_at
            if (entry.position_assigned_at) patchBody.position_assigned_at = entry.position_assigned_at
            await apiFetch(`/users/${editDialog.userId}/org-memberships/${entry.id}`, {
              method: 'PATCH',
              body: patchBody,
            })
          } catch (e: any) {
            showSnack(`Не удалось сохранить членство: ${e?.payload?.detail || e?.payload?.message || e?.message || ''}`, 'error')
          }
        }
      }

      // Sync org list membership (add/remove orgs) — position/salary handled above per-row
      // Guard: skip entirely if orgs were not loaded (prevents wiping memberships on load failure)
      if (editDialog.extraOrgsLoaded) {
        try {
          const res = await apiFetch<{ primary: any; extra: any[] }>(`/users/${editDialog.userId}/organizations`)
          const currentOrgMap = new Map<number, any>()
          if (res.primary?.id) currentOrgMap.set(res.primary.id, res.primary)
          for (const e of res.extra) currentOrgMap.set(e.id, e)

          const desiredIds = new Set(editDialog.extraOrgIds)

          // Add org membership if not present yet
          for (const oid of desiredIds) {
            if (!currentOrgMap.has(oid)) {
              try {
                await apiFetch(`/users/${editDialog.userId}/organizations/${oid}`, {
                  method: 'POST', body: {},
                })
              } catch (e: any) {
                showSnack(`Не удалось добавить организацию: ${e?.message || ''}`, 'error')
              }
            }
          }

          // Remove orgs no longer selected (including former primary)
          for (const oid of currentOrgMap.keys()) {
            if (!desiredIds.has(oid)) {
              try {
                await apiFetch(`/users/${editDialog.userId}/organizations/${oid}`, { method: 'DELETE' })
              } catch (e: any) {
                showSnack(`Не удалось удалить организацию: ${e?.message || ''}`, 'error')
              }
            }
          }
        } catch { /* non-critical */ }
      }

      // Reload user from API to get fresh department text (updated by dept membership API)
      try {
        const fresh = await apiFetch<UserItem>(`/users/${editDialog.userId}`)
        const idx = users.value.findIndex(u => u.id === editDialog.userId)
        if (idx >= 0) users.value.splice(idx, 1, fresh)
      } catch {
        const idx = users.value.findIndex(u => u.id === editDialog.userId)
        if (idx >= 0) users.value.splice(idx, 1, updated)
      }

      editDialog.show = false
      showSnack('Пользователь обновлён')
      await loadDeptTree()
      loadHierarchyTree()
      refreshHierarchy()
    } catch (e: any) {
      showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
    } finally {
      editDialog.saving = false
    }
  }

  return {
    canChangePassword, editDialog, allOrgEntries, groupedOrgEntries,
    dedupOrgAccess, setOrgHiredAt, deptsForOrg, addDeptToOrg,
    syncToContractor, openEditUser, openEditUserById, confirmDeleteOrgEntry, saveEditUser,
  }
}
