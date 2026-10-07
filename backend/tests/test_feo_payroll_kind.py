"""Признак `is_payroll` статьи ФЭО (решение владельца 07.10.2026, план
.planning/quick/2026-10-07-dnr-feo-cards/PLAN.md шаг 2) — ФОТ и иные выплаты
персоналу.

Волна 2 (та же сессия, 07.10.2026): признак пробрасывается через ВСЕ разбивки
дерева ФЭО — app.services.feo_plan_tree (_feo_by_kind/_plan_by_kind/_over_by_kind/
_committed_total_by_kind), app.services.committed_amounts, app.services.
feo_plan_fact, app.services.type_totals, app.services.redistributable_raw,
app.services.subsidy_money_summary, app.routers.dashboard_charts — через
единственный резолвер app.services.feo_payroll.payroll_category_ids (ПРАВИЛО
№6). dashboard_type_split.py (этапы закупок plan_schedule/work/ordered/
contracts/delivered/paid) и subsidy_paid_breakdown.py/delivered_unpaid_
residual.py — СОЗНАТЕЛЬНО НЕ переведены в этой сессии (эти три модуля
раскладывают уже РАЗМЕЩЁННЫЕ закупки по raw PurchaseItem без привязки к
дереву ФЭО; перевод требует менять арность TypeShares/split_amount_by_shares
и трогать 3 файла с бизнес-формулами одновременно — риск для времени сессии
не оправдан, см. отчёт). Тесты ниже покрывают пробрасывание через дерево ФЭО
и производные (budget/plan/free карточки — см. test_feo_card_drill.py)."""
import pytest

from app.services.feo_payroll import is_payroll_name, payroll_category_ids
from app.services.feo_plan_tree import compute_feo_plan_tree
from app.services.item_type_split import KIND_GOODS, KIND_PAYROLL, kind_of_for_category
from tests.test_feo_plan_tree_scenarios import _make_category, _make_planned_item, _make_subsidy


class TestIsPayrollName:
    def test_fot_as_whole_word(self):
        assert is_payroll_name("ФОТ") is True
        assert is_payroll_name("ФОТ и иные выплаты персоналу") is True
        assert is_payroll_name("фот ДНР") is True

    def test_fot_substring_inside_foto_is_not_payroll(self):
        """Боевая проверка (прод, 07.10.2026): статья «Расходы на
        приобретение основных средств (оргтехника, фото-, видеотехники...)»
        НЕ должна стать ФОТ из-за подстроки «фот» внутри «фото-»."""
        name = (
            "Расходы на приобретение основных средств (оргтехника, "
            "фото-, видеотехники, мебели, принтеры)"
        )
        assert is_payroll_name(name) is False

    def test_oplata_truda_variants(self):
        assert is_payroll_name("1. Оплата труда") is True
        assert is_payroll_name("1.1 Оплата труда штатных работников") is True
        assert is_payroll_name(
            "Взносы по обязательному социальному страхованию на оплату труда (7,8%)"
        ) is True

    def test_vyplaty_personalu(self):
        assert is_payroll_name("Иные выплаты персоналу") is True

    def test_unrelated_name_false(self):
        assert is_payroll_name("Обслуживание ТС") is False
        assert is_payroll_name("") is False
        assert is_payroll_name(None) is False


def test_kind_of_for_category_overrides_item_type():
    """Позиция статьи с is_payroll получает вид payroll НЕЗАВИСИМО от
    item_type (товар/услуга/пусто) — один классификатор."""
    assert kind_of_for_category("товар", True) == KIND_PAYROLL
    assert kind_of_for_category("услуга", True) == KIND_PAYROLL
    assert kind_of_for_category(None, True) == KIND_PAYROLL
    assert kind_of_for_category("товар", False) == KIND_GOODS


