<template>
  <v-container fluid class="pa-6" style="max-width:900px">
    <div class="mb-6">
      <h1 class="text-h5 font-weight-bold">Настройки организации</h1>
      <p class="text-body-2 text-medium-emphasis mt-1">
        Управление видимостью разделов в форме закупки. Скрытые разделы не удаляются — данные сохраняются в базе.
      </p>
    </div>

    <v-alert type="info" variant="tonal" class="mb-6" density="compact">
      По умолчанию доступен полный функционал. Вы можете скрыть разделы, которые не нужны вашей организации.
      Скрытые разделы применяются ко всем пользователям организации.
    </v-alert>

    <v-card variant="outlined">
      <v-card-title class="text-subtitle-1 font-weight-bold px-6 pt-5 pb-3">
        Разделы формы закупки
      </v-card-title>
      <v-divider />

      <v-list>
        <template v-for="(section, i) in SECTIONS" :key="section.key">
          <v-list-item class="px-6 py-4">
            <template #prepend>
              <v-icon :icon="section.icon" class="mr-3" :color="localHidden.has(section.key) ? 'grey' : 'primary'" />
            </template>
            <v-list-item-title class="font-weight-medium" :class="localHidden.has(section.key) ? 'text-medium-emphasis' : ''">
              {{ section.title }}
            </v-list-item-title>
            <v-list-item-subtitle>{{ section.description }}</v-list-item-subtitle>
            <template #append>
              <div class="d-flex align-center gap-3">
                <v-chip v-if="localHidden.has(section.key)" size="x-small" color="grey" variant="tonal">
                  Скрыт
                </v-chip>
                <v-switch
                  :model-value="!localHidden.has(section.key)"
                  color="primary"
                  hide-details
                  density="compact"
                  @update:model-value="onToggle(section, $event)"
                />
              </div>
            </template>
          </v-list-item>
          <v-divider v-if="i < SECTIONS.length - 1" />
        </template>
      </v-list>

      <v-card-actions class="px-6 py-4">
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          prepend-icon="mdi-content-save"
          @click="saveConfig"
        >
          Сохранить изменения
        </v-btn>
        <v-btn variant="text" @click="resetToDefault">Восстановить по умолчанию</v-btn>
      </v-card-actions>
    </v-card>

    <!-- Warning dialog -->
    <v-dialog v-model="warnDialog.show" max-width="480" persistent>
      <v-card>
        <v-card-title class="text-h6 pt-5 px-6 d-flex align-center gap-2">
          <v-icon icon="mdi-alert" color="warning" />
          Скрыть раздел?
        </v-card-title>
        <v-card-text class="px-6">
          <p class="text-body-1 font-weight-medium mb-2">{{ warnDialog.section?.title }}</p>
          <v-alert type="warning" variant="tonal" density="compact">
            {{ warnDialog.section?.warning }}
          </v-alert>
          <p class="text-body-2 text-medium-emphasis mt-3">
            Данные не удаляются — раздел просто не будет отображаться в форме. Вы сможете восстановить его в любой момент.
          </p>
        </v-card-text>
        <v-card-actions class="px-6 pb-5">
          <v-btn color="warning" variant="flat" @click="confirmHide">Скрыть раздел</v-btn>
          <v-btn variant="text" @click="cancelHide">Отмена</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useOrgConfig } from '@/composables/useOrgConfig'

const { hiddenSections, loadConfig, updateConfig, loading: configLoading } = useOrgConfig()

interface Section {
  key: string
  title: string
  description: string
  icon: string
  warning: string
}

const SECTIONS: Section[] = [
  {
    key: 'financial_indicators',
    title: 'Финансовые показатели',
    description: 'НМЦК, экономия, цена договора',
    icon: 'mdi-chart-bar',
    warning: 'Без финансовых показателей невозможно отслеживать НМЦК, экономию и превышения бюджета. Уже введённые данные сохранятся в базе.',
  },
  {
    key: 'contract_type',
    title: 'Тип договора',
    description: 'Рамочные договоры и их связи',
    icon: 'mdi-file-link-outline',
    warning: 'Без типа договора рамочные закупки не будут связываться между собой. Существующие связи сохранятся.',
  },
  {
    key: 'contract_params',
    title: 'Параметры договора',
    description: 'НДС, третьи лица, период оказания услуг',
    icon: 'mdi-file-cog-outline',
    warning: 'Параметры НДС и третьих лиц не будут заполнены при генерации договора. Используйте только если не работаете с НДС.',
  },
  {
    key: 'acceptance',
    title: 'Акт приёмки',
    description: 'Документы приёмки товаров и услуг',
    icon: 'mdi-clipboard-check-outline',
    warning: 'Без акта приёмки нельзя перевести закупку в статус «Поставлено». Включите раздел, если отслеживаете фактическую поставку.',
  },
  {
    key: 'payment',
    title: 'Платёж',
    description: 'Платёжные поручения и суммы оплаты',
    icon: 'mdi-bank-transfer',
    warning: 'Без раздела платежей нельзя перевести закупку в статус «Оплачено». Включите, если отслеживаете фактическую оплату.',
  },
  {
    key: 'commercial_requests',
    title: 'Запросы КП',
    description: 'Рассылка коммерческих предложений поставщикам',
    icon: 'mdi-email-fast-outline',
    warning: 'Функция рассылки коммерческих предложений поставщикам будет недоступна для всех менеджеров организации.',
  },
  {
    key: 'platform_publication',
    title: 'Публикация на площадках',
    description: 'Фабрикант, Росэлторг и другие торговые площадки',
    icon: 'mdi-web',
    warning: 'Публикация закупок на электронных торговых площадках (Фабрикант, Росэлторг) будет недоступна.',
  },
]

// Local copy of hidden sections for unsaved changes
const localHidden = ref<Set<string>>(new Set())
const saving = ref(false)

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const warnDialog = reactive<{ show: boolean; section: Section | null; }>({ show: false, section: null })

function onToggle(section: Section, visible: boolean) {
  if (!visible) {
    // Trying to hide — show warning first
    warnDialog.section = section
    warnDialog.show = true
  } else {
    // Showing — no warning needed
    localHidden.value = new Set([...localHidden.value].filter(k => k !== section.key))
  }
}

function confirmHide() {
  if (warnDialog.section) {
    localHidden.value = new Set([...localHidden.value, warnDialog.section.key])
  }
  warnDialog.show = false
  warnDialog.section = null
}

function cancelHide() {
  warnDialog.show = false
  warnDialog.section = null
}

async function saveConfig() {
  saving.value = true
  try {
    const items = SECTIONS.map(s => ({
      section_key: s.key,
      is_hidden: localHidden.value.has(s.key),
    }))
    await updateConfig(items)
    showSnack('Настройки сохранены')
  } catch {
    showSnack('Ошибка сохранения', 'error')
  } finally {
    saving.value = false
  }
}

function resetToDefault() {
  localHidden.value = new Set()
}

onMounted(async () => {
  await loadConfig()
  localHidden.value = new Set(hiddenSections.value)
})
</script>
