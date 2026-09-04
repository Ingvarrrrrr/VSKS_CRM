<template>
  <v-container fluid class="pa-6 staff-view">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Персонал</h1>
        <span class="text-body-2 text-medium-emphasis">Отделы, сотрудники и иерархия</span>
      </div>
      <v-spacer />
      <v-btn v-if="isAdmin" color="primary" size="small" variant="outlined" prepend-icon="mdi-domain-plus" @click="router.push({ path: '/organizations', query: { create: '1' } })">
        Добавить организацию
      </v-btn>
      <v-btn v-if="isAdmin" color="primary" size="small" variant="outlined" prepend-icon="mdi-folder-plus" @click="openCreateDeptFromHeader">
        Добавить отдел
      </v-btn>
      <v-btn v-if="isAdmin" color="primary" size="small" prepend-icon="mdi-account-plus" @click="openCreateUser()">
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
        <div class="d-flex align-center mb-4 flex-wrap dept-toolbar" style="gap:8px">
          <v-select
            v-model="filterDeptOrgId"
            v-if="organizations.length > 1"
            :items="organizations"
            item-title="name" item-value="id"
            label="Организация" variant="outlined" density="compact" clearable
            style="max-width:200px" hide-details
          />
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name" item-value="id"
            label="Субсидия" variant="outlined" density="compact" clearable
            style="max-width:260px" hide-details
          />
          <v-autocomplete
            v-model="filterDeptUserId"
            :items="users.map(u => ({ title: u.full_name || u.username, value: u.id }))"
            item-title="title" item-value="value"
            label="Сотрудник" variant="outlined" density="compact" clearable
            style="max-width:220px" hide-details
          />
          <v-spacer />
          <RegistryExportButton
            title="Отделы"
            :get-columns="getDeptExportColumns"
            :get-rows="getDeptExportRows"
            :get-capture-el="() => deptArea"
            @error="(msg) => showSnack(msg, 'error')"
          />
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

        <div ref="deptArea">
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
                  <div v-for="node in filteredDeptTree" :key="node.id">
                    <dept-node :node="node" :depth="0" :multi-org="organizations.length > 1" @select="selectDept" @edit="openEditDept" @delete="deleteDept" @add-member="onAddMemberInline" @edit-member="onEditMemberInline" @remove-member="onRemoveMemberInline" />
                  </div>
                </div>
                <!-- Вне отделов -->
                <div v-if="!deptLoading && unassignedUsers.length > 0" class="mt-2">
                  <div class="unassigned-folder-header d-flex align-center pa-2 rounded cursor-pointer"
                    @click="unassignedExpanded = !unassignedExpanded">
                    <v-icon :icon="unassignedExpanded ? 'mdi-folder-open-outline' : 'mdi-folder-outline'"
                      color="grey" size="18" class="mr-2" />
                    <span class="text-body-2 font-weight-medium text-medium-emphasis">Вне отделов</span>
                    <v-chip size="x-small" class="ml-2" color="grey" variant="tonal">{{ unassignedUsers.length }}</v-chip>
                    <v-icon :icon="unassignedExpanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" class="ml-auto" color="grey" />
                  </div>
                  <v-expand-transition>
                    <div v-if="unassignedExpanded" class="pl-6">
                      <div v-for="u in unassignedUsers" :key="u.id"
                        class="d-flex align-center pa-1 rounded unassigned-user-row"
                        @click="openEditUser(u)">
                        <UserAvatar :photo-url="u.photo_url" :avatar="u.avatar" :size="26" square class="mr-2 flex-shrink-0" />
                        <span class="text-body-2">{{ u.full_name || u.username }}</span>
                        <span class="text-caption text-medium-emphasis ml-2">{{ u.position || '' }}</span>
                        <v-spacer />
                        <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" class="dept-member-action"
                          title="Редактировать сотрудника" @click.stop="openEditUser(u)" />
                        <v-btn v-if="isAdmin" icon="mdi-close" size="x-small" variant="text" color="error" class="dept-member-action"
                          title="Удалить пользователя" @click.stop="confirmDelete(u)" />
                      </div>
                    </div>
                  </v-expand-transition>
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
                      <UserAvatar :photo-url="getMemberPhotoUrl(m.user_id)" :avatar="getMemberAvatar(m.user_id)" :size="28" square />
                    </template>
                    <v-list-item-title>{{ m.user_name }}</v-list-item-title>
                    <template v-slot:append>
                      <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" class="mr-1" @click="openEditUserById(m.user_id)" title="Редактировать сотрудника" />
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
        </div>
      </v-window-item>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TAB 2: Users                                           -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <v-window-item value="users">
        <div class="d-flex align-center mb-4 flex-wrap" style="gap:8px">
          <v-select
            v-model="filterUserOrgId"
            v-if="organizations.length > 1"
            :items="organizations"
            item-title="name" item-value="id"
            label="Организация" variant="outlined" density="compact" clearable
            style="max-width:200px" hide-details
          />
          <v-select
            v-model="filterUserRole"
            :items="roleItems"
            item-title="label" item-value="value"
            label="Роль" variant="outlined" density="compact" clearable
            style="max-width:160px" hide-details
          />
          <v-text-field
            v-model="filterUserSearch"
            label="Поиск по ФИО / логину / ИНН"
            prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" clearable hide-details
            style="max-width:280px"
          />
          <v-spacer />
          <v-btn v-if="isAdmin" variant="outlined" size="small" prepend-icon="mdi-download" @click="downloadUserTemplate">
            Шаблон
          </v-btn>
          <v-btn v-if="isAdmin" color="success" variant="tonal" size="small" prepend-icon="mdi-file-excel-outline" @click="userImportDialog.show = true">
            Импорт из Excel
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
          <RegistryExportButton
            title="Персонал"
            :get-columns="() => visibleHeaders.filter(h => !['actions','avatar','data-table-expand','data-table-select'].includes(h.key) && !!h.title).map(h => ({ key: h.key, title: h.title, align: h.align }))"
            :get-rows="() => filteredUsers"
            :get-capture-el="() => registryArea"
            @error="(msg) => showSnack(msg, 'error')"
          />
          <v-btn-toggle
            v-if="!staffMobile"
            v-model="staffViewMode"
            mandatory
            density="compact"
            variant="outlined"
            divided
            class="ml-1"
          >
            <v-btn value="table" size="small" icon="mdi-table" title="Таблица" />
            <v-btn value="cards" size="small" icon="mdi-view-grid" title="Карточки" />
          </v-btn-toggle>
        </div>

        <!-- Bulk actions bar -->
        <div v-if="isAdmin && selectedUsers.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
          <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
          <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedUsers.length }}</span>
          <v-spacer />
          <v-btn color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDeleteUsers">
            Удалить выбранных
          </v-btn>
          <v-btn variant="text" size="small" @click="selectedUsers = []">Снять выделение</v-btn>
        </div>

        <!-- B6: кнопка дубликатов по ИНН -->
        <v-alert
          v-if="isAdmin && duplicateInnGroups.length > 0"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
          icon="mdi-account-multiple-outline"
        >
          <div class="d-flex align-center flex-wrap" style="gap:8px">
            <span class="text-body-2">Найдены дубликаты по ИНН: <strong>{{ duplicateInnGroups.length }}</strong> группы</span>
            <v-btn size="x-small" variant="tonal" color="warning" @click="innDupDialog = true">
              Просмотреть
            </v-btn>
          </div>
        </v-alert>

        <div ref="registryArea">
        <v-data-table
            v-if="staffEffectiveView === 'table'"
            v-resizable-columns="'staff'"
            :headers="visibleHeaders"
            :items="filteredUsers"
            :loading="usersLoading"
            density="comfortable"
            show-expand
            expand-on-click
            item-value="id"
            v-model:expanded="expandedUsers"
            @update:expanded="onUserExpanded"
            v-model:selected="selectedUsers"
            :show-select="isAdmin"
          >
            <template v-slot:item.avatar="{ item }">
              <UserAvatar :photo-url="item.photo_url" :avatar="item.avatar" :size="32" square />
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
                      <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-sitemap"
                        @click.stop="activeTab = 'hierarchy'">
                        Настроить в Иерархии
                      </v-btn>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </v-data-table>

        <!-- Cards view -->
        <div v-else>
          <div v-if="filteredUsers.length === 0" class="text-center py-12 text-medium-emphasis">
            <v-icon icon="mdi-account-group-outline" size="48" color="grey-lighten-2" class="mb-3 d-block" />
            Нет сотрудников
          </div>
          <v-row v-else dense>
            <v-col
              v-for="u in staffPagedCards"
              :key="u.id"
              cols="12"
              sm="6"
              lg="4"
            >
              <v-card
                variant="outlined"
                class="pa-0 h-100"
                hover
                @click="openEditUser(u)"
              >
                <v-card-text class="pa-3">
                  <div class="d-flex align-center mb-2">
                    <v-checkbox-btn
                      v-if="isAdmin"
                      :model-value="selectedUsers.some(s => (s as any).id === u.id || s === u.id)"
                      density="compact"
                      class="mr-1 flex-shrink-0"
                      @click.stop
                      @update:model-value="toggleUserSelection(u)"
                    />
                    <v-avatar size="38" class="mr-3 flex-shrink-0" color="primary" variant="tonal">
                      <UserAvatar
                        v-if="u.photo_url || u.avatar"
                        :photo-url="u.photo_url"
                        :avatar="u.avatar"
                        :size="38"
                        square
                      />
                      <span v-else class="text-body-2 font-weight-bold">
                        {{ (u.full_name || u.username || '?').charAt(0).toUpperCase() }}
                      </span>
                    </v-avatar>
                    <div class="flex-grow-1 min-width-0">
                      <div class="text-body-1 font-weight-bold text-truncate">
                        {{ u.full_name || u.username }}
                      </div>
                      <div class="text-caption text-medium-emphasis text-truncate">
                        {{ u.position || '—' }}
                      </div>
                    </div>
                    <v-chip :color="roleColor(u.role)" size="x-small" variant="tonal" class="ml-2 flex-shrink-0">
                      {{ ROLE_LABELS[u.role] || u.role }}
                    </v-chip>
                  </div>
                  <div v-if="u.email" class="d-flex align-center text-body-2 text-truncate mb-1">
                    <v-icon icon="mdi-email-outline" size="14" class="mr-1 flex-shrink-0" color="grey" />
                    {{ u.email }}
                  </div>
                  <div v-if="u.department" class="d-flex align-center text-caption text-medium-emphasis text-truncate">
                    <v-icon icon="mdi-sitemap-outline" size="14" class="mr-1 flex-shrink-0" color="grey" />
                    {{ u.department }}
                  </div>
                </v-card-text>
                <v-card-actions class="pa-2 pt-0" @click.stop>
                  <v-spacer />
                  <template v-if="isAdmin">
                    <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
                      @click.stop="openEditUser(u)" title="Редактировать" />
                    <v-btn icon="mdi-account-supervisor" size="x-small" variant="text" color="teal"
                      @click.stop="openHierarchyDialog(u)" title="Настроить подчиненных" />
                    <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
                      @click.stop="confirmDelete(u)" :disabled="u.username === 'admin'" />
                  </template>
                </v-card-actions>
              </v-card>
            </v-col>
          </v-row>
          <v-pagination
            v-if="staffCardsTotalPages > 1"
            v-model="staffCardsPage"
            :length="staffCardsTotalPages"
            density="compact"
            :total-visible="7"
            class="d-flex justify-center mt-4"
          />
        </div>
        </div>
      </v-window-item>

      <!-- ═══════════════════════════════════════════════════════ -->
      <!-- TAB 3: Hierarchy                                       -->
      <!-- ═══════════════════════════════════════════════════════ -->
      <v-window-item value="hierarchy">
        <div class="d-flex align-center mb-3">
          <v-spacer />
          <RegistryExportButton
            title="Иерархия"
            :get-columns="getHierarchyExportColumns"
            :get-rows="getHierarchyExportRows"
            :get-capture-el="() => hierarchyArea"
            @error="(msg) => showSnack(msg, 'error')"
          />
        </div>
        <div ref="hierarchyArea">
          <HierarchyView ref="hierarchyRef" :embedded="true" @edit-user="openEditUserById" @edit-dept="openEditDeptById" @create-user="openCreateUser" @data-changed="onHierarchyDataChanged" />
        </div>
      </v-window-item>
    </v-window>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!-- DIALOGS (at root level, NOT inside tabs)                   -->
    <!-- ═══════════════════════════════════════════════════════════ -->

    <!-- 1. Create user dialog -->
    <v-dialog v-model="createDialog.show" max-width="440" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4">Добавить сотрудника</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-form ref="createFormRef">
          <v-text-field v-model="createDialog.last_name" label="Фамилия *" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-account" :rules="[v => !!v || 'Фамилия обязательна']" />
          <v-text-field v-model="createDialog.first_name" label="Имя *" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-account" :rules="[v => !!v || 'Имя обязательно']" />
          <v-text-field v-model="createDialog.middle_name" label="Отчество" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-account" hint="Необязательно — не у всех есть отчество" persistent-hint />
          <v-text-field v-model="createDialog.email" label="Email *" variant="outlined" density="compact" class="mb-3"
            hint="Используется для входа в систему" persistent-hint prepend-inner-icon="mdi-email-outline"
            type="email" :rules="[v => !!v || 'Email обязателен', v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Введите корректный email (например, ivanov@company.ru)']" />
          <v-text-field
            :model-value="formatPhoneRu(createDialog.phone)"
            @update:model-value="createDialog.phone = $event"
            label="Телефон" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-phone" placeholder="8-999-999-99-99"
            hint="Формат: 8-999-999-99-99. Для связи и интеграции с Telegram" persistent-hint
          />
          <v-text-field
            :model-value="formatPhoneRu(createDialog.work_phone)"
            @update:model-value="createDialog.work_phone = unformatPhone($event)"
            label="Рабочий телефон" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-phone-classic" placeholder="8-999-999-99-99"
          />
          <v-text-field v-model="createDialog.telegram_id" label="Telegram Chat ID" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-send" placeholder="123456789"
            hint="Числовой ID чата Telegram (узнать: написать боту @userinfobot)" persistent-hint />
          <v-text-field v-model="createDialog.max_chat_id" label="MAX (VK) Chat ID" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-message-processing" placeholder="123456789"
            hint="Числовой ID для уведомлений через MAX-бот" persistent-hint />
          <v-text-field v-model="createDialog.password" label="Пароль *" type="password" variant="outlined" density="compact" class="mb-3"
            :rules="[v => !!v || 'Пароль обязателен', v => v.length >= 6 || 'Минимум 6 символов']" />
          <v-text-field v-model="createDialog.password_confirm" label="Подтвердите пароль *" type="password" variant="outlined" density="compact" class="mb-3"
            :error="!!createDialog.password_confirm && createDialog.password !== createDialog.password_confirm"
            :error-messages="createDialog.password_confirm && createDialog.password !== createDialog.password_confirm ? 'Пароли не совпадают' : ''" />
          <v-autocomplete v-if="canPickOrg" v-model="createDialog.org_id" :items="assignableOrganizations" item-title="name" item-value="id"
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
          <v-combobox v-model="createDialog.department" :items="getDepartmentsForOrg(createDialog.org_id)" label="Отдел" variant="outlined" density="compact" clearable class="mb-3"
            :hint="createDialog.org_id ? 'Введите новый отдел или выберите из списка' : 'Сначала выберите организацию — покажем её отделы'" persistent-hint
            :no-data-text="createDialog.org_id ? 'Введите название нового отдела' : 'Сначала выберите организацию'" prepend-inner-icon="mdi-office-building-outline" />
          <v-combobox v-model="createDialog.position" :items="getPositionsForOrg(createDialog.org_id)" label="Должность" variant="outlined" density="compact" clearable class="mb-3"
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
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="createDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat"
            :loading="createDialog.saving"
            :disabled="!createDialog.email || !createDialog.password || createDialog.password !== createDialog.password_confirm || (canPickOrg && !createDialog.org_id)"
            @click="saveUser">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 2. Edit user dialog -->
    <v-dialog v-model="editDialog.show" max-width="500" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4">Редактировать: {{ editDialog.full_name || editDialog.email }}</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <div v-if="editDialog.userId" class="d-flex flex-column align-center mb-4">
            <div class="text-caption text-medium-emphasis mb-2">Фотография сотрудника</div>
            <div class="staff-photo-rect" @click="openStaffPhotoUpload">
              <img v-if="editDialog.profile_photo" :src="editDialog.profile_photo" alt="фото" />
              <v-icon v-else icon="mdi-account" size="80" color="grey-lighten-1" />
              <div class="staff-photo-overlay">
                <v-icon icon="mdi-camera" size="22" color="white" />
              </div>
            </div>
          </div>
          <ProfilePhotoUpload ref="staffPhotoUploadRef" format="rectangle" :user-id="editDialog.userId || undefined" @saved="onStaffPhotoSaved" />
          <v-text-field v-model="editDialog.email" label="Email (логин)" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-email-outline" />
          <v-text-field v-model="editDialog.last_name" label="Фамилия *" variant="outlined" density="compact" class="mb-3"
            :rules="[v => !!v || 'Фамилия обязательна']" />
          <v-text-field v-model="editDialog.first_name" label="Имя *" variant="outlined" density="compact" class="mb-3"
            :rules="[v => !!v || 'Имя обязательно']" />
          <v-text-field v-model="editDialog.middle_name" label="Отчество" variant="outlined" density="compact" class="mb-3"
            hint="Необязательно — не у всех есть отчество" persistent-hint />
          <v-select v-model="editDialog.role" :items="roleItems" item-title="label" item-value="value"
            label="Роль" variant="outlined" density="compact" class="mb-3" />
          <v-select v-model="editDialog.superior_user_id" :items="userDropdownItems" item-title="text" item-value="value"
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
                :class="{ 'avatar-pick-active': editDialog.avatar === av.id }"
                @click="editDialog.avatar = av.id">
                <v-avatar :color="av.color" size="40">
                  <v-icon :icon="av.icon" size="22" color="white" />
                </v-avatar>
              </div>
            </div>
          </div>
          <v-text-field v-model="editDialog.inn" label="ИНН" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-card-account-details-outline" placeholder="12 цифр"
            hint="ИНН физ. лица — 12 цифр" persistent-hint maxlength="12" />
          <v-text-field v-model="editDialog.city" label="Город" variant="outlined" density="compact" class="mb-3" />
          <v-text-field
            :model-value="formatPhoneRu(editDialog.phone)"
            @update:model-value="editDialog.phone = $event"
            label="Телефон" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-phone" placeholder="8-999-999-99-99"
            hint="Формат: 8-999-999-99-99" persistent-hint
          />
          <v-text-field
            :model-value="formatPhoneRu(editDialog.work_phone)"
            @update:model-value="editDialog.work_phone = unformatPhone($event)"
            label="Рабочий телефон" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-phone-classic" placeholder="8-999-999-99-99"
          />
          <v-text-field v-model="editDialog.telegram_id" label="Telegram Chat ID" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-send" placeholder="123456789"
            hint="Числовой ID — узнать: написать @userinfobot в Telegram" persistent-hint />
          <v-text-field v-model="editDialog.max_chat_id" label="MAX (VK) Chat ID" variant="outlined" density="compact" class="mb-3"
            prepend-inner-icon="mdi-message-processing" placeholder="123456789"
            hint="Числовой ID для уведомлений через MAX-бот" persistent-hint />
          <v-text-field v-if="canChangePassword" v-model="editDialog.password" label="Новый пароль (оставьте пустым чтобы не менять)" variant="outlined" density="compact" type="password" />
          <!-- Multi-org membership (available if orgs list loaded) -->
          <div v-if="organizations.length > 0" class="mb-3">
            <v-select
              v-model="editDialog.extraOrgIds"
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
              :loading="editDialog.extraOrgsLoading"
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
                    <v-btn v-if="entry.id" icon size="x-small" variant="text" color="error" @click="confirmDeleteOrgEntry(entry)" :title="'Удалить из ' + (entry.dept_name || entry.org_name)">
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
                <v-btn size="x-small" variant="text" color="purple" prepend-icon="mdi-plus" class="ml-1" @click="addDeptToOrg(group.org_id)">
                  Ещё отдел в {{ group.org_name }}
                </v-btn>
              </div>
            </div>
          </div>
          <!-- F3-checkbox: Не включать в справочник сотрудников -->
          <v-checkbox
            v-model="editDialog.exclude_from_directory"
            label="Не включать в справочник сотрудников"
            density="compact"
            hide-details
            class="mb-3"
          />

          <!-- 29-15: Может водить ТС + данные ВУ -->
          <v-checkbox
            v-model="editDialog.can_drive"
            label="Может водить ТС"
            density="compact"
            hide-details
            class="mb-2"
          />
          <v-expand-transition>
            <v-card v-if="editDialog.can_drive" variant="outlined" class="pa-4 mb-4">
              <div class="text-subtitle-2 font-weight-bold mb-3">Данные водителя</div>
              <v-row dense>
                <v-col cols="4">
                  <v-text-field
                    v-model="editDialog.license_series"
                    label="Серия ВУ"
                    maxlength="10"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col cols="8">
                  <v-text-field
                    v-model="editDialog.license_number"
                    label="Номер ВУ"
                    maxlength="20"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
              </v-row>
              <v-text-field
                v-model="editDialog.license_categories"
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
                    v-model="editDialog.license_issued_at"
                    type="date"
                    label="ВУ выдано"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
                <v-col cols="6">
                  <v-text-field
                    v-model="editDialog.license_expires_at"
                    type="date"
                    label="ВУ действует до"
                    variant="outlined"
                    density="compact"
                  />
                </v-col>
              </v-row>
              <v-chip
                v-if="editDialog.license_expires_at && driverLicenseExpiryDays(editDialog.license_expires_at) !== null && driverLicenseExpiryDays(editDialog.license_expires_at)! <= 30"
                color="warning"
                size="small"
                prepend-icon="mdi-alert"
                class="mb-2"
              >
                ВУ истекает через {{ driverLicenseExpiryDays(editDialog.license_expires_at)! }} дн.
              </v-chip>
              <v-text-field
                v-model="editDialog.medical_cert_expires_at"
                type="date"
                label="Медсправка действует до"
                variant="outlined"
                density="compact"
                class="mt-2"
              />
              <v-chip
                v-if="editDialog.medical_cert_expires_at && driverMedicalExpiryDays(editDialog.medical_cert_expires_at) !== null && driverMedicalExpiryDays(editDialog.medical_cert_expires_at)! <= 30"
                color="warning"
                size="small"
                prepend-icon="mdi-alert"
                class="mt-1"
              >
                Медсправка истекает через {{ driverMedicalExpiryDays(editDialog.medical_cert_expires_at)! }} дн.
              </v-chip>

              <!-- Phase 29.3: тахограф / психиатрия / периодический медосмотр -->
              <v-text-field
                v-model="editDialog.tachograph_card_expires_at"
                type="date"
                label="Карточка тахографа действует до"
                hint="Срок действия карты водителя для тахографа"
                persistent-hint
                density="compact"
                class="mt-2"
              />
              <v-text-field
                v-model="editDialog.periodic_medical_expires_at"
                type="date"
                label="Периодический медосмотр до"
                hint="Согласно приказу 302н — для категорий C/D/E и проф. водителей"
                persistent-hint
                density="compact"
                class="mt-2"
              />
              <v-text-field
                v-model="editDialog.psych_cert_expires_at"
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
                <img v-if="editDialog.license_scan" :src="editDialog.license_scan" alt="скан ВУ" class="license-scan-preview" />
                <div v-else class="license-scan-empty">
                  <v-icon icon="mdi-card-account-details-outline" size="36" color="grey-lighten-1" />
                  <span class="text-caption text-medium-emphasis">Загрузить скан (JPG/PNG, до 3 МБ)</span>
                </div>
              </div>
              <input ref="licenseScanInput" type="file" accept="image/*" style="display:none" @change="onLicenseScanFile" />
              <v-btn
                v-if="editDialog.license_scan"
                size="x-small"
                variant="text"
                color="error"
                prepend-icon="mdi-delete-outline"
                class="mt-1"
                @click="editDialog.license_scan = ''"
              >Удалить скан</v-btn>
            </v-card>
          </v-expand-transition>

          <!-- 17-08: «Доступ» section — per-user per-org permission overrides (D-04/D-05.2/D-08) -->
          <UserPermissionsSection
            v-if="editDialog.userId && allOrgEntries.length"
            :key="editDialog.userId"
            :user-id="editDialog.userId"
            :current-user-id="currentUserId"
            :user-role="editDialog.role"
            :org-access-list="dedupOrgAccess(allOrgEntries)"
            :all-orgs-access="editDialog.all_orgs_access"
            @update:all-orgs-access="(v) => { editDialog.all_orgs_access = v }"
          />
          <UserSubsidyAccessSection
            v-if="editDialog.userId"
            :user-id="editDialog.userId"
            :user-role="editDialog.role"
          />

          <!-- Учётки электронных площадок (ЭТП Фабрикант) -->
          <UserPlatformCredentialsSection
            v-if="editDialog.userId"
            :user-id="editDialog.userId"
            @error="(msg) => showSnack(msg, 'error')"
          />

          <!-- Диагностика видимости: отделы, которые возглавляет сотрудник -->
          <div v-if="editDialog.headedDepts.length" class="mt-3 pa-3 rounded-lg" style="background:rgba(0,128,100,0.07);border-left:3px solid #00897b">
            <div class="text-caption text-medium-emphasis mb-2 d-flex align-center">
              <v-icon size="14" class="mr-1" color="teal">mdi-eye-check-outline</v-icon>
              Видимость: возглавляет отдел(ы) — видит закупки/задачи всех участников:
            </div>
            <v-chip v-for="d in editDialog.headedDepts" :key="d.id" size="x-small" color="teal" variant="tonal" class="mr-1 mb-1">
              <v-icon start size="10">mdi-crown</v-icon>{{ d.name }}{{ d.org_name ? ' · ' + d.org_name : '' }}
            </v-chip>
          </div>
          <div v-else-if="editDialog.userId" class="mt-2 text-caption" style="color:#e65100">
            <v-icon size="13" color="warning" class="mr-1">mdi-alert-outline</v-icon>
            Не назначен начальником ни одного отдела — видит только свои закупки/задачи (+ подчинённые по иерархии).
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-account-convert" @click="syncToContractor(editDialog.userId)">
            В контрагенты
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="editDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="editDialog.saving"
            :disabled="!editDialog.last_name || !editDialog.first_name"
            @click="saveEditUser">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 3. Delete user confirm dialog -->
    <v-dialog v-model="deleteDialog.show" :max-width="deleteDialog.warning ? 480 : 340">
      <v-card>
        <v-card-title class="pa-4">Убрать сотрудника из организации?</v-card-title>
        <v-card-text>
          {{ deleteDialog.user?.full_name || deleteDialog.user?.username }}
          <div class="text-caption text-medium-emphasis mt-1">
            Сотрудник будет откреплён от этой организации. Аккаунт удалится полностью, только если это его единственная организация (с отдельным подтверждением).
          </div>
          <v-alert v-if="deleteDialog.warning" type="warning" variant="tonal" density="compact" class="mt-3 text-body-2">
            {{ deleteDialog.warning }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteDialog.deleting" @click="doDelete">
            {{ deleteDialog.warning ? 'Удалить безвозвратно' : 'Удалить' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 3b. Bulk delete users confirm dialog -->
    <v-dialog v-model="bulkDeleteUsersDialog" max-width="440" persistent>
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-alert-circle-outline" color="error" class="mr-2" />
          Удалить сотрудников?
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4 pa-4">
          <p class="mb-2">
            Вы собираетесь удалить <strong>{{ selectedUsers.length }}</strong> сотрудников.
            Это действие <strong>нельзя отменить</strong>.
          </p>
          <p class="text-caption text-medium-emphasis">
            Все данные, задачи и права доступа удалённых сотрудников будут потеряны.
            В связанных закупках и задачах исполнитель/автор станет пустым.
          </p>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" :disabled="bulkDeleteUsersLoading" @click="bulkDeleteUsersDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="bulkDeleteUsersLoading" @click="doBulkDeleteUsers">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 4. Hierarchy dialog -->
    <v-dialog v-model="hierarchyDialog.show" max-width="500" :fullscreen="mobile">
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
    <v-dialog v-model="userImportDialog.show" max-width="520" :fullscreen="mobile">
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
    <v-dialog v-model="deptDialog" max-width="520" :fullscreen="mobile">
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

            <v-select v-model="deptForm.deputy_head_user_id" :items="deptMemberItems" item-title="text" item-value="value"
              label="Зам. начальника отдела" variant="outlined" density="compact" clearable class="mb-3"
              hint="Используется в восходящей цепочке согласования заявок (ниже начальника)" persistent-hint
              :disabled="deptMemberItems.length === 0" />

            <v-select v-model="deptForm.curator_user_id" :items="userDropdownItems" item-title="text" item-value="value"
              label="Куратор" variant="outlined" density="compact" clearable class="mb-3"
              hint="Любой человек, курирующий это подразделение (в цепочке согласования выше начальника). Не обязательно зам." persistent-hint />

            <v-select v-model="deptForm.parent_id" :items="otherDeptItems" item-title="text" item-value="value"
              label="Вышестоящее подразделение" variant="outlined" density="compact" clearable
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
    <v-dialog v-model="addMemberDialog" max-width="500" :fullscreen="mobile">
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
            <v-combobox v-model="memberForm.position" :items="getPositionsForOrg(selectedDept?.org_id)" label="Должность в отделе" variant="outlined" density="compact"
              hint="Выберите из списка или введите свою" persistent-hint />
          </template>

          <!-- New user (inline creation) -->
          <template v-if="addMemberMode === 'new'">
            <v-text-field v-model="newMemberForm.last_name" label="Фамилия *" variant="outlined" density="compact" class="mb-2"
              prepend-inner-icon="mdi-account" />
            <v-text-field v-model="newMemberForm.first_name" label="Имя *" variant="outlined" density="compact" class="mb-2"
              prepend-inner-icon="mdi-account" />
            <v-text-field v-model="newMemberForm.middle_name" label="Отчество" variant="outlined" density="compact" class="mb-2"
              prepend-inner-icon="mdi-account" hint="Необязательно" persistent-hint />
            <v-text-field v-model="newMemberForm.email" label="Email *" variant="outlined" density="compact" class="mb-2"
              type="email" prepend-inner-icon="mdi-email-outline"
              :rules="[v => !!v || 'Обязательное поле', v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Введите корректный email (например, ivanov@company.ru)']" />
            <v-text-field
              :model-value="formatPhoneRu(newMemberForm.phone)"
              @update:model-value="newMemberForm.phone = $event"
              label="Телефон" variant="outlined" density="compact" class="mb-2"
              prepend-inner-icon="mdi-phone" placeholder="8-999-999-99-99"
              hint="Формат: 8-999-999-99-99" persistent-hint
            />
            <v-text-field v-model="newMemberForm.password" label="Пароль *" type="password" variant="outlined" density="compact" class="mb-2"
              :rules="[v => !!v || 'Обязательное поле', v => v.length >= 6 || 'Минимум 6 символов']" />
            <v-text-field v-model="newMemberForm.password_confirm" label="Подтвердите пароль *" type="password" variant="outlined" density="compact" class="mb-2"
              :error="!!newMemberForm.password_confirm && newMemberForm.password !== newMemberForm.password_confirm"
              :error-messages="newMemberForm.password_confirm && newMemberForm.password !== newMemberForm.password_confirm ? 'Пароли не совпадают' : ''" />
            <v-select v-model="newMemberForm.role" :items="roleItems" item-title="label" item-value="value"
              label="Роль" variant="outlined" density="compact" class="mb-2" />
            <v-combobox v-model="newMemberForm.position" :items="getPositionsForOrg(selectedDept?.org_id)" label="Должность" variant="outlined" density="compact" class="mb-2"
              hint="Выберите из списка или введите свою" persistent-hint />
            <v-text-field v-model="newMemberForm.city" label="Город" variant="outlined" density="compact" />
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="addMemberDialog = false">Отмена</v-btn>
          <v-btn v-if="addMemberMode === 'existing'" color="primary" :disabled="!memberForm.user_id" @click="addMember">Добавить</v-btn>
          <v-btn v-else color="primary"
            :disabled="!newMemberForm.email || !newMemberForm.password || !newMemberForm.last_name || !newMemberForm.first_name || newMemberForm.password.length < 6 || newMemberForm.password !== newMemberForm.password_confirm || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newMemberForm.email)"
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

    <!-- B6. INN duplicates dialog (просмотр, merge — backend TBD) -->
    <v-dialog v-model="innDupDialog" max-width="640" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-account-multiple-outline" color="warning" class="mr-2" />
          Дубликаты пользователей по ИНН
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="innDupDialog = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
            Показаны пользователи с одинаковым ИНН. Объединение (merge) будет доступно после реализации backend-эндпоинта
            <code>PATCH /api/users/{'{id}'}/merge</code> — это отдельная задача.
            Пока вы можете открыть карточку каждого и разобраться вручную.
          </v-alert>
          <div v-for="{ inn, group } in duplicateInnGroups" :key="inn" class="mb-5">
            <div class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center">
              <v-icon icon="mdi-card-account-details-outline" size="16" class="mr-1" color="warning" />
              ИНН: {{ inn }}
              <v-chip size="x-small" color="warning" variant="tonal" class="ml-2">{{ group.length }} записи</v-chip>
            </div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>ФИО</th>
                  <th>Логин</th>
                  <th>Роль</th>
                  <th>Организация</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in group" :key="u.id">
                  <td class="text-caption text-medium-emphasis">{{ u.id }}</td>
                  <td class="text-body-2">{{ u.full_name || '—' }}</td>
                  <td class="text-caption">{{ u.username }}</td>
                  <td><v-chip size="x-small" :color="roleColor(u.role)" variant="tonal">{{ ROLE_LABELS[u.role] || u.role }}</v-chip></td>
                  <td class="text-caption">{{ (u as any).org_id || '—' }}</td>
                  <td>
                    <v-btn size="x-small" variant="text" color="primary" icon="mdi-pencil"
                      @click="innDupDialog = false; openEditUser(u)" title="Открыть карточку" />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
          <div v-if="duplicateInnGroups.length === 0" class="text-center py-6 text-medium-emphasis">
            Дубликатов не найдено
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="flat" color="primary" @click="innDupDialog = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch, defineComponent, h, resolveComponent, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { formatPhoneRu, unformatPhone } from '@/utils/phoneFormat'
import UserAvatar from '@/components/UserAvatar.vue'
import HierarchyView from './HierarchyView.vue'
import UserPermissionsSection from '@/components/UserPermissionsSection.vue'
import UserSubsidyAccessSection from '@/components/UserSubsidyAccessSection.vue'
import UserPlatformCredentialsSection from '@/components/UserPlatformCredentialsSection.vue'
import ProfilePhotoUpload from '@/components/ProfilePhotoUpload.vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import { useCardView } from '@/composables/useCardView'
import { useDisplay } from 'vuetify'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'

// ── Hierarchy ref ──
const hierarchyRef = ref<InstanceType<typeof HierarchyView> | null>(null)
const registryArea = ref<HTMLElement | null>(null)
const deptArea = ref<HTMLElement | null>(null)
const hierarchyArea = ref<HTMLElement | null>(null)

function getDeptExportColumns() {
  return [
    { key: 'dept', title: 'Отдел' },
    { key: 'head', title: 'Начальник отдела' },
    { key: 'employee', title: 'Сотрудник' },
    { key: 'position', title: 'Должность' },
  ]
}
function getDeptExportRows() {
  const rows: Array<Record<string, any>> = []
  for (const d of flatDepts(deptTree.value)) {
    const members = d.members || []
    if (members.length === 0) {
      rows.push({ dept: d.name, head: d.head_user_name || '', employee: '', position: '' })
    } else {
      for (const m of members) {
        rows.push({
          dept: d.name,
          head: d.head_user_name || '',
          employee: m.user_name || '',
          position: m.position || m.user_role || '',
        })
      }
    }
  }
  return rows
}

function getHierarchyExportColumns() {
  return [
    { key: 'full_name', title: 'ФИО' },
    { key: 'role', title: 'Роль' },
    { key: 'position', title: 'Должность' },
    { key: 'department', title: 'Отдел' },
  ]
}
function getHierarchyExportRows() {
  return users.value.map((u: any) => ({
    full_name: u.full_name || u.username,
    role: ROLE_LABELS[u.role] || u.role,
    position: u.position || '',
    department: u.department || '',
  }))
}

// ── Types ──
interface UserItem {
  id: number
  username: string
  full_name?: string
  last_name?: string
  first_name?: string
  middle_name?: string
  role: string
  city?: string
  department?: string
  position?: string
  email?: string
  avatar?: string
  photo_url?: string | null
  has_signature?: boolean
  inn?: string
  org_id?: number
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
  account_owner: 'Хозяин аккаунта',
  admin: 'Администратор аккаунта',
  org_admin: 'Администратор организации',
  manager: 'Менеджер',
  employee: 'Сотрудник',
}
const roleItems = computed(() => {
  // Глобальная роль: org_admin СЮДА НЕ входит — «Администратор организации» это
  // только per-org роль (UserOrgAccess.role), не глобальная. Глобально доступны
  // Сотрудник / Менеджер / Администратор аккаунта (управляет всем аккаунтом).
  const items = [
    { value: 'manager', label: 'Менеджер' },
    { value: 'employee', label: 'Сотрудник' },
  ]
  // «Администратор аккаунта» и «Хозяин аккаунта» доступны любому, кто управляет
  // сотрудниками (org_admin и выше). Запрос 14.07: в аккаунте может не быть ни одного
  // admin/account_owner — если опции прятать, роль некому выдать в принципе.
  if (['superadmin', 'account_owner', 'admin', 'org_admin'].includes(currentRole)) {
    items.unshift({ value: 'admin', label: 'Администратор аккаунта' })
    items.unshift({ value: 'account_owner', label: 'Хозяин аккаунта' })
  }
  return items
})
const roleColor = (r: string) => ({
  superadmin: 'purple', account_owner: 'deep-orange', admin: 'error', org_admin: 'orange-darken-2', manager: 'blue', employee: 'teal',
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
const currentUserId = Number(localStorage.getItem('user_id') || 0)
const isAdmin = computed(() => ['admin', 'org_admin', 'account_owner', 'superadmin'].includes(currentRole))

// ── Snackbar ── единый механизм (useToast + ToastContainer, смонтирован в App.vue).
const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

// ═══════════════════════════════════════════════════════════════
// SHARED STATE
// ═══════════════════════════════════════════════════════════════
const users = ref<UserItem[]>([])
const usersLoading = ref(false)
const subsidies = ref<any[]>([])
const knownDepartments = ref<string[]>([])
const knownPositions = ref<string[]>([])
// Per-org dict cache: orgId → { departments, positions }
const dictsCache = ref<Record<number, { departments: string[]; positions: string[] }>>({})

async function loadDicts(orgId?: number | null) {
  const suffix = orgId ? `?org_id=${orgId}` : ''
  if (orgId && dictsCache.value[orgId]) return // already cached
  try {
    const [depts, positions] = await Promise.all([
      apiFetch<string[]>(`/users/dictionaries/departments${suffix}`),
      apiFetch<string[]>(`/users/dictionaries/positions${suffix}`),
    ])
    if (orgId) {
      dictsCache.value[orgId] = { departments: depts, positions: positions }
    } else {
      knownDepartments.value = depts
      knownPositions.value = positions
    }
  } catch {}
}

function getDepartmentsForOrg(orgId?: number | null): string[] {
  // Строго по орге: без орги и до загрузки кеша список пуст —
  // иначе в диалоге показывались отделы ВСЕХ организаций.
  if (!orgId) return []
  return dictsCache.value[orgId]?.departments ?? []
}

function getPositionsForOrg(orgId?: number | null): string[] {
  if (!orgId) return knownPositions.value
  return dictsCache.value[orgId]?.positions ?? knownPositions.value
}

// Dropdown items for user select components
const userDropdownItems = computed(() =>
  users.value.map(u => ({ text: u.full_name || u.username, value: u.id }))
)

const filteredUsers = computed(() => {
  let list = users.value
  // D-09: non-superadmin viewers don't see superadmin rows (defence-in-depth; backend also filters)
  if (currentRole !== 'superadmin') list = list.filter(u => u.role !== 'superadmin')
  if (filterUserRole.value) list = list.filter(u => u.role === filterUserRole.value)
  if (filterUserOrgId.value) list = list.filter(u => (u as any).org_id === filterUserOrgId.value)
  const q = filterUserSearch.value.trim().toLowerCase()
  if (q) {
    list = list.filter(u => {
      const fields = [
        u.full_name,
        u.username,
        (u as any).position,
        (u as any).email,
        (u as any).phone,
        (u as any).inn != null ? String((u as any).inn) : '',
      ]
      return fields.some(f => (f || '').toLowerCase().includes(q))
    })
  }
  return list
})

const { mobile } = useDisplay()

const {
  mobile: staffMobile,
  viewMode: staffViewMode,
  effectiveView: staffEffectiveView,
  page: staffCardsPage,
  totalPages: staffCardsTotalPages,
  paged: staffPagedCards,
} = useCardView<UserItem>({
  storageKey: 'staff_view_mode',
  source: () => filteredUsers.value,
  pageSize: 24,
})

// B6: дедуп пользователей по ИНН
const duplicateInnGroups = computed(() => {
  const byInn: Record<string, UserItem[]> = {}
  for (const u of users.value) {
    const inn = (u as any).inn
    if (!inn || String(inn).trim().length < 10) continue
    const key = String(inn).trim()
    if (!byInn[key]) byInn[key] = []
    byInn[key].push(u)
  }
  return Object.entries(byInn)
    .filter(([, group]) => group.length >= 2)
    .map(([inn, group]) => ({ inn, group }))
})

const innDupDialog = ref(false)

// Users not in any department
const unassignedUsers = computed(() => users.value.filter(u => !u.department))
const unassignedExpanded = ref(true)

/** Get avatar id for a department member by user_id */
function getMemberAvatar(userId: number): string | undefined {
  const u = users.value.find(x => x.id === userId)
  return u?.avatar
}

function getMemberPhotoUrl(userId: number): string | null | undefined {
  const u = users.value.find(x => x.id === userId)
  return u?.photo_url
}

// 29-15: helpers — days until expiry (null if date invalid/empty)
function driverLicenseExpiryDays(dateStr: string | null): number | null {
  if (!dateStr) return null
  const exp = new Date(dateStr)
  if (isNaN(exp.getTime())) return null
  const diff = Math.ceil((exp.getTime() - Date.now()) / 86400000)
  return diff
}
function driverMedicalExpiryDays(dateStr: string | null): number | null {
  return driverLicenseExpiryDays(dateStr)
}

// ═══════════════════════════════════════════════════════════════
// TAB 2: USERS STATE
// ═══════════════════════════════════════════════════════════════
const allColumns: ColumnDef[] = [
  { title: '', key: 'avatar', width: 50, sortable: false },
  { title: 'Email', key: 'email' },
  { title: 'ФИО', key: 'full_name' },
  { title: 'Роль', key: 'role', width: 130 },
  { title: 'Отдел', key: 'department' },
  { title: 'Должность', key: 'position' },
  { title: 'Город', key: 'city' },
  { title: 'Подпись', key: 'has_signature', width: 90, sortable: false },
  { title: '', key: 'actions', width: 100, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('staff', allColumns)
const showColumnPicker = ref(false)

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
  show: false, last_name: '', first_name: '', middle_name: '', email: '', password: '', password_confirm: '',
  role: 'employee', city: '', department: '', position: '', phone: '', work_phone: '', telegram_id: '', avatar: '', saving: false,
  org_id: null as number | null, subsidy_id: null as number | null,
})
const createFormRef = ref<any>(null)
// Pre-load dicts when superadmin picks an org in createDialog
watch(() => createDialog.org_id, (id) => { if (id) loadDicts(id) })
// Владелец, 2026-09-01: `organizations` — общий каталог ВСЕХ организаций
// (GET /organizations/, доступен любому залогиненному) для отображения имён
// (color-lookup, диагностика headedOrgs и т.д.) и для НЕ-create-dialog
// пикеров (line 44/222/659). НЕ путать с `assignableOrganizations` — узкий
// список «куда я реально могу создать/добавить сотрудника» (GET
// /organizations/assignable), нужен ТОЛЬКО для пикера в диалоге создания.
// Раньше это был ОДИН и тот же ref: openCreateUser() перезаписывал общий
// каталог узким assignable-списком, и после этого резолв имени организации
// по id ломался для орг вне assignable-скоупа текущего редактора (баг
// «Организация #28» — ХРО ВСКС не входила в assignable конкретного admin'а).
const organizations = ref<any[]>([])
const assignableOrganizations = ref<any[]>([])
const currentOrgId = parseInt(localStorage.getItem('user_org_id') || '0') || null
const currentOrgName = localStorage.getItem('user_org_name') || ''
const isSuperadmin = computed(() => currentRole === 'superadmin')
// SaaS-роли видят все орг → дать им выбор организации (account_owner Цыганов тоже).
// Менеджер, управляющий >1 орг (напр. Маркодеева → ВСКС + Донецкое), тоже должен
// выбирать целевую орг при добавлении сотрудника — иначе орг жёстко = его своя (баг).
const canPickOrg = computed(() =>
  ['superadmin', 'account_owner'].includes(currentRole) || assignableOrganizations.value.length > 1
)

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
})

const deleteDialog = reactive({ show: false, user: null as UserItem | null, deleting: false, warning: '' as string })
const selectedUsers = ref<any[]>([])
const bulkDeleteUsersDialog = ref(false)
const bulkDeleteUsersLoading = ref(false)

const staffPhotoUploadRef = ref<InstanceType<typeof ProfilePhotoUpload> | null>(null)
function openStaffPhotoUpload() { staffPhotoUploadRef.value?.open() }
function onStaffPhotoSaved(url: string | null) {
  editDialog.profile_photo = url || ''
}

// Phase 30.3: license scan upload
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
    editDialog.license_scan = String(reader.result || '')
  }
  reader.readAsDataURL(file)
  target.value = ''
}

const userImportDialog = reactive({
  show: false, file: null as File | null, loading: false,
  result: null as { created: number; skipped: number; errors: { row: number; error: string }[] } | null,
})

// All org entries from salary API (one per dept membership)
const allOrgEntries = ref<{ id: number | null; dept_id: number | null; org_id: number; org_name: string; dept_name: string; position: string; salary_amount: number | null; employment_percent: number | null; hired_at: string | null; dept_assigned_at: string | null; position_assigned_at: string | null; _idx: number }[]>([])
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
const filteredDeptTree = computed(() => {
  if (!filterDeptUserId.value) return deptTree.value
  const uid = filterDeptUserId.value
  function hasMember(node: any): boolean {
    if ((node.members || []).some((m: any) => m.user_id === uid)) return true
    return (node.children || []).some((c: any) => hasMember(c))
  }
  return deptTree.value.filter(hasMember)
})
const selectedDept = ref<any>(null)
const deptMembers = ref<any[]>([])
const delegates = ref<any[]>([])
const filterSubsidyId = ref<number | null>(null)
const filterDeptOrgId = ref<number | null>(null)
const filterDeptUserId = ref<number | null>(null)
const canChangePassword = computed(() => ['superadmin', 'account_owner'].includes(localStorage.getItem('user_role') || ''))
const filterUserRole = ref<string | null>(null)
const filterUserOrgId = ref<number | null>(null)
const filterUserSearch = ref('')

// Dept dialog
const deptDialog = ref(false)
const editingDept = ref<any>(null)
const deptForm = ref({ name: '', subsidy_id: null as number | null, head_user_id: null as number | null, deputy_head_user_id: null as number | null, curator_user_id: null as number | null, parent_id: null as number | null })

// Member dialog
const addMemberDialog = ref(false)
const addMemberMode = ref<'existing' | 'new'>('existing')
const memberForm = ref({ user_id: null as number | null, position: '' })
const newMemberForm = ref({ email: '', last_name: '', first_name: '', middle_name: '', password: '', password_confirm: '', phone: '', role: 'employee', position: '', city: '' })
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

// ── Org color map for dept nodes ──
const ORG_COLORS = ['primary', 'purple', 'orange', 'teal', 'indigo', 'pink', 'brown']
function orgColor(orgId: number | null | undefined): string {
  // Unify color logic: prefer Organization.color from DB (как в HierarchyView).
  // Если color задан админом через color-picker — возвращаем hex.
  // Иначе fallback на named Vuetify color по индексу.
  if (!orgId) return 'primary'
  const org = organizations.value.find((o: any) => o.id === orgId) as any
  if (org?.color && typeof org.color === 'string' && org.color.startsWith('#')) {
    return org.color
  }
  const idx = organizations.value.findIndex((o: any) => o.id === orgId)
  return ORG_COLORS[idx >= 0 ? idx % ORG_COLORS.length : 0]
}

// Helper: преобразует org color (hex или named) в CSS-color-value
// для inline border-color / background стилей.
function orgCssColor(orgId: number | null | undefined, alpha = 1): string {
  const c = orgColor(orgId)
  if (c.startsWith('#')) {
    // hex → используем как есть; для alpha добавляем суффикс
    if (alpha >= 1) return c
    // hex + alpha как rgba не получится напрямую — конвертируем
    const r = parseInt(c.slice(1, 3), 16)
    const g = parseInt(c.slice(3, 5), 16)
    const b = parseInt(c.slice(5, 7), 16)
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  // Vuetify named theme color
  return alpha >= 1
    ? `rgb(var(--v-theme-${c}))`
    : `rgba(var(--v-theme-${c}), ${alpha})`
}

// ── Recursive dept-node component ──
const DeptNode = defineComponent({
  name: 'DeptNode',
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
          h(DeptNode, {
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

async function onHierarchyDataChanged() {
  // Reload users silently so dept/position changes from hierarchy are reflected
  try {
    users.value = await apiFetch<UserItem[]>('/users/')
    await loadDeptTree()
  } catch { /* silent */ }
}

// Владелец, 2026-09-01: «плюсик» из отдела/орг-контекста (HierarchyView) обязан
// предзаполнить организацию и отдел, а не открывать пустую форму — иначе
// новый сотрудник (напр. Новичкова, добавленная через «+» в «Администрации»
// ВСКС) создаётся без орг/отдела и требует ручной правки. ctx — опционален:
// кнопка «Добавить сотрудника» в шапке StaffView/HierarchyView не привязана
// ни к какому отделу, там предзаполнять нечем (остаётся currentOrgId/пусто).
function openCreateUser(ctx?: { orgId?: number; departmentName?: string }) {
  createDialog.last_name = ''
  createDialog.first_name = ''
  createDialog.middle_name = ''
  createDialog.email = ''
  createDialog.password = ''
  createDialog.password_confirm = ''
  createDialog.role = 'employee'
  createDialog.city = ''
  createDialog.department = ctx?.departmentName || ''
  createDialog.position = ''
  createDialog.phone = ''
  createDialog.work_phone = ''
  createDialog.telegram_id = ''
  createDialog.avatar = ''
  createDialog.org_id = ctx?.orgId ?? currentOrgId
  createDialog.subsidy_id = null
  createDialog.saving = false
  createDialog.show = true
  // Грузим орг, в которые пользователь реально может создавать сотрудника
  // (assignable = свои + управляемые). Для менеджера с >1 орг это включит пикер
  // (canPickOrg). Если протухший createDialog.org_id не входит в список — сбрасываем.
  apiFetch<any[]>('/organizations/assignable').then(r => {
    assignableOrganizations.value = r
    if (createDialog.org_id && !r.some(o => o.id === createDialog.org_id)) {
      createDialog.org_id = r.length ? r[0].id : null
    }
  }).catch(() => {})
}

async function saveUser() {
  // Подсветить «стрелочками» (красные поля + сообщения) все незаполненные/невалидные
  // поля и проскроллить к первому проблемному, вместо общего непонятного снэкбара.
  const res = await createFormRef.value?.validate?.()
  if (res && res.valid === false) {
    await nextTick()
    const firstErr = document.querySelector('.v-dialog--active .v-input--error, .v-dialog .v-input--error') as HTMLElement | null
    firstErr?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    firstErr?.querySelector('input, textarea')?.dispatchEvent(new Event('focus'))
    showSnack('Заполните выделенные поля', 'error')
    return
  }
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
        last_name: createDialog.last_name || null,
        first_name: createDialog.first_name || null,
        middle_name: createDialog.middle_name || null,
        password: createDialog.password,
        role: createDialog.role,
        city: createDialog.city || null,
        department: normalizeDepartment(createDialog.department) || null,
        position: createDialog.position || null,
        phone: unformatPhone(createDialog.phone) || null,
        work_phone: unformatPhone(createDialog.work_phone) || null,
        telegram_id: createDialog.telegram_id || null,
        avatar: createDialog.avatar || randomAvatarId(),
        org_id: createDialog.org_id ?? null,
      },
    })
    users.value = [...users.value, u]
    createDialog.show = false
    showSnack('Сотрудник создан')
    // Reload dept tree if department was specified
    if (createDialog.department) {
      await loadDeptTree()
    }
    hierarchyRef.value?.refresh()
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  } finally {
    createDialog.saving = false
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

async function openEditDeptById(deptId: number) {
  const dept = flatDepts(deptTree.value).find(d => d.id === deptId)
  if (dept) openEditDept(dept)
}

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
    hierarchyRef.value?.refresh()
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
  } finally {
    editDialog.saving = false
  }
}

function confirmDelete(u: UserItem) {
  deleteDialog.user = u
  deleteDialog.warning = ''
  deleteDialog.show = true
}

async function doDelete() {
  if (!deleteDialog.user) return
  deleteDialog.deleting = true
  try {
    // org-контекст: удаление карточки = открепление от ЭТОЙ орг; глобальное
    // удаление аккаунта бэк делает только если это его последняя организация.
    const orgId = deleteDialog.user.org_id ?? currentOrgId
    const params = new URLSearchParams()
    if (orgId) params.set('org_id', String(orgId))
    // Второй этап (warning уже показан) — удаляем с confirm=true
    if (deleteDialog.warning) params.set('confirm', 'true')
    const qs = params.toString()
    const url = `/users/${deleteDialog.user.id}${qs ? `?${qs}` : ''}`
    const res = await apiFetch(url, { method: 'DELETE' })
    users.value = users.value.filter(u => u.id !== deleteDialog.user!.id)
    deleteDialog.show = false
    showSnack(res?.detached ? 'Сотрудник убран из организации' : 'Пользователь удален')
  } catch (e: any) {
    if (e?.status === 409 && e?.payload?.code === 'CONFIRM_DELETE_USER') {
      // Показываем предупреждение о связанных записях, требуем повторного подтверждения
      deleteDialog.warning = e.payload.message || e.message
    } else {
      showSnack(e?.payload?.message || e.message || 'Ошибка', 'error')
    }
  } finally {
    deleteDialog.deleting = false
  }
}

function confirmBulkDeleteUsers() {
  bulkDeleteUsersDialog.value = true
}

function toggleUserSelection(u: UserItem) {
  const idx = selectedUsers.value.findIndex((s: any) => (s?.id ?? s) === u.id)
  if (idx >= 0) {
    selectedUsers.value = selectedUsers.value.filter((_: any, i: number) => i !== idx)
  } else {
    selectedUsers.value = [...selectedUsers.value, u]
  }
}

async function doBulkDeleteUsers() {
  bulkDeleteUsersLoading.value = true
  const toDelete = [...selectedUsers.value]
  let deleted = 0
  const errors: string[] = []
  for (const item of toDelete) {
    const id = typeof item === 'object' ? item.id : item
    const name = typeof item === 'object' ? (item.full_name || item.username || String(id)) : String(id)
    try {
      // Диалог bulk-удаления — уже явное подтверждение, поэтому confirm=true.
      // org_id — открепить от текущей орг, а не удалять аккаунт глобально.
      const orgId = (typeof item === 'object' ? item.org_id : null) ?? currentOrgId
      await apiFetch(`/users/${id}?confirm=true${orgId ? `&org_id=${orgId}` : ''}`, { method: 'DELETE' })
      users.value = users.value.filter(u => u.id !== id)
      deleted++
    } catch (e: any) {
      const msg = e?.payload?.message || e?.message || 'Ошибка'
      errors.push(`${name}: ${msg}`)
    }
  }
  selectedUsers.value = []
  bulkDeleteUsersDialog.value = false
  bulkDeleteUsersLoading.value = false
  if (errors.length) {
    showSnack(`Удалено: ${deleted}. Ошибки (${errors.length}): ${errors.slice(0, 3).join('; ')}`, 'error')
  } else {
    showSnack(`Удалено сотрудников: ${deleted}`, 'success')
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
  a.download = 'Шаблон_импорта_сотрудников.xlsx'
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
  const qs = new URLSearchParams()
  if (filterSubsidyId.value) qs.set('subsidy_id', String(filterSubsidyId.value))
  if (filterDeptOrgId.value) qs.set('org_id', String(filterDeptOrgId.value))
  const params = qs.toString() ? `?${qs.toString()}` : ''
  try { deptTree.value = await apiFetch<any[]>(`/departments/tree${params}`) } catch { deptTree.value = [] }
  finally { deptLoading.value = false }
}

watch([filterSubsidyId, filterDeptOrgId], () => { loadDeptTree() })

function openCreateDept() {
  editingDept.value = null
  deptForm.value = { name: '', subsidy_id: filterSubsidyId.value, head_user_id: null, deputy_head_user_id: null, curator_user_id: null, parent_id: null }
  deptDialog.value = true
}

// Top-level «Добавить отдел» из шапки (доступно на всех вкладках):
// переключаемся на вкладку «Отделы» и открываем тот же диалог.
function openCreateDeptFromHeader() {
  activeTab.value = 'departments'
  openCreateDept()
}

async function openEditDept(node: any) {
  selectedDept.value = node
  await loadDeptMembers(node.id)
  editingDept.value = node
  deptForm.value = { name: node.name, subsidy_id: node.subsidy_id, head_user_id: node.head_user_id, deputy_head_user_id: node.deputy_head_user_id ?? null, curator_user_id: node.curator_user_id ?? null, parent_id: node.parent_id }
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
    dictsCache.value = {}
    knownDepartments.value = []
    await loadDicts()
    await loadDeptTree()
    hierarchyRef.value?.refresh()
  } catch (e: any) { showSnack(e?.detail || 'Ошибка', 'error') }
}

async function deleteDept(node: any) {
  if (!confirm(`Удалить отдел "${node.name}"?`)) return
  try {
    await apiFetch(`/departments/${node.id}`, { method: 'DELETE' })
    if (selectedDept.value?.id === node.id) selectedDept.value = null
    showSnack('Отдел удален')
    dictsCache.value = {}
    knownDepartments.value = []
    await loadDicts()
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
        last_name: newMemberForm.value.last_name,
        first_name: newMemberForm.value.first_name,
        middle_name: newMemberForm.value.middle_name || null,
        role: newMemberForm.value.role,
        city: newMemberForm.value.city || null,
        phone: unformatPhone(newMemberForm.value.phone) || null,
        department: selectedDept.value.name,
        position: newMemberForm.value.position || null,
        // Орг сотрудника = орг отдела, куда добавляем (напр. Донецкое), а не своя
        // орг вызывающего. Иначе backend ставил org_id = current_user.org_id (ВСКС).
        org_id: selectedDept.value.org_id ?? null,
      }),
    })
    // 2. Add to department
    await apiFetch(`/departments/${selectedDept.value.id}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: user.id, position: newMemberForm.value.position || null }),
    })
    addMemberDialog.value = false
    newMemberForm.value = { email: '', last_name: '', first_name: '', middle_name: '', password: '', password_confirm: '', phone: '', role: 'employee', position: '', city: '' }
    // Refresh all
    await Promise.all([loadUsers(), loadDeptMembers(selectedDept.value.id), loadDeptTree()])
    showSnack(`Сотрудник ${user.full_name || user.username} создан и добавлен в отдел`)
  } catch (e: any) {
    showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка при создании сотрудника', 'error')
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
  newMemberForm.value = { email: '', last_name: '', first_name: '', middle_name: '', password: '', role: 'employee', position: '', city: '' }
  addMemberMode.value = 'existing'
  addMemberDialog.value = true
}

function onEditMemberInline(payload: { dept: any; member: any; fullEdit?: boolean }) {
  if (payload.fullEdit) {
    // Open full user edit dialog instead of position-only dialog
    openEditUserById(payload.member.user_id)
    return
  }
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
  const a = document.createElement('a'); a.href = url; a.download = 'Шаблон_импорта_отделов.xlsx'; a.click()
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
  await loadDicts()
  try { organizations.value = await apiFetch<any[]>('/organizations/') } catch { organizations.value = [] }
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

/* Mobile: фильтры персонала в столбик (не сжаты в нечитаемые «(»), строки дерева переносятся */
@media (max-width: 599px) {
  .staff-view .dept-toolbar > .v-input,
  .staff-view .dept-toolbar > .v-select,
  .staff-view .dept-toolbar > .v-autocomplete {
    max-width: 100% !important;
    flex: 1 1 100%;
  }
  .staff-view .dept-tree-row {
    flex-wrap: wrap;
    row-gap: 4px;
    padding: 8px 10px;
  }
  /* счётчик «N чел.» (outlined-чип) не сжимать — иначе обрезается до «0 ч» */
  .staff-view .dept-tree-row .v-chip--variant-outlined {
    flex-shrink: 0;
  }
}
</style>

<style scoped>
/* Hierarchy tree styles */
.tree-node { margin-bottom: 16px; }
.tree-label { display: flex; align-items: center; padding: 4px 0; }
.tree-children { margin-left: 24px; border-left: 2px solid var(--crm-border); padding-left: 12px; margin-top: 4px; }
.tree-child { display: flex; align-items: center; padding: 3px 0; gap: 4px; }

/* Unassigned users folder */
.unassigned-folder-header { border: 1px dashed rgba(0,0,0,0.15); background: rgba(0,0,0,0.02); transition: background 0.15s; }
.unassigned-folder-header:hover { background: rgba(0,0,0,0.05); }
.unassigned-user-row { cursor: pointer; transition: background 0.15s; border-radius: 6px; }
.unassigned-user-row:hover { background: rgba(var(--v-theme-primary), 0.06); }

/* Avatar picker styles */
.avatar-pick { cursor: pointer; border-radius: 50%; padding: 2px; border: 2px solid transparent; transition: all 0.2s; }
.avatar-pick:hover { border-color: rgba(var(--v-theme-primary), 0.3); transform: scale(1.1); }
.avatar-pick-active { border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.4); }

/* Staff photo block in edit dialog */
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
