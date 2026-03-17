<template>
  <v-container fluid class="pa-6 staff-view">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Персонал</h1>
        <span class="text-body-2 text-medium-emphasis">Отделы, сотрудники и иерархия</span>
      </div>
      <v-spacer />
      <v-btn v-if="isAdmin" color="primary" size="small" prepend-icon="mdi-account-plus" @click="openCreateUser">
        Добавить сотрудника
      </v-btn>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="departments">
        <v-icon icon="mdi-sitemap" class="mr-2" size="18" />Отделы
      </v-tab>
      <v-tab value="users">
        <v-icon icon="mdi-account-group" class="mr-2" size="18" />Сотрудники
      </v-tab>
      <v-tab value="hierarchy">
        <v-icon icon="mdi-family-tree" class="mr-2" size="18" />Иерархия
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TAB 1: Departments                                     -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <v-window-item value="departments">
        <!-- Dept toolbar -->
        <div class="d-flex align-center mb-4 flex-wrap" style="gap:8px">
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name" item-value="id"
            label="Субсидия" variant="outlined" density="compact" clearable
            style="max-width:260px" hide-details
          />
          <v-spacer />
          <v-btn variant="outlined" size="small" prepend-icon="mdi-download" @click="downloadDeptTemplate">
            Шаблон
          </v-btn>
          <v-btn color="success" variant="tonal" size="small" prepend-icon="mdi-file-excel-outline" @click="deptImportDialog = true">
            Импорт Excel
          </v-btn>
          <v-btn color="primary" size="small" prepend-icon="mdi-plus" @click="openCreateDept">
            Добавить отдел
          </v-btn>
        </div>

        <v-row>
          <!-- Left: Department tree -->
          <v-col cols="12" md="7">
            <v-card variant="outlined">
              <v-card-title class="pa-4 d-flex align-center">
                <v-icon icon="mdi-sitemap" class="mr-2" />Дерево отделов
                <v-spacer />
                <v-btn icon="mdi-refresh" variant="text" size="small" :loading="deptLoading" @click="loadDeptTree" />
              </v-card-title>
              <v-card-text class="pa-2">
                <div v-if="deptLoading" class="d-flex justify-center py-8"><v-progress-circular indeterminate /></div>
                <div v-else-if="deptTree.length === 0" class="text-center py-8 text-medium-emphasis">
                  Нет отделов. Создайте первый или загрузите из Excel.
                </div>
                <div v-else>
                  <div v-for="node in deptTree" :key="node.id">
                    <dept-node :node="node" :depth="0" @select="selectDept" @edit="openEditDept" @delete="deleteDept" @add-member="onAddMemberInline" @edit-member="onEditMemberInline" @remove-member="onRemoveMemberInline" />
                  </div>
                </div>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Right: Selected department details -->
          <v-col cols="12" md="5">
            <v-card v-if="selectedDept" variant="outlined">
              <v-card-title class="pa-4 d-flex align-center">
                <v-icon icon="mdi-account-group" class="mr-2" />{{ selectedDept.name }}
                <v-spacer />
                <v-chip v-if="selectedDept.head_user_name" size="small" color="teal" variant="tonal" prepend-icon="mdi-crown">
                  {{ selectedDept.head_user_name }}
                </v-chip>
              </v-card-title>

              <!-- Members -->
              <v-card-text class="pa-4 pt-0">
                <div class="d-flex align-center mb-2">
                  <span class="text-subtitle-2 font-weight-medium">Сотрудники</span>
                  <v-chip size="x-small" class="ml-2" variant="tonal">{{ deptMembers.length }}</v-chip>
                  <v-spacer />
                  <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-account-plus" @click="onAddMemberInline(selectedDept)">Добавить</v-btn>
                </div>
                <v-alert v-if="deptMembers.length === 0" type="info" variant="tonal" density="compact" class="mb-2">
                  Нажмите <strong>+</strong> на отделе в дереве слева или кнопку «Добавить» выше.
                </v-alert>
                <v-list density="compact" v-if="deptMembers.length">
                  <v-list-item v-for="m in deptMembers" :key="m.id" :subtitle="m.position || m.user_role">
                    <template v-slot:prepend>
                      <v-avatar size="28" :color="getAvatar(getMemberAvatar(m.user_id)).color">
                        <v-icon :icon="getAvatar(getMemberAvatar(m.user_id)).icon" size="14" color="white" />
                      </v-avatar>
                    </template>
                    <v-list-item-title>{{ m.user_name }}</v-list-item-title>
                    <template v-slot:append>
                      <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" class="mr-1" @click="onEditMemberInline({ dept: selectedDept, member: { user_id: m.user_id, name: m.user_name, position: m.position } })" />
                      <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="removeMember(m.user_id)" />
                    </template>
                  </v-list-item>
                </v-list>
                <div v-else class="text-caption text-medium-emphasis pa-2">Нет сотрудников</div>

                <v-divider class="my-3" />

                <!-- Delegates -->
                <div class="d-flex align-center mb-2">
                  <span class="text-subtitle-2 font-weight-medium">Права на задачи</span>
                  <v-spacer />
                  <v-btn size="x-small" variant="tonal" color="orange" prepend-icon="mdi-shield-account" @click="delegateDialog = true">Добавить</v-btn>
                </div>
                <div class="text-caption text-medium-emphasis mb-2">
                  Начальник отдела автоматически может редактировать задачи своих сотрудников. Ниже — дополнительные права:
                </div>
                <v-list density="compact" v-if="delegates.length">
                  <v-list-item v-for="d in delegates" :key="d.id">
                    <v-list-item-title class="text-body-2">
                      <strong>{{ d.delegate_user_name }}</strong> может редактировать задачи <strong>{{ d.target_user_name }}</strong>
                    </v-list-item-title>
                    <template v-slot:append>
                      <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="removeDelegate(d.id)" />
                    </template>
                  </v-list-item>
                </v-list>
                <div v-else class="text-caption text-medium-emphasis pa-2">Нет дополнительных делегирований</div>
              </v-card-text>
            </v-card>

            <v-card v-else variant="outlined" style="min-height:200px">
              <v-card-text class="d-flex flex-column align-center justify-center pa-6" style="min-height:200px">
                <v-icon icon="mdi-cursor-default-click" size="48" color="grey-lighten-1" />
                <div class="text-body-1 text-medium-emphasis mt-3 mb-4">Выберите отдел в дереве слева</div>
                <v-alert type="info" variant="tonal" density="compact" class="text-left" style="max-width:360px">
                  <div class="text-body-2 font-weight-medium mb-1">Порядок настройки:</div>
                  <ol class="text-body-2 pl-4" style="line-height:1.8">
                    <li>Создайте отдел (кнопка "Добавить отдел")</li>
                    <li>Нажмите <strong>+</strong> на отделе, чтобы добавить сотрудников</li>
                    <li>Карандашом измените должность сотрудника</li>
                    <li>Отредактируйте отдел и назначьте начальника</li>
                  </ol>
                </v-alert>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TAB 2: Users                                           -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <v-window-item value="users">
        <div class="d-flex align-center mb-4 flex-wrap" style="gap:8px">
          <v-spacer />
          <v-btn v-if="isAdmin" variant="outlined" size="small" prepend-icon="mdi-download" @click="downloadUserTemplate">
            Шаблон
          </v-btn>
          <v-btn v-if="isAdmin" color="success" variant="tonal" size="small" prepend-icon="mdi-file-excel-outline" @click="userImportDialog.show = true">
            Импорт из Excel
          </v-btn>
        </div>

        <v-card variant="outlined">
          <v-data-table
            v-resizable-columns="'staff-users'"
            :headers="userHeaders"
            :items="users"
            :loading="usersLoading"
            density="comfortable"
            show-expand
            expand-on-click
            item-value="id"
            v-model:expanded="expandedUsers"
            @update:expanded="onUserExpanded"
          >
            <template v-slot:item.avatar="{ item }">
              <UserAvatar :photo-url="item.photo_url" :avatar="item.avatar" :size="32" />
            </template>
            <template v-slot:item.role="{ item }">
              <v-chip :color="roleColor(item.role)" size="small" variant="tonal">
                {{ ROLE_LABELS[item.role] || item.role }}
              </v-chip>
            </template>
            <template v-slot:item.position="{ item }">
              <span class="text-body-2">{{ item.position || '---' }}</span>
            </template>
            <template v-slot:item.has_signature="{ item }">
              <v-icon v-if="item.has_signature" icon="mdi-draw" size="18" color="success" title="Подпись создана" />
              <v-icon v-else icon="mdi-draw-pen" size="18" color="grey-lighten-1" title="Подпись не создана" />
            </template>
            <template v-slot:item.actions="{ item }">
              <div class="d-flex gap-1" v-if="isAdmin">
                <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                  @click.stop="openEditUser(item)" title="Редактировать" />
                <v-btn icon="mdi-account-supervisor" size="x-small" variant="text" color="teal"
                  @click.stop="openHierarchyDialog(item)" title="Настроить подчиненных" />
                <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                  @click.stop="confirmDelete(item)" :disabled="item.username === 'admin'" />
              </div>
            </template>
            <template v-slot:expanded-row="{ item, columns }">
              <tr>
                <td :colspan="columns.length + 1" class="pa-0">
                  <div class="px-4 py-3 bg-grey-lighten-5">
                    <div v-if="taskAuthorityLoading[item.id]" class="d-flex align-center ga-2 py-1">
                      <v-progress-circular size="16" indeterminate />
                      <span class="text-caption text-medium-emphasis">Загрузка...</span>
                    </div>
                    <div v-else class="d-flex ga-4 flex-wrap align-start">
                      <div>
                        <div class="text-caption font-weight-medium text-medium-emphasis mb-1 d-flex align-center">
                          <v-icon size="14" class="mr-1" color="teal">mdi-arrow-right-circle</v-icon>
                          Может ставить задачи:
                        </div>
                        <div v-if="!taskAuthority[item.id]?.can_assign_to?.length" class="text-caption text-medium-emphasis">—</div>
                        <v-chip
                          v-for="u in taskAuthority[item.id]?.can_assign_to" :key="u.id"
                          size="x-small" color="teal" variant="tonal" class="mr-1 mb-1">
                          {{ u.full_name || u.username }}
                        </v-chip>
                      </div>
                      <div>
                        <div class="text-caption font-weight-medium text-medium-emphasis mb-1 d-flex align-center">
                          <v-icon size="14" class="mr-1" color="indigo">mdi-arrow-left-circle</v-icon>
                          Кто ставит ему задачи:
                        </div>
                        <div v-if="!taskAuthority[item.id]?.can_receive_from?.length" class="text-caption text-medium-emphasis">—</div>
                        <v-chip
                          v-for="u in taskAuthority[item.id]?.can_receive_from" :key="u.id"
                          size="x-small" color="indigo" variant="tonal" class="mr-1 mb-1">
                          {{ u.full_name || u.username }}
                        </v-chip>
                      </div>
                      <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-sitemap" to="/hierarchy">
                        Настроить в Иерархии
                      </v-btn>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </v-data-table>
        </v-card>
      </v-window-item>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TAB 3: Hierarchy                                       -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <v-window-item value="hierarchy">
        <!-- Editor link banner -->
        <v-alert
          type="info" variant="tonal" density="compact" class="mb-4"
          prepend-icon="mdi-sitemap"
        >
          <div class="d-flex align-center justify-space-between flex-wrap" style="gap:8px">
            <span>Для создания и редактирования связей используйте визуальный редактор иерархии</span>
            <v-btn color="primary" variant="flat" size="small" to="/hierarchy" prepend-icon="mdi-sitemap">
              Открыть редактор иерархии →
            </v-btn>
          </div>
        </v-alert>
        <v-card variant="outlined">
          <v-card-title class="pa-4 d-flex align-center">
            <v-icon icon="mdi-family-tree" class="mr-2" />Дерево подчиненности (только чтение)
            <v-spacer />
            <v-btn icon="mdi-refresh" variant="text" size="small" :loading="treeLoading" @click="loadHierarchyTree" />
          </v-card-title>
          <v-card-text>
            <div v-if="treeLoading" class="text-center py-4">
              <v-progress-circular indeterminate size="24" />
            </div>
            <div v-else-if="hierarchyTree.length === 0" class="text-caption text-medium-emphasis text-center py-4">
              Нет настроенной иерархии
            </div>
            <div v-else>
              <div v-for="node in hierarchyTree" :key="node.id" class="tree-node">
                <div class="tree-label">
                  <v-avatar :color="getAvatar(node.avatar).color" size="24" class="mr-2">
                    <v-icon :icon="getAvatar(node.avatar).icon" size="14" color="white" />
                  </v-avatar>
                  <span class="font-weight-medium text-body-2">{{ node.full_name || node.username }}</span>
                  <v-chip size="x-small" :color="roleColor(node.role)" variant="tonal" class="ml-1">
                    {{ ROLE_LABELS[node.role] || node.role }}
                  </v-chip>
                </div>
                <div class="tree-children" v-if="node.subordinates?.length">
                  <div v-for="sub in node.subordinates" :key="sub.id" class="tree-child">
                    <v-avatar :color="getAvatar((sub as any).avatar).color" size="20" class="mr-1">
                      <v-icon :icon="getAvatar((sub as any).avatar).icon" size="12" color="white" />
                    </v-avatar>
                    <span class="text-body-2">{{ sub.full_name || sub.username }}</span>
                    <v-chip size="x-small" :color="roleColor(sub.role)" variant="tonal" class="ml-1">
                      {{ ROLE_LABELS[sub.role] || sub.role }}
                    </v-chip>
                  </div>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!-- DIALOGS (at root level, NOT inside tabs)                   -->
    <!-- ═══════════════════════════════════════════════════════════ -->

    <!-- 1. Create user dialog -->
    <v-dialog v-model="createDialog.show" max-width="440">
      <v-card>
        <v-card-title class="pa-4">Добавить сотрудника</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field v-model="createDialog.full_name" label="ФИО *" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-account" :rules="[v => !!v || 'ФИО обязательно']" />
          <v-text-field v-model="createDialog.email" label="Email *" variant="outlined" density="compact" class="mb-3"
            hint="Используется для входа в систему" persistent-hint prepend-inner-icon="mdi-email-outline"
            type="email" :rules="[v => !!v || 'Email обязателен', v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Введите корректный email (например, ivanov@company.ru)']" />
          <v-text-field v-model="createDialog.phone" label="Телефон" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-phone" placeholder="+7 (999) 123-45-67"
            hint="Для связи и интеграции с Telegram" persistent-hint />
          <v-text-field v-model="createDialog.telegram_id" label="Telegram" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-send" placeholder="@username"
            hint="Для уведомлений через Telegram-бот" persistent-hint />
          <v-text-field v-model="createDialog.password" label="Пароль *" type="password" variant="outlined" density="compact" class="mb-3"
            :rules="[v => !!v || 'Пароль обязателен', v => v.length >= 6 || 'Минимум 6 символов']" />
          <v-text-field v-model="createDialog.password_confirm" label="Подтвердите пароль *" type="password" variant="outlined" density="compact" class="mb-3"
            :error="!!createDialog.password_confirm && createDialog.password !== createDialog.password_confirm"
            :error-messages="createDialog.password_confirm && createDialog.password !== createDialog.password_confirm ? 'Пароли не совпадают' : ''" />
          <v-autocomplete v-if="isSuperadmin" v-model="createDialog.org_id" :items="organizations" item-title="name" item-value="id"
            label="Организация *" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-domain" :rules="[v => !!v || 'Организация обязательна']" />
          <v-text-field v-else label="Организация" variant="outlined" density="compact" class="mb-3"
            :model-value="currentOrgName" disabled prepend-inner-icon="mdi-domain" />
          <v-select
            v-model="createDialog.role"
            :items="roleItems"
            item-title="label" item-value="value"
            label="Роль"
            variant="outlined" density="compact" class="mb-3"
          />
          <v-combobox v-model="createDialog.department" :items="knownDepartments" label="Отдел" variant="outlined" density="compact" clearable class="mb-3"
            hint="Введите новый отдел или выберите из списка" persistent-hint
            no-data-text="Введите название нового отдела" prepend-inner-icon="mdi-office-building-outline" />
          <v-combobox v-model="createDialog.position" :items="knownPositions" label="Должность" variant="outlined" density="compact" clearable class="mb-3"
            hint="Введите новую должность или выберите из списка" persistent-hint
            no-data-text="Введите название новой должности" prepend-inner-icon="mdi-briefcase-outline" />
          <v-autocomplete v-model="createDialog.subsidy_id" :items="subsidies" item-title="name" item-value="id"
            label="Субсидия" variant="outlined" density="compact" clearable class="mb-3"
            prepend-inner-icon="mdi-cash-multiple" hint="Необязательно" persistent-hint />
          <!-- Avatar picker -->
          <div class="mb-3">
            <div class="text-caption text-medium-emphasis mb-1">Аватарка</div>
            <div class="d-flex flex-wrap" style="gap:8px">
              <div v-for="av in AVATARS" :key="av.id"
                class="avatar-pick"
                :class="{ 'avatar-pick-active': createDialog.avatar === av.id }"
                @click="createDialog.avatar = av.id">
                <v-avatar :color="av.color" size="40">
                  <v-icon :icon="av.icon" size="22" color="white" />
                </v-avatar>
              </div>
            </div>
          </div>
          <v-text-field v-model="createDialog.city" label="Город" variant="outlined" density="compact" />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="createDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat"
            :loading="createDialog.saving"
            :disabled="!createDialog.email || !createDialog.password || createDialog.password !== createDialog.password_confirm || (isSuperadmin && !createDialog.org_id)"
            @click="saveUser">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 2. Edit user dialog -->
    <v-dialog v-model="editDialog.show" max-width="500">
      <v-card>
        <v-card-title class="pa-4">Редактировать: {{ editDialog.full_name || editDialog.email }}</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field v-model="editDialog.email" label="Email (логин)" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-email-outline" />
          <v-text-field v-model="editDialog.full_name" label="ФИО" variant="outlined" density="compact" class="mb-3" />
          <v-select v-model="editDialog.role" :items="roleItems" item-title="label" item-value="value"
            label="Роль" variant="outlined" density="compact" class="mb-3" />
          <v-combobox v-model="editDialog.department" :items="knownDepartments" label="Отдел" variant="outlined" density="compact" clearable class="mb-3"
            hint="Введите новый отдел или выберите из списка" persistent-hint
            no-data-text="Введите название нового отдела" prepend-inner-icon="mdi-office-building-outline" />
          <v-combobox v-model="editDialog.position" :items="knownPositions" label="Должность" variant="outlined" density="compact" clearable class="mb-3"
            hint="Введите новую должность или выберите из списка" persistent-hint
            no-data-text="Введите название новой должности" prepend-inner-icon="mdi-briefcase-outline" />
          <!-- Avatar picker -->
          <div class="mb-3">
            <div class="text-caption text-medium-emphasis mb-1">Аватарка</div>
            <div class="d-flex flex-wrap" style="gap:8px">
              <div v-for="av in AVATARS" :key="av.id"
                class="avatar-pick"
                :class="{ 'avatar-pick-active': editDialog.avatar === av.id }"
                @click="editDialog.avatar = av.id">
                <v-avatar :color="av.color" size="40">
                  <v-icon :icon="av.icon" size="22" color="white" />
                </v-avatar>
              </div>
            </div>
          </div>
          <v-text-field v-model="editDialog.city" label="Город" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="editDialog.password" label="Новый пароль (оставьте пустым чтобы не менять)" variant="outlined" density="compact" type="password" />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="editDialog.saving" @click="saveEditUser">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 3. Delete user confirm dialog -->
    <v-dialog v-model="deleteDialog.show" max-width="340">
      <v-card>
        <v-card-title class="pa-4">Удалить пользователя?</v-card-title>
        <v-card-text>{{ deleteDialog.user?.full_name || deleteDialog.user?.username }}</v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 4. Hierarchy dialog -->
    <v-dialog v-model="hierarchyDialog.show" max-width="500">
      <v-card v-if="hierarchyDialog.user">
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-account-supervisor" color="teal" class="mr-2" />
          Подчиненные: {{ hierarchyDialog.user.full_name || hierarchyDialog.user.username }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="hierarchyDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <div class="mb-3">
            <v-autocomplete
              v-model="hierarchyDialog.newSubId"
              :items="hierarchyDialog.availableUsers"
              item-title="display"
              item-value="id"
              label="Добавить подчиненного"
              variant="outlined" density="compact"
              hide-details
            />
            <v-btn size="small" color="teal" variant="tonal" class="mt-2"
              :disabled="!hierarchyDialog.newSubId"
              :loading="hierarchyDialog.adding"
              @click="addSubordinate">
              Добавить
            </v-btn>
          </div>
          <v-divider class="mb-3" />
          <div class="text-body-2 font-weight-medium mb-2">Прямые подчиненные:</div>
          <div v-if="hierarchyDialog.subordinates.length === 0" class="text-caption text-medium-emphasis">
            Нет подчиненных
          </div>
          <v-chip
            v-for="s in hierarchyDialog.subordinates" :key="s.id"
            class="ma-1" size="small" :color="roleColor(s.role)" variant="tonal"
            closable @click:close="removeSubordinate(s.id)">
            {{ s.full_name || s.username }}
          </v-chip>
          <div v-if="hierarchyDialog.allSubordinates.length > hierarchyDialog.subordinates.length" class="mt-3">
            <div class="text-body-2 font-weight-medium mb-1">Все подчиненные (все уровни):</div>
            <v-chip
              v-for="s in allSubsNotDirect" :key="s.id"
              class="ma-1" size="x-small" color="grey" variant="tonal">
              {{ s.full_name || s.username }}
            </v-chip>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 5. User import Excel dialog -->
    <v-dialog v-model="userImportDialog.show" max-width="520">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-file-excel-outline" color="success" class="mr-2" />
          Импорт пользователей из Excel
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-btn variant="text" color="primary" size="small" prepend-icon="mdi-download" class="mb-4"
            @click="downloadUserTemplate">
            Скачать шаблон
          </v-btn>
          <v-file-input
            v-model="userImportDialog.file"
            label="Выберите Excel файл"
            accept=".xlsx,.xls"
            variant="outlined" density="compact"
            prepend-icon="mdi-file-upload-outline"
            :disabled="userImportDialog.loading"
          />
          <v-alert v-if="userImportDialog.result" :type="userImportDialog.result.errors?.length ? 'warning' : 'success'" class="mt-3" density="compact">
            Создано: {{ userImportDialog.result.created }}, пропущено: {{ userImportDialog.result.skipped }}
            <div v-if="userImportDialog.result.errors?.length" class="mt-2">
              <div v-for="(e, i) in userImportDialog.result.errors" :key="i" class="text-body-2">
                Строка {{ e.row }}: {{ e.error }}
              </div>
            </div>
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="userImportDialog.show = false">Закрыть</v-btn>
          <v-btn color="success" variant="flat"
            :loading="userImportDialog.loading"
            :disabled="!userImportDialog.file"
            @click="doUserImport">
            Импортировать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 6. Dept create/edit dialog -->
    <v-dialog v-model="deptDialog" max-width="520">
      <v-card>
        <v-card-title>{{ editingDept ? 'Редактировать отдел' : 'Новый отдел' }}</v-card-title>
        <v-card-text>
          <!-- Step hints for new department -->
          <v-alert v-if="!editingDept" type="info" variant="tonal" density="compact" class="mb-4">
            <div class="text-body-2 font-weight-medium mb-1">Как заполнить:</div>
            <ol class="text-body-2 pl-4" style="line-height:1.6">
              <li>Введите название отдела (например, "Отдел закупок")</li>
              <li>Привяжите к субсидии, если отдел работает по конкретной субсидии</li>
              <li>Начальника и сотрудников добавите после создания отдела</li>
            </ol>
          </v-alert>

          <v-text-field v-model="deptForm.name" label="Название отдела *" variant="outlined" density="compact" class="mb-3"
            placeholder="Например: Отдел закупок, Бухгалтерия, Склад" />

          <v-select v-model="deptForm.subsidy_id" :items="subsidies" item-title="name" item-value="id"
            label="Субсидия" variant="outlined" density="compact" clearable class="mb-3"
            hint="Если отдел обслуживает конкретную субсидию. Оставьте пустым для общего отдела." persistent-hint />

          <template v-if="editingDept">
            <v-select v-model="deptForm.head_user_id" :items="deptMemberItems" item-title="text" item-value="value"
              label="Начальник отдела" variant="outlined" density="compact" clearable class="mb-3"
              :hint="deptMemberItems.length === 0 ? 'Сначала добавьте сотрудников в отдел (кнопка справа)' : 'Выберите из сотрудников этого отдела'"
              persistent-hint :disabled="deptMemberItems.length === 0" />

            <v-select v-model="deptForm.parent_id" :items="otherDeptItems" item-title="text" item-value="value"
              label="Входит в состав отдела" variant="outlined" density="compact" clearable
              hint="Если это подотдел внутри другого (например, Сектор мониторинга внутри Отдела закупок)" persistent-hint />
          </template>

          <v-alert v-if="!editingDept" type="warning" variant="tonal" density="compact" class="mt-2">
            После создания отдела нажмите на него в дереве слева, чтобы добавить сотрудников и назначить начальника.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deptDialog = false">Отмена</v-btn>
          <v-btn color="primary" :disabled="!deptForm.name" @click="saveDept">{{ editingDept ? 'Сохранить' : 'Создать' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 7. Add member to dept dialog -->
    <v-dialog v-model="addMemberDialog" max-width="500">
      <v-card>
        <v-card-title class="d-flex align-center">
          Добавить сотрудника в отдел
          <v-spacer />
          <v-chip v-if="selectedDept" size="small" variant="tonal" color="primary">{{ selectedDept.name }}</v-chip>
        </v-card-title>
        <v-card-text>
          <!-- Toggle: existing or new -->
          <v-btn-toggle v-model="addMemberMode" mandatory density="compact" color="primary" class="mb-3" style="width:100%">
            <v-btn value="existing" size="small" style="flex:1"><v-icon icon="mdi-account-search" class="mr-1" size="16"/>Существующий</v-btn>
            <v-btn value="new" size="small" style="flex:1"><v-icon icon="mdi-account-plus" class="mr-1" size="16"/>Создать нового</v-btn>
          </v-btn-toggle>

          <!-- Existing user -->
          <template v-if="addMemberMode === 'existing'">
            <v-select v-model="memberForm.user_id" :items="userDropdownItems" item-title="text" item-value="value"
              label="Сотрудник *" variant="outlined" density="compact" class="mb-3"
              hint="Список пользователей вашей организации" persistent-hint />
            <v-combobox v-model="memberForm.position" :items="knownPositions" label="Должность в отделе" variant="outlined" density="compact"
              hint="Выберите из списка или введите свою" persistent-hint />
          </template>

          <!-- New user (inline creation) -->
          <template v-if="addMemberMode === 'new'">
            <v-text-field v-model="newMemberForm.full_name" label="ФИО *" variant="outlined" density="compact" class="mb-2"
              prepend-inner-icon="mdi-account" />
            <v-text-field v-model="newMemberForm.email" label="Email *" variant="outlined" density="compact" class="mb-2"
              type="email" prepend-inner-icon="mdi-email-outline"
              :rules="[v => !!v || 'Обязательное поле', v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Введите корректный email (например, ivanov@company.ru)']" />
            <v-text-field v-model="newMemberForm.phone" label="Телефон" variant="outlined" density="compact" class="mb-2"
              prepend-inner-icon="mdi-phone" placeholder="+7 (999) 123-45-67"
              hint="Для связи и интеграции с Telegram" persistent-hint />
            <v-text-field v-model="newMemberForm.password" label="Пароль *" type="password" variant="outlined" density="compact" class="mb-2"
              :rules="[v => !!v || 'Обязательное поле', v => v.length >= 6 || 'Минимум 6 символов']" />
            <v-text-field v-model="newMemberForm.password_confirm" label="Подтвердите пароль *" type="password" variant="outlined" density="compact" class="mb-2"
              :error="!!newMemberForm.password_confirm && newMemberForm.password !== newMemberForm.password_confirm"
              :error-messages="newMemberForm.password_confirm && newMemberForm.password !== newMemberForm.password_confirm ? 'Пароли не совпадают' : ''" />
            <v-select v-model="newMemberForm.role" :items="roleItems" item-title="label" item-value="value"
              label="Роль" variant="outlined" density="compact" class="mb-2" />
            <v-combobox v-model="newMemberForm.position" :items="knownPositions" label="Должность" variant="outlined" density="compact" class="mb-2"
              hint="Выберите из списка или введите свою" persistent-hint />
            <v-text-field v-model="newMemberForm.city" label="Город" variant="outlined" density="compact" />
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="addMemberDialog = false">Отмена</v-btn>
          <v-btn v-if="addMemberMode === 'existing'" color="primary" :disabled="!memberForm.user_id" @click="addMember">Добавить</v-btn>
          <v-btn v-else color="primary"
            :disabled="!newMemberForm.email || !newMemberForm.password || !newMemberForm.full_name || newMemberForm.password.length < 6 || newMemberForm.password !== newMemberForm.password_confirm || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newMemberForm.email)"
            :loading="newMemberSaving" @click="createAndAddMember">Создать и добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 7b. Edit member position dialog -->
    <v-dialog v-model="editMemberDialog" max-width="400">
      <v-card class="dialog-card">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-pencil" color="primary" class="mr-2" />
          Должность сотрудника
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="editMemberDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div class="text-body-2 font-weight-medium mb-3">{{ editMemberTarget?.name }}</div>
          <v-text-field v-model="editMemberForm.position" label="Должность в отделе"
            variant="outlined" density="compact" placeholder="Менеджер, Специалист, Ведущий инженер..."
            hide-details />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="editMemberDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveEditMember">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 8. Add delegate dialog -->
    <v-dialog v-model="delegateDialog" max-width="480">
      <v-card>
        <v-card-title>Дополнительное право на задачи</v-card-title>
        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            Начальник отдела <strong>автоматически</strong> может редактировать задачи своих сотрудников. Здесь вы можете дать такое право <strong>дополнительно</strong> любому другому пользователю.
          </v-alert>
          <v-select v-model="delegateForm.delegate_user_id" :items="userDropdownItems" item-title="text" item-value="value"
            label="Кто получает право редактировать *" variant="outlined" density="compact" class="mb-3"
            hint="Выберите пользователя, которому даете право" persistent-hint />
          <v-select v-model="delegateForm.target_user_id" :items="userDropdownItems" item-title="text" item-value="value"
            label="Чьи задачи можно будет редактировать *" variant="outlined" density="compact"
            hint="Выберите сотрудника организации" persistent-hint />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="delegateDialog = false">Отмена</v-btn>
          <v-btn color="primary" :disabled="!delegateForm.delegate_user_id || !delegateForm.target_user_id" @click="addDelegate">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 9. Dept import Excel dialog -->
    <v-dialog v-model="deptImportDialog" max-width="500">
      <v-card>
        <v-card-title>Импорт отделов из Excel</v-card-title>
        <v-card-text>
          <v-btn variant="outlined" size="small" prepend-icon="mdi-download" class="mb-3" @click="downloadDeptTemplate">Скачать шаблон</v-btn>
          <v-file-input v-model="deptImportFile" label="Выберите файл .xlsx" accept=".xlsx,.xls" variant="outlined" density="compact" />
          <v-alert v-if="deptImportResult" :type="deptImportResult.errors?.length ? 'warning' : 'success'" variant="tonal" class="mt-2">
            Создано отделов: {{ deptImportResult.created_departments }}, сотрудников: {{ deptImportResult.created_members }}
            <div v-for="err in deptImportResult.errors?.slice(0, 5)" :key="err.row" class="text-caption">Строка {{ err.row }}: {{ err.error }}</div>
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deptImportDialog = false">Закрыть</v-btn>
          <v-btn color="primary" :loading="deptImporting" :disabled="!deptImportFile" @click="doDeptImport">Импортировать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch, defineComponent, h, resolveComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import UserAvatar from '@/components/UserAvatar.vue'

// ── Types ──
interface UserItem {
  id: number
  username: string
  full_name?: string
  role: string
  city?: string
  department?: string
  position?: string
  email?: string
  avatar?: string
  photo_url?: string | null
  has_signature?: boolean
}
interface SubordinateItem { id: number; username: string; full_name?: string; role: string; avatar?: string }
interface TreeNode extends UserItem { subordinates?: SubordinateItem[] }

// ── Avatars ──
const AVATARS = [
  { id: 'man',     icon: 'mdi-face-man',             color: '#4CAF50', label: 'Парень' },
  { id: 'woman',   icon: 'mdi-face-woman',           color: '#E91E63', label: 'Девушка' },
  { id: 'cowboy',  icon: 'mdi-account-cowboy-hat',    color: '#FF9800', label: 'Ковбой' },
  { id: 'ninja',   icon: 'mdi-ninja',                color: '#607D8B', label: 'Ниндзя' },
  { id: 'robot',   icon: 'mdi-robot',                color: '#2196F3', label: 'Робот' },
  { id: 'cool',    icon: 'mdi-emoticon-cool-outline', color: '#9C27B0', label: 'Крутой' },
  { id: 'alien',   icon: 'mdi-alien',                color: '#00BCD4', label: 'Пришелец' },
  { id: 'pirate',  icon: 'mdi-pirate',               color: '#795548', label: 'Пират' },
]

function getAvatar(id?: string | null) {
  return AVATARS.find(a => a.id === id) || AVATARS[0]
}
function randomAvatarId() {
  return AVATARS[Math.floor(Math.random() * AVATARS.length)].id
}

// ── Constants ──
const ROLE_LABELS: Record<string, string> = {
  superadmin: 'Суперадмин',
  org_admin: 'Администратор',
  manager: 'Менеджер',
  employee: 'Сотрудник',
  admin: 'Администратор',
}
const roleItems = [
  { value: 'org_admin', label: 'Администратор' },
  { value: 'manager', label: 'Менеджер' },
  { value: 'employee', label: 'Сотрудник' },
]
const roleColor = (r: string) => ({
  superadmin: 'purple', org_admin: 'error', admin: 'error', manager: 'blue', employee: 'teal',
}[r] || 'grey')

// ── Route / Tab ──
const route = useRoute()
const router = useRouter()
const activeTab = ref((route.query.tab as string) || 'departments')

watch(activeTab, (val) => {
  router.replace({ query: { ...route.query, tab: val } })
})

// ── Auth ──
const currentRole = localStorage.getItem('user_role') || ''
const isAdmin = computed(() => ['admin', 'org_admin', 'superadmin'].includes(currentRole))

// ── Snackbar ──
const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

// ═══════════════════════════════════════════════════════════════
// SHARED STATE
// ═══════════════════════════════════════════════════════════════
const users = ref<UserItem[]>([])
const usersLoading = ref(false)
const subsidies = ref<any[]>([])
const knownDepartments = ref<string[]>([])
const knownPositions = ref<string[]>([])

// Dropdown items for user select components
const userDropdownItems = computed(() =>
  users.value.map(u => ({ text: u.full_name || u.username, value: u.id }))
)

/** Get avatar id for a department member by user_id */
function getMemberAvatar(userId: number): string | undefined {
  const u = users.value.find(x => x.id === userId)
  return u?.avatar
}

// ═══════════════════════════════════════════════════════════════
// TAB 2: USERS STATE
// ═══════════════════════════════════════════════════════════════
const userHeaders = [
  { title: '', key: 'avatar', width: 50, sortable: false },
  { title: 'Email', key: 'email', minWidth: 140 },
  { title: 'ФИО', key: 'full_name', minWidth: 140 },
  { title: 'Роль', key: 'role', width: 130 },
  { title: 'Отдел', key: 'department', minWidth: 120 },
  { title: 'Должность', key: 'position', minWidth: 120 },
  { title: 'Город', key: 'city', minWidth: 90 },
  { title: 'Подпись', key: 'has_signature', width: 90, sortable: false },
  { title: '', key: 'actions', width: 100, sortable: false },
]

// Task authority expand
const expandedUsers = ref<number[]>([])
const taskAuthority = ref<Record<number, { can_assign_to: any[]; can_receive_from: any[] }>>({})
const taskAuthorityLoading = ref<Record<number, boolean>>({})

async function loadTaskAuthority(userId: number) {
  if (taskAuthority.value[userId]) return
  taskAuthorityLoading.value = { ...taskAuthorityLoading.value, [userId]: true }
  try {
    const data = await apiFetch<{ can_assign_to: any[]; can_receive_from: any[] }>(`/users/${userId}/task-authority`)
    taskAuthority.value = { ...taskAuthority.value, [userId]: data }
  } catch {
    taskAuthority.value = { ...taskAuthority.value, [userId]: { can_assign_to: [], can_receive_from: [] } }
  } finally {
    taskAuthorityLoading.value = { ...taskAuthorityLoading.value, [userId]: false }
  }
}

async function onUserExpanded(expanded: number[]) {
  for (const uid of expanded) {
    if (!taskAuthority.value[uid]) {
      loadTaskAuthority(uid)
    }
  }
}

const createDialog = reactive({
  show: false, full_name: '', email: '', password: '', password_confirm: '',
  role: 'employee', city: '', department: '', position: '', phone: '', telegram_id: '', avatar: '', saving: false,
  org_id: null as number | null, subsidy_id: null as number | null,
})
const organizations = ref<any[]>([])
const currentOrgId = parseInt(localStorage.getItem('user_org_id') || '0') || null
const currentOrgName = localStorage.getItem('user_org_name') || ''
const isSuperadmin = computed(() => currentRole === 'superadmin')

const editDialog = reactive({
  show: false, userId: 0, username: '', full_name: '', role: 'employee', city: '',
  department: '', position: '', email: '', password: '', avatar: '', saving: false,
})

const deleteDialog = reactive({ show: false, user: null as UserItem | null, deleting: false })

const userImportDialog = reactive({
  show: false, file: null as File | null, loading: false,
  result: null as { created: number; skipped: number; errors: { row: number; error: string }[] } | null,
})

// ── TAB 3: HIERARCHY STATE ──
const treeLoading = ref(false)
const hierarchyTree = ref<TreeNode[]>([])

const hierarchyDialog = reactive({
  show: false,
  user: null as UserItem | null,
  subordinates: [] as SubordinateItem[],
  allSubordinates: [] as SubordinateItem[],
  newSubId: null as number | null,
  adding: false,
  availableUsers: [] as { id: number; display: string }[],
})

const allSubsNotDirect = computed(() =>
  hierarchyDialog.allSubordinates.filter(a => !hierarchyDialog.subordinates.some(s => s.id === a.id))
)

// ═══════════════════════════════════════════════════════════════
// TAB 1: DEPARTMENTS STATE
// ═══════════════════════════════════════════════════════════════
const deptLoading = ref(false)
const deptTree = ref<any[]>([])
const selectedDept = ref<any>(null)
const deptMembers = ref<any[]>([])
const delegates = ref<any[]>([])
const filterSubsidyId = ref<number | null>(null)

// Dept dialog
const deptDialog = ref(false)
const editingDept = ref<any>(null)
const deptForm = ref({ name: '', subsidy_id: null as number | null, head_user_id: null as number | null, parent_id: null as number | null })

// Member dialog
const addMemberDialog = ref(false)
const addMemberMode = ref<'existing' | 'new'>('existing')
const memberForm = ref({ user_id: null as number | null, position: '' })
const newMemberForm = ref({ email: '', full_name: '', password: '', password_confirm: '', phone: '', role: 'employee', position: '', city: '' })
const newMemberSaving = ref(false)

// Edit member position dialog
const editMemberDialog = ref(false)
const editMemberTarget = ref<any>(null)
const editMemberForm = ref({ position: '' })

// Delegate dialog
const delegateDialog = ref(false)
const delegateForm = ref({ target_user_id: null as number | null, delegate_user_id: null as number | null })

// Dept import
const deptImportDialog = ref(false)
const deptImportFile = ref<File | null>(null)
const deptImporting = ref(false)
const deptImportResult = ref<any>(null)

// Computed from dept
const memberUserItems = computed(() =>
  deptMembers.value.map(m => ({ text: m.user_name || '?', value: m.user_id }))
)
const deptMemberItems = computed(() => {
  if (!selectedDept.value) return []
  const ms = selectedDept.value.members || []
  return ms.map((m: any) => ({ text: m.name || '?', value: m.user_id }))
})
const otherDeptItems = computed(() =>
  flatDepts(deptTree.value)
    .filter(d => !editingDept.value || d.id !== editingDept.value.id)
    .map(d => ({ text: d.name, value: d.id }))
)

function flatDepts(nodes: any[]): any[] {
  const out: any[] = []
  for (const n of nodes) {
    out.push(n)
    if (n.children) out.push(...flatDepts(n.children))
  }
  return out
}

// ── Recursive dept-node component ──
const DeptNode = defineComponent({
  name: 'DeptNode',
  props: { node: Object, depth: { type: Number, default: 0 } },
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

      const items = [
        h('div', {
          class: 'dept-tree-row', style: { paddingLeft: indent + 'px' },
          onClick: () => emit('select', n),
        }, [
          n.children?.length
            ? h(VIcon, {
                icon: expanded.value ? 'mdi-chevron-down' : 'mdi-chevron-right',
                size: 18, class: 'mr-1 dept-chevron',
                onClick: (e: Event) => { e.stopPropagation(); expanded.value = !expanded.value },
              })
            : h('span', { style: 'width:22px;display:inline-block' }),
          h(VIcon, { icon: 'mdi-folder-account', size: 18, color: 'primary', class: 'mr-2' }),
          h('span', { class: 'font-weight-medium text-body-2' }, n.name),
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
            h(VBtn, { icon: 'mdi-pencil', size: 'x-small', variant: 'text', color: 'primary', class: 'dept-member-action', title: 'Изменить должность', onClick: (e: Event) => { e.stopPropagation(); emit('edit-member', { dept: n, member: m }) } }),
            h(VBtn, { icon: 'mdi-close', size: 'x-small', variant: 'text', color: 'error', class: 'dept-member-action', title: 'Убрать из отдела', onClick: (e: Event) => { e.stopPropagation(); emit('remove-member', { deptId: n.id, userId: m.user_id }) } }),
          ])
        ) : []),
        // Children
        ...(expanded.value ? (n.children || []).map((child: any) =>
          h(DeptNode, {
            node: child, depth: props.depth + 1,
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

// ═══════════════════════════════════════════════════════════════
// FUNCTIONS: Users
// ═══════════════════════════════════════════════════════════════
function normalizeDepartment(val: string | null | undefined): string | null {
  if (!val || typeof val !== 'string') return null
  return val.trim().split(/\s+/).map(w =>
    w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
  ).join(' ')
}

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await apiFetch<UserItem[]>('/users/')
  } finally {
    usersLoading.value = false
  }
}

function openCreateUser() {
  createDialog.full_name = ''
  createDialog.email = ''
  createDialog.password = ''
  createDialog.password_confirm = ''
  createDialog.role = 'employee'
  createDialog.city = ''
  createDialog.department = ''
  createDialog.position = ''
  createDialog.phone = ''
  createDialog.telegram_id = ''
  createDialog.avatar = ''
  createDialog.org_id = currentOrgId
  createDialog.subsidy_id = null
  createDialog.saving = false
  createDialog.show = true
  // Load organizations for superadmin
  if (isSuperadmin.value && organizations.value.length === 0) {
    apiFetch<any[]>('/organizations/').then(r => { organizations.value = r }).catch(() => {})
  }
}

async function saveUser() {
  if (createDialog.password !== createDialog.password_confirm) {
    showSnack('Пароли не совпадают', 'error')
    return
  }
  if (!createDialog.email) {
    showSnack('Email обязателен', 'error')
    return
  }
  createDialog.saving = true
  try {
    const u = await apiFetch<UserItem>('/users/', {
      method: 'POST',
      body: {
        email: createDialog.email,
        full_name: createDialog.full_name || null,
        password: createDialog.password,
        role: createDialog.role,
        city: createDialog.city || null,
        department: normalizeDepartment(createDialog.department) || null,
        position: createDialog.position || null,
        phone: createDialog.phone || null,
        telegram_id: createDialog.telegram_id || null,
        avatar: createDialog.avatar || randomAvatarId(),
        org_id: isSuperadmin.value ? createDialog.org_id : null,
      },
    })
    users.value = [...users.value, u]
    createDialog.show = false
    showSnack('Сотрудник создан')
    // Reload dept tree if department was specified
    if (createDialog.department) {
      await loadDeptTree()
    }
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    createDialog.saving = false
  }
}

function openEditUser(item: UserItem) {
  editDialog.userId = item.id
  editDialog.username = item.username
  editDialog.full_name = item.full_name || ''
  editDialog.role = item.role
  editDialog.city = item.city || ''
  editDialog.department = item.department || ''
  editDialog.position = item.position || ''
  editDialog.email = item.email || ''
  editDialog.password = ''
  editDialog.avatar = item.avatar || ''
  editDialog.show = true
}

async function saveEditUser() {
  editDialog.saving = true
  try {
    const body: any = {
      full_name: editDialog.full_name || null,
      role: editDialog.role,
      city: editDialog.city || null,
      department: normalizeDepartment(editDialog.department) || null,
      position: editDialog.position || null,
      email: editDialog.email || null,
      avatar: editDialog.avatar || null,
    }
    if (editDialog.password) body.password = editDialog.password
    const updated = await apiFetch<UserItem>(`/users/${editDialog.userId}`, {
      method: 'PATCH', body: JSON.stringify(body),
    })
    const idx = users.value.findIndex(u => u.id === editDialog.userId)
    if (idx >= 0) users.value.splice(idx, 1, updated)
    editDialog.show = false
    showSnack('Пользователь обновлен')
    loadHierarchyTree()
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка', 'error')
  } finally {
    editDialog.saving = false
  }
}

function confirmDelete(u: UserItem) {
  deleteDialog.user = u
  deleteDialog.show = true
}

async function doDelete() {
  if (!deleteDialog.user) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/users/${deleteDialog.user.id}`, { method: 'DELETE' })
    users.value = users.value.filter(u => u.id !== deleteDialog.user!.id)
    deleteDialog.show = false
    showSnack('Пользователь удален')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

async function downloadUserTemplate() {
  const token = localStorage.getItem('auth_token')
  const resp = await fetch('/api/users/import/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'users_template.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

async function doUserImport() {
  if (!userImportDialog.file) return
  userImportDialog.loading = true
  userImportDialog.result = null
  try {
    const token = localStorage.getItem('auth_token')
    const fd = new FormData()
    fd.append('file', userImportDialog.file)
    const resp = await fetch('/api/users/import/excel', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: fd,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.message || err.detail || `Ошибка ${resp.status}`)
    }
    userImportDialog.result = await resp.json()
    if (userImportDialog.result!.created > 0) {
      showSnack(`Импортировано ${userImportDialog.result!.created} пользователей`)
      loadUsers()
    }
  } catch (e: any) {
    showSnack(e.message || 'Ошибка импорта', 'error')
  } finally {
    userImportDialog.loading = false
  }
}

// ═══════════════════════════════════════════════════════════════
// FUNCTIONS: Hierarchy
// ═══════════════════════════════════════════════════════════════
async function loadHierarchyTree() {
  treeLoading.value = true
  try {
    const allUsers = await apiFetch<UserItem[]>('/users/')
    const tree: TreeNode[] = []
    for (const u of allUsers) {
      const subs = await apiFetch<SubordinateItem[]>(`/users/${u.id}/subordinates`).catch(() => [])
      if (subs.length > 0) {
        tree.push({ ...u, subordinates: subs })
      }
    }
    hierarchyTree.value = tree
  } finally {
    treeLoading.value = false
  }
}

async function openHierarchyDialog(u: UserItem) {
  hierarchyDialog.user = u
  hierarchyDialog.newSubId = null
  hierarchyDialog.show = true
  hierarchyDialog.subordinates = await apiFetch<SubordinateItem[]>(`/users/${u.id}/subordinates`).catch(() => [])
  hierarchyDialog.allSubordinates = await apiFetch<SubordinateItem[]>(`/users/${u.id}/subordinates/all`).catch(() => [])
  const allSubIds = new Set(hierarchyDialog.allSubordinates.map(s => s.id))
  hierarchyDialog.availableUsers = users.value
    .filter(x => x.id !== u.id && !allSubIds.has(x.id))
    .map(x => ({ id: x.id, display: x.full_name ? `${x.full_name} (${x.username})` : x.username }))
}

async function addSubordinate() {
  if (!hierarchyDialog.user || !hierarchyDialog.newSubId) return
  hierarchyDialog.adding = true
  try {
    const s = await apiFetch<SubordinateItem>(`/users/${hierarchyDialog.user.id}/subordinates`, {
      method: 'POST',
      body: { subordinate_id: hierarchyDialog.newSubId },
    })
    hierarchyDialog.subordinates = [...hierarchyDialog.subordinates, s]
    hierarchyDialog.allSubordinates = [...hierarchyDialog.allSubordinates, s]
    hierarchyDialog.availableUsers = hierarchyDialog.availableUsers.filter(x => x.id !== hierarchyDialog.newSubId)
    hierarchyDialog.newSubId = null
    loadHierarchyTree()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    hierarchyDialog.adding = false
  }
}

async function removeSubordinate(subId: number) {
  if (!hierarchyDialog.user) return
  try {
    await apiFetch(`/users/${hierarchyDialog.user.id}/subordinates/${subId}`, { method: 'DELETE' })
    hierarchyDialog.subordinates = hierarchyDialog.subordinates.filter(s => s.id !== subId)
    hierarchyDialog.allSubordinates = hierarchyDialog.allSubordinates.filter(s => s.id !== subId)
    loadHierarchyTree()
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  }
}

// ═══════════════════════════════════════════════════════════════
// FUNCTIONS: Departments
// ═══════════════════════════════════════════════════════════════
async function loadDeptTree() {
  deptLoading.value = true
  const params = filterSubsidyId.value ? `?subsidy_id=${filterSubsidyId.value}` : ''
  try { deptTree.value = await apiFetch<any[]>(`/departments/tree${params}`) } catch { deptTree.value = [] }
  finally { deptLoading.value = false }
}

watch(filterSubsidyId, () => { loadDeptTree() })

function openCreateDept() {
  editingDept.value = null
  deptForm.value = { name: '', subsidy_id: filterSubsidyId.value, head_user_id: null, parent_id: null }
  deptDialog.value = true
}

async function openEditDept(node: any) {
  selectedDept.value = node
  await loadDeptMembers(node.id)
  editingDept.value = node
  deptForm.value = { name: node.name, subsidy_id: node.subsidy_id, head_user_id: node.head_user_id, parent_id: node.parent_id }
  deptDialog.value = true
}

async function saveDept() {
  try {
    if (editingDept.value) {
      await apiFetch(`/departments/${editingDept.value.id}`, { method: 'PATCH', body: JSON.stringify(deptForm.value) })
    } else {
      await apiFetch('/departments/', { method: 'POST', body: JSON.stringify(deptForm.value) })
    }
    deptDialog.value = false
    showSnack(editingDept.value ? 'Отдел обновлен' : 'Отдел создан')
    await loadDeptTree()
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function deleteDept(node: any) {
  if (!confirm(`Удалить отдел "${node.name}"?`)) return
  try {
    await apiFetch(`/departments/${node.id}`, { method: 'DELETE' })
    if (selectedDept.value?.id === node.id) selectedDept.value = null
    showSnack('Отдел удален')
    await loadDeptTree()
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function selectDept(node: any) {
  selectedDept.value = node
  await Promise.all([loadDeptMembers(node.id), loadDelegates()])
}

async function loadDeptMembers(deptId: number) {
  try { deptMembers.value = await apiFetch<any[]>(`/departments/${deptId}/members`) } catch { deptMembers.value = [] }
}

async function loadDelegates() {
  try { delegates.value = await apiFetch<any[]>('/departments/delegates') } catch { delegates.value = [] }
}

async function addMember() {
  if (!selectedDept.value || !memberForm.value.user_id) return
  try {
    await apiFetch(`/departments/${selectedDept.value.id}/members`, {
      method: 'POST', body: JSON.stringify(memberForm.value),
    })
    addMemberDialog.value = false
    memberForm.value = { user_id: null, position: '' }
    await loadDeptMembers(selectedDept.value.id)
    await loadDeptTree()
    showSnack('Сотрудник добавлен в отдел')
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function createAndAddMember() {
  if (!selectedDept.value) return
  newMemberSaving.value = true
  try {
    // 1. Create user
    const user = await apiFetch<any>('/users/', {
      method: 'POST',
      body: JSON.stringify({
        email: newMemberForm.value.email,
        password: newMemberForm.value.password,
        full_name: newMemberForm.value.full_name,
        role: newMemberForm.value.role,
        city: newMemberForm.value.city || null,
        phone: newMemberForm.value.phone || null,
        department: selectedDept.value.name,
        position: newMemberForm.value.position || null,
      }),
    })
    // 2. Add to department
    await apiFetch(`/departments/${selectedDept.value.id}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: user.id, position: newMemberForm.value.position || null }),
    })
    addMemberDialog.value = false
    newMemberForm.value = { email: '', full_name: '', password: '', role: 'employee', position: '', city: '' }
    // Refresh all
    await Promise.all([loadUsers(), loadDeptMembers(selectedDept.value.id), loadDeptTree()])
    showSnack(`Сотрудник ${user.full_name || user.username} создан и добавлен в отдел`)
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка при создании сотрудника', 'error')
  } finally {
    newMemberSaving.value = false
  }
}

async function removeMember(userId: number) {
  if (!selectedDept.value) return
  try {
    await apiFetch(`/departments/${selectedDept.value.id}/members/${userId}`, { method: 'DELETE' })
    await loadDeptMembers(selectedDept.value.id)
    await loadDeptTree()
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

// Inline handlers for tree buttons
function onAddMemberInline(dept: any) {
  selectedDept.value = dept
  memberForm.value = { user_id: null, position: '' }
  newMemberForm.value = { email: '', full_name: '', password: '', role: 'employee', position: '', city: '' }
  addMemberMode.value = 'existing'
  addMemberDialog.value = true
}

function onEditMemberInline(payload: { dept: any; member: any }) {
  selectedDept.value = payload.dept
  editMemberTarget.value = payload.member
  editMemberForm.value = { position: payload.member.position || '' }
  editMemberDialog.value = true
}

async function onRemoveMemberInline(payload: { deptId: number; userId: number }) {
  try {
    await apiFetch(`/departments/${payload.deptId}/members/${payload.userId}`, { method: 'DELETE' })
    await loadDeptTree()
    if (selectedDept.value?.id === payload.deptId) {
      await loadDeptMembers(payload.deptId)
    }
    showSnack('Сотрудник убран из отдела')
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function saveEditMember() {
  if (!selectedDept.value || !editMemberTarget.value) return
  try {
    await apiFetch(`/departments/${selectedDept.value.id}/members/${editMemberTarget.value.user_id}`, {
      method: 'PATCH',
      body: JSON.stringify({ position: editMemberForm.value.position }),
    })
    editMemberDialog.value = false
    await loadDeptTree()
    if (selectedDept.value) await loadDeptMembers(selectedDept.value.id)
    showSnack('Должность обновлена')
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function addDelegate() {
  try {
    await apiFetch('/departments/delegates', { method: 'POST', body: JSON.stringify(delegateForm.value) })
    delegateDialog.value = false
    delegateForm.value = { target_user_id: null, delegate_user_id: null }
    await loadDelegates()
    showSnack('Делегирование добавлено')
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function removeDelegate(id: number) {
  try {
    await apiFetch(`/departments/delegates/${id}`, { method: 'DELETE' })
    await loadDelegates()
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function downloadDeptTemplate() {
  const token = localStorage.getItem('auth_token')
  const res = await fetch('/api/departments/import/template', { headers: { Authorization: `Bearer ${token}` } })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'departments_template.xlsx'; a.click()
  URL.revokeObjectURL(url)
}

async function doDeptImport() {
  if (!deptImportFile.value) return
  deptImporting.value = true
  deptImportResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', deptImportFile.value)
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/departments/import/excel', {
      method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: fd,
    })
    deptImportResult.value = await res.json()
    await loadDeptTree()
  } catch (e) { showSnack('Ошибка импорта', 'error') }
  finally { deptImporting.value = false }
}

// ═══════════════════════════════════════════════════════════════
// LIFECYCLE
// ═══════════════════════════════════════════════════════════════
onMounted(async () => {
  loadUsers()
  loadDeptTree()
  loadHierarchyTree()
  try { subsidies.value = await apiFetch<any[]>('/subsidies/') } catch { subsidies.value = [] }
  try { knownDepartments.value = await apiFetch<string[]>('/users/dictionaries/departments') } catch {}
  try { knownPositions.value = await apiFetch<string[]>('/users/dictionaries/positions') } catch {}
})
</script>

<style>
/* Department tree styles — NOT scoped, because DeptNode is a child component via defineComponent */
.staff-view .dept-tree-row {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  margin: 6px 4px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 2px solid rgba(var(--v-theme-primary), 0.25);
  border-left: 5px solid rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
  box-shadow: 0 2px 4px rgba(0,0,0,0.08);
}
.staff-view .dept-tree-row:hover {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 4px 12px rgba(var(--v-theme-primary), 0.2);
  transform: translateX(4px);
}
.staff-view .dept-tree-row:hover .dept-row-arrow {
  opacity: 1;
  transform: translateX(3px);
}
.staff-view .dept-tree-row:active {
  background: rgba(var(--v-theme-primary), 0.18);
  transform: translateX(2px);
}
.staff-view .dept-row-arrow {
  opacity: 0.4;
  transition: all 0.2s ease;
}
.staff-view .dept-chevron { cursor: pointer; }
.staff-view .dept-member-row {
  display: flex;
  align-items: center;
  padding: 5px 14px;
  margin: 1px 4px 1px 8px;
  border-radius: 6px;
  opacity: 0.85;
  transition: all 0.15s;
}
.staff-view .dept-member-row:hover { opacity: 1; background: var(--crm-surface-hover); }
.staff-view .dept-member-action { opacity: 0.3; transition: opacity 0.15s; }
.staff-view .dept-member-row:hover .dept-member-action { opacity: 1; }
.staff-view .feo-set-hint {
  cursor: pointer;
  text-decoration: underline dotted;
  color: #3B82F6;
}
.staff-view .feo-set-hint:hover { color: #2563EB; }
</style>

<style scoped>
/* Hierarchy tree styles */
.tree-node { margin-bottom: 16px; }
.tree-label { display: flex; align-items: center; padding: 4px 0; }
.tree-children { margin-left: 24px; border-left: 2px solid var(--crm-border); padding-left: 12px; margin-top: 4px; }
.tree-child { display: flex; align-items: center; padding: 3px 0; gap: 4px; }

/* Avatar picker styles */
.avatar-pick { cursor: pointer; border-radius: 50%; padding: 2px; border: 2px solid transparent; transition: all 0.2s; }
.avatar-pick:hover { border-color: rgba(var(--v-theme-primary), 0.3); transform: scale(1.1); }
.avatar-pick-active { border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.4); }
</style>
