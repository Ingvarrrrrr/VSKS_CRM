"""Настраиваемые сроки актуальности цены по категориям товара (владелец, 2026-08-29).

Владелец: «Срок актуальности РАЗНЫЙ для разных видов товаров: бытовые — до
2 месяцев, продукты питания — около 2 недель». `scope_kind` определяет, по
какому полю товара матчится правило (category / product_type / item_kind),
'default' — правило-фолбэк ('*'). `org_id IS NULL` — глобальное правило
(видно всем организациям); `org_id` заданный — override конкретной орги.
См. app/services/price_freshness.py::evaluate для порядка применения.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from app.database import Base


class PriceFreshnessRule(Base):
    __tablename__ = "price_freshness_rules"
    __table_args__ = (
        UniqueConstraint("org_id", "scope_kind", "scope_key", name="uq_price_freshness_rule_scope"),
    )

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    scope_kind = Column(String(20), nullable=False)  # 'default' | 'category' | 'product_type' | 'item_kind'
    scope_key = Column(String(200), nullable=False)  # '*' для default, иначе значение поля
    ttl_days = Column(Integer, nullable=False)