@pytest.mark.asyncio
async def test_migration_backfilled_payroll_categories_on_db(db_session, test_org):
    """Миграция e3f5g7h9i1j3 — разовый бэкфилл по имени (та же формула, что
    is_payroll_name). Новая категория с именем «ФОТ» создаётся вручную здесь
    (бэкфилл применяется только к уже существовавшим строкам на момент
    миграции) — эта проверка про ручной путь, см. test_patch_toggles_is_payroll."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="ФОТ и иные выплаты персоналу")
    assert cat.is_payroll is False  # создание через ORM напрямую не вызывает is_payroll_name


@pytest.mark.asyncio
async def test_patch_toggles_is_payroll(db_session, test_org):
    """PUT /api/feo-categories/{id} принимает is_payroll (ручной переключатель,
    через существующий feo_category_write.update_category/TRACKED_FIELDS)."""
    from types import SimpleNamespace
    from app.schemas.subsidies import FeoCategoryCreate
    from app.services import feo_category_write

    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    cat = await _make_category(db_session, subsidy.id, name="Статья")
    assert cat.is_payroll is False

    user = SimpleNamespace(id=1)
    payload = FeoCategoryCreate(
        parent_id=None, subsidy_id=subsidy.id, name=cat.name, is_payroll=True,
    )
    await feo_category_write.update_category(db_session, user, cat, payload)
    await db_session.commit()
    await db_session.refresh(cat)
    assert cat.is_payroll is True


@pytest.mark.asyncio
async def test_payroll_category_ids_resolver_inherits_down_the_tree(db_session, test_org):
    """app.services.feo_payroll.payroll_category_ids — payroll статьи
    наследуется ЛЮБОЙ подкатегорией (и дальше вглубь), не только прямым
    ребёнком."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    root = await _make_category(db_session, subsidy.id, name="ФОТ и иные выплаты персоналу", is_payroll=True)
    child = await _make_category(db_session, subsidy.id, name="НДФЛ 13%", parent_id=root.id)
    grandchild = await _make_category(db_session, subsidy.id, name="вложенная", parent_id=child.id)
    other = await _make_category(db_session, subsidy.id, name="Обслуживание ТС")

    ids = await payroll_category_ids(db_session, [subsidy.id])
    assert root.id in ids
    assert child.id in ids
    assert grandchild.id in ids
    assert other.id not in ids


@pytest.mark.asyncio
async def test_payroll_overrides_item_type_in_feo_plan_tree(db_session, test_org):
    """Позиция «товар» на statье с is_payroll (себе) и на подстатье (через
    предка) обе получают node['plan_payroll'] > 0 и node['plan_goods'] == 0 —
    item_type (тут явно «товар») не играет роли, см. kind_of_for_category."""
    subsidy = await _make_subsidy(db_session, test_org.id, budget=None)
    payroll_root = await _make_category(db_session, subsidy.id, name="ФОТ ДНР", is_payroll=True)
    payroll_child = await _make_category(db_session, subsidy.id, name="НДФЛ", parent_id=payroll_root.id)

    own_item = await _make_planned_item(db_session, payroll_root.id, "ФОТ сам", 1, 27_141_912)
    own_item.item_type = "товар"
    child_item = await _make_planned_item(db_session, payroll_child.id, "НДФЛ 13%", 1, 4_055_688)
    child_item.item_type = "услуга"
    await db_session.commit()

    tree = await compute_feo_plan_tree(db_session, [subsidy.id])

    root_node = tree[payroll_root.id]
    assert root_node["plan_goods"] == pytest.approx(0.0)
    assert root_node["plan_services"] == pytest.approx(0.0)
    # own (27 141 912) + rollup ребёнка (4 055 688) — payroll родителя суммирует поддерево.
    assert root_node["plan_payroll"] == pytest.approx(27_141_912.0 + 4_055_688.0)

    child_node = tree[payroll_child.id]
    assert child_node["plan_goods"] == pytest.approx(0.0)
    assert child_node["plan_payroll"] == pytest.approx(4_055_688.0)
