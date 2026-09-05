"""Идемпотентные сиды PermissionTab/PermissionAction/RolePermission,
выполняемые при каждом старте приложения. Перенесено 1:1 из
app/__init__.py.lifespan при разрезании файла на модули (Правило №5).
Каждый блок — отдельная функция с исходным комментарием-заголовком;
run() вызывает их в исходном порядке.
"""
import logging

from app.database import async_session


async def _payment_registry_tab_and_actions():
    # Phase 22: idempotent seed для tab payment_registry + 3 actions
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionTab, PermissionAction, RolePermission
        async with async_session() as db:
            # 1. Tab
            ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'payment_registry'))
            if not ex.scalar_one_or_none():
                db.add(PermissionTab(tab_key='payment_registry', title='Реестр платежей'))
            # 2. Actions
            for action_key, description in [
                ('payment.import', 'Импорт банковских выписок'),
                ('payment.confirm', 'Подтверждение матча платежа'),
                ('payment.unbind', 'Откат подтверждения платежа'),
            ]:
                ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == action_key))
                if not ex.scalar_one_or_none():
                    db.add(PermissionAction(action_key=action_key, description=description))
            await db.commit()
            # 3. Role permissions (granted=True)
            # tab payment_registry — все 5 ролей (superadmin/admin/org_admin/manager/employee)
            # action payment.import — admin, manager, superadmin
            # action payment.confirm — admin, manager, org_admin, superadmin
            # action payment.unbind — admin, superadmin
            ROLE_PERMS = [
                ('superadmin', 'payment_registry'), ('admin', 'payment_registry'),
                ('org_admin', 'payment_registry'), ('manager', 'payment_registry'),
                ('employee', 'payment_registry'),
                ('superadmin', 'payment.import'), ('admin', 'payment.import'), ('manager', 'payment.import'),
                ('superadmin', 'payment.confirm'), ('admin', 'payment.confirm'),
                ('manager', 'payment.confirm'), ('org_admin', 'payment.confirm'),
                ('superadmin', 'payment.unbind'), ('admin', 'payment.unbind'),
            ]
            for role_name, key in ROLE_PERMS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == key,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=key, granted=True))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 22 permission seed skipped (non-fatal): {e}")


