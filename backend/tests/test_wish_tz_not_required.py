"""«Без ТЗ (мелкие закупки)» — согласующий заявки может освободить закупку от
гейта ТЗ так же, как это исторически устроено для purchase_method='advance'
(владелец, 30.09; заявка №92 «Расходные материалы для постройки и проведения
слёта»).

Единственный гейт, который на это смотрит — app.services.documents.contexts.
_require_tz_duplicates_resolved_for_doc, через единый хелпер
app.services.tz_items.tz_required (ПРАВИЛО №6 — не вторая копия
`purchase_method == 'advance'`). Эти тесты покрывают:
  1. tz_required() как чистую функцию (обе ветки освобождения + обычная закупка).
  2. POST /api/wishes/{id}/approve?tz_not_required=true — флаг сохраняется на
     заявке (Wish.tz_not_required/tz_waived_by_user_id) и переезжает на
     созданную закупку (wish_distribution.py::_distribute_wish_to_purchases).
  3. Без флага — обычная заявка по-прежнему НЕ освобождена (контроль).
  4. Закупка с tz_not_required=True проходит гейт генерации документа, как
     авансовая (mirrors test_purchase_tz.py::
     test_generate_document_advance_skips_duplicates_gate).

Паттерн фикстур (test_org/test_admin_user/admin_headers, Subsidy с
require_planned_dates=False) — по образцу test_wish_approve_distribution.py.
"""
import os
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.wish import Wish
from app.models.wish_item import WishItem
from app.models.purchase import Purchase
from app.models.purchase_item import PurchaseItem
from app.models.subsidy import Subsidy
from app.models.feo_category import FeoCategory
from app.models.permission import RolePermission
from app.services.tz_items import tz_required


# ── 1. tz_required() — единый хелпер, чистая функция ────────────────────────

def test_tz_required_true_for_ordinary_purchase():
    p = SimpleNamespace(purchase_method="single", tz_not_required=False)
    assert tz_required(p) is True


def test_tz_required_false_for_advance():
    p = SimpleNamespace(purchase_method="advance", tz_not_required=False)
    assert tz_required(p) is False


def test_tz_required_false_when_waived_by_approver():
    p = SimpleNamespace(purchase_method="single", tz_not_required=True)
    assert tz_required(p) is False


def test_tz_required_missing_attrs_defaults_to_required():
    # Duck-typing safety: объект без атрибутов вовсе (getattr default) —
    # ТЗ считается нужным, гейт не отключается молча.
    assert tz_required(SimpleNamespace()) is True


# ── 2-3. Согласование заявки с галочкой «Без ТЗ» ────────────────────────────

async def _grant_tz_waive(db_session, role_name: str) -> None:
    """Выдаёт роли право purchase.tz_waive — upsert, а не голый INSERT
    (make_role_permission фикстуры conftest.py), т.к. тесты этого файла
    делят один и тот же dev-Postgres БЕЗ отката между запусками: после
    `alembic upgrade` миграции c9f1h3j5l7n9 (или повторного прогона сьюта)
    строка role_permissions(role_name='org_admin', key='purchase.tz_waive')
    уже может существовать (granted=False по умолчанию) — второй INSERT той
    же пары бьётся об UniqueConstraint('role_name','key')."""
    existing = (await db_session.execute(
        select(RolePermission).where(
            RolePermission.role_name == role_name,
            RolePermission.key == 'purchase.tz_waive',
        )
    )).scalar_one_or_none()
    if existing:
        existing.granted = True
    else:
        db_session.add(RolePermission(role_name=role_name, key='purchase.tz_waive', granted=True))
    await db_session.commit()


async def _seed_submitted_wish(db_session, test_org, test_user):
    subsidy = Subsidy(name=f"TestSubsidy-{id(db_session)}", year=2026, budget=0, require_planned_dates=False)
    db_session.add(subsidy)
    await db_session.flush()
    feo_cat = FeoCategory(subsidy_id=subsidy.id, level=1, name="Прочее")
    db_session.add(feo_cat)
    await db_session.flush()

    w = Wish(
        org_id=test_org.id,
        title="Расходные материалы для постройки и проведения слёта",
        status="submitted",
        created_by=test_user.id,
        subsidy_id=subsidy.id,
        feo_category_id=feo_cat.id,
    )
    db_session.add(w)
    await db_session.flush()
    db_session.add(WishItem(
        wish_id=w.id, item_name="Скотч упаковочный",
        quantity=Decimal("10"), unit_price=Decimal("100"), total_price=Decimal("1000"),
    ))
    await db_session.commit()
    await db_session.refresh(w)
    return w


