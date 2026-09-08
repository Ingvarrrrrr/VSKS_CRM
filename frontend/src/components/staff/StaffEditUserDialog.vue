<template>
  <v-dialog v-model="dialog.show" max-width="500" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">Редактировать: {{ dialog.full_name || dialog.email }}</v-card-title>
      <v-card-text class="pa-4 pt-0">
        <div v-if="dialog.userId" class="d-flex flex-column align-center mb-4">
          <div class="text-caption text-medium-emphasis mb-2">Фотография сотрудника</div>
          <div class="staff-photo-rect" @click="openStaffPhotoUpload">
            <img v-if="dialog.profile_photo" :src="dialog.profile_photo" alt="фото" />
            <v-icon v-else icon="mdi-account" size="80" color="grey-lighten-1" />
            <div class="staff-photo-overlay">
              <v-icon icon="mdi-camera" size="22" color="white" />
            </div>
          </div>
        </div>
        <ProfilePhotoUpload ref="staffPhotoUploadRef" format="rectangle" :user-id="dialog.userId || undefined" @saved="onStaffPhotoSaved" />
        <v-text-field v-model="dialog.email" label="Email (логин)" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-email-outline" />
        <v-text-field v-model="dialog.last_name" label="Фамилия *" variant="outlined" density="compact" class="mb-3"
          :rules="[v => !!v || 'Фамилия обязательна']" />
        <v-text-field v-model="dialog.first_name" label="Имя *" variant="outlined" density="compact" class="mb-3"
          :rules="[v => !!v || 'Имя обязательно']" />
        <v-text-field v-model="dialog.middle_name" label="Отчество" variant="outlined" density="compact" class="mb-3"
          hint="Необязательно — не у всех есть отчество" persistent-hint />
        <v-select v-model="dialog.role" :items="roleItems" item-title="label" item-value="value"
          label="Роль" variant="outlined" density="compact" class="mb-3" />
        <v-select v-model="dialog.superior_user_id" :items="userDropdownItems" item-title="text" item-value="value"
          label="Вышестоящий начальник" variant="outlined" density="compact" clearable class="mb-3"
          prepend-inner-icon="mdi-account-arrow-up"
          hint="Ручной override иерархии для авторасстановки согласующих (если фактически подчиняется не своему отделу)" persistent-hint />
        <!-- Отдел и Должность перенесены вниз в блок "Организации, должности, оклад" -->
        <!-- Avatar picker -->
        <div class="mb-3">
          <div class="text-caption text-medium-emphasis mb-1">Аватарка</div>
          <div class="d-flex flex-wrap" style="gap:8px">
            <div v-for="av in AVATARS" :key="av.id"
              class="avatar-pick"
              :class="{ 'avatar-pick-active': dialog.avatar === av.id }"
              @click="dialog.avatar = av.id">
              <v-avatar :color="av.color" size="40">
                <v-icon :icon="av.icon" size="22" color="white" />
              </v-avatar>
            </div>
          </div>
        </div>
        <v-text-field v-model="dialog.inn" label="ИНН" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-card-account-details-outline" placeholder="12 цифр"
          hint="ИНН физ. лица — 12 цифр" persistent-hint maxlength="12" />
        <v-text-field v-model="dialog.city" label="Город" variant="outlined" density="compact" class="mb-3" />
        <v-text-field
          :model-value="formatPhoneRu(dialog.phone)"
          @update:model-value="dialog.phone = $event"
          label="Телефон" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-phone" placeholder="8-999-999-99-99"
          hint="Формат: 8-999-999-99-99" persistent-hint
        />
        <v-text-field
          :model-value="formatPhoneRu(dialog.work_phone)"
          @update:model-value="dialog.work_phone = unformatPhone($event)"
          label="Рабочий телефон" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-phone-classic" placeholder="8-999-999-99-99"
        />
        <v-text-field v-model="dialog.telegram_id" label="Telegram Chat ID" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-send" placeholder="123456789"
          hint="Числовой ID — узнать: написать @userinfobot в Telegram" persistent-hint />
        <v-text-field v-model="dialog.max_chat_id" label="MAX (VK) Chat ID" variant="outlined" density="compact" class="mb-3"
          prepend-inner-icon="mdi-message-processing" placeholder="123456789"
          hint="Числовой ID для уведомлений через MAX-бот" persistent-hint />
        <v-text-field v-if="canChangePassword" v-model="dialog.password" label="Новый пароль (оставьте пустым чтобы не менять)" variant="outlined" density="compact" type="password" />
        <!-- Multi-org membership (available if orgs list loaded) -->
        <div v-if="organizations.length > 0" class="mb-3">
          <v-select
            v-model="dialog.extraOrgIds"
            :items="organizations"
            item-title="name"
            item-value="id"
            label="В организациях"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            prepend-inner-icon="mdi-domain-plus"
            :loading="dialog.extraOrgsLoading"
            hint="Пользователь будет виден и доступен в этих организациях. Удаление организации уберёт сотрудника из неё."
            persistent-hint
          />
          <!-- Position per extra org -->
          <div v-if="allOrgEntries.length" class="mt-2">
            <div class="text-caption text-medium-emphasis mb-1 d-flex align-center">
              <v-icon size="12" class="mr-1">mdi-briefcase-outline</v-icon>
              Организации, должности, оклад:
            </div>
            <!-- Группировка по org: несколько отделов одной организации отображаются под одним заголовком -->
            <div v-for="group in groupedOrgEntries" :key="group.org_id" class="mb-4">
              <div class="text-caption font-weight-medium mb-1 px-1 d-flex align-center" style="color:#7b1fa2">
                <v-icon size="12" class="mr-1">mdi-domain</v-icon>{{ group.org_name }}
              </div>
              <!-- Дата трудоустройства — ОБЩАЯ на организацию, не на отдел; правка уходит на все строки этой org -->
              <v-text-field
                :model-value="group.hired_at"
                @update:model-value="v => setOrgHiredAt(group.org_id, v)"
                label="Дата трудоустройства"
                variant="outlined"
                density="compact"
                type="date"
                hide-details
                class="mb-2"
                prepend-inner-icon="mdi-calendar-account"
              />
              <div v-for="(entry, ei) in group.entries" :key="entry.id ?? 'new-' + ei" class="mb-2 pa-3 rounded-lg" :style="{ background: 'rgba(0,0,0,0.04)', position: 'relative', borderLeft: '4px solid ' + orgCssColor(group.org_id) }">
                <div class="d-flex align-center mb-2">
                  <v-chip size="small" color="purple" variant="tonal">{{ entry.dept_name || 'Без отдела' }}</v-chip>
                  <v-spacer />
                  <v-btn v-if="entry.id" icon size="x-small" variant="text" color="error" @click="$emit('delete-org-entry', entry)" :title="'Удалить из ' + (entry.dept_name || entry.org_name)">
                    <v-icon size="18">mdi-delete</v-icon>
                  </v-btn>
                  <v-btn v-else-if="(entry as any).is_new" icon size="x-small" variant="text" color="grey" @click="allOrgEntries.splice(allOrgEntries.indexOf(entry as any), 1)" title="Отмена">
                    <v-icon size="18">mdi-close</v-icon>
                  </v-btn>
                </div>
                <v-row dense>
                  <!-- Для новых строк — выбор отдела через автокомплит; для существующих — readonly -->
                  <v-col cols="12" md="6">
                    <v-autocomplete
                      v-if="(entry as any).is_new"
                      v-model="entry.dept_id"
                      :items="deptsForOrg(group.org_id)"
                      label="Отдел"
                      variant="outlined"
                      density="compact"
                      hide-details
                      clearable
                      prepend-inner-icon="mdi-office-building-outline"
                      @update:model-value="val => { const d = deptsForOrg(group.org_id).find(x => x.value === val); if (d) entry.dept_name = d.title }"
                    />
                    <v-text-field
                      v-else
                      :model-value="entry.dept_name"
                      label="Отдел"
                      variant="outlined"
                      density="compact"
                      hide-details
                      readonly
                      prepend-inner-icon="mdi-office-building-outline"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-combobox v-model="entry.position" :items="getPositionsForOrg(entry.org_id)" label="Должность" variant="outlined" density="compact" hide-details clearable
                      prepend-inner-icon="mdi-briefcase-outline" />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field v-model.number="entry.salary_amount" label="Оклад ₽" variant="outlined" density="compact" type="number" hide-details />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field v-model.number="entry.employment_percent" label="% ставки" variant="outlined" density="compact" type="number" hide-details />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field
                      v-model="entry.dept_assigned_at"
                      label="Дата назначения в отдел"
                      variant="outlined"
                      density="compact"
                      type="date"
                      hide-details="auto"
                      :disabled="!entry.dept_id"
                      hint="Подставляется автоматически при переводе в отдел; можно поправить руками"
                    />
                  </v-col>
                  <v-col cols="6">
                    <v-text-field
                      v-model="entry.position_assigned_at"
                      label="Дата назначения на должность"
                      variant="outlined"
                      density="compact"
                      type="date"
                      hide-details="auto"
                      hint="При приёме = дате трудоустройства; при смене должности — дате смены; можно поправить руками"
                    />
                  </v-col>
                </v-row>
              </div>
              <!-- Кнопка «+ ещё отдел в этой организации» -->
              <v-btn size="x-small" variant="text" color="purple" prepend-icon="mdi-plus" class="ml-1" @click="$emit('add-dept-to-org', group.org_id)">
                Ещё отдел в {{ group.org_name }}
              </v-btn>
            </div>
          </div>
        </div>
        <!-- F3-checkbox: Не включать в справочник сотрудников -->
        <v-checkbox
          v-model="dialog.exclude_from_directory"
          label="Не включать в справочник сотрудников"
          density="compact"
          hide-details
          class="mb-3"
        />

        <!-- 29-15: Может водить ТС + данные ВУ -->
        <v-checkbox
          v-model="dialog.can_drive"
          label="Может водить ТС"
          density="compact"
          hide-details
          class="mb-2"
        />
        <v-expand-transition>
          <v-card v-if="dialog.can_drive" variant="outlined" class="pa-4 mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-3">Данные водителя</div>
            <v-row dense>
              <v-col cols="4">
                <v-text-field
                  v-model="dialog.license_series"
                  label="Серия ВУ"
                  maxlength="10"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="8">
                <v-text-field
                  v-model="dialog.license_number"
                  label="Номер ВУ"
                  maxlength="20"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>
            <v-text-field
              v-model="dialog.license_categories"
              label="Категории (через запятую)"
              placeholder="A, B, C, D, CE"
              maxlength="50"
              variant="outlined"
              density="compact"
              class="mb-2"
            />
            <v-row dense>
              <v-col cols="6">
                <v-text-field
                  v-model="dialog.license_issued_at"
                  type="date"
                  label="ВУ выдано"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="dialog.license_expires_at"
                  type="date"
                  label="ВУ действует до"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>
            <v-chip
              v-if="dialog.license_expires_at && driverLicenseExpiryDays(dialog.license_expires_at) !== null && driverLicenseExpiryDays(dialog.license_expires_at)! <= 30"
              color="warning"
              size="small"
              prepend-icon="mdi-alert"
              class="mb-2"
            >
              ВУ истекает через {{ driverLicenseExpiryDays(dialog.license_expires_at)! }} дн.
            </v-chip>
            <v-text-field
              v-model="dialog.medical_cert_expires_at"
              type="date"
              label="Медсправка действует до"
              variant="outlined"
              density="compact"
              class="mt-2"
            />
            <v-chip
              v-if="dialog.medical_cert_expires_at && driverMedicalExpiryDays(dialog.medical_cert_expires_at) !== null && driverMedicalExpiryDays(dialog.medical_cert_expires_at)! <= 30"
              color="warning"
              size="small"
              prepend-icon="mdi-alert"
              class="mt-1"
            >
              Медсправка истекает через {{ driverMedicalExpiryDays(dialog.medical_cert_expires_at)! }} дн.
            </v-chip>

            <!-- Phase 29.3: тахограф / психиатрия / периодический медосмотр -->
            <v-text-field
              v-model="dialog.tachograph_card_expires_at"
              type="date"
              label="Карточка тахографа действует до"
              hint="Срок действия карты водителя для тахографа"
              persistent-hint
              density="compact"
              class="mt-2"
            />
            <v-text-field
              v-model="dialog.periodic_medical_expires_at"
              type="date"
              label="Периодический медосмотр до"
              hint="Согласно приказу 302н — для категорий C/D/E и проф. водителей"
              persistent-hint
              density="compact"
              class="mt-2"
            />
            <v-text-field
              v-model="dialog.psych_cert_expires_at"
              type="date"
              label="Психиатрическое освидетельствование до"
              hint="Согласно приказу 302н — раз в 5 лет"
              persistent-hint
              density="compact"
              class="mt-2"
            />

            <!-- Phase 30.3: скан водительского удостоверения -->
            <div class="text-caption text-medium-emphasis mt-3 mb-1">Скан водительского удостоверения</div>
            <div class="license-scan-wrap" @click="onLicenseScanClick">
              <img v-if="dialog.license_scan" :src="dialog.license_scan" alt="скан ВУ" class="license-scan-preview" />
              <div v-else class="license-scan-empty">
                <v-icon icon="mdi-card-account-details-outline" size="36" color="grey-lighten-1" />
                <span class="text-caption text-medium-emphasis">Загрузить скан (JPG/PNG, до 3 МБ)</span>
              </div>
            </div>
            <input ref="licenseScanInput" type="file" accept="image/*" style="display:none" @change="onLicenseScanFile" />
            <v-btn
              v-if="dialog.license_scan"
              size="x-small"
              variant="text"
              color="error"
              prepend-icon="mdi-delete-outline"
              class="mt-1"
              @click="dialog.license_scan = ''"
            >Удалить скан</v-btn>
          </v-card>
        </v-expand-transition>

        <!-- 17-08: «Доступ» section — per-user per-org permission overrides (D-04/D-05.2/D-08) -->
        <UserPermissionsSection
          v-if="dialog.userId && allOrgEntries.length"
          :key="dialog.userId"
          :user-id="dialog.userId"
          :current-user-id="currentUserId"
          :user-role="dialog.role"
          :org-access-list="dedupOrgAccess(allOrgEntries)"
          :all-orgs-access="dialog.all_orgs_access"
          @update:all-orgs-access="(v: boolean) => { dialog.all_orgs_access = v }"
        />
        <UserSubsidyAccessSection
          v-if="dialog.userId"
          :user-id="dialog.userId"
          :user-role="dialog.role"
        />

        <!-- Учётки электронных площадок (ЭТП Фабрикант) -->
        <UserPlatformCredentialsSection
          v-if="dialog.userId"
          :user-id="dialog.userId"
          @error="(msg: string) => $emit('error', msg)"
        />

        <!-- Диагностика видимости: отделы, которые возглавляет сотрудник -->
        <div v-if="dialog.headedDepts.length" class="mt-3 pa-3 rounded-lg" style="background:rgba(0,128,100,0.07);border-left:3px solid #00897b">
          <div class="text-caption text-medium-emphasis mb-2 d-flex align-center">
            <v-icon size="14" class="mr-1" color="teal">mdi-eye-check-outline</v-icon>
            Видимость: возглавляет отдел(ы) — видит закупки/задачи всех участников:
          </div>
          <v-chip v-for="d in dialog.headedDepts" :key="d.id" size="x-small" color="teal" variant="tonal" class="mr-1 mb-1">
            <v-icon start size="10">mdi-crown</v-icon>{{ d.name }}{{ d.org_name ? ' · ' + d.org_name : '' }}
          </v-chip>
        </div>
        <div v-else-if="dialog.userId" class="mt-2 text-caption" style="color:#e65100">
          <v-icon size="13" color="warning" class="mr-1">mdi-alert-outline</v-icon>
          Не назначен начальником ни одного отдела — видит только свои закупки/задачи (+ подчинённые по иерархии).
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-account-convert" @click="$emit('sync-to-contractor', dialog.userId)">
          В контрагенты
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="dialog.saving"
          :disabled="!dialog.last_name || !dialog.first_name"
          @click="$emit('save')">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ProfilePhotoUpload from '@/components/ProfilePhotoUpload.vue'