async def _phase29_vehicles_tab_and_actions():
    # Phase 29: vehicles tab + 6 actions (idempotent permission seed)
    try:
        from sqlalchemy import select as _sel29
        from app.models.permission import PermissionTab as _PT29, PermissionAction as _PA29, RolePermission as _RP29
        async with async_session() as db:
            # 1. Tab
            ex = await db.execute(_sel29(_PT29).where(_PT29.tab_key == 'vehicles'))
            if not ex.scalar_one_or_none():
                db.add(_PT29(tab_key='vehicles', title='Имущество'))
            await db.commit()
            # 2. Actions
            for _ak29, _desc29 in [
                ('vehicle.edit',           'Редактирование карточки ТС'),
                ('vehicle.delete',         'Удаление ТС'),
                ('vehicle.import',         'Импорт Excel реестра ТС'),
                ('vehicle.odometer.write', 'Ввод пробега'),
                ('vehicle.repair.write',   'Добавление ремонтов'),
                ('vehicle.trip.create',    'Создание путевых листов'),
            ]:
                ex = await db.execute(_sel29(_PA29).where(_PA29.action_key == _ak29))
                if not ex.scalar_one_or_none():
                    db.add(_PA29(action_key=_ak29, description=_desc29))
            await db.commit()
            # 3. Role defaults
            # (key, role_name, granted)
            # viewer role — tab visibility only, no actions
            _ROLE_PERMS_29 = [
                # tab visibility: superadmin/account_owner/admin/org_admin/manager/employee/viewer
                *[('vehicles', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee', 'viewer']],
                # vehicle.edit: admin+ yes; manager yes; employee explicit no
                *[('vehicle.edit', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager']],
                ('vehicle.edit', 'employee', False),
                # vehicle.delete: admin+ only
                *[('vehicle.delete', r, True) for r in ['superadmin', 'account_owner', 'admin']],
                *[('vehicle.delete', r, False) for r in ['org_admin', 'manager', 'employee']],
                # vehicle.import: admin/org_admin yes; manager/employee explicit no
                *[('vehicle.import', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin']],
                *[('vehicle.import', r, False) for r in ['manager', 'employee']],
                # vehicle.odometer.write: all active roles yes
                *[('vehicle.odometer.write', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee']],
                # vehicle.repair.write: admin/manager yes; employee explicit no
                *[('vehicle.repair.write', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager']],
                ('vehicle.repair.write', 'employee', False),
                # vehicle.trip.create: admin/manager yes; employee explicit no
                *[('vehicle.trip.create', r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager']],
                ('vehicle.trip.create', 'employee', False),
            ]
            for _key29, _role29, _granted29 in _ROLE_PERMS_29:
                ex = await db.execute(_sel29(_RP29).where(
                    _RP29.role_name == _role29,
                    _RP29.key == _key29,
                ))
                if not ex.scalar_one_or_none():
                    db.add(_RP29(role_name=_role29, key=_key29, granted=_granted29))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 29 permission seed skipped (non-fatal): {e}")


async def _autoblock_vehicle_fields_manage():
    # Автоблок: право vehicle.fields.manage — управление составом полей карточки ТС
    # (идемпотентный сид, тем же стилем что Phase 29 выше, см. AUTOBLOCK_FIELDS_SPEC.md §5)
    try:
        from sqlalchemy import select as _selab
        from app.models.permission import PermissionAction as _PAab, RolePermission as _RPab
        async with async_session() as db:
            _ak_ab = 'vehicle.fields.manage'
            ex = await db.execute(_selab(_PAab).where(_PAab.action_key == _ak_ab))
            if not ex.scalar_one_or_none():
                db.add(_PAab(action_key=_ak_ab, description='Управление составом полей карточки ТС'))
            await db.commit()

            _ROLE_PERMS_AB = [
                *[(_ak_ab, r, True) for r in ['superadmin', 'account_owner', 'admin', 'org_admin']],
                *[(_ak_ab, r, False) for r in ['manager', 'employee']],
            ]
            for _key_ab, _role_ab, _granted_ab in _ROLE_PERMS_AB:
                ex = await db.execute(_selab(_RPab).where(
                    _RPab.role_name == _role_ab,
                    _RPab.key == _key_ab,
                ))
                if not ex.scalar_one_or_none():
                    db.add(_RPab(role_name=_role_ab, key=_key_ab, granted=_granted_ab))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Автоблок vehicle.fields.manage permission seed skipped (non-fatal): {e}")


async def _documents_view_all_in_org():
    # Phase 28 → Phase 26-Y: idempotent seed для action 'documents.view_all_in_org'
    # (без него руководители без отдела не видят документы своей org → Цыганов кейс).
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'documents.view_all_in_org'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Видеть все документы организации без фильтра по ответственному исполнителю',
                ))
                await db.commit()
            # Role defaults — true для SaaS+admin+org_admin, false для manager/employee
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True),
                ('admin', True), ('org_admin', True),
                ('manager', False), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-Y view_all action seed skipped (non-fatal): {e}")


async def _advance_reports_create_tab():
    # Phase 26-Q: idempotent seed для нового tab advance_reports.create
    # (отделяем «создание авансового отчёта» от «реестра авансовых отчётов»)
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionTab, RolePermission
        async with async_session() as db:
            ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'advance_reports.create'))
            if not ex.scalar_one_or_none():
                db.add(PermissionTab(tab_key='advance_reports.create', title='Авансовый отчёт (создание)'))
                await db.commit()
            # Role permissions: разрешено всем ролям, кому был разрешён advance_reports
            ALL_ADV_ROLES = ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager', 'employee']
            for role_name in ALL_ADV_ROLES:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == 'advance_reports.create',
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key='advance_reports.create', granted=True))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 26-Q permission seed skipped (non-fatal): {e}")


async def _purchase_status_change_action():
    # Phase 27.4-10: idempotent seed для action 'purchase.status_change'
    # Дефолт: admin/manager/account_owner/superadmin=TRUE; employee=FALSE.
    # Управляет возможностью двигать статусы закупок в Канбане и через /transition.
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'purchase.status_change'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Изменение статуса закупки',
                ))
                await db.commit()
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True),
                ('admin', True), ('org_admin', True),
                ('manager', True), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 27.4-10 purchase.status_change seed skipped (non-fatal): {e}")


async def _feo_budget_visibility_actions():
    # ФЭО budget visibility: два action-ключа.
    # feo_budget.view_leaf — видеть остаток по листовой (последней) ФЭО-категории (по умолчанию все роли).
    # feo_budget.view_all_levels — видеть остатки и по вышестоящим уровням ФЭО (по умолчанию менеджер+).
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            FEO_BUDGET_ACTIONS = [
                ('feo_budget.view_leaf',
                 'Видеть остаток бюджета по листовой (последней) категории ФЭО',
                 [('superadmin', True), ('account_owner', True), ('admin', True),
                  ('org_admin', True), ('manager', True), ('employee', True)]),
                ('feo_budget.view_all_levels',
                 'Видеть остатки бюджета по всем уровням ФЭО (вышестоящие категории)',
                 [('superadmin', True), ('account_owner', True), ('admin', True),
                  ('org_admin', True), ('manager', True), ('employee', False)]),
            ]
            for action_key, description, role_defaults in FEO_BUDGET_ACTIONS:
                ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == action_key))
                if not ex.scalar_one_or_none():
                    db.add(PermissionAction(action_key=action_key, description=description))
                    await db.commit()
                for role_name, granted in role_defaults:
                    ex = await db.execute(_sel(RolePermission).where(
                        RolePermission.role_name == role_name,
                        RolePermission.key == action_key,
                    ))
                    if not ex.scalar_one_or_none():
                        db.add(RolePermission(role_name=role_name, key=action_key, granted=granted))
                await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"feo_budget visibility action seed skipped (non-fatal): {e}")


