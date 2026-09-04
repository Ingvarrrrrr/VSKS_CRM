// Двустороннее автозаполнение «организация ⇄ ИНН» через справочник контрагентов.
//
// Контекст (жалоба владельца, 2026-09-03): в карточке ТС поля «Владелец»/
// «Эксплуатант» (owner_org_id/assigned_org_id — FK на organizations) искали
// только среди ~27 внутренних организаций аккаунта. Владелец хочет искать по
// ВСЕЙ базе контрагентов и чтобы ИНН⇄название подставлялись сами.
//
// Решение (переиспользует паттерн HierarchyView.vue::onNewOrgContractorSelect/
// onEditOrgContractorSelect, но не копирует код 1:1 — там форма создания/
// редактирования организации с открытыми полями, здесь — narrow-выбор FK):
//   - Список автокомплита = внутренние организации (есть готовый org_id) UNION
//     результаты server-search по /api/contractors/ (могут ещё не иметь
//     организации в аккаунте).
//   - Выбор org-элемента — сразу известный id, подставляем инн из orgsList.
//   - Выбор contractor-элемента:
//       1) если у контрагента уже ЕСТЬ организация в orgsList (Organization.
//          contractor_id === id) — используем её id, дубль не создаём;
//       2) иначе, если роль пользователя входит в OWNER_ROLES (superadmin/
//          account_owner — единственные, кому backend разрешает
//          POST /api/organizations/, см. create_organization) — создаём
//          организацию автоматически, привязанную к этому контрагенту
//          (contractor_id), и её реквизиты денормализуем в organizations
//          так же, как это делает HierarchyView (name/inn/kpp/ogrn/address/
//          подписант — «реквизиты живут у контрагента» соблюдено: contractor_id
//          хранит источник правды, org — рабочую копию для FK и списков);
//       3) иначе (обычный менеджер) — НЕ пытаемся создать организацию в обход
//          прав доступа; возвращаем понятную причину отказа, выбор не
//          применяется, карточка ТС остаётся сохраняемой как есть.
//   - INN с уникальным индексом на organizations: если backend отвечает 400
//     «уже существует «Имя» (id=N)» (сценарий: organizational с таким ИНН уже
//     есть, но вне видимости текущего пользователя) — парсим id из сообщения
//     и переиспользуем его вместо падения в ошибку.
import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useContractorsStore } from '@/stores/contractors'

export interface OrgLikeItem {
  id: number
  name: string
  inn?: string | null
  contractor_id?: number | null
}

export interface OrgOrContractorOption {
  uid: string // 'org-<id>' | 'contractor-<id>'
  kind: 'org' | 'contractor'
  id: number
  name: string
  inn?: string | null
}

const OWNER_ROLES = ['superadmin', 'account_owner']

export interface ResolveResult {
  orgId: number | null
  orgName?: string
  orgInn?: string | null
  createdOrg?: OrgLikeItem
  message?: string
  error?: string
}