import UserPermissionsSection from '@/components/UserPermissionsSection.vue'
import UserSubsidyAccessSection from '@/components/UserSubsidyAccessSection.vue'
import UserPlatformCredentialsSection from '@/components/UserPlatformCredentialsSection.vue'
import { formatPhoneRu, unformatPhone } from '@/utils/phoneFormat'
import { AVATARS, driverLicenseExpiryDays, driverMedicalExpiryDays } from '@/composables/staff/staffLabels'
import type { OrgEntry } from '@/composables/staff/staffTypes'

const props = defineProps<{
  dialog: any
  mobile: boolean
  canChangePassword: boolean
  roleItems: { value: string; label: string }[]
  userDropdownItems: { text: string; value: number }[]
  organizations: any[]
  allOrgEntries: OrgEntry[]
  groupedOrgEntries: { org_id: number; org_name: string; hired_at: string | null; entries: OrgEntry[] }[]
  dedupOrgAccess: (entries: OrgEntry[]) => { org_id: number; org_name: string; role: string }[]
  setOrgHiredAt: (orgId: number, value: string | null) => void
  deptsForOrg: (orgId: number) => { title: string; value: number }[]
  orgCssColor: (orgId: number | null | undefined, alpha?: number) => string
  getPositionsForOrg: (orgId?: number | null) => string[]
  currentUserId: number
}>()
defineEmits<{
  (e: 'save'): void
  (e: 'delete-org-entry', entry: OrgEntry): void
  (e: 'add-dept-to-org', orgId: number): void
  (e: 'sync-to-contractor', userId: number): void
  (e: 'error', msg: string): void
}>()