async def _feo_budget_view_tree_amounts_action():
    # Задача владельца (2026-08-06): «остаток средств напротив каждой категории ФЭО
    # при выборе». Отдельный action-ключ (НЕ admin.* — иначе жёстко срезается у
    # employee даже персональным грантом, см. app.auth.permissions._get_effective_simple)
    # гейтит суммы (budget/free) на КАЖДОМ узле дерева выбора категории ФЭО
    # (GET /feo-categories/plan-tree, см. роутер feo_categories.get_feo_plan_tree).
    # Отличается от feo_budget.view_leaf/view_all_levels выше (те гейтят /leaves и
    # /budget-residuals — старые экраны); этот — новый проп nodeAmounts у
    # FeoTreeSelect.vue. Дефолт: все роли кроме employee.
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'feo_budget.view_tree_amounts'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Видеть суммы по ФЭО (финансирование и свободный остаток) в дереве выбора категорий',
                ))
                await db.commit()
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True),
                ('admin', True), ('org_admin', True),
                ('manager', True), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"feo_budget.view_tree_amounts seed skipped (non-fatal): {e}")


async def _wish_edit_feo_action():
    # Владелец (2026-08-19): «менять позиции может только тот, кто имеет право» —
    # правку категории ФЭО/плановой позиции построчно (коммит 80dfe9c) мог делать
    # любой согласующий из цепочки, включая случайного участника (например,
    # юриста). Отдельное action-право wish.edit_feo сужает это до менеджеров+.
    # Дефолт: superadmin/admin/org_admin/manager=TRUE; employee=FALSE (сознательно,
    # это и есть защита).
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'wish.edit_feo'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Перераспределение позиций заявки по категориям ФЭО и плановым позициям',
                ))
                await db.commit()
            ROLE_DEFAULTS = [
                ('superadmin', True), ('admin', True),
                ('org_admin', True), ('manager', True),
                ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"wish.edit_feo action seed skipped (non-fatal): {e}")