export function useOrgContractorAutofill(orgsList: Ref<OrgLikeItem[]>) {
  const contractorsStore = useContractorsStore()
  const searchResults = ref<any[]>([])
  let searchTimeout: ReturnType<typeof setTimeout> | null = null

  function search(query: string) {
    if (searchTimeout) clearTimeout(searchTimeout)
    if (!query || query.trim().length < 2) return
    searchTimeout = setTimeout(async () => {
      const list = await contractorsStore.search(query.trim(), 50)
      const existing = new Set(searchResults.value.map((c: any) => c.id))
      for (const c of list) {
        if (!existing.has(c.id)) searchResults.value.push(c)
      }
    }, 300)
  }

  // Поиск и по названию, и по ИНН (contains) — v-autocomplete's item-title
  // фильтрует только по name, а нам нужно и по инн (см. custom-filter в
  // HierarchyView::orgContractorFilter — тот же приём).
  function customFilter(_value: string, query: string, item?: any): boolean {
    const q = (query || '').toLowerCase()
    if (!q) return true
    const raw = item?.raw ?? {}
    const name = (raw.name || '').toLowerCase()
    const inn = (raw.inn || '').toLowerCase()
    return name.includes(q) || inn.includes(q)
  }

  function buildOptions(currentId: number | null, currentName?: string | null): OrgOrContractorOption[] {
    const opts: OrgOrContractorOption[] = orgsList.value.map(o => ({
      uid: `org-${o.id}`, kind: 'org' as const, id: o.id, name: o.name, inn: o.inn ?? null,
    }))
    // Защита от «id вместо названия» (см. комментарий у ownerOrgItems выше по
    // файлу) — если текущая орг не попала в общий список, подмешиваем её по
    // имени из самой карточки ТС.
    if (currentId != null && currentName && !opts.some(o => o.id === currentId)) {
      opts.push({ uid: `org-${currentId}`, kind: 'org', id: currentId, name: currentName, inn: null })
    }
    const linkedContractorIds = new Set(
      orgsList.value.map(o => o.contractor_id).filter((x): x is number => x != null)
    )
    for (const c of searchResults.value) {
      if (linkedContractorIds.has(c.id)) continue // уже представлен org-элементом выше
      opts.push({ uid: `contractor-${c.id}`, kind: 'contractor', id: c.id, name: c.name, inn: c.inn ?? null })
    }
    return opts
  }

  function canCreateOrg(): boolean {
    const role = localStorage.getItem('user_role')
    return !!role && OWNER_ROLES.includes(role)
  }

  async function resolveSelection(uid: string | null): Promise<ResolveResult> {
    if (!uid) return { orgId: null }
    const dash = uid.indexOf('-')
    const kind = uid.slice(0, dash)
    const id = Number(uid.slice(dash + 1))
    if (!Number.isFinite(id)) return { orgId: null, error: 'Некорректный выбор' }

    if (kind === 'org') {
      const org = orgsList.value.find(o => o.id === id)
      return { orgId: id, orgName: org?.name, orgInn: org?.inn ?? null }
    }

    // kind === 'contractor'
    const c = searchResults.value.find((x: any) => x.id === id)
    if (!c) return { orgId: null, error: 'Контрагент не найден в результатах поиска — повторите ввод' }

    const already = orgsList.value.find(o => o.contractor_id === id)
    if (already) return { orgId: already.id, orgName: already.name, orgInn: already.inn ?? null }

    if (!canCreateOrg()) {
      return {
        orgId: null,
        error: `У контрагента «${c.name}» ещё нет организации в аккаунте. Создать её может ` +
          `администратор/владелец аккаунта — обратитесь к нему либо выберите уже существующую организацию.`,
      }
    }

    try {
      const body: Record<string, any> = {
        name: c.name,
        full_name: c.full_name || null,
        inn: c.inn || null,
        kpp: c.kpp || null,
        ogrn: c.ogrn || null,
        address: c.address || null,
        signatory_last_name: c.signatory_last_name || null,
        signatory_first_name: c.signatory_first_name || null,
        signatory_middle_name: c.signatory_middle_name || null,
        signatory_position: c.signatory_position || null,
        contractor_id: id,
      }
      const created = await apiFetch<any>('/organizations/', { method: 'POST', body })
      const newOrg: OrgLikeItem = { id: created.id, name: created.name, inn: created.inn ?? c.inn ?? null, contractor_id: id }
      return {
        orgId: newOrg.id, orgName: newOrg.name, orgInn: newOrg.inn, createdOrg: newOrg,
        message: `Создана организация «${newOrg.name}», привязанная к контрагенту (ИНН ${newOrg.inn || '—'})`,
      }
    } catch (e: any) {
      const msg: string = e?.payload?.message || e?.payload?.detail || e?.message || ''
      // «Организация с ИНН ... уже существует: «Имя» (id=123).» — переиспользуем.
      const m = /«([^»]+)»\s*\(id=(\d+)\)/.exec(msg)
      if (m) {
        const existingId = Number(m[2])
        const existingName = m[1]
        const reused: OrgLikeItem = { id: existingId, name: existingName, inn: c.inn ?? null, contractor_id: id }
        return {
          orgId: existingId, orgName: existingName, orgInn: reused.inn, createdOrg: reused,
          message: `Организация с таким ИНН уже есть в системе: «${existingName}» — использована она, дубль не создан`,
        }
      }
      return { orgId: null, error: msg || 'Не удалось создать организацию по данным контрагента' }
    }
  }

  return { searchResults, search, customFilter, buildOptions, resolveSelection }
}