// Фото профиля и скан ВУ — UI-состояние диалога, мутирует `dialog` (тот же
// reactive-объект editDialog, что и в родителе) напрямую. Дословный перенос
// из StaffView.vue (openStaffPhotoUpload/onStaffPhotoSaved/onLicenseScan*).
const staffPhotoUploadRef = ref<InstanceType<typeof ProfilePhotoUpload> | null>(null)
function openStaffPhotoUpload() { staffPhotoUploadRef.value?.open() }
function onStaffPhotoSaved(url: string | null) {
  props.dialog.profile_photo = url || ''
}

const licenseScanInput = ref<HTMLInputElement | null>(null)
function onLicenseScanClick() {
  licenseScanInput.value?.click()
}
async function onLicenseScanFile(ev: Event) {
  const target = ev.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    alert('Только изображения (JPG/PNG)')
    target.value = ''
    return
  }
  if (file.size > 3_000_000) {
    alert('Файл слишком большой (макс 3 МБ)')
    target.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    props.dialog.license_scan = String(reader.result || '')
  }
  reader.readAsDataURL(file)
  target.value = ''
}
</script>

<style scoped>
/* Avatar picker + фото профиля + скан ВУ — перенесено из StaffView.vue */
.avatar-pick { cursor: pointer; border-radius: 50%; padding: 2px; border: 2px solid transparent; transition: all 0.2s; }
.avatar-pick:hover { border-color: rgba(var(--v-theme-primary), 0.3); transform: scale(1.1); }
.avatar-pick-active { border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.4); }

.staff-photo-rect {
  width: 160px; height: 200px; border-radius: 12px; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.04); border: 2px solid rgba(0,0,0,0.08);
  cursor: pointer; position: relative;
}
.staff-photo-rect img { width: 100%; height: 100%; object-fit: cover; }
.staff-photo-overlay {
  position: absolute; bottom: 0; left: 0; right: 0; height: 32px;
  background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
}

/* Phase 30.3: license scan upload preview */
.license-scan-wrap {
  width: 100%; min-height: 120px; border-radius: 10px;
  border: 2px dashed rgba(0,0,0,0.15);
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.03); cursor: pointer; overflow: hidden;
  transition: border-color .12s, background .12s;
}
.license-scan-wrap:hover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.05);
}
.license-scan-preview { width: 100%; max-height: 220px; object-fit: contain; }
.license-scan-empty {
  display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 16px;
}
</style>