async def _feo_category_edit_action():
    # Этап B1 (2026-09-01): отдельное action-право feo_category.edit на редактирование
    # справочника категорий ФЭО (создание/правка/удаление/перенос/импорт), сегодня это
    # управляется исключительно вкладкой feo_categories. Дефолты зеркалят нынешнюю
    # выдачу таба: superadmin/account_owner/admin/org_admin=TRUE; manager/employee=FALSE.
    # Гейты на эндпоинтах роутера feo_categories ставит следующий шаг — здесь только сид
    # ключа + бэкфилл персональных выдач (см. ниже), чтобы никто не потерял доступ.
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission, UserOrgPermissionOverride
        async with async_session() as db:
            ACTION_KEY = 'feo_category.edit'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Редактирование справочника категорий ФЭО (создание, правка, удаление, перенос, импорт)',
                ))
                await db.commit()
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True), ('admin', True),
                ('org_admin', True), ('manager', False), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()

            # Бэкфилл персональных выдач: у кого была персональная галочка на таб
            # feo_categories (granted=True), тот не должен потерять доступ, когда
            # следующий шаг поставит гейты по feo_category.edit на эндпоинтах.
            src_rows = (await db.execute(_sel(UserOrgPermissionOverride).where(
                UserOrgPermissionOverride.key == 'feo_categories',
                UserOrgPermissionOverride.granted == True,
            ))).scalars().all()
            for src in src_rows:
                ex = await db.execute(_sel(UserOrgPermissionOverride).where(
                    UserOrgPermissionOverride.user_org_access_id == src.user_org_access_id,
                    UserOrgPermissionOverride.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(UserOrgPermissionOverride(
                        user_org_access_id=src.user_org_access_id,
                        key=ACTION_KEY,
                        granted=True,
                    ))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"feo_category.edit action seed skipped (non-fatal): {e}")


async def _plan_excess_decide_action():
    # Владелец (2026-08-29): «превышение не может согласовывать любой из цепочки
    # согласования… только определённые люди — например, только владельцы или
    # только финансисты. У начальника отдела таких прав быть не может». На вопрос
    # «кому по умолчанию давать право» — никому, выдаётся галочкой поимённо. См.
    # app.routers.plan_excess (гейт /decide и _authorized_plan_excess_approvers) —
    # ОБА используют app.auth.permissions.has_org_key с этим ключом, вторая логика
    # не пишется. Дефолт: superadmin/account_owner=TRUE (SaaS-обход, как и везде);
    # admin/org_admin/manager/employee=FALSE — организационные роли НЕ получают
    # это право автоматически, только персональным или субсидийным грантом.
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionAction, RolePermission
        async with async_session() as db:
            ACTION_KEY = 'plan_excess.decide'
            ex = await db.execute(_sel(PermissionAction).where(PermissionAction.action_key == ACTION_KEY))
            if not ex.scalar_one_or_none():
                db.add(PermissionAction(
                    action_key=ACTION_KEY,
                    description='Согласование превышения плана ФЭО (только уполномоченные — финансисты, владельцы)',
                ))
                await db.commit()
            ROLE_DEFAULTS = [
                ('superadmin', True), ('account_owner', True),
                ('admin', False), ('org_admin', False),
                ('manager', False), ('employee', False),
            ]
            for role_name, granted in ROLE_DEFAULTS:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == ACTION_KEY,
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key=ACTION_KEY, granted=granted))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"plan_excess.decide action seed skipped (non-fatal): {e}")


async def _staff_directory_tab():
    # Phase 18: idempotent seed для tab 'staff_directory' (all 5 roles)
    try:
        from sqlalchemy import select as _sel
        from app.models.permission import PermissionTab, RolePermission
        async with async_session() as db:
            ex = await db.execute(_sel(PermissionTab).where(PermissionTab.tab_key == 'staff_directory'))
            if not ex.scalar_one_or_none():
                db.add(PermissionTab(tab_key='staff_directory', title='Справочник сотрудников'))
                await db.commit()
            ALL_SD_ROLES = ['superadmin', 'admin', 'org_admin', 'manager', 'employee']
            for role_name in ALL_SD_ROLES:
                ex = await db.execute(_sel(RolePermission).where(
                    RolePermission.role_name == role_name,
                    RolePermission.key == 'staff_directory',
                ))
                if not ex.scalar_one_or_none():
                    db.add(RolePermission(role_name=role_name, key='staff_directory', granted=True))
            await db.commit()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Phase 18 staff_directory tab seed skipped (non-fatal): {e}")


async def run():
    """Вызывает все idempotent сиды прав в исходном порядке (см. app/__init__.py.lifespan до разрезания)."""
    await _payment_registry_tab_and_actions()
    await _phase29_vehicles_tab_and_actions()
    await _autoblock_vehicle_fields_manage()
    await _documents_view_all_in_org()
    await _advance_reports_create_tab()
    await _purchase_status_change_action()
    await _feo_budget_visibility_actions()
    await _feo_budget_view_tree_amounts_action()
    await _wish_edit_feo_action()
    await _feo_category_edit_action()
    await _plan_excess_decide_action()
    await _staff_directory_tab()