@pytest.mark.asyncio
async def test_approve_with_tz_not_required_requires_permission_403(
    client, db_session, admin_headers, test_org, test_user,
):
    """Владелец (30.09, уточнение): «ОТДЕЛЬНОЕ разрешение в ролях — кому можно
    отменять необходимость ТЗ, а кому нет» — org_admin проходит общую проверку
    «может согласовать заявку» (MANAGER_ROLES), но БЕЗ гранта purchase.tz_waive
    не может поставить флаг: 403, заявка не согласована, закупка не создана."""
    w = await _seed_submitted_wish(db_session, test_org, test_user)

    resp = await client.post(
        f"/api/wishes/{w.id}/approve?tz_not_required=true", headers=admin_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "purchase.tz_waive" in resp.json().get("message", "")

    await db_session.refresh(w)
    assert w.status == "submitted", "Отказ по праву должен целиком отменять действие, а не половинчато"
    assert w.tz_not_required is False

    purchase = (await db_session.execute(
        select(Purchase).where(Purchase.wish_id == w.id)
    )).scalars().first()
    assert purchase is None


@pytest.mark.asyncio
async def test_approve_with_tz_not_required_propagates_to_purchase(
    client, db_session, admin_headers, test_org, test_user, test_admin_user,
):
    # org_admin по умолчанию НЕ имеет purchase.tz_waive (см. permission_seeds.py::
    # _purchase_tz_waive_action) — выдаём явно, как сделал бы владелец в реальной
    # системе (Admin → Roles).
    await _grant_tz_waive(db_session, 'org_admin')

    w = await _seed_submitted_wish(db_session, test_org, test_user)

    resp = await client.post(
        f"/api/wishes/{w.id}/approve?tz_not_required=true", headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "converted"

    await db_session.refresh(w)
    assert w.tz_not_required is True
    assert w.tz_waived_by_user_id == test_admin_user.id

    purchase = (await db_session.execute(
        select(Purchase).where(Purchase.wish_id == w.id)
    )).scalars().one()
    assert purchase.tz_not_required is True, "Флаг заявки обязан переехать на созданную закупку"
    assert purchase.tz_waived_by_user_id == test_admin_user.id
    # Обычная (не авансовая) закупка — освобождение именно через флаг, не через
    # purchase_method.
    assert purchase.purchase_method != "advance"
    assert tz_required(purchase) is False


@pytest.mark.asyncio
async def test_approve_without_flag_leaves_purchase_tz_required(
    client, db_session, admin_headers, test_org, test_user,
):
    """Контроль: без галочки согласование НЕ освобождает закупку от ТЗ."""
    w = await _seed_submitted_wish(db_session, test_org, test_user)

    resp = await client.post(f"/api/wishes/{w.id}/approve", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    await db_session.refresh(w)
    assert w.tz_not_required is False
    assert w.tz_waived_by_user_id is None

    purchase = (await db_session.execute(
        select(Purchase).where(Purchase.wish_id == w.id)
    )).scalars().one()
    assert purchase.tz_not_required is False
    assert tz_required(purchase) is True


# ── 4. Закупка с tz_not_required=True проходит ТЗ-гейт документа ───────────

def _template_exists() -> bool:
    return os.path.exists("/app/templates/contract_tz.docx")


_SKIP_NO_TEMPLATE = pytest.mark.skipif(
    not _template_exists(),
    reason="contract_tz.docx not available in test environment — template-dependent test skipped",
)


async def _make_purchase_with_duplicates(db_session, **purchase_kwargs) -> Purchase:
    p = Purchase(status="planned", item_type="goods", item_name="Test purchase TZ dup", **purchase_kwargs)
    db_session.add(p)
    await db_session.flush()
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="Огнетушитель ОП-5", unit="шт",
        quantity=Decimal("2"), unit_price=Decimal("1000"), total_price=Decimal("2000"),
    ))
    db_session.add(PurchaseItem(
        purchase_id=p.id, item_name="огнетушитель оп-5", unit="шт",
        quantity=Decimal("3"), unit_price=Decimal("1000"), total_price=Decimal("3000"),
    ))
    await db_session.commit()
    await db_session.refresh(p)
    return p


@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_generate_document_tz_not_required_skips_duplicates_gate(client, db_session, auth_headers):
    """Как у авансовых (test_purchase_tz.py::
    test_generate_document_advance_skips_duplicates_gate), но через флаг
    tz_not_required, выставленный согласующим на обычной закупке."""
    p = await _make_purchase_with_duplicates(db_session, tz_not_required=True)

    resp = await client.get(f"/api/purchases/{p.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 200, resp.text


@_SKIP_NO_TEMPLATE
@pytest.mark.asyncio
async def test_generate_document_still_blocked_without_flag(client, db_session, auth_headers):
    """Контроль: без tz_not_required и без purchase_method='advance' гейт
    по-прежнему требует явного решения по дублям строк ТЗ."""
    p = await _make_purchase_with_duplicates(db_session)

    resp = await client.get(f"/api/purchases/{p.id}/documents/tech_spec", headers=auth_headers)
    assert resp.status_code == 409, resp.text


# ── 5. Переход «Заключён договор» не блокируется отсутствием ТЗ ────────────
# Владелец (30.09, заявка №92, рамочный договор): «после того как согласующий
# разрешит или запретит — можно двигать дальше». purchase_transition_core.py
# автокопирует PurchaseItem → ContractItem для tz_not_required=True так же,
# как уже делает для purchase_method='advance' (но без гейта чеков/receipts —
# это не авансовый), см. test_purchase_transitions.py::
# test_contracted_requires_contract_items_422 для контроля «требуется без флага».

@pytest.mark.asyncio
async def test_contracted_transition_autocopies_items_when_tz_waived(
    client, db_session, make_purchase_with_items, admin_headers,
):
    from datetime import date
    from app.models.contract_item import ContractItem
    from sqlalchemy import func

    p = await make_purchase_with_items(items_count=2)
    p.status = "confirmed"
    p.contract_number = "TEST-TZ-WAIVED-001"
    p.contract_date = date(2026, 5, 14)
    p.tz_not_required = True
    await db_session.commit()

    resp = await client.post(
        f"/api/purchases/{p.id}/transition?status=contracted", headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    await db_session.refresh(p)
    assert p.status == "contracted"

    ci_count = await db_session.scalar(
        select(func.count()).select_from(ContractItem).where(ContractItem.purchase_id == p.id)
    )
    assert ci_count == 2, "ContractItem должны были автоскопироваться из PurchaseItem без ручного 'Скопировать из заявки'"


# ── 6. Договор печатается БЕЗ приложения «ТЕХНИЧЕСКОЕ ЗАДАНИЕ», когда его
# отменил согласующий ────────────────────────────────────────────────────────
# Прямой тест кода, изменённого в services/documents/generate.py: тот же
# append_tz_table_for_contract (реальная функция python-docx, не мок), что и
# в проде — просто без тяжёлой обвязки generate_document (subsidy/contractor/
# подписант и т.п., не относящихся к этой правке). tz_required() — тот же
# хелпер, что гейтит вызов в generate.py.

def _contract_items_list():
    return [{
        "num": 1, "name": "Бумага А4", "description": None,
        "quantity": "5", "unit": "уп.", "unit_price": "300", "total_price": "1500",
        "_product": None,
    }]


def _render_base_contract_docx() -> bytes:
    from docx import Document as _DocxDoc
    doc = _DocxDoc()
    doc.add_paragraph("Договор № Т-1 — основной текст.")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_contract_doc_has_no_tz_appendix_when_waived():
    from app.services.documents.stages_contract_tz import append_tz_table_for_contract

    p = SimpleNamespace(purchase_method="single", tz_not_required=True, contract_number="Т-1", contract_date=None)
    buf = BytesIO(_render_base_contract_docx())
    if tz_required(p):
        buf = append_tz_table_for_contract(buf, "contract", _contract_items_list(), p)

    from docx import Document as _DocxDoc
    out_doc = _DocxDoc(buf)
    full_text = "\n".join(par.text for par in out_doc.paragraphs)
    assert "ТЕХНИЧЕСКОЕ ЗАДАНИЕ" not in full_text
    assert len(out_doc.tables) == 0, "Без ТЗ приложение-таблица не добавляется вовсе"


def test_contract_doc_has_tz_appendix_when_required():
    """Контроль: обычная (не waived) закупка по-прежнему печатает приложение ТЗ."""
    from app.services.documents.stages_contract_tz import append_tz_table_for_contract

    p = SimpleNamespace(purchase_method="single", tz_not_required=False, contract_number="Т-1", contract_date=None)
    buf = BytesIO(_render_base_contract_docx())
    if tz_required(p):
        buf = append_tz_table_for_contract(buf, "contract", _contract_items_list(), p)

    from docx import Document as _DocxDoc
    out_doc = _DocxDoc(buf)
    full_text = "\n".join(par.text for par in out_doc.paragraphs)
    assert "ТЕХНИЧЕСКОЕ ЗАДАНИЕ" in full_text
    assert len(out_doc.tables) == 1
